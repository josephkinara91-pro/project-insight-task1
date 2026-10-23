"""Result validation, independent gate-level miter, and isolated invocation."""
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import z3
from models import Reachability
from generate import decode_word

COMB = {"BUF", "NOT", "AND2", "OR2", "XOR2", "XNOR2", "NAND2", "NOR2", "MUX2", "AOI21", "OAI21"}


def actual_synchronizes(netlist, sequence):
    """Independent 1-bit bit-vector gate interpretation, for the submitted word.

The reference uses Boolean transition templates and existential refinement.
This check composes bit-vector expressions for a fixed submitted sequence and
asks whether any initial assignment disagrees with the zero-initial execution.
"""
    module = netlist["modules"]["top"]
    registers, pending = [], []
    for name, c in sorted(module["cells"].items()):
        pins = {k: v[0] for k, v in c["connections"].items()}
        (pending if c["type"] in COMB else registers).append((c["type"], pins))
    initial = [z3.BitVec(f"powerup_{i}", 1) for i in range(len(registers))]
    state = list(initial)
    ordered = []
    available = {"0", "1"}
    for p in module["ports"].values():
        if p["direction"] == "input": available.update(p["bits"])
    available.update(p["Q"] for _, p in registers)
    while pending:
        ready = [(k, p) for k, p in pending if all(v in available for a, v in p.items() if a != "Y")]
        assert ready, "Invalid private combinational graph"
        ordered.extend(ready)
        available.update(p["Y"] for _, p in ready)
        pending = [(k, p) for k, p in pending if p["Y"] not in available]
    zero, one = z3.BitVecVal(0, 1), z3.BitVecVal(1, 1)
    for row in sequence:
        values = {"0": zero, "1": one}
        for name, port in module["ports"].items():
            if port["direction"] == "input" and name != "clk":
                for bit, net in enumerate(port["bits"]): values[net] = one if row[name] >> bit & 1 else zero
        values.update((p["Q"], v) for (_, p), v in zip(registers, state))
        for kind, p in ordered:
            a = values[p["A"]]
            b = values[p["B"]] if "B" in p else zero
            c = values[p["C"]] if "C" in p else zero
            if kind == "BUF": result = a
            elif kind == "NOT": result = ~a
            elif kind == "AND2": result = a & b
            elif kind == "OR2": result = a | b
            elif kind == "XOR2": result = a ^ b
            elif kind == "XNOR2": result = ~(a ^ b)
            elif kind == "NAND2": result = ~(a & b)
            elif kind == "NOR2": result = ~(a | b)
            elif kind == "MUX2":
                s = values[p["S"]]
                result = (~s & a) | (s & b)
            elif kind == "AOI21": result = ~((a & b) | c)
            elif kind == "OAI21": result = ~((a | b) & c)
            values[p["Y"]] = z3.simplify(result)
        nxt = []
        for q, (kind, p) in zip(state, registers):
            d = values[p["D"]]
            if kind in ("DFFE", "DFFRE", "DFFER"):
                e = values[p["E"]]
            if kind in ("DFFR", "DFFRE", "DFFER"):
                r = values[p["R"]]
            if kind == "DFFE": d = (e & d) | (~e & q)
            elif kind == "DFFR": d = ~r & d
            elif kind == "DFFS": d = values[p["S"]] | d
            elif kind == "DFFRE": d = ~r & ((e & d) | (~e & q))
            elif kind == "DFFER": d = (e & ~r & d) | (~e & q)
            elif kind != "DFF": raise AssertionError("Unknown private flop")
            nxt.append(z3.simplify(d))
        state = nxt
    solver = z3.Solver()
    constants = [z3.simplify(z3.substitute(v, *[(q, zero) for q in initial])) for v in state]
    solver.add(z3.Or([a != b for a, b in zip(state, constants)]))
    result = solver.check()
    assert result != z3.unknown, "Verifier miter was inconclusive"
    return result == z3.unsat


def validate_answer(answer, record, netlist):
    assert isinstance(answer, dict) and set(answer) == {"length", "sequence"}, "Output keys"
    length, sequence = answer["length"], answer["sequence"]
    assert isinstance(sequence, list), "Sequence must be a list"
    expected = record["minimum"]
    if length is None:
        assert sequence == [], "Null answer needs an empty sequence"
        assert expected is None, "A sequence exists within the budget"
        return
    assert type(length) is int and 0 <= length <= record["budget"], "Length/budget"
    assert length == expected, "Sequence length is not the exact minimum"
    assert len(sequence) == length, "Length differs from sequence size"
    ports = {n: len(p["bits"]) for n, p in netlist["modules"]["top"]["ports"].items()
             if p["direction"] == "input" and n != "clk"}
    for row in sequence:
        assert isinstance(row, dict) and set(row) == set(ports), "Input port set"
        assert all(type(row[n]) is int and 0 <= row[n] < 1 << w for n, w in ports.items()), "Input width/type"
    assert Reachability(record["blocks"]).validate(decode_word(sequence, record["mapping"]["frame"])), "Initial state still influences storage"
    assert actual_synchronizes(netlist, sequence), "Gate-level counterexample to submitted sequence"


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (360, 361))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def isolated_run(netlist, budget):
    """Only this child runs agent code. Private material stays in the parent."""
    code = os.open("/app/boot_sequence.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        assert stat.S_ISREG(os.fstat(code).st_mode), "Deliverable must be a regular Python file"
        os.fchmod(code, 0o644)
    finally:
        os.close(code)
    with tempfile.TemporaryDirectory(prefix="boot-case-") as directory:
        work = Path(directory)
        os.chown(work, 65534, 65534)
        work.chmod(0o700)
        source, output = work / "input.json", work / "result.json"
        source.write_text(json.dumps(netlist))
        source.chmod(0o444)
        log_path = work / "candidate.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, "/app/boot_sequence.py", str(source), str(budget), str(output)],
                cwd=work, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                     "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1"},
                preexec_fn=_limits, start_new_session=True)
            try:
                returncode = process.wait(timeout=180)
            finally:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
        assert returncode == 0, "Candidate must exit zero"
        fd = os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "r") as stream:
            info = os.fstat(stream.fileno())
            assert stat.S_ISREG(info.st_mode) and info.st_size <= 1024**2, "Output must be a regular JSON file of at most 1 MiB"
            return json.load(stream)
