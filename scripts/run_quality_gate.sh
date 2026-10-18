#!/bin/sh
# Balanced Quality Gate pipeline (Lab 5). Runs inside the pinned fleet-metrics image:
#   docker run --rm --cpus=2 --memory=2g -v "$PWD:/work" fleet-metrics:1 sh scripts/run_quality_gate.sh
set -e
rm -rf mutants coverage.json
PYTHONPATH=src python -m pytest tests/unit -q -p no:cacheprovider --cov --cov-report=json
mutmut run --max-children 2 > /dev/null 2>&1 || true
mutmut export-cicd-stats > /dev/null 2>&1
python scripts/quality_gate.py
