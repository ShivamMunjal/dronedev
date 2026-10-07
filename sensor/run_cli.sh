#!/bin/bash
set -e
CLI="/Users/shivammunjal/Claude Code/DroneProject/sensor/external/fp-sns-datalog2/Utilities/cli_example/bin_macos/arm64/cli_example"
# ensure rpath fallback
export DYLD_LIBRARY_PATH="$(dirname "$CLI"):${DYLD_LIBRARY_PATH:-}"
exec "$CLI" "$@"
