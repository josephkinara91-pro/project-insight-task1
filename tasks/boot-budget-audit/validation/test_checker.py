"""Negative controls and certificate soundness, independent of hosted trials."""
import copy
import json
from pathlib import Path
import sys
import pytest

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "tests"))
from models import Reachability, actual_step, quotient_constants, quotient_step, states, uses_quotient, representative, width
from generate import build, encode_word
from checker import actual_synchronizes, validate_answer
MANIFEST = json.loads((TASK / "tests/private/manifest.json").read_text())


def case(index):
    record = MANIFEST[index]
    netlist = json.loads((TASK / "tests/private" / (record["name"]+".json")).read_text())
    answer = dict(length=record["minimum"], sequence=encode_word(record["witness"], record["mapping"]["frame"]))
    return record, netlist, answer


def test_false_null():
    r, n, a = case(1)
    with pytest.raises(AssertionError): validate_answer(dict(length=None, sequence=[]), r, n)


def test_nonminimal_but_valid():
    r, n, a = case(1)
    a["sequence"].append(a["sequence"][-1])
    a["length"] += 1
    assert actual_synchronizes(n, a["sequence"])
    with pytest.raises(AssertionError): validate_answer(a, r, n)


@pytest.mark.parametrize("change", ["boolean", "missing", "extra", "negative", "wide", "wrong_count"])
def test_schema_boundary(change):
    r, n, a = case(1)
    name = next(iter(a["sequence"][0]))
    if change == "boolean": a["sequence"][0][name] = True
    if change == "missing": del a["sequence"][0][name]
    if change == "extra": a["sequence"][0]["clk"] = 1
    if change == "negative": a["sequence"][0][name] = -1
    if change == "wide": a["sequence"][0][name] = 1 << len(n["modules"]["top"]["ports"][name]["bits"])
    if change == "wrong_count": a["sequence"].pop()
    with pytest.raises(AssertionError): validate_answer(a, r, n)


def test_clear_before_load_is_not_universal():
    r, n, _ = case(8)
    sequence = encode_word([1, 1, 1, 1, 3], r["mapping"]["frame"])
    a = dict(length=5, sequence=sequence)
    assert not actual_synchronizes(n, sequence)
    with pytest.raises(AssertionError): validate_answer(a, r, n)


def test_primary_output_does_not_cover_state():
    r, n, _ = case(8)
    sequence = encode_word([3]*5, r["mapping"]["frame"])
    assert not actual_synchronizes(n, sequence)


def test_every_gate_and_flop():
    # Use the independent bit-vector checker on tiny stateful cells. A known D
    # does not initialize an enabled flop when E=0, and reset priorities differ.
    from netlist import gate_value
    kinds = ["BUF", "NOT", "AND2", "OR2", "XOR2", "XNOR2", "NAND2", "NOR2", "MUX2", "AOI21", "OAI21"]
    for kind in kinds:
        for v in range(8):
            a,b,c = v&1,(v>>1)&1,(v>>2)&1
            expected = {"BUF":a,"NOT":1-a,"AND2":a*b,"OR2":int(bool(a or b)),"XOR2":int(a!=b),"XNOR2":int(a==b),"NAND2":1-a*b,"NOR2":int(not(a or b)),"MUX2":b if c else a,"AOI21":int(not(a*b or c)),"OAI21":int(not((a or b) and c))}[kind]
            assert gate_value(kind, dict(A=a,B=b,C=c,S=c)) == expected


def test_universal_word_not_pair_distance():
    r, _, _ = case(13)
    b = r["blocks"][0]
    pairs = [(a,c) for a in range(4) for c in range(a+1,4)]
    distances = []
    for pair in pairs:
        frontier={pair}
        for depth in range(5):
            if any(a==c for a,c in frontier):
                distances.append(depth)
                break
            frontier={tuple(sorted((actual_step(b,a,u),actual_step(b,c,u))))
                      for a,c in frontier for u in range(2)}
    assert max(distances) == 3
    assert Reachability([b]).minimum(4)[0] == 4


def test_public_copies_identical():
    for source in (TASK / "environment").rglob("*"):
        if source.is_file() and (source.name=="netlist.py" or "data" in source.relative_to(TASK/"environment").parts):
            target = TASK / "tests/public" / source.relative_to(TASK / "environment")
            assert source.read_bytes() == target.read_bytes()
