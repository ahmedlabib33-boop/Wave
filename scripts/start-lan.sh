#!/usr/bin/env bash
# Bind the existing self-hosted service to the laptop LAN interface for a phone on the same trusted network.
set -euo pipefail
cd "$(dirname "$0")"
NILE_HOST=0.0.0.0 exec ./start.sh
