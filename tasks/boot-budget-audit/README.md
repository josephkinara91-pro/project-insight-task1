Category: Hardware
Sub-Category: RTL

# Boot budget audit

This proposal replaces the earlier unbounded power-up initialization problem with a bounded firmware sign-off task. The deliverable is a reusable tool that either supplies a shortest common initialization sequence within a supplied cycle budget or establishes that the budget is insufficient. It does not claim that an unsuccessful bounded search proves impossibility for all future time.

## Professional use and difficulty

An RTL formal-verification engineer assessing a partial-reset architecture needs to know which firmware actions eliminate power-up dependence before a block is enabled. Initializing visible outputs is insufficient if a status flag, circulating pointer, or enabled pipeline register still carries unknown history. A useful tool must handle all initial register assignments and find one sequence that works for all of them without observing their contents.

The synthetic inputs combine gate-level forms of configuration banks, sticky status, reset-qualified registers, pipelines with stalls, saturating filters, a switch debouncer, recirculating state and a three-way arbitration pointer. Controls are shared across components, as they are when boot firmware drives a small interface. Their reference models and the netlist generator are included privately for review. No existing proprietary design or employment history is claimed.

The deciding knowledge is the order of the quantifiers. The required claim is that there exists one input word that makes every possible initial state agree. Merging each pair with a different word, or testing a word on a finite sample, does not establish that claim. In the pointer case every pair can merge within three cycles, but a single word for all states needs four. In the shared-stall case independent blocks need fifteen and six active cycles, but their incompatible enables make the combined minimum twenty-one. A 24-bit equality in sticky status also makes an incorrect clear-before-load order fail on initial states unlikely to occur in a small simulation sample.

This is intended for a practitioner familiar with sequential equivalence, reset analysis and symbolic transition systems. The estimated implementation effort is eight focused expert hours. The supplied loader removes routine JSON parsing from the challenge; the agent still has to choose, implement and debug an exact analysis.

## Solution approach

The reference builds Boolean next-state functions from the mapped cells. For a proposed length it first asks for a common input word on a finite set of initial states. A separate miter then searches for an arbitrary initial state whose final storage differs from the all-zero execution of that same word. A counterexample is added to the candidate problem and the process repeats.

A candidate is accepted only when the miter is unsatisfiable. Infeasibility is reported only when the finite-witness candidate formula is unsatisfiable: adding more initial states cannot make that formula satisfiable. Since a synchronized state remains synchronized under any common suffix, feasibility is monotone in length, and a binary search establishes the exact minimum within the supplied budget. Solver `unknown`, process failure and timeout are errors, not null answers.

There are no private-fixture imports, netlist-name branches or stored answers in the reference tool. Its only public dependency is the supplied loader and the pinned solver package. The generator and independent minimum checker use no reference-solver code.

## Independent verification

The private checker derives minima by breadth-first search over products of reachable component-state sets. This representation is exact because component storage starts independently arbitrary and components share only primary inputs. The search uses the same input word for every component, so it retains the coupling that a per-block maximum loses.

Small components are enumerated completely. Wide load-only banks have an exact finite quotient: distinguish the constants that the circuit can load or compare, and group all other values in an OTHER class. An OTHER singleton is never treated as initialized. For the locked and sticky banks the flag remains a separate state bit. The transition either preserves an unknown value or overwrites the entire bank with a known constant; it never partially edits or compares an unrepresented value. These properties make the quotient preserve the existence and length of synchronizing words.

The verifier recomputes every minimum, rather than trusting a hand-entered number. Every successful answer must have that exact length, pass the independent component checker and pass a second gate-level miter. That miter uses one-bit bit-vector arithmetic and composes the submitted word; it does not use the reference's Boolean transition templates or synthesis algorithm. Known witnesses are checked against the actual netlist too.

All eighteen base cases and six independently generated equivalents are graded. Equivalent forms vary instance and net names, JSON order, input packing and inversion, and register storage polarity. These transformations preserve the problem, rather than changing the expected answer depending on submitted source. Tests permit every valid minimum-length word. They reject unnecessary extra cycles, false nulls, state-dependent words, malformed output and uninitialized internal state.

The fixture generator is separately checked against the arithmetic models: exhaustive one-step checks for each small component, and symbolic one-step equivalence for every state and input of the wide components. There are 37 distinct component configurations in that check.

## Grading boundary

Only `/app/boot_sequence.py` crosses from the agent to the verifier. The two images contain byte-identical public loader and example files; only the verifier contains private cases, expected minima, model code and tests. Candidate code runs as UID/GID 65534 in a fresh working directory. Private tests and reward files remain root-only. Each child has the resource limits stated in the instruction, and its process group is killed on completion or timeout. The parent rejects symlink outputs and reads only a bounded regular JSON file.

The candidate cannot write the reward. Root-owned pytest results determine the binary reward after candidate execution, and the wrapper exits cleanly with zero even when the task is not solved. No packages are installed or fetched while grading.

## Validation evidence

- Repository static report: all 21 checks passed locally.
- Reference against independent models and the gate-level checker: 24 of 24 base/variant invocations passed. Individual runs took approximately 0.1–10.6 seconds in the development runtime; the documented allowance is 180 seconds.
- Private-key rederivation and witness checks: 18 passed.
- Negative controls and schema/logic boundary checks: 13 passed.
- Fixture one-step equivalence: 37 passed.
- A deliberately incorrect two-initial-state sampling baseline was rejected on five of seven selected cases. These are competitor tests, **not** frontier-model trials and **not** evidence that Pass@3 has passed.

Per-case results are in `validation/reference_timings.json` and `validation/sampling_results.json`. They record local executions, not container or hosted rewards. This development runtime has no usable Docker daemon or privilege-changing capability. The full Harbor Oracle/Nop runs, child-identity isolation and hosted five-trial difficulty gate still require the project runner. The authoritative result is the check report for the submitted commit, not this document.

## Reproduce

From the repository root, in a Python 3.11 environment containing `z3-solver==4.13.3.0`, `pytest==9.1.1` and `pytest-json-ctrf==0.5.2`:

```bash
python3 tasks/boot-budget-audit/tests/generate.py
python3 tasks/boot-budget-audit/validation/benchmark.py
PYTHONPATH=tasks/boot-budget-audit/environment python3 -m pytest tasks/boot-budget-audit/validation -q
python3 -m pytest tasks/boot-budget-audit/tests/test_outputs.py -k private_key -q
bash checks/static-report.sh tasks/boot-budget-audit
```

On a host with Docker and Harbor 0.18.0:

```bash
harbor run -p tasks/boot-budget-audit --agent oracle --env docker
harbor run -p tasks/boot-budget-audit --agent nop --env docker
```

The current repository README describes two initial difficulty trials followed by three fresh trials, with at most two solves across five valid trials. The attached historical guide describes an older two-trial gate. The repository's current workflow and actual PR reports govern this submission.

The supplied guide names the bf16 dot-product and lossless multicast RTL reference tasks but does not include their full RTL pages. The live examples redirect to a Handshake sign-in page in this environment. Their brief summaries informed the focus on observable sequential behavior; no claim is made to have inspected their private implementations or complete evaluation traces.

This proposal and implementation are AI-assisted. The submitting domain expert should verify the task and the platform's current authorship and proposal requirements before making any human-authorship attestation. No approval, acceptance, model failure or hosted score has been fabricated.
