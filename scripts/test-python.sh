#!/usr/bin/env bash
set -euo pipefail
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 -m unittest discover -s research -p 'test_*.py' -v
python3 -m unittest discover -s journal -p 'test_*.py' -v
