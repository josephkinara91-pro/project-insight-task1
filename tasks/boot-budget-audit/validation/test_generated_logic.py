"""Prove fixture synthesis against the independent arithmetic descriptions.

Small blocks: every actual state and every input, through the public binary
gate simulator. Wide banks: one-step symbolic equivalence for every stored
bit, flag and control, against separate bit-vector equations.
"""
import json
from pathlib import Path
import sys
import tempfile
import pytest
import z3

TASK = Path(__file__).resolve().parents[1]
for sub in ("tests", "environment", "solution"):
    sys.path.insert(0, str(TASK/sub))
from models import CASES, actual_step, uses_quotient, width
from generate import build, encode_word
from netlist import Circuit
from reference import Synthesizer

UNIQUE = {json.dumps(b, sort_keys=True): b for _, _, blocks in CASES for b in blocks}
BLOCKS = list(UNIQUE.values())


@pytest.mark.parametrize("index,b", list(enumerate(BLOCKS)), ids=lambda b: b["kind"] if isinstance(b,dict) else str(b))
def test_one_step(index, b):
    netlist, mapping = build([b], 271+index)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/"circuit.json"
        path.write_text(json.dumps(netlist))
        c = Circuit(path)
    flop_index = {p["Q"]: i for i, (_,p) in enumerate(c.flops)}
    if not uses_quotient(b):
        for q in range(1 << width(b)):
            physical = sum((((q>>i)&1)^inverse) << flop_index[net]
                           for i,(net,inverse) in enumerate(mapping["state_map"]))
            for u in range(16):
                out = c.step(physical, encode_word([u], mapping["frame"])[0])
                logical = sum((((out>>flop_index[net])&1)^inverse) << i
                              for i,(net,inverse) in enumerate(mapping["state_map"]))
                assert logical == actual_step(b,q,u)
        return
    s = Synthesizer(c)
    actual_bits = []
    q_bits = []
    for net, inv in mapping["state_map"]:
        i = flop_index[net]
        q_bits.append(z3.Not(s.q[i]) if inv else s.q[i])
        actual_bits.append(z3.Not(s.functions[i]) if inv else s.functions[i])
    input_index = {(name,bit): i for i,(name,bit,_) in enumerate(s.input_bits)}
    u = [z3.Not(s.u[input_index[name,bit]]) if inv else s.u[input_index[name,bit]]
         for name,bit,inv in mapping["frame"]]
    n = b["bits"]
    data = z3.Concat(*[z3.If(q, z3.BitVecVal(1,1), z3.BitVecVal(0,1)) for q in reversed(q_bits[:n])])
    seed = z3.BitVecVal(b["seed"],n)
    def cond(pair):
        mask,value=pair
        return z3.And([u[i] == bool(value>>i&1) for i in range(4) if mask>>i&1])
    kind = b["kind"]
    flag = None
    if kind=="bank": expected=z3.If(cond(b["enable"]), seed, data)
    elif kind=="priority":
        if b["priority"]=="reset": expected=z3.If(u[1],0,z3.If(u[0],seed,data))
        else: expected=z3.If(u[0],z3.If(u[1],0,seed),data)
    elif kind=="locked":
        expected=z3.If(z3.And(cond(b["write"]),z3.Not(q_bits[n])),seed,data)
        flag=z3.If(cond(b["unlock"]),False,z3.If(cond(b["lock"]),True,q_bits[n]))
    elif kind=="sticky":
        bad=data==z3.BitVecVal(b["trap"],n)
        expected=z3.If(cond(b["enable"]),seed,data)
        flag=z3.If(cond(b["clear"]),bad,z3.Or(q_bits[n],bad))
    expected_bits=[z3.Extract(i,i,expected)==1 for i in range(n)]
    if flag is not None: expected_bits.append(flag)
    miter=z3.Solver()
    miter.add(z3.Or([a!=e for a,e in zip(actual_bits,expected_bits)]))
    assert miter.check()==z3.unsat
