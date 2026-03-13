"""Tests for halt_hold_logic.py — HALT/HOLD lifecycle management."""
from __future__ import annotations

import time
import pytest

from pressure_monitor import SignalQuality
from mutation_boundary import StateObject, OpenQuestion
from halt_hold_logic import (
    HaltHoldController,
    HaltEvent,
    HaltRelease,
    HoldEvent,
    HoldReviewEvent,
    ResumeEvent,
    ClosureEvent,
    VALID_STAGES,
    VALID_CLOSURE_REASONS,
)


def _make_state(**overrides) -> StateObject:
    defaults = {
        "state_id": "state-001",
        "active_cycle_id": "cycle-001",
        "role_occupancy_map": {"A": "OBSERVE"},
        "current_stage": "B",
    }
    defaults.update(overrides)
    return StateObject(**defaults)


class TestHaltEntry:
    def test_basic_halt_entry(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B", "node_C"])

        assert isinstance(event, HaltEvent)
        assert event.trigger_condition_id == "c-001"
        assert event.triggering_node == "node_A"
        assert event.diagnostic_timeout > 0

    def test_diagnosing_node_different_from_triggering(self):
        """FIX 1 (§1): diagnosing_node != triggering_node when possible."""
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B", "node_C"])
        assert event.diagnosing_node != event.triggering_node
        assert event.diagnosing_node == "node_B"

    def test_diagnosing_node_fallback_when_no_alternative(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A"])
        assert event.diagnosing_node == "node_A"  # no alternative

    def test_diagnosing_node_empty_list(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", [])
        assert event.diagnosing_node == "node_A"  # fallback

    def test_halt_requires_trigger_condition(self):
        ctrl = HaltHoldController()
        with pytest.raises(ValueError, match="trigger_condition_id"):
            ctrl.enter_halt("", "node_A", ["node_A"])

    def test_halt_requires_triggering_node(self):
        ctrl = HaltHoldController()
        with pytest.raises(ValueError, match="triggering_node"):
            ctrl.enter_halt("c-001", "", ["node_A"])

    def test_halt_tracked_as_active(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        assert event.halt_event_id in ctrl.active_halts

    def test_custom_diagnostic_timeout(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"], diagnostic_timeout=10.0)
        assert event.diagnostic_timeout == 10.0


class TestDiagnosticTimeout:
    """FIX 1: Diagnostic timeout prevents infinite HALT."""

    def test_no_timeout_immediately(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"], diagnostic_timeout=100.0)
        assert ctrl.check_diagnostic_timeout(event) is False

    def test_timeout_exceeded(self):
        ctrl = HaltHoldController(default_diagnostic_timeout=0.01)
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"], diagnostic_timeout=0.01)
        time.sleep(0.02)
        assert ctrl.check_diagnostic_timeout(event) is True


class TestHaltRelease:
    def test_release_all_conditions_met(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        release = ctrl.release_halt(
            event.halt_event_id,
            trigger_cleared=True,
            diagnostic_record="Anomaly investigated and resolved",
            release_verdict="RELEASE",
        )

        assert isinstance(release, HaltRelease)
        assert release.release_verdict == "RELEASE"
        assert event.halt_event_id not in ctrl.active_halts

    def test_release_hold_for_resolution(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        release = ctrl.release_halt(
            event.halt_event_id,
            trigger_cleared=True,
            diagnostic_record="Partially resolved",
            release_verdict="HOLD_FOR_RESOLUTION",
        )
        assert release.release_verdict == "HOLD_FOR_RESOLUTION"

    def test_release_fails_trigger_not_cleared(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R1"):
            ctrl.release_halt(event.halt_event_id, False, "record", "RELEASE")

    def test_release_fails_no_diagnostic_record(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R2"):
            ctrl.release_halt(event.halt_event_id, True, "", "RELEASE")

    def test_release_fails_invalid_verdict(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R3"):
            ctrl.release_halt(event.halt_event_id, True, "record", "INVALID")

    def test_release_unknown_halt_raises(self):
        ctrl = HaltHoldController()
        with pytest.raises(ValueError, match="No active HALT"):
            ctrl.release_halt("nonexistent", True, "record", "RELEASE")


class TestHoldEntry:
    def test_basic_hold_entry(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("degraded signal", "improved_signal_quality")

        assert isinstance(event, HoldEvent)
        assert event.insufficiency_reason == "degraded signal"
        assert event.requested_signal == "improved_signal_quality"

    def test_hold_requires_reason(self):
        ctrl = HaltHoldController()
        with pytest.raises(ValueError, match="reason"):
            ctrl.enter_hold("", "signal")

    def test_hold_tracked_as_active(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        assert event.hold_event_id in ctrl.active_holds

    def test_custom_review_interval(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal", review_interval=30.0)
        assert event.review_interval == 30.0


class TestHoldReview:
    def test_continue_hold(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        review = ctrl.review_hold(event)
        assert review.recommendation == "continue_hold"

    def test_close_on_sufficient_signal(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        review = ctrl.review_hold(event, signal_status="sufficient")
        assert review.recommendation == "close"


class TestHoldExit:
    def test_exit_signal_sufficient(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        result = ctrl.exit_hold(event.hold_event_id, "signal_sufficient", "new_signal_ref")
        assert result["action"] == "resume"
        assert event.hold_event_id not in ctrl.active_holds

    def test_exit_constraint_confirmed(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        result = ctrl.exit_hold(event.hold_event_id, "constraint_confirmed")
        assert result["action"] == "escalate_to_halt"

    def test_exit_scope_closed(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        result = ctrl.exit_hold(event.hold_event_id, "scope_closed")
        assert result["action"] == "terminate"

    def test_exit_invalid_path_raises(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        with pytest.raises(ValueError, match="Invalid exit_path"):
            ctrl.exit_hold(event.hold_event_id, "invalid_path")

    def test_exit_unknown_hold_raises(self):
        ctrl = HaltHoldController()
        with pytest.raises(ValueError, match="No active HOLD"):
            ctrl.exit_hold("nonexistent", "signal_sufficient")


class TestResumeTarget:
    """Engine patch §8: resume target determination."""

    def test_local_ambiguity_resumes_A(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_B",
            "node_A",
            ["node_A", "node_B", "node_C"],
        )
        assert event.resume_target_stage == "A"
        assert event.second_node_review is False

    def test_claim_invalidated_rewinds_B(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "claim_invalidated",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "B"

    def test_signal_corrupted_rewinds_A(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "signal_corrupted",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "A"

    def test_integration_invalidated_resumes_D(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "integration_invalidated",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "D"

    def test_cycle_compromised_terminates(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "cycle_compromised",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "terminate"

    def test_unknown_class_fails_closed_to_terminate(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "unknown_class",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "terminate"


class TestSecondNodeReview:
    """FIX 3 (§8): Second-node review when diagnosing_node == interrupt source."""

    def test_second_node_review_required(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_A",
            "node_A",  # same as diagnosing
            ["node_A", "node_B", "node_C"],
        )
        assert event.second_node_review is True
        assert event.reviewing_node == "node_B"

    def test_second_node_review_not_needed(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_B",
            "node_A",
            ["node_A", "node_B", "node_C"],
        )
        assert event.second_node_review is False
        assert event.reviewing_node == ""

    def test_second_node_review_no_alternative_terminates(self):
        """Fail-closed: if no alternative node, cannot proceed."""
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_A",
            "node_A",
            ["node_A"],  # only one node
        )
        assert event.second_node_review is True
        assert event.resume_target_stage == "terminate"


class TestCycleClosure:
    def test_integration_complete(self):
        ctrl = HaltHoldController()
        state = _make_state()
        event = ctrl.close_cycle("cycle-001", "integration_complete", state)
        assert isinstance(event, ClosureEvent)
        assert event.closure_reason == "integration_complete"

    def test_scope_withdrawn(self):
        ctrl = HaltHoldController()
        state = _make_state()
        event = ctrl.close_cycle("cycle-001", "scope_withdrawn", state)
        assert event.closure_reason == "scope_withdrawn"

    def test_contradiction_requires_diagnostic(self):
        ctrl = HaltHoldController()
        state = _make_state()
        with pytest.raises(ValueError, match="diagnostic_confirmation"):
            ctrl.close_cycle("cycle-001", "contradiction_confirmed", state)

    def test_contradiction_with_diagnostic(self):
        ctrl = HaltHoldController()
        state = _make_state()
        event = ctrl.close_cycle("cycle-001", "contradiction_confirmed", state, diagnostic_confirmation=True)
        assert event.closure_reason == "contradiction_confirmed"

    def test_invalid_reason_raises(self):
        ctrl = HaltHoldController()
        state = _make_state()
        with pytest.raises(ValueError, match="Invalid closure_reason"):
            ctrl.close_cycle("cycle-001", "invalid_reason", state)

    def test_no_zombie_continuation(self):
        """No zombie continuation after closure."""
        ctrl = HaltHoldController()
        state = _make_state()
        ctrl.close_cycle("cycle-001", "integration_complete", state)
        with pytest.raises(ValueError, match="already closed"):
            ctrl.close_cycle("cycle-001", "integration_complete", state)

    def test_is_cycle_closed(self):
        ctrl = HaltHoldController()
        state = _make_state()
        assert ctrl.is_cycle_closed("cycle-001") is False
        ctrl.close_cycle("cycle-001", "integration_complete", state)
        assert ctrl.is_cycle_closed("cycle-001") is True

    def test_closure_captures_open_questions(self):
        ctrl = HaltHoldController()
        state = _make_state(
            open_questions=(
                OpenQuestion("q-001", "Unresolved", blocking=False),
                OpenQuestion("q-002", "Also unresolved", blocking=True),
            ),
        )
        event = ctrl.close_cycle("cycle-001", "operator_closure", state)
        assert "q-001" in event.open_questions_remaining
        assert "q-002" in event.open_questions_remaining


class TestHaltEventFrozen:
    def test_halt_event_frozen(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(AttributeError):
            event.triggering_node = "modified"

    def test_hold_event_frozen(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("reason", "signal")
        with pytest.raises(AttributeError):
            event.insufficiency_reason = "modified"

    def test_resume_event_frozen(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        with pytest.raises(AttributeError):
            event.resume_target_stage = "modified"
