#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-src}"
if [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN=python3
fi
"${PYTHON_BIN}" -m turbo.cli validate
"${PYTHON_BIN}" -m unittest discover -s tests -v
"${PYTHON_BIN}" -m turbo.cli run
"${PYTHON_BIN}" -m turbo.cli context

