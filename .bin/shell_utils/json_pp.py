#!/usr/bin/env python3
"""Pretty-print JSON from stdin, a file, or a string argument.

Usage:
  cat data.json | json_pp
  json_pp file.json
  json_pp '{"key": "value"}'
"""
import json
import sys


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # Try as file first, then as raw JSON string
        try:
            with open(arg) as f:
                data = json.load(f)
        except (FileNotFoundError, IsADirectoryError):
            data = json.loads(arg)
    else:
        data = json.load(sys.stdin)

    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (json.JSONDecodeError, BrokenPipeError) as e:
        if isinstance(e, json.JSONDecodeError):
            print(f"Invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
