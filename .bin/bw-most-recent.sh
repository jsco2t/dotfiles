#!/bin/bash

if [[ "$BW_SESSION" == "" ]]; then
  echo "ERROR: 'BW_SESSION' is not defined. Please run 'bw login' and export the session key from the login" >&2
  exit 1
fi
set -euo pipefail  # Exit on error, undefined vars, pipe failures

bw list items |\
jq -r 'sort_by( -( .revisionDate | sub("\\.[0-9]+Z$"; "Z") |
       strptime("%Y-%m-%dT%H:%M:%SZ") | mktime )) |
       .[] | ( .name + " [" + .revisionDate + "]")' |\
head -n10
