"""Tests for admissibility_graph.py — upstream admissibility boundary."""
from __future__ import annotations

import pytest

from x_layer import (
    XPacket,
    ConfidenceClass,
    ConsequenceClass,
    Node,
)
from admissibility_graph import (
    AdmissibilityBoundary,
    AdmissibilityResult,
    ClosedAdmissibilityGraph,
    RuleFailure,
    evaluate_rules,
    DECLARED_EDGES,
    rule_evidence_anchor_required,
    rule_assumption_count_bound,
    rule_ambiguity_preservation_required,
    rule_confidence_consequence_match,
    rule_actor_intent_attribution_ban,
    rule_scope_drift_fail,
    rule_temporal_drift_fail,
    rule_prohibited_inferential_jump,
    rule_provenance_required,
    rule_omitted_alternative_detection,
)
from constraint_declaration import Constraint, SeverityClass


def _make_packet(**overrides) -> XPacket:
    defaults = {
        "packet_id": "pkt-001",
        "signal_id": "sig-001",
        "source_node": "OBSERVE",
        "target_node": "INTERPRET_X",
        "transition_kind": "signal",
        "claimed_object": "anomalous behavior",
        "claimed_intent": "flagging for review",
        "source_span": "The system observed anomalous behavior",
        "assumptions": (),
        "ambiguity_markers": (),
        "omitted_alternatives": (),
        "confidence_class": ConfidenceClass.MEDIUM,
        "consequence_class": ConsequenceClass.LOW,
        "provenance_hash": "abc123hash",
        "timestamp": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return XPacket(**defaults)


class TestClosedAdmissibilityGraph:
    """Graph topology: only declared edges permitted."""

    def test_declared_edge_exists(self):
        graph = ClosedAdmissibilityGraph()
        assert graph.edge_exists("OBSERVE", "INTERPRET_X") is True
        assert graph.edge_exists("INTERPRET_X", "VERIFY") is True
        assert graph.edge_exists("VERIFY", "ROUTE") is True
        assert graph.edge_exists("VERIFY", "STOP") is True

    def test_undeclared_edge_denied(self):
        graph = ClosedAdmissibilityGraph()
        assert graph.edge_exists("OBSERVE", "ROUTE") is False
        assert graph.edge_exists("ROUTE", "OBSERVE") is False
        assert graph.edge_exists("STOP", "OBSERVE") is False

    def test_transit_valid_kind(self):
        graph = ClosedAdmissibilityGraph()
        ok, reason = graph.check_transit("OBSERVE", "INTERPRET_X", "signal")
        assert ok is True

    def test_transit_invalid_kind(self):
        graph = ClosedAdmissibilityGraph()
        ok, reason = graph.check_transit("OBSERVE", "INTERPRET_X", "invalid_kind")
        assert ok is False
        assert "not allowed" in reason

    def test_transit_undeclared_edge(self):
        graph = ClosedAdmissibilityGraph()
        ok, reason = graph.check_transit("OBSERVE", "ROUTE", "signal")
        assert ok is False
        assert "No declared edge" in reason

    def test_custom_edges(self):
        from admissibility_graph import EdgeSpec
        custom = (EdgeSpec(Node.OBSERVE, Node.STOP, frozenset({"emergency"}), frozenset({"admin"})),)
        graph = ClosedAdmissibilityGraph(edges=custom)
        assert graph.edge_exists("OBSERVE", "STOP") is True
        assert graph.edge_exists("OBSERVE", "INTERPRET_X") is False


class TestRule1EvidenceAnchor:
    def test_pass_with_source_span(self):
        p = _make_packet(source_span="evidence text")
        ok, _ = rule_evidence_anchor_required(p)
        assert ok is True

    def test_fail_empty_source_span(self):
        p = _make_packet(source_span="")
        ok, reason = rule_evidence_anchor_required(p)
        assert ok is False
        assert "source_span" in reason

    def test_fail_whitespace_source_span(self):
        p = _make_packet(source_span="   ")
        ok, reason = rule_evidence_anchor_required(p)
        assert ok is False


class TestRule2AssumptionCount:
    def test_pass_under_threshold(self):
        p = _make_packet(assumptions=("a1", "a2", "a3"))
        ok, _ = rule_assumption_count_bound(p)
        assert ok is True

    def test_fail_over_threshold(self):
        p = _make_packet(assumptions=("a1", "a2", "a3", "a4"))
        ok, reason = rule_assumption_count_bound(p)
        assert ok is False
        assert "exceeds" in reason

    def test_pass_zero_assumptions(self):
        p = _make_packet(assumptions=())
        ok, _ = rule_assumption_count_bound(p)
        assert ok is True


class TestRule3AmbiguityPreservation:
    def test_pass_no_markers(self):
        p = _make_packet(ambiguity_markers=(), omitted_alternatives=())
        ok, _ = rule_ambiguity_preservation_required(p)
        assert ok is True

    def test_pass_markers_with_alternatives(self):
        p = _make_packet(ambiguity_markers=("m1",), omitted_alternatives=("alt1",))
        ok, _ = rule_ambiguity_preservation_required(p)
        assert ok is True

    def test_fail_markers_without_alternatives(self):
        p = _make_packet(ambiguity_markers=("m1",), omitted_alternatives=())
        ok, reason = rule_ambiguity_preservation_required(p)
        assert ok is False
        assert "undocumented" in reason


class TestRule4ConfidenceConsequence:
    def test_pass_low_consequence(self):
        p = _make_packet(confidence_class=ConfidenceClass.LOW, consequence_class=ConsequenceClass.LOW)
        ok, _ = rule_confidence_consequence_match(p)
        assert ok is True

    def test_fail_critical_consequence_low_confidence(self):
        p = _make_packet(confidence_class=ConfidenceClass.LOW, consequence_class=ConsequenceClass.CRITICAL)
        ok, reason = rule_confidence_consequence_match(p)
        assert ok is False
        assert "CRITICAL" in reason

    def test_fail_high_consequence_low_confidence(self):
        p = _make_packet(confidence_class=ConfidenceClass.LOW, consequence_class=ConsequenceClass.HIGH)
        ok, reason = rule_confidence_consequence_match(p)
        assert ok is False

    def test_pass_critical_consequence_high_confidence(self):
        p = _make_packet(confidence_class=ConfidenceClass.HIGH, consequence_class=ConsequenceClass.CRITICAL)
        ok, _ = rule_confidence_consequence_match(p)
        assert ok is True


class TestRule5IntentAttributionBan:
    def test_pass_no_mental_state(self):
        p = _make_packet(claimed_intent="flagging for review")
        ok, _ = rule_actor_intent_attribution_ban(p)
        assert ok is True

    def test_fail_mental_state_without_evidence(self):
        p = _make_packet(
            claimed_intent="the actor believes this is correct",
            source_span="The system observed a change",
        )
        ok, reason = rule_actor_intent_attribution_ban(p)
        assert ok is False
        assert "believes" in reason

    def test_pass_mental_state_with_evidence(self):
        p = _make_packet(
            claimed_intent="the actor believes this is correct",
            source_span="the actor believes this is correct as stated",
        )
        ok, _ = rule_actor_intent_attribution_ban(p)
        assert ok is True


class TestRule6ScopeDrift:
    def test_pass_no_expansion(self):
        p = _make_packet(claimed_object="specific thing")
        ok, _ = rule_scope_drift_fail(p)
        assert ok is True

    def test_fail_scope_expansion(self):
        p = _make_packet(
            claimed_object="all systems affected",
            source_span="one system showed anomaly",
        )
        ok, reason = rule_scope_drift_fail(p)
        assert ok is False
        assert "all" in reason

    def test_pass_expansion_in_source(self):
        p = _make_packet(
            claimed_object="all systems affected",
            source_span="all systems affected per monitoring",
        )
        ok, _ = rule_scope_drift_fail(p)
        assert ok is True


class TestRule7TemporalDrift:
    def test_pass_no_temporal(self):
        p = _make_packet(claimed_object="current state")
        ok, _ = rule_temporal_drift_fail(p)
        assert ok is True

    def test_fail_temporal_drift(self):
        p = _make_packet(
            claimed_intent="this has always been the case historically",
            source_span="current observation",
        )
        ok, reason = rule_temporal_drift_fail(p)
        assert ok is False

    def test_pass_temporal_in_source(self):
        p = _make_packet(
            claimed_intent="historically documented",
            source_span="historically documented in records",
        )
        ok, _ = rule_temporal_drift_fail(p)
        assert ok is True


class TestRule8ProhibitedJump:
    def test_pass_no_prohibited(self):
        p = _make_packet(claimed_intent="normal routing")
        ok, _ = rule_prohibited_inferential_jump(p)
        assert ok is True

    def test_fail_correlation_to_causation(self):
        p = _make_packet(claimed_intent="this shows correlation to causation clearly")
        ok, reason = rule_prohibited_inferential_jump(p)
        assert ok is False
        assert "correlation_to_causation" in reason

    def test_fail_absence_to_denial(self):
        p = _make_packet(claimed_intent="absence to denial is established")
        ok, reason = rule_prohibited_inferential_jump(p)
        assert ok is False

    def test_fail_silence_as_agreement(self):
        p = _make_packet(claimed_intent="silence as agreement was observed")
        ok, reason = rule_prohibited_inferential_jump(p)
        assert ok is False

    def test_fail_partial_to_universal(self):
        p = _make_packet(claimed_object="partial to universal application")
        ok, reason = rule_prohibited_inferential_jump(p)
        assert ok is False


class TestRule9Provenance:
    def test_pass_with_provenance(self):
        p = _make_packet(signal_id="sig-001", provenance_hash="hash123")
        ok, _ = rule_provenance_required(p)
        assert ok is True

    def test_fail_empty_signal_id(self):
        p = _make_packet(signal_id="")
        ok, reason = rule_provenance_required(p)
        assert ok is False
        assert "signal_id" in reason

    def test_fail_empty_provenance_hash(self):
        p = _make_packet(provenance_hash="")
        ok, reason = rule_provenance_required(p)
        assert ok is False
        assert "provenance_hash" in reason


class TestRule10OmittedAlternative:
    def test_pass_no_markers(self):
        p = _make_packet(ambiguity_markers=(), omitted_alternatives=())
        ok, _ = rule_omitted_alternative_detection(p)
        assert ok is True

    def test_pass_markers_with_alternatives(self):
        p = _make_packet(ambiguity_markers=("m1",), omitted_alternatives=("alt1",))
        ok, _ = rule_omitted_alternative_detection(p)
        assert ok is True

    def test_fail_markers_without_alternatives(self):
        p = _make_packet(ambiguity_markers=("m1",), omitted_alternatives=())
        ok, reason = rule_omitted_alternative_detection(p)
        assert ok is False


class TestEvaluateRules:
    def test_all_pass(self):
        p = _make_packet()
        failures = evaluate_rules(p)
        assert len(failures) == 0

    def test_multiple_failures(self):
        p = _make_packet(
            source_span="",
            signal_id="",
            assumptions=("a1", "a2", "a3", "a4"),
        )
        failures = evaluate_rules(p)
        assert len(failures) >= 2
        rule_names = {f.rule for f in failures}
        assert "EVIDENCE_ANCHOR_REQUIRED" in rule_names
        assert "ASSUMPTION_COUNT_BOUND" in rule_names


class TestAdmissibilityBoundary:
    def test_admissible_packet(self):
        graph = ClosedAdmissibilityGraph()
        boundary = AdmissibilityBoundary(graph)
        packet = _make_packet()
        result = boundary.check(packet)

        assert result.admitted is True
        assert result.packet_id == "pkt-001"
        assert len(result.rule_failures) == 0
        assert result.graph_failure is None

    def test_graph_failure(self):
        graph = ClosedAdmissibilityGraph()
        boundary = AdmissibilityBoundary(graph)
        packet = _make_packet(source_node="OBSERVE", target_node="ROUTE")
        result = boundary.check(packet)

        assert result.admitted is False
        assert result.graph_failure is not None

    def test_rule_failure(self):
        graph = ClosedAdmissibilityGraph()
        boundary = AdmissibilityBoundary(graph)
        packet = _make_packet(source_span="")
        result = boundary.check(packet)

        assert result.admitted is False
        assert any(f.rule == "EVIDENCE_ANCHOR_REQUIRED" for f in result.rule_failures)

    def test_constraint_failure(self):
        graph = ClosedAdmissibilityGraph()
        constraint = Constraint(
            constraint_id="c-001",
            label="test",
            description="test constraint",
            trigger_test="anomalous behavior",
            severity_class=SeverityClass.HALT_REQUIRED,
            allowed_response_set=("HALT",),
        )
        boundary = AdmissibilityBoundary(graph, active_constraints=[constraint])
        packet = _make_packet()
        result = boundary.check(packet)

        assert result.admitted is False
        assert "c-001" in result.constraint_failures

    def test_multiple_failures_combined(self):
        graph = ClosedAdmissibilityGraph()
        boundary = AdmissibilityBoundary(graph)
        packet = _make_packet(
            source_node="OBSERVE",
            target_node="ROUTE",
            source_span="",
        )
        result = boundary.check(packet)

        assert result.admitted is False
        assert result.graph_failure is not None
        assert len(result.rule_failures) > 0

    def test_update_constraints(self):
        graph = ClosedAdmissibilityGraph()
        boundary = AdmissibilityBoundary(graph)
        packet = _make_packet()

        # Initially no constraints
        result = boundary.check(packet)
        assert result.admitted is True

        # Add constraint
        constraint = Constraint(
            constraint_id="c-002",
            label="test",
            description="test",
            trigger_test="anomalous behavior",
            severity_class=SeverityClass.HALT_REQUIRED,
        )
        boundary.update_constraints([constraint])
        result = boundary.check(packet)
        assert result.admitted is False


class TestAdmissibilityResultFrozen:
    def test_result_is_frozen(self):
        result = AdmissibilityResult(admitted=True, packet_id="pkt-001")
        with pytest.raises(AttributeError):
            result.admitted = False
