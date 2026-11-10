"""Immutable compressed checkpoint objects; small JSON state retains durable references."""
import json
import sqlite3
import zlib

from snapshot import digest


def pack(meta, state):
    with sqlite3.connect(meta / "snapshots.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, data BLOB NOT NULL)")

        def visit(value, key=None):
            if key in ("baseline", "checkpoint", "before") and isinstance(value, dict):
                identity = digest(value)
                if not db.execute("SELECT 1 FROM snapshots WHERE id=?", (identity,)).fetchone():
                    db.execute("INSERT INTO snapshots VALUES (?,?)", (identity, zlib.compress(json.dumps(value).encode())))
                return {"$snapshot": identity}
            if isinstance(value, dict):
                return {k: visit(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [visit(v) for v in value]
            return value

        return visit(state)


def unpack(meta, state):
    cache = {}
    db = None
    try:
        def visit(value):
            nonlocal db
            if isinstance(value, dict) and set(value) == {"$snapshot"}:
                identity = value["$snapshot"]
                if identity not in cache:
                    if db is None:
                        db = sqlite3.connect((meta / "snapshots.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
                    row = db.execute("SELECT data FROM snapshots WHERE id=?", (identity,)).fetchone()
                    if row is None:
                        raise ValueError("missing checkpoint object: " + identity)
                    data = json.loads(zlib.decompress(row[0]))
                    if digest(data) != identity:
                        raise ValueError("corrupt checkpoint object: " + identity)
                    cache[identity] = data
                # Callers treat snapshot maps as immutable values.
                return cache[identity]
            if isinstance(value, dict):
                return {k: visit(v) for k, v in value.items()}
            if isinstance(value, list):
                return [visit(v) for v in value]
            return value
        return visit(state)
    except (sqlite3.Error, zlib.error) as exc:
        raise ValueError("cannot read checkpoint store; restore the matching .tp/snapshots.sqlite3: " + str(exc)) from exc
    finally:
        if db is not None:
            db.close()
