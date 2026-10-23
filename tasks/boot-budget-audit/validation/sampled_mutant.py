"""Deliberately incorrect baseline: check only two concrete power-up states.

This is a calibration competitor, never copied into either runtime image.
It retains the same SAT search and minimization as the reference but removes
the universally quantified validation/refinement step.
"""
import json
from pathlib import Path
import sys
import z3

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "environment"))
sys.path.insert(0, str(TASK / "solution"))
from netlist import Circuit
from reference import Synthesizer


class Sampled(Synthesizer):
    def at_length(self, length):
        controls = [[z3.Bool(f"in_{t}_{i}") for i in range(len(self.u))] for t in range(length)]
        solver = z3.Solver()
        a = self.unroll(solver, controls, self.concrete(0), "a")
        b = self.unroll(solver, controls, self.concrete((1 << self.n)-1), "b")
        solver.add([x == y for x, y in zip(a, b)])
        result = solver.check()
        if result == z3.unsat: return None
        assert result == z3.sat
        m = solver.model()
        return [[z3.is_true(m.eval(u, model_completion=True)) for u in row] for row in controls]


if __name__ == "__main__":
    answer = Sampled(Circuit(sys.argv[1])).solve(int(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(answer))
