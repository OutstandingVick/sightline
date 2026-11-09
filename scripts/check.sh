#!/bin/sh
# Every offline check for the plugin: Python tests, lint, Desktop half tests, Hermes doctor/validate.
set -e
cd "$(dirname "$0")/.."
python -m pytest -q
ruff check .
node --check desktop/plugin.js
node --test tests/js/*.test.mjs
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
