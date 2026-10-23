"""Public loader and binary simulator; bit positions are little-endian.

Circuit exposes input_ports (port name -> signal IDs), gates (topological order),
and flops (state-bit order). Each gate/flop is (type, scalar connection dict).
step(state_integer, port_values) returns the next state integer after one edge.
This helper contains no initialization search or expected answers.
"""
import json

GATE_PINS = {
    "BUF": "A", "NOT": "A", "AND2": "AB", "OR2": "AB", "XOR2": "AB",
    "XNOR2": "AB", "NAND2": "AB", "NOR2": "AB", "MUX2": "ABS",
    "AOI21": "ABC", "OAI21": "ABC",
}
FF_PINS = {"DFF": "CD", "DFFE": "CDE", "DFFR": "CDR", "DFFS": "CDS",
           "DFFRE": "CDRE", "DFFER": "CDRE"}


def gate_value(kind, values):
    a = values["A"]
    if kind == "BUF": return a
    if kind == "NOT": return a ^ 1
    b = values["B"]
    if kind == "AND2": return a & b
    if kind == "OR2": return a | b
    if kind == "XOR2": return a ^ b
    if kind == "XNOR2": return (a ^ b) ^ 1
    if kind == "NAND2": return (a & b) ^ 1
    if kind == "NOR2": return (a | b) ^ 1
    if kind == "MUX2": return b if values["S"] else a
    if kind == "AOI21": return ((a & b) | values["C"]) ^ 1
    if kind == "OAI21": return ((a | b) & values["C"]) ^ 1
    raise ValueError(kind)


class Circuit:
    def __init__(self, path):
        with open(path) as f:
            module = json.load(f)["modules"]["top"]
        self.input_ports = {n: p["bits"] for n, p in module["ports"].items()
                            if p["direction"] == "input" and n != "clk"}
        self.flops, pending = [], []
        for name, cell in sorted(module["cells"].items()):
            kind = cell["type"]
            pins = {p: bits[0] for p, bits in cell["connections"].items()}
            if any(len(b) != 1 for b in cell["connections"].values()):
                raise ValueError("Cell pins must be scalar")
            if kind in FF_PINS: self.flops.append((kind, pins))
            elif kind in GATE_PINS: pending.append((kind, pins))
            else: raise ValueError("Unknown cell: " + kind)
        ready = {"0", "1"}
        for bits in self.input_ports.values(): ready.update(bits)
        ready.update(p["Q"] for _, p in self.flops)
        self.gates = []
        while pending:
            batch = [(k, p) for k, p in pending if all(p[a] in ready for a in GATE_PINS[k])]
            if not batch: raise ValueError("Undriven net or combinational cycle")
            self.gates.extend(batch)
            ready.update(p["Y"] for _, p in batch)
            pending = [(k, p) for k, p in pending if p["Y"] not in ready]
        self.state_bits = len(self.flops)

    def step(self, state, inputs):
        v = {"0": 0, "1": 1}
        for name, bits in self.input_ports.items():
            for i, bit in enumerate(bits): v[bit] = (inputs[name] >> i) & 1
        for i, (_, p) in enumerate(self.flops): v[p["Q"]] = (state >> i) & 1
        for kind, p in self.gates:
            v[p["Y"]] = gate_value(kind, {a: v[p[a]] for a in GATE_PINS[kind]})
        out = 0
        for i, (kind, p) in enumerate(self.flops):
            d, q = v[p["D"]], (state >> i) & 1
            if kind == "DFFE": d = d if v[p["E"]] else q
            elif kind == "DFFR": d = 0 if v[p["R"]] else d
            elif kind == "DFFS": d = 1 if v[p["S"]] else d
            elif kind == "DFFRE": d = 0 if v[p["R"]] else (d if v[p["E"]] else q)
            elif kind == "DFFER": d = (0 if v[p["R"]] else d) if v[p["E"]] else q
            out |= d << i
        return out
