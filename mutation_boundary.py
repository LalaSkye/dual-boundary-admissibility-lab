"""Downstream state mutation admissibility gate.

Position in pipeline: SIXTH — after routing decision, before commit.
No state mutation occurs unless BOTH boundaries pass.

... → route decision → [MUTATION_BOUNDARY] → commit | deny

State rules from Engine patch §3:
- State object is append-updated, not silently overwritten
- Each state transition emits new state_id
- Trace references state_id
- State contains only operational facts, not interpretive narrative
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from x_layer import XPacket
from pressure_monitor import SignalQuality
from admissibility_graph import AdmissibilityResult


@dataclass(frozen=True)
class OpenQuestion:
    """A typed open question — not free text."""
    question_id: str
    question_text: str
    blocking: bool


@dataclass(frozen=True)
class StateObject:
    """System state — frozen, immutable. From Engine patch §3.

    State contains only operational facts, not interpretive narrative.
    Each transition creates a new StateObject with a new state_id.
    """
    state_id: str
    active_cycle_id: str
    role_occupancy_map: dict
    current_stage: str  # "A" | "B" | "C" | "D"
    active_claim_stack: tuple[str, ...] = field(default_factory=tuple)
    open_questions: tuple[OpenQuestion, ...] = field(default_factory=tuple)
    active_constraints: tuple[str, ...] = field(default_factory=tuple)
    current_mode: str = "normal"  # "normal" | "defensive" | "halt" | "hold"
    current_signal_quality: SignalQuality = SignalQuality.GOOD
    halt_status: str = "none"  # "none" | "active" | "releasing"
    hold_status: str = "none"  # "none" | "active" | "releasing"
    predecessor_state_id: str = ""


@dataclass(frozen=True)
class MutationResult:
    """Result of a mutation attempt."""
    allowed: bool
    new_state: StateObject | None
    denial_reason: str


class MutationBoundary:
    """Downstream state mutation admissibility gate.

    No state mutation occurs unless BOTH:
    1. The interpretive packet was admissible upstream
    2. The current state remains admissible downstream

    Fail-closed: any doubt → deny.
    """

    def attempt_mutation(
        self,
        current_state: StateObject,
        proposed_transition: XPacket,
        upstream_result: AdmissibilityResult,
    ) -> MutationResult:
        """Check downstream admissibility. State is append-updated, not silently overwritten.

        Checks:
        1. Upstream admissibility must have passed
        2. No blocking open questions
        3. HALT/HOLD status permits mutation
        4. Signal quality is sufficient
        5. Mode is compatible with transition
        """
        # ── Check 1: Upstream must be admitted ──
        if not upstream_result.admitted:
            reasons = []
            if upstream_result.graph_failure:
                reasons.append(f"graph: {upstream_result.graph_failure}")
            for rf in upstream_result.rule_failures:
                reasons.append(f"rule {rf.rule}: {rf.reason}")
            for cf in upstream_result.constraint_failures:
                reasons.append(f"constraint: {cf}")
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason=f"upstream_inadmissible: {'; '.join(reasons)}",
            )

        # ── Check 2: No blocking open questions ──
        blocking = [q for q in current_state.open_questions if q.blocking]
        if blocking:
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason=f"blocking_open_questions: {[q.question_id for q in blocking]}",
            )

        # ── Check 3: HALT/HOLD status ──
        if current_state.halt_status == "active":
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason="halt_active: no mutations during active HALT",
            )
        if current_state.hold_status == "active":
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason="hold_active: no mutations during active HOLD",
            )

        # ── Check 4: Signal quality ──
        if current_state.current_signal_quality == SignalQuality.INSUFFICIENT:
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason="signal_insufficient: cannot mutate with insufficient signal quality",
            )

        # ── Check 5: Mode compatibility ──
        if current_state.current_mode == "halt":
            return MutationResult(
                allowed=False,
                new_state=None,
                denial_reason="mode_halt: system in halt mode",
            )

        # ── All checks passed — create new state ──
        new_state = StateObject(
            state_id=str(uuid.uuid4()),
            active_cycle_id=current_state.active_cycle_id,
            role_occupancy_map=current_state.role_occupancy_map,
            current_stage=current_state.current_stage,
            active_claim_stack=current_state.active_claim_stack + (proposed_transition.claimed_object,),
            open_questions=current_state.open_questions,
            active_constraints=current_state.active_constraints,
            current_mode=current_state.current_mode,
            current_signal_quality=current_state.current_signal_quality,
            halt_status=current_state.halt_status,
            hold_status=current_state.hold_status,
            predecessor_state_id=current_state.state_id,
        )

        return MutationResult(
            allowed=True,
            new_state=new_state,
            denial_reason="",
        )
