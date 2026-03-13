# dual-boundary-admissibility-lab

Admissibility Rotation Corridor — a closed constitutional runtime with visible interrupt geometry.

## What This Is

A deterministic control system that constrains **both** what may count as a valid transition candidate **and** what state mutations may occur under live pressure.

This repo integrates two boundary layers into a single continuous mechanism:

- **Upstream boundary**: eliminates interpretation drift before any transition candidate exists
- **Downstream boundary**: enforces state admissibility before any mutation occurs

Between them: pressure monitoring, C-sector rotation, and HALT/HOLD logic with three adversarial fixes built in from day one.

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

### The Two-Boundary Model

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

Where:
- **A** = signal initiation
- **B** = exploration / transformation
- **D** = integration / stabilisation
- **C** = interrupt vector

And additionally:
- HOLD for insufficiency
- HALT for violation
- RELEASE only by explicit verdict
- ROTATION only by declared trigger
- CONSTRAINTS must be named
- PROVENANCE must persist through wrapping
- STATE must be reconstructable
- CLOSURE must be explicit

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
| `corridor.py` | The full pipeline: wires everything together |

## Three Adversarial Fixes (Built In)

These fixes close escape routes identified by adversarial review:

1. **Diagnostic timeout** (§1): HALT cannot deadlock. If diagnosis doesn't complete within the timeout window, HALT escalates to HOLD_FOR_RESOLUTION.

2. **Emergency constraint declaration** (§4): Emergency HALT claims cannot bypass the constraint declaration surface. Any immediate-damage assertion MUST emit a provisional constraint that is valid only for the HALT duration and must be ratified during diagnostic review.

3. **Second-node review** (§8): When the diagnosing node is also the interrupt source, resume target classification requires review by a second node. Prevents adversarial resume target manipulation.

## 10 Admissibility Rules (Upstream)

| # | Rule | What It Catches |
|---|---|---|
| 1 | EVIDENCE_ANCHOR_REQUIRED | Empty source span — no evidence backing |
| 2 | ASSUMPTION_COUNT_BOUND | Too many assumptions (default threshold: 3) |
| 3 | AMBIGUITY_PRESERVATION_REQUIRED | Collapsed ambiguity without documentation |
| 4 | CONFIDENCE_CONSEQUENCE_MATCH | LOW confidence + HIGH/CRITICAL consequence |
| 5 | ACTOR_INTENT_ATTRIBUTION_BAN | Mental state attribution without evidence |
| 6 | SCOPE_DRIFT_FAIL | Interpretation expands beyond source |
| 7 | TEMPORAL_DRIFT_FAIL | Temporal claims not in source signal |
| 8 | PROHIBITED_INFERENTIAL_JUMP | Correlation→causation, absence→denial, etc. |
| 9 | PROVENANCE_REQUIRED | Missing provenance chain |
| 10 | OMITTED_ALTERNATIVE_DETECTION | Multiple readings without documented alternatives |

## Running Tests

```bash
python -m pytest tests/ -v
```

261 tests. stdlib only. No external dependencies.

## Demo Scenario

```bash
python examples/demo_scenario.py
```

Runs the full six-step scenario:
1. Admissible packet enters → committed
2. Pressure rises (degraded signal + denials)
3. C rotates into control
4. Provisional emergency constraint declared
5. Unsafe mutation denied
6. HOLD_FOR_RESOLUTION emitted

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

## Lineage

This repo subsumes and extends [interpretation-boundary-lab](https://github.com/LalaSkye/interpretation-boundary-lab). The upstream admissibility layer is the same 10-rule system with closed graph topology. The downstream layer, pressure monitoring, C-sector rotation, HALT/HOLD logic, and constraint declaration are new — derived from the Engine Archive Completion Patch and its adversarial review.

## License

MIT
