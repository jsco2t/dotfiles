"""Detached local command worker; receipt survives loss of the calling agent/helper."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def stamp():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    os.replace(temporary, path)


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 0.5
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.025)
    # Kill surviving grandchildren even if their direct parent exited on SIGTERM.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def main(directory):
    spec = json.loads((directory / "spec.json").read_text())
    status, code = "failed", 127
    with Path(spec["log"]).open("wb") as output:
        process = None
        try:
            if (directory / "cancel").exists():
                status, code = "interrupted", 130
            else:
                process = subprocess.Popen(spec["argv"], cwd=spec["cwd"], stdin=subprocess.DEVNULL,
                                           stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                atomic(directory / "process.json", dict(pid=process.pid, started=stamp()))
                deadline = time.monotonic() + spec["timeout_seconds"]
                while process.poll() is None:
                    if (directory / "cancel").exists():
                        stop(process)
                        status, code = "interrupted", 130
                        break
                    if time.monotonic() >= deadline:
                        stop(process)
                        status, code = "failed", 124
                        output.write(b"Check timeout; process group stopped.\n")
                        break
                    time.sleep(0.025)
                else:
                    code = process.returncode
                    status = "completed" if code == 0 else "failed"
        except BaseException as exc:
            if process is not None and process.poll() is None:
                stop(process)
            output.write((str(exc) + "\n").encode())
        output.flush()
        os.fsync(output.fileno())
    atomic(directory / "receipt.json", dict(status=status, exit_code=code, ended=stamp()))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
