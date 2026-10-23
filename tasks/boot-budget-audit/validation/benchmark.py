"""Local reference/model cross-check; does not claim Harbor or hosted scores."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "tests"))
from models import Reachability
from generate import decode_word, build
from checker import validate_answer


def main():
    originals = json.loads((TASK / "tests/private/manifest.json").read_text())
    records = [(r, json.loads((TASK / "tests/private" / (r["name"]+".json")).read_text())) for r in originals]
    for i in [3, 7, 8, 9, 13, 14]:
        r = originals[i]
        netlist, mapping = build(r["blocks"], r["seed"]+94117)
        records.append((dict(r, name=r["name"]+"-variant", mapping=mapping), netlist))
    env = dict(os.environ, PYTHONPATH=str(TASK / "environment"))
    timings = []
    with tempfile.TemporaryDirectory() as directory:
        for record, netlist in records:
            out = Path(directory) / "answer.json"
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(netlist))
            start = time.monotonic()
            process = subprocess.run([sys.executable, str(TASK / "solution/reference.py"),
                                      str(source),
                                      str(record["budget"]), str(out)],
                                     env=env, capture_output=True, text=True, timeout=180)
            elapsed = time.monotonic()-start
            if process.returncode:
                raise RuntimeError(record["name"] + ": " + process.stderr)
            answer = json.loads(out.read_text())
            assert answer["length"] == record["minimum"], (record["name"], answer, record["minimum"])
            validate_answer(answer, record, netlist)
            timings.append(dict(case=record["name"], length=answer["length"], seconds=round(elapsed, 3)))
            print(json.dumps(timings[-1]), flush=True)
    (TASK / "validation/reference_timings.json").write_text(json.dumps(timings, indent=2) + "\n")


if __name__ == "__main__": main()
