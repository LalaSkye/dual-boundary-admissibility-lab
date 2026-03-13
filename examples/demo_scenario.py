#!/usr/bin/env python3
"""Demo scenario — runnable walkthrough of the Admissibility Rotation Corridor.

Steps:
1. Admissible packet enters and commits
2. Pressure rises (degraded signal + multiple denials)
3. C rotates into control
4. Provisional emergency constraint declared
5. Unsafe mutation denied
6. HOLD_FOR_RESOLUTION emitted

Run:
    python -m examples.demo_scenario
"""
from __future__ import annotations

import sys
import uuid

sys.path.insert(0, ".")

from x_layer import XLayer, SignalEnvelope
from admissibility_graph import ClosedAdmissibilityGraph
from pressure_monitor import PressureMonitor, PressureSource
from c_rotation import CRotationEngine
from mutation_boundary import MutationBoundary, StateObject
from constraint_declaration import ConstraintRegistry
from halt_hold_logic import HaltHoldController
from corridor import AdmissibilityRotationCorridor


def _signal(**overrides) -> SignalEnvelope:
    defaults = {
        "source_id": "sig-001",
        "timestamp": "2025-01-01T00:00:00Z",
        "content": "The system observed normal behavior",
        "content_type": "text/plain",
        "provenance_hash": "abc123hash",
    }
    defaults.update(overrides)
    return SignalEnvelope(**defaults)


def _interp(**overrides) -> dict:
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


def run_demo() -> None:
    print("=" * 72)
    print("  Admissibility Rotation Corridor — Demo Scenario")
    print("=" * 72)

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
    print("\n── Step 1: Admissible packet enters ──")
    result1 = corridor.process(_signal(), _interp())
    print(f"  Outcome: {result1.outcome}")
    print(f"  Admitted: {result1.admissibility_result.admitted}")
    assert result1.outcome == "commit"
    print("  ✓ Packet committed successfully")

    # ── Step 2: Pressure rises ──
    print("\n── Step 2: Pressure rises (degraded signal + denials) ──")
    pressure.evaluate_signal_quality(0.4, 0.5, 0.6)  # DEGRADED
    for i in range(5):
        pressure.make_event(PressureSource.DEGRADED_SIGNAL, 0.8, f"denial {i}")
    pressure.make_event(PressureSource.THRESHOLD_PROXIMITY, 0.9, "approaching threshold")
    pressure.make_event(PressureSource.ROUTE_CONGESTION, 0.85, "congested")
    pressure.make_event(PressureSource.CONFLICTING_C, 0.8, "conflict detected")
    pressure.make_event(PressureSource.EMERGENT_CONSTRAINT, 0.9, "constraint emerging")

    assessment = pressure.assess()
    print(f"  Total pressure: {assessment.total_pressure:.4f}")
    print(f"  Recommendation: {assessment.recommendation}")
    print(f"  Signal quality: {assessment.signal_quality.value}")
    assert assessment.total_pressure >= 0.7
    assert assessment.recommendation == "rotate_c"
    print("  ✓ Pressure high enough for C rotation")

    # ── Step 3: C rotates into control ──
    print("\n── Step 3: C rotates into control ──")
    rotation = corridor.c_rotation.check_and_rotate(trigger_node="node_B")
    print(f"  Rotation event: {rotation.rotation_event_id if rotation else 'None'}")
    print(f"  C active: {corridor.c_rotation.c_active}")
    assert rotation is not None
    assert corridor.c_rotation.c_active is True
    print("  ✓ C rotation completed")

    # ── Step 4: Provisional emergency constraint declared ──
    print("\n── Step 4: Emergency constraint declared ──")
    halt_event = ctrl.enter_halt(
        trigger_condition_id="THRESHOLD_BREACH",
        triggering_node="node_B",
        available_nodes=["node_A", "node_B", "node_C", "node_D"],
    )
    print(f"  HALT entered: {halt_event.halt_event_id}")
    print(f"  Triggering node: {halt_event.triggering_node}")
    print(f"  Diagnosing node: {halt_event.diagnosing_node}")
    assert halt_event.diagnosing_node != halt_event.triggering_node

    emergency = registry.declare_emergency(
        trigger_test="unsafe_mutation_attempt",
        asserting_node="node_C",
        halt_event_id=halt_event.halt_event_id,
    )
    print(f"  Emergency constraint: {emergency.constraint_id}")
    print(f"  Provisional: {emergency.provisional}")
    assert emergency.provisional is True
    print("  ✓ Emergency constraint declared (provisional)")

    # ── Step 5: Unsafe mutation denied ──
    print("\n── Step 5: Unsafe mutation denied ──")
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

    result2 = corridor.process(
        _signal(source_id="sig-002"),
        _interp(
            claimed_object="unsafe mutation attempt",
            claimed_intent="bypass constraint",
        ),
    )
    print(f"  Outcome: {result2.outcome}")
    assert result2.outcome in ("deny", "hold")
    print("  ✓ Mutation denied (halt active)")

    # ── Step 6: HOLD_FOR_RESOLUTION emitted ──
    print("\n── Step 6: HOLD_FOR_RESOLUTION emitted ──")
    release = ctrl.release_halt(
        halt_event.halt_event_id,
        trigger_cleared=True,
        diagnostic_record="Emergency constraint declared, mutation denied, holding for resolution",
        release_verdict="HOLD_FOR_RESOLUTION",
    )
    print(f"  Release verdict: {release.release_verdict}")
    assert release.release_verdict == "HOLD_FOR_RESOLUTION"
    print("  ✓ HALT released with HOLD_FOR_RESOLUTION")

    print("\n" + "=" * 72)
    print("  Demo scenario completed successfully!")
    print("=" * 72)
    print("\n  Pipeline trace (last run):")
    for step in result2.trace:
        print(f"    → {step}")


if __name__ == "__main__":
    run_demo()
