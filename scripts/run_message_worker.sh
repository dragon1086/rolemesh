#!/bin/bash
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=src python3 -m rolemesh.workers.message_worker "$@"
