#!/bin/bash
# Private pytest and reward generation stay root; checker.py drops privileges
# only for candidate processes and kills their entire process group afterwards.
set -uo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
cd /tests
python3 -m pytest -p pytest_json_ctrf --json-ctrf=/logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?
if [ "$rc" -eq 0 ]; then
    echo -n 1 > /logs/verifier/reward.txt
else
    echo -n 0 > /logs/verifier/reward.txt
fi
exit 0
