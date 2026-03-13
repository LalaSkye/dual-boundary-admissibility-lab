"""The Admissibility Rotation Corridor — main pipeline.

Ties everything together into the minimal flow:
signal → X_packet → interpretive_admissibility_check → pressure_assessment
    → {route | rotate_c | hold | halt} → state_mutation_check → commit | deny

This is the single continuous mechanism from upstream interpretation
admissibility to downstream state mutation control.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from x_layer import XLayer, XPacket, SignalEnvelope
from admissibility_graph import (
    AdmissibilityBoundary,
    AdmissibilityResult,
    ClosedAdmissibilityGraph,
)
from pressure_monitor import (
    PressureMonitor,
    PressureAssessment,
    PressureSource,
    SignalQuality,
)
from c_rotation import CRotationEngine, RotationEvent
from mutation_boundary import MutationBoundary, MutationResult, StateObject
from constraint_declaration import ConstraintRegistry
from halt_hold_logic import (
    HaltHoldController,
    HaltEvent,
    HoldEvent,
)


@dataclass(frozen=True)
class CorridorResult:
    """Full pipeline result — frozen, immutable."""
    packet_id: str
    outcome: str  # "commit" | "deny" | "hold" | "halt"
    admissibility_result: AdmissibilityResult
    pressure_assessment: PressureAssessment
    mutation_result: MutationResult | None = None
    rotation_event: RotationEvent | None = None
    halt_event: HaltEvent | None = None
    hold_event: HoldEvent | None = None
    trace: tuple[str, ...] = field(default_factory=tuple)


class AdmissibilityRotationCorridor:
    """The full pipeline: ties everything together.

    Wire together: XLayer, AdmissibilityBoundary, PressureMonitor,
    CRotationEngine, MutationBoundary, ConstraintRegistry, HaltHoldController.
    """

    def __init__(
        self,
        x_layer: XLayer | None = None,
        graph: ClosedAdmissibilityGraph | None = None,
        pressure_monitor: PressureMonitor | None = None,
        constraint_registry: ConstraintRegistry | None = None,
        halt_hold_controller: HaltHoldController | None = None,
        current_state: StateObject | None = None,
        available_nodes: list[str] | None = None,
    ) -> None:
        self.x_layer = x_layer or XLayer()
        self._graph = graph or ClosedAdmissibilityGraph()
        self.pressure_monitor = pressure_monitor or PressureMonitor()
        self.constraint_registry = constraint_registry or ConstraintRegistry()
        self.halt_hold = halt_hold_controller or HaltHoldController()
        self.mutation_boundary = MutationBoundary()
        self.c_rotation = CRotationEngine(
            pressure_monitor=self.pressure_monitor,
        )
        self._boundary = AdmissibilityBoundary(
            graph=self._graph,
            active_constraints=self.constraint_registry.get_all_active(),
        )
        self._current_state = current_state or StateObject(
            state_id=str(uuid.uuid4()),
            active_cycle_id=str(uuid.uuid4()),
            role_occupancy_map={"A": "OBSERVE", "B": "INTERPRET", "C": "CONSTRAINT", "D": "ROUTE"},
            current_stage="A",
        )
        self._available_nodes = available_nodes or ["node_A", "node_B", "node_C", "node_D"]

    @property
    def current_state(self) -> StateObject:
        return self._current_state

    @current_state.setter
    def current_state(self, state: StateObject) -> None:
        self._current_state = state

    def process(
        self,
        signal: SignalEnvelope,
        interpretation: dict,
    ) -> CorridorResult:
        """The full pipeline:

        1. X-layer generates packet
        2. Admissibility boundary checks upstream
        3. If inadmissible → deny (record pressure)
        4. Pressure monitor assesses
        5. If pressure → C rotation / hold / halt
        6. If routable → mutation boundary checks downstream
        7. If mutation admissible → commit
        8. If mutation denied → deny
        """
        trace: list[str] = []

        # ── 1. X-layer generates packet ──
        packet = self.x_layer.generate_packet(signal, interpretation)
        trace.append(f"packet_generated:{packet.packet_id}")

        # ── 2. Admissibility boundary checks upstream ──
        self._boundary.update_constraints(self.constraint_registry.get_all_active())
        admissibility = self._boundary.check(packet)
        trace.append(f"admissibility_check:admitted={admissibility.admitted}")

        # ── 3. If inadmissible → deny (record pressure) ──
        if not admissibility.admitted:
            self.pressure_monitor.make_event(
                source=PressureSource.DEGRADED_SIGNAL,
                score=0.4,
                detail=f"packet {packet.packet_id} denied upstream",
            )
            trace.append("outcome:deny:upstream_inadmissible")
            assessment = self.pressure_monitor.assess()
            return CorridorResult(
                packet_id=packet.packet_id,
                outcome="deny",
                admissibility_result=admissibility,
                pressure_assessment=assessment,
                trace=tuple(trace),
            )

        # ── 4. Pressure monitor assesses ──
        assessment = self.pressure_monitor.assess()
        trace.append(f"pressure_assessment:{assessment.recommendation}")

        # ── 5. Handle pressure recommendations ──
        rotation_event = None
        halt_event = None
        hold_event = None

        if assessment.recommendation == "halt":
            # HALT — only if constraint evidence exists
            # Find trigger constraint
            active_constraints = self.constraint_registry.get_all_active()
            trigger_id = ""
            for c in active_constraints:
                if c.severity_class.value == "HALT_REQUIRED":
                    trigger_id = c.constraint_id
                    break

            if trigger_id:
                halt_event = self.halt_hold.enter_halt(
                    trigger_condition_id=trigger_id,
                    triggering_node=packet.source_node,
                    available_nodes=self._available_nodes,
                )
                self.c_rotation.set_halt_active(True)
                trace.append(f"halt_entered:{halt_event.halt_event_id}")
                return CorridorResult(
                    packet_id=packet.packet_id,
                    outcome="halt",
                    admissibility_result=admissibility,
                    pressure_assessment=assessment,
                    halt_event=halt_event,
                    trace=tuple(trace),
                )
            else:
                # No constraint evidence — downgrade to hold
                assessment = PressureAssessment(
                    total_pressure=assessment.total_pressure,
                    recommendation="hold",
                    active_sources=assessment.active_sources,
                    signal_quality=assessment.signal_quality,
                )

        if assessment.recommendation == "rotate_c":
            rotation_event = self.c_rotation.check_and_rotate(
                trigger_node=packet.source_node,
            )
            if rotation_event:
                trace.append(f"c_rotated:{rotation_event.rotation_event_id}")

        if assessment.recommendation == "hold":
            hold_event = self.halt_hold.enter_hold(
                reason=f"pressure={assessment.total_pressure:.4f}, quality={assessment.signal_quality.value}",
                requested_signal="improved_signal_quality",
            )
            self.c_rotation.set_hold_active(True)
            trace.append(f"hold_entered:{hold_event.hold_event_id}")

            # Update state to reflect hold
            self._current_state = StateObject(
                state_id=str(uuid.uuid4()),
                active_cycle_id=self._current_state.active_cycle_id,
                role_occupancy_map=self._current_state.role_occupancy_map,
                current_stage=self._current_state.current_stage,
                active_claim_stack=self._current_state.active_claim_stack,
                open_questions=self._current_state.open_questions,
                active_constraints=self._current_state.active_constraints,
                current_mode="hold",
                current_signal_quality=self._current_state.current_signal_quality,
                halt_status=self._current_state.halt_status,
                hold_status="active",
                predecessor_state_id=self._current_state.state_id,
            )

            return CorridorResult(
                packet_id=packet.packet_id,
                outcome="hold",
                admissibility_result=admissibility,
                pressure_assessment=assessment,
                rotation_event=rotation_event,
                hold_event=hold_event,
                trace=tuple(trace),
            )

        # ── 6. Mutation boundary checks downstream ──
        mutation = self.mutation_boundary.attempt_mutation(
            current_state=self._current_state,
            proposed_transition=packet,
            upstream_result=admissibility,
        )
        trace.append(f"mutation_check:allowed={mutation.allowed}")

        # ── 7/8. Commit or deny ──
        if mutation.allowed:
            self._current_state = mutation.new_state
            trace.append("outcome:commit")
            return CorridorResult(
                packet_id=packet.packet_id,
                outcome="commit",
                admissibility_result=admissibility,
                pressure_assessment=assessment,
                mutation_result=mutation,
                rotation_event=rotation_event,
                trace=tuple(trace),
            )
        else:
            trace.append(f"outcome:deny:mutation_denied:{mutation.denial_reason}")
            return CorridorResult(
                packet_id=packet.packet_id,
                outcome="deny",
                admissibility_result=admissibility,
                pressure_assessment=assessment,
                mutation_result=mutation,
                rotation_event=rotation_event,
                trace=tuple(trace),
            )
