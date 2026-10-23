"""Construct mapped Boolean netlists from private arithmetic block models.

Small next-state functions are synthesized by Shannon decomposition. Wide
load-only banks are built as muxes. This is a data generator, not a solver.
All net identifiers, instance names, storage polarities and input frames vary.
"""
import json
import random
from pathlib import Path
from models import actual_step, width, CASES, EXAMPLES, Reachability


class Builder:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.next_id = 2
        self.cells = {}
        self.state_map = []
        self.clock = self.net()
        self.ports = {"clk": {"direction": "input", "bits": [self.clock]}}
        widths = self.rng.choice([(1, 3), (2, 2), (3, 1), (4,)])
        physical = []
        for j, count in enumerate(widths):
            name = ["control", "qualify"][j]
            bits = [self.net() for _ in range(count)]
            self.ports[name] = {"direction": "input", "bits": bits}
            physical.extend((name, i, bit) for i, bit in enumerate(bits))
        self.rng.shuffle(physical)
        self.frame, self.u = [], []
        for name, bit, net in physical:
            inverse = self.rng.randrange(2)
            self.frame.append((name, bit, inverse))
            self.u.append(self.inv(net) if inverse else net)

    def net(self):
        self.next_id += 1
        return self.next_id

    def add(self, kind, **pins):
        name = "i_" + self.rng.randbytes(8).hex()
        self.cells[name] = {"hide_name": 0, "type": kind, "parameters": {},
                            "attributes": {}, "connections": {k: [v] for k, v in pins.items()}}

    def gate(self, kind, **pins):
        y = self.net()
        self.add(kind, Y=y, **pins)
        return y

    def inv(self, a):
        if isinstance(a, str): return "1" if a == "0" else "0"
        return self.gate("NOT", A=a)

    def mux(self, s, a, b):
        if a == b: return a
        if a == "0" and b == "1": return s
        if a == "1" and b == "0": return self.inv(s)
        style = self.rng.randrange(4)
        if style == 0: return self.gate("MUX2", A=a, B=b, S=s)
        ns = self.inv(s)
        if style == 1:
            x = self.gate("NAND2", A=ns, B=a)
            y = self.gate("NAND2", A=s, B=b)
            return self.gate("NAND2", A=x, B=y)
        if style == 2:
            x = self.gate("AND2", A=ns, B=a)
            y = self.gate("AND2", A=s, B=b)
            return self.gate("OR2", A=x, B=y)
        x = self.gate("AND2", A=ns, B=a)
        return self.inv(self.gate("AOI21", A=s, B=b, C=x))

    def condition(self, mask_value):
        mask, value = mask_value
        signals = [self.u[i] if value >> i & 1 else self.inv(self.u[i])
                   for i in range(4) if mask >> i & 1]
        if not signals: return "1"
        result = signals[0]
        for signal in signals[1:]: result = self.gate("AND2", A=result, B=signal)
        return result

    def storage(self, count):
        bits, raw, polarity = [], [], []
        for _ in range(count):
            physical = self.net()
            invert = self.rng.randrange(2)
            raw.append(physical)
            bits.append(self.inv(physical) if invert else physical)
            polarity.append(invert)
            self.state_map.append((physical, invert))
        return bits, raw, polarity

    def block(self, b):
        n, kind = b["bits"], b["kind"]
        q, raw, polarity = self.storage(width(b))
        if kind in ("bank", "locked", "sticky", "priority"):
            load = self.condition(b.get("enable", (0, 0)))
            if kind == "locked":
                write = self.condition(b["write"])
                load = self.gate("AND2", A=write, B=self.inv(q[n]))
            if kind == "priority": load = self.u[0]
            data = [self.mux(load, q[i], str(b["seed"] >> i & 1)) for i in range(n)]
            if kind == "locked":
                lock = self.mux(self.condition(b["lock"]), q[n], "1")
                data.append(self.mux(self.condition(b["unlock"]), lock, "0"))
            if kind == "sticky":
                comparisons = [self.gate("XNOR2", A=bit, B=str(b["trap"] >> i & 1))
                               for i, bit in enumerate(q[:n])]
                bad = comparisons[0]
                for term in comparisons[1:]: bad = self.gate("AND2", A=bad, B=term)
                sticky = self.gate("OR2", A=q[n], B=bad)
                data.append(self.mux(self.condition(b["clear"]), sticky, bad))
            if kind == "priority":
                # Use actual priority-sensitive library flops, without polarity
                # inversion, so cell semantics are exercised directly.
                for i in range(n):
                    # q[i] inverter, if created, is a harmless dangling wire.
                    self.state_map[-n+i] = (raw[i], 0)
                    cell = "DFFRE" if b["priority"] == "reset" else "DFFER"
                    self.add(cell, C=self.clock, Q=raw[i], D=str(b["seed"] >> i & 1),
                             R=self.u[1], E=self.u[0])
                return
        else:
            count = len(q)
            # Low-order truth-table variables are controls, then logical Q bits.
            variables = self.u + q
            outputs = [actual_step(b, i >> 4, i & 15) for i in range(1 << (count+4))]
            cache = {}

            def synth(values, level):
                if all(v == values[0] for v in values): return str(values[0])
                key = (level, values)
                if key not in cache:
                    low = synth(values[0::2], level+1)
                    high = synth(values[1::2], level+1)
                    cache[key] = self.mux(variables[level], low, high)
                return cache[key]

            data = [synth(tuple(v >> i & 1 for v in outputs), 0) for i in range(count)]
        for d, physical, invert in zip(data, raw, polarity):
            self.add("DFF", C=self.clock, D=self.inv(d) if invert else d, Q=physical)

    def finish(self):
        # A primary output intentionally exposes only one register: checking it
        # alone is insufficient. Combinational-only designs expose an input.
        out = self.state_map[0][0] if self.state_map else self.u[0]
        self.ports["observe"] = {"direction": "output", "bits": [out]}
        ids = list(range(3, self.next_id+1))
        names = self.rng.sample(range(17, 17+len(ids)*7), len(ids))
        rename = dict(zip(ids, names))
        def mapped(bit): return rename[bit] if isinstance(bit, int) else bit
        ports = {n: dict(direction=p["direction"], bits=[mapped(v) for v in p["bits"]])
                 for n, p in self.ports.items()}
        cells = list(self.cells.items())
        self.rng.shuffle(cells)
        transformed = {}
        for name, cell in cells:
            transformed[name] = dict(cell, connections={k: [mapped(v[0])] for k, v in cell["connections"].items()})
        state_map = [(mapped(bit), inv) for bit, inv in self.state_map]
        return {"creator": "boot-budget mapped-cell fixture", "modules": {
            "top": {"ports": ports, "cells": transformed, "netnames": {}}}}, state_map


def build(blocks, seed):
    builder = Builder(seed)
    for b in blocks: builder.block(b)
    netlist, state_map = builder.finish()
    return netlist, {"frame": builder.frame, "state_map": state_map}


def encode_word(word, frame):
    result = []
    for u in word:
        row = {name: 0 for name, _, _ in frame}
        for i, (name, bit, inverse) in enumerate(frame):
            row[name] |= ((u >> i & 1) ^ inverse) << bit
        result.append(row)
    return result


def decode_word(sequence, frame):
    return [sum((((row[name] >> bit) & 1) ^ inverse) << i
                for i, (name, bit, inverse) in enumerate(frame)) for row in sequence]


def generate_all(root):
    private = root / "tests" / "private"
    examples = root / "environment" / "data" / "examples"
    private.mkdir(parents=True, exist_ok=True)
    examples.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (name, budget, blocks) in enumerate(CASES):
        netlist, mapping = build(blocks, 71003 + 1009*index)
        minimum, witness, visited = Reachability(blocks).minimum(budget)
        record = dict(name=name, budget=budget, blocks=blocks, minimum=minimum,
                      witness=witness, visited=visited, mapping=mapping, seed=71003+1009*index)
        (private / f"{name}.json").write_text(json.dumps(netlist, separators=(",", ":")) + "\n")
        records.append(record)
        print(name, "flops", sum(width(b) for b in blocks), "minimum", minimum, "beliefs", visited, flush=True)
    (private / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    for index, (name, budget, blocks) in enumerate(EXAMPLES):
        netlist, mapping = build(blocks, 109+index)
        minimum, word, _ = Reachability(blocks).minimum(budget)
        (examples / f"{name}.json").write_text(json.dumps(netlist, indent=2) + "\n")
        (examples / f"{name}.answer.json").write_text(json.dumps({"length": minimum, "sequence": encode_word(word, mapping["frame"])}, indent=2) + "\n")
        (examples / f"{name}.budget.txt").write_text(str(budget) + "\n")


if __name__ == "__main__":
    generate_all(Path(__file__).resolve().parents[1])
