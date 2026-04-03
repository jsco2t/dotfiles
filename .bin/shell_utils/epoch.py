#!/usr/bin/env python3
"""Convert between epoch timestamps and human-readable dates.

Usage:
  epoch                    # print current epoch
  epoch 1680000000         # epoch -> human-readable (local + UTC)
  epoch 1680000000000      # handles millisecond epochs too
  epoch 2024-01-15         # date string -> epoch
  epoch 2024-01-15T10:30   # datetime string -> epoch
"""
import sys
import time
from datetime import datetime, timezone


def epoch_to_human(ts):
    # Handle millisecond epochs
    if ts > 1e12:
        ts = ts / 1000
    local = datetime.fromtimestamp(ts)
    utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    print(f"Epoch:  {int(ts)}")
    print(f"Local:  {local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"UTC:    {utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")


def human_to_epoch(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            ts = int(dt.timestamp())
            print(ts)
            return
        except ValueError:
            continue
    print(f"Unrecognized date format: {s}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(int(time.time()))
        return

    arg = sys.argv[1]
    try:
        epoch_to_human(float(arg))
    except ValueError:
        human_to_epoch(arg)


if __name__ == "__main__":
    main()
