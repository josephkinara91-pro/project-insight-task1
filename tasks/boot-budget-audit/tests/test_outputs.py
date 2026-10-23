"""All grading assertions are on the required program's observable behavior."""
import json
from pathlib import Path
import pytest
from checker import isolated_run, validate_answer, actual_synchronizes
from models import Reachability
from generate import encode_word, build

ROOT = Path(__file__).resolve().parent
RECORDS = json.loads((ROOT / "private/manifest.json").read_text())


def test_program_exists():
    """The declared executable Python deliverable must exist."""
    assert Path("/app/boot_sequence.py").is_file()


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["name"])
def test_private_key(record):
    """Independent finite-state reachability must reproduce each exact minimum."""
    length, word, _ = Reachability(record["blocks"]).minimum(record["budget"])
    assert length == record["minimum"]
    if length is not None:
        netlist = json.loads((ROOT / "private" / (record["name"]+".json")).read_text())
        assert actual_synchronizes(netlist, encode_word(word, record["mapping"]["frame"]))


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["name"])
def test_bounded_initialization(record):
    """Unseen circuits require an exact minimum and a universally valid word."""
    netlist = json.loads((ROOT / "private" / (record["name"]+".json")).read_text())
    answer = isolated_run(netlist, record["budget"])
    validate_answer(answer, record, netlist)


@pytest.mark.parametrize("index", [3, 7, 8, 9, 13, 14])
def test_equivalent_input_frame(index):
    """Names, bit packing, input inversions and register storage polarity are immaterial."""
    original = RECORDS[index]
    netlist, mapping = build(original["blocks"], original["seed"]+94117)
    record = dict(original, mapping=mapping)
    answer = isolated_run(netlist, record["budget"])
    validate_answer(answer, record, netlist)
