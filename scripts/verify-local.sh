#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-src}"
python3 -m turbo.cli validate
python3 -m unittest discover -s tests -v
python3 -m turbo.cli run
python3 -m turbo.cli context --limit 10

