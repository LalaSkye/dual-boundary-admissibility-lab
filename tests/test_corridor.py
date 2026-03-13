"""Integration tests for corridor.py — the full Admissibility Rotation Corridor pipeline."""
from __future__ import annotations

import uuid
import pytest

from x_layer import XLayer, SignalEnvelope, ConfidenceClass, ConsequenceClass
from admissibility_graph import ClosedAdmissibilityGraph
from pressure_monitor import PressureMonitor, PressureSource, SignalQuality
from c_rotation import CRotationEngine
from mutation_boundary import MutationBoundary, StateObject, OpenQuestion
from constraint_declaration import Constraint, ConstraintRegistry, SeverityClass
from halt_hold_logic import HaltHoldController
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


def _make_corridor(**overrides) -> AdmissibilityRotationCorridor:
    return AdmissibilityRotationCorridor(**overrides)


class TestCleanPath:
    """Clean path: admissible packet, no pressure, mutation allowed → commit."""

    def test_clean_commit(self):
        corridor = _make_corridor()
        result = corridor.process(_make_signal(), _make_interpretation())

        assert result.outcome == "commit"
        assert result.admissibility_result.admitted is True
        assert result.mutation_result is not None
        assert result.mutation_result.allowed is True
        assert result.halt_event is None
        assert result.hold_event is None

    def test_clean_commit_trace(self):
        corridor = _make_corridor()
        result = corridor.process(_make_signal(), _make_interpretation())
        assert any("packet_generated" in t for t in result.trace)
        assert any("admissibility_check" in t for t in result.trace)
        assert any("mutation_check" in t for t in result.trace)
        assert any("commit" in t for t in result.trace)

    def test_clean_commit_state_updated(self):
        corridor = _make_corridor()
        initial_state_id = corridor.current_state.state_id
        result = corridor.process(_make_signal(), _make_interpretation())
        assert corridor.current_state.state_id != initial_state_id

    def test_multiple_clean_commits(self):
        corridor = _make_corridor()
        r1 = corridor.process(_make_signal(), _make_interpretation())
        r2 = corridor.process(
            _make_signal(source_id="sig-002"),
            _make_interpretation(claimed_object="second observation"),
        )
        assert r1.outcome == "commit"
        assert r2.outcome == "commit"
        assert len(corridor.current_state.active_claim_stack) == 2


class TestInadmissiblePacket:
    """Inadmissible packet → deny, pressure recorded."""

    def test_graph_failure_deny(self):
        corridor = _make_corridor()
        result = corridor.process(
            _make_signal(),
            _make_interpretation(
                source_node="OBSERVE",
                target_node="ROUTE",  # undeclared edge
            ),
        )
        assert result.outcome == "deny"
        assert result.admissibility_result.admitted is False
        assert result.admissibility_result.graph_failure is not None

    def test_rule_failure_deny(self):
        corridor = _make_corridor()
        result = corridor.process(
            _make_signal(),
            _make_interpretation(
                assumptions=["a1", "a2", "a3", "a4"],  # exceeds threshold → rule failure
            ),
        )
        assert result.outcome == "deny"
        assert len(result.admissibility_result.rule_failures) > 0

    def test_deny_records_pressure(self):
        corridor = _make_corridor()
        corridor.process(
            _make_signal(),
            _make_interpretation(source_node="OBSERVE", target_node="ROUTE"),
        )
        assert len(corridor.pressure_monitor.events) > 0


class TestPressureHold:
    """Degraded signal → HOLD."""

    def test_degraded_signal_hold(self):
        corridor = _make_corridor()
        corridor.pressure_monitor.evaluate_signal_quality(0.5, 0.5, 0.5)
        result = corridor.process(_make_signal(), _make_interpretation())

        assert result.outcome == "hold"
        assert result.hold_event is not None

    def test_insufficient_signal_hold(self):
        corridor = _make_corridor()
        corridor.pressure_monitor.evaluate_signal_quality(0.1, 0.1, 0.1)
        result = corridor.process(_make_signal(), _make_interpretation())
        assert result.outcome == "hold"

    def test_hold_updates_state_mode(self):
        corridor = _make_corridor()
        corridor.pressure_monitor.evaluate_signal_quality(0.5, 0.5, 0.5)
        corridor.process(_make_signal(), _make_interpretation())
        assert corridor.current_state.hold_status == "active"


class TestCRotation:
    """Pressure above interrupt threshold → C rotation."""

    def test_c_rotation_on_high_pressure(self):
        corridor = _make_corridor()
        # Push pressure high
        for source in PressureSource:
            corridor.pressure_monitor.make_event(source, 0.9, "high pressure")
        result = corridor.process(_make_signal(), _make_interpretation())

        assert result.rotation_event is not None
        assert corridor.c_rotation.c_active is True


class TestHaltReleaseCycle:
    """HALT release with all three conditions."""

    def test_halt_entry_and_release(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_halt("c-001", "node_A", ["node_A", "node_B"])
        release = ctrl.release_halt(
            event.halt_event_id,
            trigger_cleared=True,
            diagnostic_record="Issue investigated and resolved",
            release_verdict="RELEASE",
        )
        assert release.release_verdict == "RELEASE"
        assert event.halt_event_id not in ctrl.active_halts


class TestHoldTimeoutAndReview:
    def test_hold_review_cadence(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("degraded signal", "better_signal")
        review = ctrl.review_hold(event, signal_status="pending")
        assert review.recommendation == "continue_hold"

    def test_hold_close_on_sufficient(self):
        ctrl = HaltHoldController()
        event = ctrl.enter_hold("degraded signal", "better_signal")
        review = ctrl.review_hold(event, signal_status="sufficient")
        assert review.recommendation == "close"


class TestCycleClosure:
    """Cycle closure — all four conditions."""

    def test_integration_complete(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="D",
        )
        event = ctrl.close_cycle("cycle-001", "integration_complete", state)
        assert event.closure_reason == "integration_complete"

    def test_scope_withdrawn(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="B",
        )
        event = ctrl.close_cycle("cycle-001", "scope_withdrawn", state)
        assert event.closure_reason == "scope_withdrawn"

    def test_contradiction_confirmed(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="C",
        )
        event = ctrl.close_cycle("cycle-001", "contradiction_confirmed", state, diagnostic_confirmation=True)
        assert event.closure_reason == "contradiction_confirmed"

    def test_operator_closure(self):
        ctrl = HaltHoldController()
        state = StateObject(
            state_id="s1", active_cycle_id="cycle-001",
            role_occupancy_map={}, current_stage="A",
        )
        event = ctrl.close_cycle("cycle-001", "operator_closure", state)
        assert event.closure_reason == "operator_closure"


class TestDemoScenario:
    """The demo scenario from the spec:
    1. Admissible packet enters
    2. Pressure rises (degraded signal + multiple denials)
    3. C rotates into control
    4. Provisional emergency constraint declared
    5. Unsafe mutation denied
    6. HOLD_FOR_RESOLUTION emitted
    """

    def test_full_demo_scenario(self):
        # Setup
        registry = ConstraintRegistry()
        pressure = PressureMonitor()
        ctrl = HaltHoldController()
        corridor = AdmissibilityRotationCorridor(
            constraint_registry=registry,
            pressure_monitor=pressure,
            halt_hold_controller=ctrl,
            available_nodes=["node_A", "node_B", "node_C", "node_D"],
        )

        # ── Step 1: Admissible packet enters and commits ──
        result1 = corridor.process(
            _make_signal(source_id="sig-001"),
            _make_interpretation(
                claimed_object="normal system state",
                claimed_intent="standard routing",
                source_span="The system observed normal behavior",
            ),
        )
        assert result1.outcome == "commit"
        assert result1.admissibility_result.admitted is True

        # ── Step 2: Pressure rises — degraded signal + multiple denials ──
        pressure.evaluate_signal_quality(0.4, 0.5, 0.6)  # DEGRADED

        # Record denials driving pressure up
        for i in range(5):
            pressure.make_event(
                PressureSource.DEGRADED_SIGNAL, 0.8,
                f"denial {i} recorded",
            )
        pressure.make_event(PressureSource.THRESHOLD_PROXIMITY, 0.9, "approaching threshold")
        pressure.make_event(PressureSource.ROUTE_CONGESTION, 0.85, "congested")
        pressure.make_event(PressureSource.CONFLICTING_C, 0.8, "conflict detected")
        pressure.make_event(PressureSource.EMERGENT_CONSTRAINT, 0.9, "constraint emerging")

        assessment = pressure.assess()
        assert assessment.total_pressure >= 0.7
        assert assessment.recommendation == "rotate_c"

        # ── Step 3: C rotates into control ──
        rotation = corridor.c_rotation.check_and_rotate(trigger_node="node_B")
        assert rotation is not None
        assert corridor.c_rotation.c_active is True

        # ── Step 4: Provisional emergency constraint declared ──
        halt_event = ctrl.enter_halt(
            trigger_condition_id="THRESHOLD_BREACH",
            triggering_node="node_B",
            available_nodes=["node_A", "node_B", "node_C", "node_D"],
        )
        emergency_constraint = registry.declare_emergency(
            trigger_test="unsafe_mutation_attempt",
            asserting_node="node_C",
            halt_event_id=halt_event.halt_event_id,
        )
        assert emergency_constraint.provisional is True
        assert emergency_constraint.label == "EMERGENCY_CONSTRAINT_DECLARATION"

        # ── Step 5: Unsafe mutation denied ──
        # Update corridor state to reflect halt
        corridor.current_state = StateObject(
            state_id=str(uuid.uuid4()),
            active_cycle_id=corridor.current_state.active_cycle_id,
            role_occupancy_map=corridor.current_state.role_occupancy_map,
            current_stage="C",
            active_claim_stack=corridor.current_state.active_claim_stack,
            current_mode="halt",
            halt_status="active",
            hold_status="none",
            predecessor_state_id=corridor.current_state.state_id,
        )

        # Try to commit — should be denied
        result2 = corridor.process(
            _make_signal(source_id="sig-002"),
            _make_interpretation(
                claimed_object="unsafe mutation attempt",
                claimed_intent="bypass constraint",
                source_span="The system observed normal behavior",
            ),
        )
        # The mutation boundary should deny due to halt_active state
        assert result2.outcome in ("deny", "hold")

        # ── Step 6: HOLD_FOR_RESOLUTION emitted ──
        release = ctrl.release_halt(
            halt_event.halt_event_id,
            trigger_cleared=True,
            diagnostic_record="Emergency constraint declared, mutation denied, holding for resolution",
            release_verdict="HOLD_FOR_RESOLUTION",
        )
        assert release.release_verdict == "HOLD_FOR_RESOLUTION"

    def test_corridor_result_frozen(self):
        corridor = _make_corridor()
        result = corridor.process(_make_signal(), _make_interpretation())
        with pytest.raises(AttributeError):
            result.outcome = "modified"


class TestCorridorMutationDeniedDownstream:
    """Mutation denied downstream even when upstream admits."""

    def test_halt_state_blocks_mutation(self):
        state = StateObject(
            state_id="s1",
            active_cycle_id="cycle-001",
            role_occupancy_map={"A": "OBSERVE"},
            current_stage="B",
            halt_status="active",
            current_mode="halt",
        )
        corridor = _make_corridor(current_state=state)
        result = corridor.process(_make_signal(), _make_interpretation())
        assert result.outcome == "deny"
        assert result.mutation_result is not None
        assert result.mutation_result.allowed is False

    def test_hold_state_blocks_mutation(self):
        state = StateObject(
            state_id="s1",
            active_cycle_id="cycle-001",
            role_occupancy_map={"A": "OBSERVE"},
            current_stage="B",
            hold_status="active",
        )
        corridor = _make_corridor(current_state=state)
        result = corridor.process(_make_signal(), _make_interpretation())
        assert result.outcome == "deny"

    def test_blocking_question_blocks_mutation(self):
        state = StateObject(
            state_id="s1",
            active_cycle_id="cycle-001",
            role_occupancy_map={"A": "OBSERVE"},
            current_stage="B",
            open_questions=(OpenQuestion("q-001", "blocking", blocking=True),),
        )
        corridor = _make_corridor(current_state=state)
        result = corridor.process(_make_signal(), _make_interpretation())
        assert result.outcome == "deny"
