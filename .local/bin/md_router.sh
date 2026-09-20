#!/bin/sh

set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)

if [ -x "$script_dir/oom-edit" ]; then
	exec "$script_dir/oom-edit" -- "$@"
fi

exec hx -- "$@"
