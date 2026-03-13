"""HALT/HOLD entry, exit, diagnostic timeout, release, and resume.

Position in pipeline: FIFTH — activated when pressure assessment recommends halt/hold.

From Engine patch §1, §7, §8 and the three adversarial review fixes:

FIX 1 (§1): Diagnostic timeout prevents infinite HALT.
FIX 2 (§4): Emergency constraint declaration for immediate-damage claims.
FIX 3 (§8): Second-node review when diagnosing_node == interrupt source.

INVARIANTS:
- No silent exit from HALT
- No infinite residence in HALT without escalation (diagnostic timeout)
- No indefinite HOLD without review
- Resumption must target a declared stage
- No zombie continuation after closure
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mutation_boundary import StateObject


VALID_STAGES = {"A", "B", "C", "D", "terminate"}
VALID_CLOSURE_REASONS = {
    "integration_complete",
    "scope_withdrawn",
    "contradiction_confirmed",
    "operator_closure",
}


@dataclass(frozen=True)
class HaltEvent:
    """Record of HALT entry."""
    halt_event_id: str
    trigger_condition_id: str
    triggering_node: str
    diagnosing_node: str
    timestamp: str
    diagnostic_timeout: float  # seconds
    _entry_time: float = field(default_factory=time.monotonic, repr=False)


@dataclass(frozen=True)
class HaltRelease:
    """Record of HALT release."""
    halt_event_id: str
    trigger_condition_id: str
    diagnosing_node: str
    resolution_summary: str
    release_verdict: str  # "RELEASE" | "HOLD_FOR_RESOLUTION"
    release_timestamp: str


@dataclass(frozen=True)
class HoldEvent:
    """Record of HOLD entry."""
    hold_event_id: str
    insufficiency_reason: str
    requested_signal: str
    timestamp: str
    review_interval: float  # seconds
    _entry_time: float = field(default_factory=time.monotonic, repr=False)


@dataclass(frozen=True)
class HoldReviewEvent:
    """Record of a periodic HOLD review."""
    hold_event_id: str
    elapsed_duration: float
    signal_status: str
    recommendation: str  # "continue_hold" | "escalate" | "close"
    timestamp: str


@dataclass(frozen=True)
class ResumeEvent:
    """Record of a resumption after interrupt."""
    resume_event_id: str
    source_interrupt_id: str
    resume_target_stage: str
    justification: str
    second_node_review: bool
    reviewing_node: str
    timestamp: str


@dataclass(frozen=True)
class ClosureEvent:
    """Record of cycle closure."""
    closure_event_id: str
    cycle_id: str
    closure_reason: str
    open_questions_remaining: tuple[str, ...]
    final_state_summary: str
    timestamp: str


class HaltHoldController:
    """Manages HALT and HOLD lifecycle.

    Three adversarial review fixes built in:
    1. Diagnostic timeout prevents infinite HALT
    2. Emergency constraint declarations (via ConstraintRegistry)
    3. Second-node review when diagnosing_node == interrupt source
    """

    def __init__(self, default_diagnostic_timeout: float = 300.0, default_review_interval: float = 60.0) -> None:
        self._default_diagnostic_timeout = default_diagnostic_timeout
        self._default_review_interval = default_review_interval
        self._active_halts: dict[str, HaltEvent] = {}
        self._active_holds: dict[str, HoldEvent] = {}
        self._closed_cycles: set[str] = set()

    @property
    def active_halts(self) -> dict[str, HaltEvent]:
        return dict(self._active_halts)

    @property
    def active_holds(self) -> dict[str, HoldEvent]:
        return dict(self._active_holds)

    def enter_halt(
        self,
        trigger_condition_id: str,
        triggering_node: str,
        available_nodes: list[str],
        diagnostic_timeout: float | None = None,
    ) -> HaltEvent:
        """Enter HALT. Selects diagnosing_node != triggering_node if possible.

        FIX 1 (§1): diagnostic_timeout is REQUIRED — prevents infinite HALT.
        If no alternative node available, diagnosing_node == triggering_node
        but second_node_review will be required at resume.
        """
        if not trigger_condition_id:
            raise ValueError("trigger_condition_id required for HALT entry")
        if not triggering_node:
            raise ValueError("triggering_node required for HALT entry")

        timeout = diagnostic_timeout if diagnostic_timeout is not None else self._default_diagnostic_timeout

        # Select diagnosing node: prefer different from triggering
        diagnosing = triggering_node  # fallback
        for node in available_nodes:
            if node != triggering_node:
                diagnosing = node
                break

        event = HaltEvent(
            halt_event_id=str(uuid.uuid4()),
            trigger_condition_id=trigger_condition_id,
            triggering_node=triggering_node,
            diagnosing_node=diagnosing,
            timestamp=datetime.now(timezone.utc).isoformat(),
            diagnostic_timeout=timeout,
        )
        self._active_halts[event.halt_event_id] = event
        return event

    def check_diagnostic_timeout(self, halt_event: HaltEvent) -> bool:
        """Returns True if timeout exceeded. If True, escalate to HOLD_FOR_RESOLUTION.

        FIX 1: This prevents infinite residence in HALT.
        """
        elapsed = time.monotonic() - halt_event._entry_time
        return elapsed > halt_event.diagnostic_timeout

    def release_halt(
        self,
        halt_event_id: str,
        trigger_cleared: bool,
        diagnostic_record: str,
        release_verdict: str,
    ) -> HaltRelease:
        """Release HALT only if all three conditions satisfied:

        R1. trigger_condition no longer holds
        R2. diagnostic record exists
        R3. release verdict explicitly emitted

        Raises ValueError if any condition not met.
        """
        if halt_event_id not in self._active_halts:
            raise ValueError(f"No active HALT with id {halt_event_id}")

        halt = self._active_halts[halt_event_id]

        # R1: trigger must be cleared
        if not trigger_cleared:
            raise ValueError("Cannot release HALT: trigger_condition still holds (R1)")

        # R2: diagnostic record must exist
        if not diagnostic_record or not diagnostic_record.strip():
            raise ValueError("Cannot release HALT: no diagnostic record (R2)")

        # R3: release verdict must be explicit
        if release_verdict not in ("RELEASE", "HOLD_FOR_RESOLUTION"):
            raise ValueError(f"Invalid release_verdict: {release_verdict} (R3)")

        release = HaltRelease(
            halt_event_id=halt_event_id,
            trigger_condition_id=halt.trigger_condition_id,
            diagnosing_node=halt.diagnosing_node,
            resolution_summary=diagnostic_record,
            release_verdict=release_verdict,
            release_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        del self._active_halts[halt_event_id]
        return release

    def enter_hold(
        self,
        reason: str,
        requested_signal: str,
        review_interval: float | None = None,
    ) -> HoldEvent:
        """Enter HOLD for insufficient signal."""
        if not reason:
            raise ValueError("reason required for HOLD entry")

        interval = review_interval if review_interval is not None else self._default_review_interval

        event = HoldEvent(
            hold_event_id=str(uuid.uuid4()),
            insufficiency_reason=reason,
            requested_signal=requested_signal,
            timestamp=datetime.now(timezone.utc).isoformat(),
            review_interval=interval,
        )
        self._active_holds[event.hold_event_id] = event
        return event

    def review_hold(self, hold_event: HoldEvent, signal_status: str = "pending") -> HoldReviewEvent:
        """Periodic hold review to prevent silent drift.

        From adversarial review §7: holds must be reviewed, not left to drift.
        """
        elapsed = time.monotonic() - hold_event._entry_time

        if signal_status == "sufficient":
            recommendation = "close"
        elif elapsed > hold_event.review_interval * 3:
            recommendation = "escalate"
        else:
            recommendation = "continue_hold"

        return HoldReviewEvent(
            hold_event_id=hold_event.hold_event_id,
            elapsed_duration=elapsed,
            signal_status=signal_status,
            recommendation=recommendation,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def exit_hold(
        self,
        hold_event_id: str,
        exit_path: str,
        new_signal_reference: str = "",
    ) -> dict:
        """Exit HOLD by one of three paths:

        H1. signal_sufficient → resume
        H2. constraint_confirmed → escalate to HALT
        H3. scope_closed → terminate
        """
        if hold_event_id not in self._active_holds:
            raise ValueError(f"No active HOLD with id {hold_event_id}")

        valid_paths = {"signal_sufficient", "constraint_confirmed", "scope_closed"}
        if exit_path not in valid_paths:
            raise ValueError(f"Invalid exit_path: {exit_path} (must be one of {valid_paths})")

        hold = self._active_holds[hold_event_id]
        del self._active_holds[hold_event_id]

        if exit_path == "signal_sufficient":
            return {
                "action": "resume",
                "hold_event_id": hold_event_id,
                "new_signal_reference": new_signal_reference,
            }
        elif exit_path == "constraint_confirmed":
            return {
                "action": "escalate_to_halt",
                "hold_event_id": hold_event_id,
                "constraint_confirmed": True,
            }
        else:  # scope_closed
            return {
                "action": "terminate",
                "hold_event_id": hold_event_id,
            }

    def determine_resume_target(
        self,
        interrupt_event: dict,
        diagnostic_class: str,
        diagnosing_node: str,
        interrupt_source: str,
        available_nodes: list[str],
    ) -> ResumeEvent:
        """Resume target per Engine patch §8.

        Case A: local ambiguity → resume prior stage
        Case B: transformed claim invalidated → rewind to B
        Case C: initiating signal corrupted → rewind to A
        Case D: integration invalidated → resume at D
        Case E: whole cycle compromised → terminate

        FIX 3 (§8): If diagnosing_node == interrupt_source, requires second_node_review.
        """
        # Determine if second-node review is needed
        needs_second_review = (diagnosing_node == interrupt_source)
        reviewing_node = ""

        if needs_second_review:
            # Select a different node for review
            for node in available_nodes:
                if node != diagnosing_node:
                    reviewing_node = node
                    break
            if not reviewing_node:
                # No alternative node — cannot proceed without second review
                # Fail-closed: force HOLD_FOR_RESOLUTION
                return ResumeEvent(
                    resume_event_id=str(uuid.uuid4()),
                    source_interrupt_id=interrupt_event.get("interrupt_id", "unknown"),
                    resume_target_stage="terminate",
                    justification="No alternative node for second-node review; fail-closed to terminate",
                    second_node_review=True,
                    reviewing_node="",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

        # Map diagnostic_class to resume target
        resume_map = {
            "local_ambiguity": "A",      # Case A: resume prior stage
            "claim_invalidated": "B",     # Case B: rewind to B
            "signal_corrupted": "A",      # Case C: rewind to A
            "integration_invalidated": "D",  # Case D: resume at D
            "cycle_compromised": "terminate",  # Case E: terminate
        }

        target = resume_map.get(diagnostic_class, "terminate")  # Fail-closed

        return ResumeEvent(
            resume_event_id=str(uuid.uuid4()),
            source_interrupt_id=interrupt_event.get("interrupt_id", "unknown"),
            resume_target_stage=target,
            justification=f"Diagnostic class '{diagnostic_class}' → resume at {target}",
            second_node_review=needs_second_review,
            reviewing_node=reviewing_node,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def close_cycle(
        self,
        cycle_id: str,
        reason: str,
        state: StateObject,
        diagnostic_confirmation: bool = False,
    ) -> ClosureEvent:
        """Close a cycle.

        Valid reasons: integration_complete, scope_withdrawn, contradiction_confirmed, operator_closure
        C3 (contradiction_confirmed) requires diagnostic confirmation.
        No zombie continuation after closure.
        """
        if reason not in VALID_CLOSURE_REASONS:
            raise ValueError(f"Invalid closure_reason: {reason} (must be one of {VALID_CLOSURE_REASONS})")

        if reason == "contradiction_confirmed" and not diagnostic_confirmation:
            raise ValueError("contradiction_confirmed closure requires diagnostic_confirmation=True")

        if cycle_id in self._closed_cycles:
            raise ValueError(f"Cycle {cycle_id} already closed — no zombie continuation")

        remaining_questions = tuple(
            q.question_id for q in state.open_questions
        )

        self._closed_cycles.add(cycle_id)

        return ClosureEvent(
            closure_event_id=str(uuid.uuid4()),
            cycle_id=cycle_id,
            closure_reason=reason,
            open_questions_remaining=remaining_questions,
            final_state_summary=f"stage={state.current_stage}, mode={state.current_mode}, claims={len(state.active_claim_stack)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def is_cycle_closed(self, cycle_id: str) -> bool:
        return cycle_id in self._closed_cycles
