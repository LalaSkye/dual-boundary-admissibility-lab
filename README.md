[![CI](https://github.com/LalaSkye/dual-boundary-admissibility-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/LalaSkye/dual-boundary-admissibility-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-261%20passing-brightgreen)]()

# dual-boundary-admissibility-lab

**Two gates. One corridor. Meaning construction governed before execution is even considered.**

## Why This Exists

Every published AI governance system gates at the execution boundary — the moment an action is about to change state. Faramesh says interpretation governance is "explicitly outside the scope." Other published approaches say "you can't govern thinking directly."

This repo treats that as a design choice, not an axiom. It governs at the interpretation layer — *before* a transition candidate exists — then gates again at the mutation boundary. The corridor between the two boundaries is instrumented under pressure. Nothing executes without passing both.

## Architecture

```
signal
  → X_packet                         (typed transit, not authority)
  → interpretive_admissibility_check  (10 rules + closed graph topology)
  → pressure_assessment               (5 pressure sources, 3 signal quality axes)
  → { route | rotate_C | hold | halt }
  → state_mutation_check              (downstream admissibility gate)
  → commit | deny
```

### The Two-Boundary Corridor

```
 ┌────────────────────────────────────────────────────────┐
 │                 ADMISSIBILITY ROTATION CORRIDOR         │
 │                                                         │
 │   ┌──────────┐   ┌────────────┐   ┌─────────────────┐ │
 │   │ UPSTREAM  │   │  PRESSURE  │   │   DOWNSTREAM    │ │
 │   │ BOUNDARY  │──▶│  MONITOR   │──▶│   BOUNDARY      │ │
 │   │           │   │            │   │                 │ │
 │   │ • 10 rules│   │ • 5 sources│   │ • state check   │ │
 │   │ • closed  │   │ • signal   │   │ • append-only   │ │
 │   │   graph   │   │   quality  │   │ • provenance    │ │
 │   │ • provn.  │   │ • sentinel │   │   lock          │ │
 │   └──────────┘   └─────┬──────┘   └─────────────────┘ │
 │                         │                               │
 │                    ┌────▼─────┐                         │
 │                    │ C-SECTOR │                         │
 │                    │ ROTATION │                         │
 │                    │          │                         │
 │                    │ HALT /   │                         │
 │                    │ HOLD     │                         │
 │                    └──────────┘                         │
 └────────────────────────────────────────────────────────┘
```

## Core Geometry

```
A → B → D
    ↓
    C
```

- **A** = signal initiation
- **B** = exploration / transformation
- **D** = integration / stabilisation
- **C** = interrupt vector (pressure-activated, not failure-activated)

Additional invariants on the geometry:
- HOLD for insufficiency
- HALT for violation
- RELEASE only by explicit verdict
- ROTATION only by declared trigger
- CONSTRAINTS must be named
- PROVENANCE must persist through wrapping
- STATE must be reconstructable
- CLOSURE must be explicit

## Quick Start

```bash
git clone https://github.com/LalaSkye/dual-boundary-admissibility-lab.git
cd dual-boundary-admissibility-lab
python examples/demo_scenario.py
```

Expected output:

```
========================================================================
  Admissibility Rotation Corridor — Demo Scenario
========================================================================

── Step 1: Admissible packet enters ──
  Outcome: commit
  Admitted: True
  ✓ Packet committed successfully

── Step 2: Pressure rises (degraded signal + denials) ──
  Total pressure: 0.8550
  Recommendation: rotate_c
  Signal quality: DEGRADED
  ✓ Pressure high enough for C rotation

── Step 3: C rotates into control ──
  Rotation event: <uuid>
  C active: True
  ✓ C rotation completed

── Step 4: Emergency constraint declared ──
  HALT entered: <uuid>
  Triggering node: node_B
  Diagnosing node: node_C
  Emergency constraint: <uuid>
  Provisional: True
  ✓ Emergency constraint declared (provisional)

── Step 5: Unsafe mutation denied ──
  Outcome: deny
  ✓ Mutation denied (halt active)

── Step 6: HOLD_FOR_RESOLUTION emitted ──
  Release verdict: HOLD_FOR_RESOLUTION
  ✓ HALT released with HOLD_FOR_RESOLUTION

========================================================================
  Demo scenario completed successfully!
========================================================================
```

The demo runs the full six-step scenario in sequence: clean commit under normal conditions, pressure accumulation, C rotation, emergency constraint declaration, mutation denial, and HOLD_FOR_RESOLUTION.

## Modules

| Module | Purpose |
|---|---|
| `x_layer.py` | X-layer: constrained interpretive packet generation (typed transit, not authority) |
| `admissibility_graph.py` | Upstream boundary: closed graph + 10 named admissibility rules |
| `pressure_monitor.py` | Pressure tracking: 5 sources, 3 signal quality axes, sentinel thresholds |
| `c_rotation.py` | C-sector rotation: pressure-activated defensive routing + multi-C arbitration |
| `mutation_boundary.py` | Downstream boundary: state mutation gate with append-only state objects |
| `constraint_declaration.py` | Constraint registry: declared constraints + emergency provisional declarations |
| `halt_hold_logic.py` | HALT/HOLD entry/exit, diagnostic timeout, release conditions, resume targeting |
| `corridor.py` | Full pipeline: wires all modules into the corridor |

## 10 Admissibility Rules (Upstream Boundary)

| # | Rule | What It Catches |
|---|---|---|
| 1 | `EVIDENCE_ANCHOR_REQUIRED` | Empty source span — no evidence backing |
| 2 | `ASSUMPTION_COUNT_BOUND` | Too many assumptions (default threshold: 3) |
| 3 | `AMBIGUITY_PRESERVATION_REQUIRED` | Collapsed ambiguity without documentation |
| 4 | `CONFIDENCE_CONSEQUENCE_MATCH` | LOW confidence + HIGH/CRITICAL consequence |
| 5 | `ACTOR_INTENT_ATTRIBUTION_BAN` | Mental state attribution without evidence |
| 6 | `SCOPE_DRIFT_FAIL` | Interpretation expands beyond source |
| 7 | `TEMPORAL_DRIFT_FAIL` | Temporal claims not in source signal |
| 8 | `PROHIBITED_INFERENTIAL_JUMP` | Correlation→causation, absence→denial, etc. |
| 9 | `PROVENANCE_REQUIRED` | Missing provenance chain |
| 10 | `OMITTED_ALTERNATIVE_DETECTION` | Multiple readings without documented alternatives |

## Three Adversarial Fixes (Built In)

These close escape routes identified during adversarial review:

1. **Diagnostic timeout** (§1): HALT cannot deadlock. If diagnosis does not complete within the timeout window, HALT escalates to HOLD_FOR_RESOLUTION.

2. **Emergency constraint declaration** (§4): Emergency HALT claims cannot bypass the constraint declaration surface. Any immediate-damage assertion must emit a provisional constraint valid only for the HALT duration, ratified during diagnostic review.

3. **Second-node review** (§8): When the diagnosing node is also the interrupt source, resume target classification requires review by a second node. Prevents adversarial resume target manipulation.

## Invariants

- No silent exit from HALT
- No infinite residence in HALT without escalation
- No indefinite HOLD without review
- No boundary enforcement without boundary declaration
- No state mutation without upstream admissibility
- No state mutation without downstream admissibility
- Weak signal alone does not justify HALT
- Resumption must target a declared stage
- No zombie continuation after closure
- No cosmetic laundering of logic (provenance lock)

## Running Tests

```bash
python -m pytest tests/ -v
```

261 tests. stdlib only. No external dependencies.

## Lineage

This repo subsumes and extends [interpretation-boundary-lab](https://github.com/LalaSkye/interpretation-boundary-lab). The upstream admissibility layer uses the same 10-rule system with closed graph topology. The downstream layer, pressure monitoring, C-sector rotation, HALT/HOLD logic, and constraint declaration are new — derived from the Engine Archive Completion Patch and its adversarial review.

## Part of the Execution Boundary Series

| Repo | Layer | What It Does |
|---|---|---|
| [interpretation-boundary-lab](https://github.com/LalaSkye/interpretation-boundary-lab) | Upstream boundary | 10-rule admissibility gate for interpretations |
| [dual-boundary-admissibility-lab](https://github.com/LalaSkye/dual-boundary-admissibility-lab) | Full corridor | Dual-boundary model with pressure monitoring and C-sector rotation |
| [execution-boundary-lab](https://github.com/LalaSkye/execution-boundary-lab) | Execution boundary | Demonstrates cascading failures without upstream governance |
| [stop-machine](https://github.com/LalaSkye/stop-machine) | Control primitive | Deterministic three-state stop controller |
| [constraint-workshop](https://github.com/LalaSkye/constraint-workshop) | Control primitives | Execution gate, invariant litmus, stop machine |
| [csgr-lab](https://github.com/LalaSkye/csgr-lab) | Measurement | Contracted stability and drift measurement |
| [invariant-lock](https://github.com/LalaSkye/invariant-lock) | Drift prevention | Refuse execution unless version increments |
| [policy-lint](https://github.com/LalaSkye/policy-lint) | Policy validation | Deterministic linter for governance statements |
| [deterministic-lexicon](https://github.com/LalaSkye/deterministic-lexicon) | Vocabulary | Fixed terms, exact matches, no inference |

## License

MIT

---

## Authorship & Rights

All architecture, methods, and system designs in this repository are the original work of **Ricky Dean Jones** unless otherwise stated.
No rights to use, reproduce, or implement are granted without explicit permission beyond the terms of the repository licence.

**Author:** Ricky Dean Jones
**Repository owner:** [LalaSkye](https://github.com/LalaSkye)
**Status:** Active research / architecture work
**Part of:** [Execution Boundary Series](https://github.com/LalaSkye) — TrinityOS / AlvianTech

---

This repository demonstrates deterministic control using standard engineering techniques. No proprietary frameworks or external implementations are used.

