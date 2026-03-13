"""Tests for mutation_boundary.py — downstream state mutation gate."""
from __future__ import annotations

import pytest

from x_layer import XPacket, ConfidenceClass, ConsequenceClass
from admissibility_graph import AdmissibilityResult, RuleFailure
from pressure_monitor import SignalQuality
from mutation_boundary import (
    MutationBoundary,
    MutationResult,
    StateObject,
    OpenQuestion,
)


def _make_packet(**overrides) -> XPacket:
    defaults = {
        "packet_id": "pkt-001",
        "signal_id": "sig-001",
        "source_node": "OBSERVE",
        "target_node": "INTERPRET_X",
        "transition_kind": "signal",
        "claimed_object": "test claim",
        "claimed_intent": "test intent",
        "source_span": "test evidence",
        "provenance_hash": "hash123",
        "timestamp": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return XPacket(**defaults)


def _make_state(**overrides) -> StateObject:
    defaults = {
        "state_id": "state-001",
        "active_cycle_id": "cycle-001",
        "role_occupancy_map": {"A": "OBSERVE", "B": "INTERPRET", "C": "CONSTRAINT", "D": "ROUTE"},
        "current_stage": "B",
        "active_claim_stack": (),
        "open_questions": (),
        "active_constraints": (),
        "current_mode": "normal",
        "current_signal_quality": SignalQuality.GOOD,
        "halt_status": "none",
        "hold_status": "none",
        "predecessor_state_id": "",
    }
    defaults.update(overrides)
    return StateObject(**defaults)


def _make_admitted_result(packet_id: str = "pkt-001") -> AdmissibilityResult:
    return AdmissibilityResult(admitted=True, packet_id=packet_id)


def _make_denied_result(packet_id: str = "pkt-001") -> AdmissibilityResult:
    return AdmissibilityResult(
        admitted=False,
        packet_id=packet_id,
        rule_failures=(RuleFailure(rule="TEST_RULE", reason="test failure"),),
    )


class TestMutationBoundaryHappyPath:
    def test_allowed_mutation(self):
        boundary = MutationBoundary()
        state = _make_state()
        packet = _make_packet()
        result = boundary.attempt_mutation(state, packet, _make_admitted_result())

        assert result.allowed is True
        assert result.new_state is not None
        assert result.denial_reason == ""

    def test_new_state_has_new_id(self):
        boundary = MutationBoundary()
        state = _make_state()
        packet = _make_packet()
        result = boundary.attempt_mutation(state, packet, _make_admitted_result())

        assert result.new_state.state_id != state.state_id

    def test_new_state_links_predecessor(self):
        boundary = MutationBoundary()
        state = _make_state()
        packet = _make_packet()
        result = boundary.attempt_mutation(state, packet, _make_admitted_result())

        assert result.new_state.predecessor_state_id == state.state_id

    def test_claim_appended_to_stack(self):
        boundary = MutationBoundary()
        state = _make_state(active_claim_stack=("existing_claim",))
        packet = _make_packet(claimed_object="new_claim")
        result = boundary.attempt_mutation(state, packet, _make_admitted_result())

        assert "existing_claim" in result.new_state.active_claim_stack
        assert "new_claim" in result.new_state.active_claim_stack


class TestMutationBoundaryDenials:
    def test_upstream_inadmissible(self):
        boundary = MutationBoundary()
        state = _make_state()
        packet = _make_packet()
        result = boundary.attempt_mutation(state, packet, _make_denied_result())

        assert result.allowed is False
        assert "upstream_inadmissible" in result.denial_reason

    def test_blocking_open_questions(self):
        boundary = MutationBoundary()
        state = _make_state(
            open_questions=(
                OpenQuestion("q-001", "Unresolved issue", blocking=True),
            ),
        )
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())

        assert result.allowed is False
        assert "blocking_open_questions" in result.denial_reason

    def test_non_blocking_questions_allowed(self):
        boundary = MutationBoundary()
        state = _make_state(
            open_questions=(
                OpenQuestion("q-001", "Minor question", blocking=False),
            ),
        )
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())
        assert result.allowed is True

    def test_halt_active_denies(self):
        boundary = MutationBoundary()
        state = _make_state(halt_status="active")
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())

        assert result.allowed is False
        assert "halt_active" in result.denial_reason

    def test_hold_active_denies(self):
        boundary = MutationBoundary()
        state = _make_state(hold_status="active")
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())

        assert result.allowed is False
        assert "hold_active" in result.denial_reason

    def test_insufficient_signal_denies(self):
        boundary = MutationBoundary()
        state = _make_state(current_signal_quality=SignalQuality.INSUFFICIENT)
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())

        assert result.allowed is False
        assert "signal_insufficient" in result.denial_reason

    def test_halt_mode_denies(self):
        boundary = MutationBoundary()
        state = _make_state(current_mode="halt")
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())

        assert result.allowed is False
        assert "mode_halt" in result.denial_reason

    def test_degraded_signal_allowed(self):
        """DEGRADED signal does NOT block mutation (only INSUFFICIENT does)."""
        boundary = MutationBoundary()
        state = _make_state(current_signal_quality=SignalQuality.DEGRADED)
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())
        assert result.allowed is True


class TestStateObjectFrozen:
    def test_state_is_frozen(self):
        state = _make_state()
        with pytest.raises(AttributeError):
            state.state_id = "modified"

    def test_mutation_result_frozen(self):
        result = MutationResult(allowed=True, new_state=None, denial_reason="")
        with pytest.raises(AttributeError):
            result.allowed = False

    def test_open_question_frozen(self):
        q = OpenQuestion("q-001", "test", blocking=True)
        with pytest.raises(AttributeError):
            q.blocking = False


class TestMutationBoundaryInvariants:
    def test_denied_mutation_has_no_new_state(self):
        boundary = MutationBoundary()
        state = _make_state(halt_status="active")
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())
        assert result.new_state is None

    def test_allowed_mutation_preserves_cycle_id(self):
        boundary = MutationBoundary()
        state = _make_state(active_cycle_id="cycle-XYZ")
        result = boundary.attempt_mutation(state, _make_packet(), _make_admitted_result())
        assert result.new_state.active_cycle_id == "cycle-XYZ"

    def test_upstream_denial_includes_details(self):
        boundary = MutationBoundary()
        state = _make_state()
        upstream = AdmissibilityResult(
            admitted=False,
            packet_id="pkt-001",
            graph_failure="No declared edge",
            rule_failures=(RuleFailure("R1", "fail1"), RuleFailure("R2", "fail2")),
            constraint_failures=("c-001",),
        )
        result = boundary.attempt_mutation(state, _make_packet(), upstream)
        assert "graph" in result.denial_reason
        assert "R1" in result.denial_reason
        assert "c-001" in result.denial_reason
