"""Pressure-activated C-sector rotation with defensive routing.

Position in pipeline: FOURTH — when pressure crosses interrupt threshold,
C rotates in and system moves from ordinary to defensive routing.

... → pressure_assessment → [C_ROTATION] → rotation_event → ...

Rules from Engine patch §5:
- No mid-claim rotation unless HALT or HOLD active
- C rotates last unless C is source of reassignment (self_recusal)
- Every rotation emits prior and new maps

Multi-C arbitration per Engine patch §2:
1. All assertions accepted
2. System enters HALT immediately
3. Single active_C selected by: earliest timestamp, signal relevance, merge, HOLD_FOR_RESOLUTION
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pressure_monitor import PressureMonitor, PressureAssessment


@dataclass(frozen=True)
class CAssertion:
    """A node's assertion of C-sector authority."""
    assertion_id: str
    asserting_node: str
    timestamp: str
    signal_relevance: float  # 0.0 to 1.0
    rationale: str


@dataclass(frozen=True)
class MultiCResolution:
    """Result of multi-C arbitration."""
    active_c: str  # selected node
    resolution_method: str  # "earliest_timestamp" | "signal_relevance" | "merge" | "HOLD_FOR_RESOLUTION"
    all_assertions: tuple[CAssertion, ...]
    halt_required: bool


@dataclass(frozen=True)
class RotationEvent:
    """Record of a C-sector rotation."""
    rotation_event_id: str
    prior_role_map: dict
    new_role_map: dict
    trigger_type: str  # "cycle_complete" | "manual_reassignment" | "halt_reconfiguration" | "fatigue_or_signal_degradation"
    authorising_source: str
    timestamp: str
    rationale: str
    self_recusal: bool  # True if C self-initiated


class CRotationEngine:
    """Manages C-sector rotation based on pressure.

    When pressure crosses interrupt threshold, C rotates into control
    and the system transitions from ordinary routing to defensive routing.
    """

    def __init__(
        self,
        pressure_monitor: PressureMonitor,
        interrupt_threshold: float = 0.7,
    ) -> None:
        self._pressure_monitor = pressure_monitor
        self._interrupt_threshold = interrupt_threshold
        self._current_role_map: dict[str, str] = {
            "A": "OBSERVE",
            "B": "INTERPRET",
            "C": "CONSTRAINT",
            "D": "ROUTE",
        }
        self._c_active: bool = False
        self._active_c_node: str = ""
        self._halt_active: bool = False
        self._hold_active: bool = False
        self._rotation_log: list[RotationEvent] = []

    @property
    def c_active(self) -> bool:
        return self._c_active

    @property
    def active_c_node(self) -> str:
        return self._active_c_node

    @property
    def rotation_log(self) -> list[RotationEvent]:
        return list(self._rotation_log)

    def set_halt_active(self, active: bool) -> None:
        self._halt_active = active

    def set_hold_active(self, active: bool) -> None:
        self._hold_active = active

    def check_and_rotate(self, trigger_node: str = "system") -> RotationEvent | None:
        """Check pressure, rotate if needed. Returns event or None.

        Rotation rules:
        - No mid-claim rotation unless HALT or HOLD active
        - C rotates last unless self_recusal
        """
        assessment = self._pressure_monitor.assess()

        if assessment.total_pressure < self._interrupt_threshold:
            return None

        if self._c_active:
            # Already rotated — no re-rotation unless HALT/HOLD active
            if not self._halt_active and not self._hold_active:
                return None

        prior_map = dict(self._current_role_map)
        new_map = dict(self._current_role_map)
        new_map["C"] = "CONSTRAINT_ACTIVE"

        self._c_active = True
        self._active_c_node = trigger_node

        event = RotationEvent(
            rotation_event_id=str(uuid.uuid4()),
            prior_role_map=prior_map,
            new_role_map=new_map,
            trigger_type="fatigue_or_signal_degradation",
            authorising_source=trigger_node,
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale=f"Pressure {assessment.total_pressure:.4f} >= threshold {self._interrupt_threshold}",
            self_recusal=False,
        )
        self._current_role_map = new_map
        self._rotation_log.append(event)
        return event

    def force_rotate(
        self,
        trigger_type: str,
        authorising_source: str,
        rationale: str,
        self_recusal: bool = False,
    ) -> RotationEvent:
        """Force a rotation regardless of pressure. Used for manual/halt scenarios."""
        prior_map = dict(self._current_role_map)
        new_map = dict(self._current_role_map)
        new_map["C"] = "CONSTRAINT_ACTIVE"

        self._c_active = True
        self._active_c_node = authorising_source

        event = RotationEvent(
            rotation_event_id=str(uuid.uuid4()),
            prior_role_map=prior_map,
            new_role_map=new_map,
            trigger_type=trigger_type,
            authorising_source=authorising_source,
            timestamp=datetime.now(timezone.utc).isoformat(),
            rationale=rationale,
            self_recusal=self_recusal,
        )
        self._current_role_map = new_map
        self._rotation_log.append(event)
        return event

    def resolve_multi_c(self, assertions: list[CAssertion]) -> MultiCResolution:
        """Multi-C arbitration per Engine patch §2.

        Priority resolution:
        P1. All assertions accepted (logged)
        P2. System enters HALT immediately
        P3. Single active_C selected:
            a. Earliest timestamp
            b. Highest signal_relevance (tie-break)
            c. Merge if compatible
            d. HOLD_FOR_RESOLUTION if unresolvable
        """
        if not assertions:
            raise ValueError("No C assertions to resolve")

        if len(assertions) == 1:
            a = assertions[0]
            self._active_c_node = a.asserting_node
            self._c_active = True
            return MultiCResolution(
                active_c=a.asserting_node,
                resolution_method="earliest_timestamp",
                all_assertions=tuple(assertions),
                halt_required=False,
            )

        # Sort by timestamp, then by signal_relevance (descending)
        sorted_assertions = sorted(
            assertions,
            key=lambda a: (a.timestamp, -a.signal_relevance),
        )

        # Check if all timestamps are the same (collision)
        timestamps = {a.timestamp for a in assertions}
        if len(timestamps) == 1:
            # Timestamp collision — check signal relevance
            relevances = {a.signal_relevance for a in assertions}
            if len(relevances) == 1:
                # Both same relevance — HOLD_FOR_RESOLUTION
                return MultiCResolution(
                    active_c=sorted_assertions[0].asserting_node,
                    resolution_method="HOLD_FOR_RESOLUTION",
                    all_assertions=tuple(assertions),
                    halt_required=True,
                )
            else:
                # Select highest relevance
                selected = max(assertions, key=lambda a: a.signal_relevance)
                self._active_c_node = selected.asserting_node
                self._c_active = True
                return MultiCResolution(
                    active_c=selected.asserting_node,
                    resolution_method="signal_relevance",
                    all_assertions=tuple(assertions),
                    halt_required=True,
                )

        # Different timestamps — select earliest
        selected = sorted_assertions[0]
        self._active_c_node = selected.asserting_node
        self._c_active = True
        return MultiCResolution(
            active_c=selected.asserting_node,
            resolution_method="earliest_timestamp",
            all_assertions=tuple(assertions),
            halt_required=True,
        )

    def reset(self) -> None:
        """Reset rotation state."""
        self._c_active = False
        self._active_c_node = ""
        self._current_role_map = {
            "A": "OBSERVE",
            "B": "INTERPRET",
            "C": "CONSTRAINT",
            "D": "ROUTE",
        }
