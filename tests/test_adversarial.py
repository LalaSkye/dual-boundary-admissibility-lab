"""Adversarial scenario tests — from the adversarial review.

Tests the three built-in fixes and additional adversarial attack vectors.
"""
from __future__ import annotations

import time
import uuid
import pytest

from x_layer import XLayer, XPacket, SignalEnvelope, ConfidenceClass, ConsequenceClass
from admissibility_graph import (
    AdmissibilityBoundary,
    AdmissibilityResult,
    ClosedAdmissibilityGraph,
    evaluate_rules,
)
from pressure_monitor import PressureMonitor, PressureSource, SignalQuality
from c_rotation import CRotationEngine, CAssertion
from mutation_boundary import MutationBoundary, MutationResult, StateObject, OpenQuestion
from constraint_declaration import Constraint, ConstraintRegistry, SeverityClass
from halt_hold_logic import HaltHoldController, HaltEvent
from corridor import AdmissibilityRotationCorridor, CorridorResult


def _make_signal(**overrides) -> SignalEnvelope:
    defaults = {
        "source_id": "sig-001",
        "timestamp": "2025-01-01T00:00:00Z",
        "content": "The system observed normal behavior",
        "content_type": "text/plain",
        "provenance_hash": "abc123hash",
    }
    defaults.update(overrides)
    return SignalEnvelope(**defaults)


def _make_interpretation(**overrides) -> dict:
    defaults = {
        "source_node": "OBSERVE",
        "target_node": "INTERPRET_X",
        "transition_kind": "signal",
        "claimed_object": "normal behavior",
        "claimed_intent": "standard routing",
        "source_span": "The system observed normal behavior",
    }
    defaults.update(overrides)
    return defaults


def _make_packet(**overrides) -> XPacket:
    defaults = {
        "packet_id": "pkt-001",
        "signal_id": "sig-001",
        "source_node": "OBSERVE",
        "target_node": "INTERPRET_X",
        "transition_kind": "signal",
        "claimed_object": "normal behavior",
        "claimed_intent": "standard routing",
        "source_span": "The system observed normal behavior",
        "provenance_hash": "abc123hash",
        "timestamp": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return XPacket(**defaults)


class TestAdversarial1SelfDiagnosingNode:
    """§1 attack: Self-diagnosing node — diagnosing_node should not be triggering_node."""

    def test_diagnosing_node_differs_from_triggering(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B", "node_C"])
        assert event.diagnosing_node != event.triggering_node

    def test_all_three_nodes_available(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_B", ["node_A", "node_B", "node_C"])
        assert event.diagnosing_node != "node_B"

    def test_single_node_fallback(self):
        """When only triggering node available, it must self-diagnose but second-node review enforced at resume."""
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A"])
        assert event.diagnosing_node == "node_A"

        # But resume with same node requires second-node review
        resume = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_A",  # diagnosing
            "node_A",  # interrupt source
            ["node_A"],  # only one node
        )
        assert resume.second_node_review is True
        assert resume.resume_target_stage == "terminate"  # fail-closed

    def test_diagnostic_timeout_prevents_infinite_halt(self):
        """FIX 1: diagnostic timeout prevents infinite HALT."""
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"], diagnostic_timeout=0.01)
        time.sleep(0.02)
        assert ctrl.check_diagnostic_timeout(event) is True


class TestAdversarial2UndeclaredConstraint:
    """§4 attack: Undeclared constraint escalation — emergency must produce provisional constraint."""

    def test_emergency_produces_provisional(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("damage_detected", "node_C", "halt-001")
        assert c.provisional is True
        assert c.constraint_id.startswith("EMERGENCY-")

    def test_emergency_has_halt_scope(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("damage_detected", "node_C", "halt-001")
        assert c.provisional_expiry == "halt-001"

    def test_no_enforcement_without_declaration(self):
        """INVARIANT: No boundary enforcement without boundary declaration."""
        reg = ConstraintRegistry()
        # Cannot have enforcement without a constraint_id
        assert reg.get("nonexistent") is None
        assert len(reg.get_all_active()) == 0

    def test_emergency_without_trigger_test_rejected(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="trigger_test"):
            reg.declare_emergency("", "node_C", "halt-001")

    def test_emergency_without_halt_id_rejected(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="halt_event_id"):
            reg.declare_emergency("trigger", "node_C", "")

    def test_provisional_must_be_ratified_or_rejected(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")

        # Can ratify
        reg.ratify_provisional(c.constraint_id)
        ratified = reg.get(c.constraint_id)
        assert ratified.provisional is False

    def test_provisional_rejection(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")
        reg.reject_provisional(c.constraint_id)
        assert reg.get(c.constraint_id) is None

    def test_provisional_expiry_on_halt_end(self):
        reg = ConstraintRegistry()
        c1 = reg.declare_emergency("t1", "node_A", "halt-001")
        c2 = reg.declare_emergency("t2", "node_B", "halt-001")
        expired = reg.expire_for_halt("halt-001")
        assert len(expired) == 2


class TestAdversarial3ResumeTargetManipulation:
    """§8 attack: Resume target manipulation — second-node review required."""

    def test_second_node_review_enforced(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "claim_invalidated",
            "node_A",  # diagnosing_node
            "node_A",  # interrupt_source (same!)
            ["node_A", "node_B", "node_C"],
        )
        assert event.second_node_review is True
        assert event.reviewing_node != "node_A"
        assert event.reviewing_node in ["node_B", "node_C"]

    def test_different_nodes_no_second_review(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "claim_invalidated",
            "node_B",  # diagnosing_node
            "node_A",  # interrupt_source (different)
            ["node_A", "node_B", "node_C"],
        )
        assert event.second_node_review is False

    def test_no_alternative_node_terminates(self):
        """Fail-closed: if no alternative node for second review, terminate."""
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "local_ambiguity",
            "node_A",
            "node_A",
            ["node_A"],
        )
        assert event.resume_target_stage == "terminate"


class TestAdversarial4SignalSelfRating:
    """§6 attack: Signal self-rating gaming — disagreement → HOLD."""

    def test_good_signal_allows_route(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.8, 0.8, 0.8)
        assert quality == SignalQuality.GOOD
        assessment = mon.assess()
        assert assessment.recommendation == "route"

    def test_degraded_signal_holds(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.5, 0.5, 0.5)
        assert quality == SignalQuality.DEGRADED
        assessment = mon.assess()
        assert assessment.recommendation == "hold"

    def test_insufficient_signal_holds(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.2, 0.2, 0.2)
        assert quality == SignalQuality.INSUFFICIENT
        assessment = mon.assess()
        assert assessment.recommendation == "hold"

    def test_conflicting_axes_degrades(self):
        """One axis good, others not → DEGRADED."""
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.9, 0.4, 0.8)
        assert quality == SignalQuality.DEGRADED


class TestAdversarial5VictorianAunt:
    """Victorian aunt attack: node claims everything is urgent → blocked without constraint_id."""

    def test_urgency_without_constraint_id_denied(self):
        """No boundary enforcement without boundary declaration."""
        registry = ConstraintRegistry()
        boundary = AdmissibilityBoundary(ClosedAdmissibilityGraph())

        # No constraints declared — urgency claim alone cannot block
        packet = _make_packet()
        result = boundary.check(packet)
        assert result.admitted is True  # No constraint to enforce

    def test_urgency_with_constraint_blocks(self):
        registry = ConstraintRegistry()
        constraint = Constraint(
            constraint_id="c-urgent",
            label="URGENT",
            description="urgent block",
            trigger_test="normal behavior",
            severity_class=SeverityClass.HALT_REQUIRED,
        )
        boundary = AdmissibilityBoundary(ClosedAdmissibilityGraph(), [constraint])
        packet = _make_packet()
        result = boundary.check(packet)
        assert result.admitted is False
        assert "c-urgent" in result.constraint_failures

    def test_halt_requires_constraint_evidence(self):
        """Pressure alone does NOT produce HALT — HALT requires constraint evidence."""
        mon = PressureMonitor()
        for source in PressureSource:
            mon.make_event(source, 1.0, "max pressure")
        assessment = mon.assess()
        assert assessment.recommendation != "halt"


class TestAdversarial6ThresholdManipulation:
    """§9 attack: Threshold manipulation mid-cycle."""

    def test_threshold_respected(self):
        mon = PressureMonitor(notice_threshold=0.3, interrupt_threshold=0.7)
        mon.make_event(PressureSource.DEGRADED_SIGNAL, 0.5, "test")
        assessment = mon.assess()
        # Below interrupt, check notice
        assert assessment.total_pressure < 0.7

    def test_thresholds_immutable_during_assessment(self):
        """Thresholds set at init time and cannot be changed without new instance."""
        mon = PressureMonitor(notice_threshold=0.3, interrupt_threshold=0.7)
        assert mon.notice_threshold == 0.3
        assert mon.interrupt_threshold == 0.7
        # Cannot set new thresholds — properties are read-only
        with pytest.raises(AttributeError):
            mon.notice_threshold = 0.1

    def test_invalid_threshold_order_rejected(self):
        with pytest.raises(ValueError):
            PressureMonitor(notice_threshold=0.8, interrupt_threshold=0.3)


class TestAdversarial7ClosureByDeclaration:
    """§11 attack: C3 contradiction requires diagnostic confirmation."""

    def test_contradiction_without_diagnostic_rejected(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="C",
        )
        with pytest.raises(ValueError, match="diagnostic_confirmation"):
            ctrl.close_cycle("cycle-001", "contradiction_confirmed", state)

    def test_contradiction_with_diagnostic_accepted(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="C",
        )
        event = ctrl.close_cycle("cycle-001", "contradiction_confirmed", state, diagnostic_confirmation=True)
        assert event.closure_reason == "contradiction_confirmed"

    def test_other_closures_no_diagnostic_needed(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="D",
        )
        event = ctrl.close_cycle("cycle-001", "integration_complete", state)
        assert event.closure_reason == "integration_complete"

    def test_no_zombie_after_closure(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="D",
        )
        ctrl.close_cycle("cycle-001", "integration_complete", state)
        with pytest.raises(ValueError, match="already closed"):
            ctrl.close_cycle("cycle-001", "scope_withdrawn", state)


class TestAdversarial8MultiCTimestampCollision:
    """§2 attack: Multi-C timestamp collision — verify arbitration under P1-P4."""

    def test_different_timestamps_earliest_wins(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:02Z", 0.8, "claim A"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:01Z", 0.8, "claim B"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.active_c == "node_B"
        assert result.resolution_method == "earliest_timestamp"
        assert result.halt_required is True

    def test_same_timestamp_different_relevance(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:00Z", 0.5, "claim A"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:00Z", 0.9, "claim B"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.active_c == "node_B"
        assert result.resolution_method == "signal_relevance"
        assert result.halt_required is True

    def test_same_timestamp_same_relevance_hold(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:00Z", 0.8, "claim A"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:00Z", 0.8, "claim B"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.resolution_method == "HOLD_FOR_RESOLUTION"
        assert result.halt_required is True

    def test_all_assertions_logged(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:01Z", 0.8, "claim A"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:00Z", 0.7, "claim B"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert len(result.all_assertions) == 2


class TestHaltReleaseConditions:
    """HALT release requires all three conditions: R1, R2, R3."""

    def test_all_conditions_met(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        release = ctrl.release_halt(event.halt_event_id, True, "record", "RELEASE")
        assert release.release_verdict == "RELEASE"

    def test_r1_fail_trigger_not_cleared(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R1"):
            ctrl.release_halt(event.halt_event_id, False, "record", "RELEASE")

    def test_r2_fail_no_diagnostic(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R2"):
            ctrl.release_halt(event.halt_event_id, True, "", "RELEASE")

    def test_r3_fail_invalid_verdict(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        with pytest.raises(ValueError, match="R3"):
            ctrl.release_halt(event.halt_event_id, True, "record", "YOLO")


class TestFailClosedDefaults:
    """Verify fail-closed behavior: missing data → deny or hold, never allow."""

    def test_empty_packet_all_rules_fail(self):
        packet = XPacket(
            packet_id="pkt-001",
            signal_id="",
            source_node="OBSERVE",
            target_node="INTERPRET_X",
            transition_kind="signal",
            claimed_object="",
            claimed_intent="",
            source_span="",
            provenance_hash="",
            timestamp="",
        )
        failures = evaluate_rules(packet)
        assert len(failures) >= 2  # At least evidence anchor + provenance

    def test_unknown_resume_class_terminates(self):
        ctrl = HaltHoldController()
        event = ctrl.determine_resume_target(
            {"interrupt_id": "int-001"},
            "totally_unknown_class",
            "node_B",
            "node_A",
            ["node_A", "node_B"],
        )
        assert event.resume_target_stage == "terminate"

    def test_invalid_closure_reason_raises(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="D",
        )
        with pytest.raises(ValueError):
            ctrl.close_cycle("cycle-001", "because_i_said_so", state)

    def test_mutation_denied_when_upstream_denied(self):
        boundary = MutationBoundary()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="B",
        )
        upstream = AdmissibilityResult(admitted=False, packet_id="pkt-001")
        result = boundary.attempt_mutation(state, _make_packet(), upstream)
        assert result.allowed is False

    def test_mutation_denied_during_halt(self):
        boundary = MutationBoundary()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="B",
            halt_status="active",
        )
        upstream = AdmissibilityResult(admitted=True, packet_id="pkt-001")
        result = boundary.attempt_mutation(state, _make_packet(), upstream)
        assert result.allowed is False

    def test_mutation_denied_during_hold(self):
        boundary = MutationBoundary()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="B",
            hold_status="active",
        )
        upstream = AdmissibilityResult(admitted=True, packet_id="pkt-001")
        result = boundary.attempt_mutation(state, _make_packet(), upstream)
        assert result.allowed is False

    def test_mutation_denied_insufficient_signal(self):
        boundary = MutationBoundary()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="B",
            current_signal_quality=SignalQuality.INSUFFICIENT,
        )
        upstream = AdmissibilityResult(admitted=True, packet_id="pkt-001")
        result = boundary.attempt_mutation(state, _make_packet(), upstream)
        assert result.allowed is False
