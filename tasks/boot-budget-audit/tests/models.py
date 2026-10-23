"""Independent arithmetic models and exact reachability of possible-state sets.

All component states start independently arbitrary. Components share inputs,
not storage, so a reachable global belief is exactly a product of local sets.
Wide load-only registers have a finite EXACT quotient: explicitly represented
constants and an OTHER class. OTHER is never counted as a known final value.
No SAT/SMT library, gate parser, or reference-solver function is used here.
"""
from collections import deque
from functools import lru_cache


def hit(u, condition):
    mask, value = condition
    return u & mask == value


def width(b):
    return b["bits"] + (1 if b["kind"] in ("sticky", "locked") else
                        2 if b["kind"] == "debounce" else 0)


def actual_step(b, q, u):
    kind, n = b["kind"], b["bits"]
    mask = (1 << n) - 1
    enabled = hit(u, b.get("enable", (0, 0)))
    if kind == "bank": return b["seed"] if enabled else q
    if kind == "priority":
        r, e = bool(u & 2), bool(u & 1)
        if b["priority"] == "reset": return 0 if r else (b["seed"] if e else q)
        return (0 if r else b["seed"]) if e else q
    if kind == "locked":
        data, lock = q & mask, q >> n
        if hit(u, b["write"]) and not lock: data = b["seed"]
        if hit(u, b["unlock"]): lock = 0
        elif hit(u, b["lock"]): lock = 1
        return data | lock << n
    if kind == "sticky":
        data, flag = q & mask, q >> n
        bad = int(data == b["trap"])
        flag = bad if hit(u, b["clear"]) else flag | bad
        if enabled: data = b["seed"]
        return data | flag << n
    if kind == "shift": return ((q << 1) & mask) if enabled else q
    if kind == "sat": return min(mask, q + 1) if enabled else q
    if kind == "leaky":
        return min(mask, q - (q >> b["shift"]) + (b["drive"] if enabled else 0))
    if kind == "lfsr":
        if "load" in b and hit(u, b["load"]): return b["seed"]
        feedback = ((q >> (n - 1)) ^ q) & 1
        return ((q << 1) | feedback) & mask
    if kind == "johnson": return ((q << 1) | (1 ^ (q >> (n-1)))) & mask
    if kind == "pointer":
        if q == 3: return 0  # hardware self-correction for an illegal pointer
        park = hit(u, b["park"])
        return (0 if q == 2 else q) if park else (q + 1) % 3
    if kind == "debounce":
        count, previous, stable = q & mask, (q >> n) & 1, q >> (n+1)
        raw = (u >> b["raw"]) & 1
        if raw != previous: count = 0
        else:
            if count == mask: stable = raw
            count = min(mask, count + 1)
        return count | raw << n | stable << (n+1)
    raise ValueError(kind)


def quotient_constants(b):
    if b["kind"] == "sticky": return [b["seed"], b["trap"]]
    if b["kind"] == "priority": return [0, b["seed"]]
    return [b["seed"]]


def uses_quotient(b):
    return b["kind"] in ("bank", "priority", "locked", "sticky")


def states(b):
    if not uses_quotient(b): return range(1 << width(b))
    k = len(quotient_constants(b)) + 1  # last index is OTHER
    return range(k * (2 if b["kind"] in ("locked", "sticky") else 1))


def representative(b, state):
    if not uses_quotient(b): return state
    values = quotient_constants(b)
    classes = len(values) + 1
    flag, which = divmod(state, classes)
    if which < len(values): value = values[which]
    else:
        value = next(i for i in range(len(values) + 1) if i not in values)
    return value | flag << b["bits"]


def quotient_step(b, state, u):
    q = actual_step(b, representative(b, state), u)
    if not uses_quotient(b): return q
    constants = quotient_constants(b)
    low = q & ((1 << b["bits"]) - 1)
    which = constants.index(low) if low in constants else len(constants)
    return (q >> b["bits"]) * (len(constants) + 1) + which


def singleton(b, possible):
    if len(possible) != 1: return False
    if not uses_quotient(b): return True
    k = len(quotient_constants(b)) + 1
    return next(iter(possible)) % k != k - 1


class Reachability:
    def __init__(self, blocks):
        self.blocks = blocks
        self.initial = tuple(frozenset(states(b)) for b in blocks)
        self.tables = [[[quotient_step(b, s, u) for s in states(b)] for u in range(16)]
                       for b in blocks]

    @lru_cache(maxsize=None)
    def image(self, i, values, u):
        table = self.tables[i][u]
        return frozenset(table[s] for s in values)

    def advance(self, belief, u):
        return tuple(self.image(i, values, u) for i, values in enumerate(belief))

    def synchronized(self, belief):
        return all(singleton(b, values) for b, values in zip(self.blocks, belief))

    def validate(self, word):
        belief = self.initial
        for u in word: belief = self.advance(belief, u)
        return self.synchronized(belief)

    def minimum(self, budget):
        queue = deque([(self.initial, ())])
        visited = {self.initial}
        while queue:
            belief, word = queue.popleft()
            if self.synchronized(belief): return len(word), list(word), len(visited)
            if len(word) == budget: continue
            for u in range(16):
                nxt = self.advance(belief, u)
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, word + (u,)))
        return None, [], len(visited)


def block(kind, bits, **kw): return dict(kind=kind, bits=bits, **kw)


CASES = [
    ("combinational", 0, []),
    ("pipeline", 8, [block("shift", 6, enable=(1, 1)), block("bank", 24, enable=(8, 8), seed=0x35A107)]),
    ("short-budget", 5, [block("shift", 6, enable=(1, 1)), block("bank", 20, enable=(8, 8), seed=0x491B3)]),
    ("shared-stall", 24, [block("sat", 4, enable=(1, 0)), block("shift", 6, enable=(1, 1)), block("bank", 24, enable=(2, 2), seed=0x951C72)]),
    ("stall-budget", 20, [block("sat", 4, enable=(1, 0)), block("shift", 6, enable=(1, 1)), block("bank", 24, enable=(2, 2), seed=0xA73C09)]),
    ("filter-deadband", 32, [block("leaky", 5, enable=(2, 2), shift=3, drive=4), block("bank", 28, enable=(8, 8), seed=0x573AC91)]),
    ("qualified-control", 20, [block("debounce", 3, raw=0), block("shift", 5, enable=(3, 2)), block("locked", 16, seed=0xA4D3, unlock=(3, 1), write=(3, 2), lock=(3, 3))]),
    ("reset-priority", 5, [block("priority", 17, seed=0x19531, priority="reset"), block("priority", 19, seed=0x571A3, priority="enable"), block("shift", 3, enable=(3, 2))]),
    ("rare-status", 8, [block("sticky", 24, seed=0x923C17, trap=0xEB6D41, enable=(3, 3), clear=(3, 1)), block("shift", 4, enable=(3, 1))]),
    ("configuration-order", 8, [block("sticky", 20, seed=0xAB713, trap=0xE93D5, enable=(3, 1), clear=(3, 2)), block("locked", 16, seed=0x5719, unlock=(3, 2), write=(3, 3), lock=(3, 1))]),
    ("unseeded-state", 32, [block("lfsr", 5), block("bank", 32, seed=0x67AB1239, enable=(4, 4)), block("shift", 7, enable=(1, 1))]),
    ("seed-and-drain", 12, [block("lfsr", 7, load=(3, 0), seed=0x53), block("shift", 5, enable=(3, 3)), block("bank", 24, seed=0xA0B1C2, enable=(8, 8))]),
    ("recirculating-state", 24, [block("johnson", 6), block("bank", 24, seed=0xA91C35, enable=(2, 2))]),
    ("three-way-pointer", 8, [block("pointer", 2, park=(1, 1)), block("bank", 24, seed=0xA17351, enable=(8, 8))]),
    ("coupled-pointers", 16, [block("pointer", 2, park=(1, 1)), block("pointer", 2, park=(1, 0)), block("locked", 16, seed=0xD395, unlock=(3, 1), write=(3, 2), lock=(3, 3))]),
    ("flag-and-filter", 24, [block("sticky", 24, seed=0x67135A, trap=0x9AC721, enable=(3, 1), clear=(3, 2)), block("leaky", 5, enable=(1, 1), shift=3, drive=4)]),
    ("zero-budget", 0, [block("bank", 32, seed=0x7139ABCD, enable=(3, 1))]),
    ("interlocked-boot", 24, [block("locked", 20, seed=0xA7B13, unlock=(3, 1), write=(3, 2), lock=(3, 3)), block("sat", 3, enable=(3, 3)), block("shift", 4, enable=(3, 0)), block("pointer", 2, park=(2, 2))]),
]


EXAMPLES = [
    ("load", 2, [block("bank", 4, seed=9, enable=(1, 1))]),
    ("flush", 4, [block("shift", 3, enable=(2, 2))]),
    ("hold", 4, [block("lfsr", 3)]),
    ("empty", 0, []),
]
