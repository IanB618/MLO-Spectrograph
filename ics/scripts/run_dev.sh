#!/usr/bin/env bash
set -euo pipefail
flask --app src.web:create_app run --host 0.0.0.0 --port 5000 --debug
