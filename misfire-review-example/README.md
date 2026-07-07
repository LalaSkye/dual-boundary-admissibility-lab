# Worked Misfire Review Receipt — Synthetic Example

**Status:** SYNTHETIC WORKED RECEIPT / NON-CANONICAL / NO RULE REVISION APPLIED  
**Purpose:** Show one bounded corridor from a candidate wrong gate decision to review classification, cause assignment, regression requirements, claim limit, and explicit stop.

This example does **not** establish a universal adjudicator, external authority, production correctness, or a self-modifying rule system. It demonstrates the shape of one inspectable misfire review object.

---

## 1. Receipt identity

| Field | Value |
|---|---|
| `review_receipt_id` | `MR-001-SYNTHETIC-SCOPE-FALSE-ALLOW` |
| `source_repo` | `LalaSkye/dual-boundary-admissibility-lab` |
| `baseline_ref` | `e0e1e953d29169e7b5f32d1dd14c694ab3b7cc28` |
| `decision_id` | `SYN-SCOPE-001` |
| `original_verdict` | `ALLOW / expected corridor outcome: commit` |
| `review_verdict` | `FALSE_ALLOW` |
| `cause_classification` | `RULE_DEFECT — lexical scope-expansion coverage gap` |
| `rule_under_review` | `SCOPE_DRIFT_FAIL` |
| `revision_status` | `PROPOSED ONLY — no rule change applied by this receipt` |

---

## 2. Source decision object

### Signal envelope

```text
source_id: sig-scope-001
timestamp: 2026-07-07T00:00:00Z
content: Node 7 reported packet loss.
content_type: text/plain
provenance_hash: synthetic-provenance-scope-001
```

### Interpretation presented to the corridor

```text
source_node: OBSERVE
target_node: INTERPRET_X
transition_kind: signal
claimed_object: The fleet is compromised.
claimed_intent: standard routing
source_span: Node 7 reported packet loss.
assumptions: []
ambiguity_markers: []
omitted_alternatives: []
confidence_class: MEDIUM
consequence_class: LOW
```

---

## 3. Original gate path

Under the baseline source identified above, this synthetic object is expected to pass the current deterministic checks because:

1. the declared graph edge `OBSERVE -> INTERPRET_X` permits `signal` transit;
2. the evidence anchor is non-empty;
3. assumption count is within threshold;
4. no ambiguity marker is declared;
5. confidence/consequence pairing is permitted;
6. no banned mental-state attribution is present;
7. `SCOPE_DRIFT_FAIL` checks the current marker set `all`, `every`, `always`, and `never`; the broader population term `fleet` is not covered by that lexical test;
8. no temporal drift marker is present;
9. no prohibited inferential-jump token is present;
10. provenance fields are present;
11. under the default normal corridor state, no downstream HOLD/HALT/open-question/signal-quality condition blocks mutation.

### Original decision summary

```text
UPSTREAM: expected admitted
DOWNSTREAM: expected allowed under default normal state
CORRIDOR: expected commit
```

**Evidence basis for this worked review:** code inspection of `x_layer.py`, `admissibility_graph.py`, `corridor.py`, and `mutation_boundary.py` at the named baseline ref.

**Important:** this first receipt records a worked code-path review, not an attached runtime execution trace. A future executable regression fixture would be a separate object and separate claim.

---

## 4. Adjudication object

| Field | Value |
|---|---|
| `adjudicator_role` | `LAB_MISFIRE_REVIEWER` |
| `authority_basis` | Repo-local synthetic review role, bounded to classifying this example under the named standard only. No external or third-party authority claimed. |
| `standard_id` | `SCOPE_ANCHOR_REVIEW_STANDARD_v0.1-SYNTHETIC` |
| `standard_rule` | A claimed object that expands from one explicitly evidenced instance to a broader population class must either carry evidence anchoring that broader population or remain scoped to the evidenced instance. |
| `review_scope` | Decision `SYN-SCOPE-001`, rule `SCOPE_DRIFT_FAIL`, baseline ref named above. |
| `evidence_set` | The synthetic signal/interpretation in this receipt plus the four named source files at the baseline ref. |
| `evidence_cutoff` | Baseline ref `e0e1e953d29169e7b5f32d1dd14c694ab3b7cc28`. Later code or evidence is outside this receipt. |

### Review finding

Under the named synthetic standard, the original expected ALLOW/commit is classified as:

```text
FALSE_ALLOW
```

### Reason

The source evidence is bounded to one named node. The claimed object expands to a fleet-level condition. The current scope-drift rule does not detect that expansion because its implementation checks a narrow lexical marker set rather than the evidenced population boundary itself.

This receipt therefore classifies the candidate misfire as:

```text
RULE_DEFECT
not IMPLEMENTATION_BUG
not STALE_STATE
not AUTHORITY_ERROR
not MISSING_PROVENANCE
not WORLD_CHANGED_AFTER_DECISION
```

The classification is bounded to this example and this named standard.

---

## 5. Revision proposal

**No rule change is made by this receipt.**

Candidate revision objective:

> Detect population or scope expansion relative to the source evidence without converting every broader noun into an automatic denial.

Any proposed rule change must arrive as a separate reviewable change with its own tests and claim boundary.

---

## 6. Required regression before any revision can be promoted

A candidate revision must demonstrate at least:

1. **Misfire case closes:**
   - source: `Node 7 reported packet loss.`
   - claim: `The fleet is compromised.`
   - expected: upstream `DENY` or `HOLD`, no commit.

2. **Bounded claim remains playable:**
   - source: `Node 7 reported packet loss.`
   - claim: `Node 7 reported packet loss.`
   - expected: this scope relation alone does not cause denial.

3. **Population evidence can support population claim:**
   - source evidence explicitly establishes the relevant fleet-level population condition;
   - a matching fleet-level claim is not rejected merely for being fleet-level.

4. **No silent regression:**
   - existing tests remain passing;
   - any changed expectation is named and reviewed rather than hidden inside a broad rule rewrite.

5. **Claim limit preserved:**
   - passing these regressions would prove only the tested behaviour of the revised rule on the named fixtures.

---

## 7. Review stop

This review stops at the following bounded claim:

> At baseline ref `e0e1e953d29169e7b5f32d1dd14c694ab3b7cc28`, code-path inspection shows a synthetic packet whose one-node evidence can be carried into a fleet-level claim without the current lexical scope-drift rule detecting that expansion. Under `SCOPE_ANCHOR_REVIEW_STANDARD_v0.1-SYNTHETIC`, the expected ALLOW/commit is classified as a `FALSE_ALLOW` caused by a bounded rule-coverage defect.

This receipt does **not** prove:

- universal wrongness of the gate;
- completeness of the review evidence;
- that every population-level claim is inadmissible;
- that the proposed revision objective is sufficient;
- that the reviewer cannot be wrong;
- production safety;
- deployment coverage;
- path-universal enforcement;
- external validation;
- future correctness after code changes.

Further challenge, rule revision, implementation, or promotion requires a **new review object**.

---

## 8. Receipt claim limit

```text
FINAL FOR THIS CORRIDOR
!=
TRUE FOR ALL CORRIDORS
```

This receipt establishes only a bounded synthetic review classification under the named baseline ref, evidence set, reviewer role, standard, scope, and stop condition.

**STOP:** Review closed at classification + regression requirements. No rule mutation performed.