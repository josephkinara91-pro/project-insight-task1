"""Exact bounded open-loop synthesis by counterexample-guided refinement.

The candidate problem is existential on control bits and contains concrete
initial-state witnesses. A second solver looks for ANY initial state whose
final register values differ from the all-zero execution of that same word.
Only UNSAT in the first solver proves infeasibility, and only UNSAT in the
second proves a candidate synchronizes all states. No finite sample is a proof.
"""
import json
import sys
import z3
from netlist import Circuit


class Synthesizer:
    def __init__(self, circuit):
        self.circuit = circuit
        self.n = circuit.state_bits
        self.input_bits = [(name, i, signal)
                           for name, bits in sorted(circuit.input_ports.items())
                           for i, signal in enumerate(bits)]
        self.q = [z3.Bool(f"q_{i}") for i in range(self.n)]
        self.u = [z3.Bool(f"u_{i}") for i in range(len(self.input_bits))]
        v = {"0": z3.BoolVal(False), "1": z3.BoolVal(True)}
        v.update((sig, u) for (_, _, sig), u in zip(self.input_bits, self.u))
        v.update((p["Q"], q) for (_, p), q in zip(circuit.flops, self.q))
        for k, p in circuit.gates:
            a = v[p["A"]]
            b = v[p["B"]] if "B" in p else None
            if k == "BUF": y = a
            elif k == "NOT": y = z3.Not(a)
            elif k == "AND2": y = z3.And(a, b)
            elif k == "OR2": y = z3.Or(a, b)
            elif k == "XOR2": y = z3.Xor(a, b)
            elif k == "XNOR2": y = z3.Not(z3.Xor(a, b))
            elif k == "NAND2": y = z3.Not(z3.And(a, b))
            elif k == "NOR2": y = z3.Not(z3.Or(a, b))
            elif k == "MUX2": y = z3.If(v[p["S"]], b, a)
            elif k == "AOI21": y = z3.Not(z3.Or(z3.And(a, b), v[p["C"]]))
            elif k == "OAI21": y = z3.Not(z3.And(z3.Or(a, b), v[p["C"]]))
            else: raise ValueError(k)
            v[p["Y"]] = z3.simplify(y)
        self.functions = []
        for i, (k, p) in enumerate(circuit.flops):
            d, q = v[p["D"]], self.q[i]
            if k == "DFFE": d = z3.If(v[p["E"]], d, q)
            elif k == "DFFR": d = z3.If(v[p["R"]], False, d)
            elif k == "DFFS": d = z3.If(v[p["S"]], True, d)
            elif k == "DFFRE": d = z3.If(v[p["R"]], False, z3.If(v[p["E"]], d, q))
            elif k == "DFFER": d = z3.If(v[p["E"]], z3.If(v[p["R"]], False, d), q)
            self.functions.append(z3.simplify(d))
        self.witnesses = {0, (1 << self.n) - 1}
        self.iterations = 0

    def unroll(self, solver, controls, initial, prefix):
        state = initial
        for t, inputs in enumerate(controls):
            mapping = list(zip(self.q, state)) + list(zip(self.u, inputs))
            nxt = [z3.Bool(f"{prefix}_{t}_{i}") for i in range(self.n)]
            solver.add([x == z3.simplify(z3.substitute(f, *mapping))
                        for x, f in zip(nxt, self.functions)])
            state = nxt
        return state

    def concrete(self, value):
        return [z3.BoolVal(bool(value >> i & 1)) for i in range(self.n)]

    def at_length(self, length):
        controls = [[z3.Bool(f"in_{t}_{i}") for i in range(len(self.u))]
                    for t in range(length)]
        candidate = z3.Solver()
        anchor = self.unroll(candidate, controls, self.concrete(0), "anchor")
        seen = set()

        def add_witness(value):
            if value in seen or value == 0: return
            seen.add(value)
            final = self.unroll(candidate, controls, self.concrete(value), f"sample_{len(seen)}")
            candidate.add([a == b for a, b in zip(anchor, final)])

        for value in sorted(self.witnesses): add_witness(value)
        checker = z3.Solver()
        unknown = [z3.Bool(f"initial_{i}") for i in range(self.n)]
        final = self.unroll(checker, controls, unknown, "unknown")
        zero = self.unroll(checker, controls, self.concrete(0), "zero")
        checker.add(z3.Or([a != b for a, b in zip(final, zero)]))
        while True:
            self.iterations += 1
            result = candidate.check()
            if result == z3.unsat: return None
            if result != z3.sat: raise RuntimeError("Candidate solve returned unknown")
            model = candidate.model()
            word = [[z3.is_true(model.eval(u, model_completion=True)) for u in row]
                    for row in controls]
            checker.push()
            checker.add([u == bit for row, bits in zip(controls, word)
                         for u, bit in zip(row, bits)])
            result = checker.check()
            if result == z3.unsat:
                checker.pop()
                return word
            if result != z3.sat: raise RuntimeError("Counterexample solve returned unknown")
            model = checker.model()
            value = sum(int(z3.is_true(model.eval(q, model_completion=True))) << i
                        for i, q in enumerate(unknown))
            checker.pop()
            if value in seen or value == 0:
                raise AssertionError("Counterexample is already constrained")
            self.witnesses.add(value)
            add_witness(value)

    def solve(self, budget):
        if self.n == 0: return {"length": 0, "sequence": []}
        if budget == 0: return {"length": None, "sequence": []}
        best = self.at_length(budget)
        if best is None: return {"length": None, "sequence": []}
        lo, hi = 0, budget
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            word = self.at_length(mid)
            if word is None: lo = mid
            else: hi, best = mid, word
        sequence = []
        for bits in best:
            row = {name: 0 for name in self.circuit.input_ports}
            for (name, bit, _), value in zip(self.input_bits, bits):
                row[name] |= int(value) << bit
            sequence.append(row)
        return {"length": hi, "sequence": sequence}


def main():
    if len(sys.argv) != 4: raise SystemExit("usage: boot_sequence.py NETLIST MAX_CYCLES OUTPUT")
    circuit = Circuit(sys.argv[1])
    solver = Synthesizer(circuit)
    result = solver.solve(int(sys.argv[2]))
    with open(sys.argv[3], "w") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__": main()
