"""Constraint objects and emergency provisional declarations.

Position in pipeline: Referenced by admissibility checks and halt/hold logic.
Constraints are the formal mechanism for boundary enforcement.

INVARIANT: No boundary enforcement without boundary declaration.
FIX from adversarial review §4: Emergency claims MUST emit EMERGENCY_CONSTRAINT_DECLARATION.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SeverityClass(Enum):
    ADVISORY = "ADVISORY"
    HOLD_REQUIRED = "HOLD_REQUIRED"
    HALT_REQUIRED = "HALT_REQUIRED"


@dataclass(frozen=True)
class Constraint:
    """Immutable constraint declaration.

    provisional=True for emergency declarations that must be ratified
    during diagnostic review. Scoped to a specific halt_event_id.
    """
    constraint_id: str
    label: str
    description: str
    trigger_test: str
    severity_class: SeverityClass
    allowed_response_set: tuple[str, ...] = field(default_factory=lambda: ("CONTINUE",))
    release_test: str = ""
    provenance_source: str = ""
    version: str = "1"
    provisional: bool = False
    provisional_expiry: str = ""  # halt_event_id that scopes this constraint


class ConstraintRegistry:
    """Registry of active constraints.

    Supports standard constraints and emergency provisional declarations.
    """

    def __init__(self) -> None:
        self._constraints: dict[str, Constraint] = {}
        self._rejected: set[str] = set()

    def add(self, constraint: Constraint) -> None:
        """Register a constraint. Raises ValueError on duplicate ID."""
        if constraint.constraint_id in self._constraints:
            raise ValueError(f"Duplicate constraint_id: {constraint.constraint_id}")
        self._constraints[constraint.constraint_id] = constraint

    def get(self, constraint_id: str) -> Constraint | None:
        """Retrieve a constraint by ID. Returns None if not found or rejected."""
        if constraint_id in self._rejected:
            return None
        return self._constraints.get(constraint_id)

    def get_all_active(self) -> list[Constraint]:
        """Return all non-rejected constraints."""
        return [
            c for cid, c in self._constraints.items()
            if cid not in self._rejected
        ]

    def declare_emergency(
        self,
        trigger_test: str,
        asserting_node: str,
        halt_event_id: str,
    ) -> Constraint:
        """Emergency constraint declaration per adversarial review §4 fix.

        - Generates provisional constraint_id
        - Sets provisional=True
        - Valid only for duration of the HALT (scoped by halt_event_id)
        - Must be ratified, modified, or rejected during diagnostic review

        Raises ValueError if trigger_test is empty.
        """
        if not trigger_test or not trigger_test.strip():
            raise ValueError("Emergency constraint requires non-empty trigger_test")
        if not halt_event_id or not halt_event_id.strip():
            raise ValueError("Emergency constraint requires halt_event_id scope")

        constraint = Constraint(
            constraint_id=f"EMERGENCY-{uuid.uuid4().hex[:12]}",
            label=f"EMERGENCY_CONSTRAINT_DECLARATION",
            description=f"Provisional constraint declared by {asserting_node} during HALT {halt_event_id}",
            trigger_test=trigger_test,
            severity_class=SeverityClass.HALT_REQUIRED,
            allowed_response_set=("HALT",),
            release_test=f"diagnostic_review_complete({halt_event_id})",
            provenance_source=asserting_node,
            version="1",
            provisional=True,
            provisional_expiry=halt_event_id,
        )
        self.add(constraint)
        return constraint

    def ratify_provisional(self, constraint_id: str) -> None:
        """Ratify a provisional constraint, making it permanent.

        Replaces the provisional constraint with a non-provisional copy.
        Raises ValueError if constraint not found or not provisional.
        """
        c = self._constraints.get(constraint_id)
        if c is None:
            raise ValueError(f"Constraint not found: {constraint_id}")
        if not c.provisional:
            raise ValueError(f"Constraint is not provisional: {constraint_id}")

        ratified = Constraint(
            constraint_id=c.constraint_id,
            label=c.label,
            description=c.description,
            trigger_test=c.trigger_test,
            severity_class=c.severity_class,
            allowed_response_set=c.allowed_response_set,
            release_test=c.release_test,
            provenance_source=c.provenance_source,
            version=c.version,
            provisional=False,
            provisional_expiry="",
        )
        self._constraints[constraint_id] = ratified

    def reject_provisional(self, constraint_id: str) -> None:
        """Reject a provisional constraint. It will no longer be returned by get().

        Raises ValueError if constraint not found or not provisional.
        """
        c = self._constraints.get(constraint_id)
        if c is None:
            raise ValueError(f"Constraint not found: {constraint_id}")
        if not c.provisional:
            raise ValueError(f"Constraint is not provisional: {constraint_id}")
        self._rejected.add(constraint_id)

    def expire_for_halt(self, halt_event_id: str) -> list[str]:
        """Expire all provisional constraints scoped to the given halt_event_id.

        Returns list of expired constraint_ids.
        """
        expired = []
        for cid, c in self._constraints.items():
            if c.provisional and c.provisional_expiry == halt_event_id and cid not in self._rejected:
                self._rejected.add(cid)
                expired.append(cid)
        return expired

    def check_violations(self, packet_fields: dict) -> list[str]:
        """Check active constraints for violations against packet fields.

        Returns list of constraint_ids that are violated.
        Simple string-match on trigger_test for evaluable conditions.
        """
        violations = []
        for c in self.get_all_active():
            # Simple trigger evaluation: check if trigger_test condition
            # matches something in the packet fields
            trigger = c.trigger_test.lower()
            for key, val in packet_fields.items():
                val_lower = str(val).lower()
                if trigger in val_lower or val_lower in trigger:
                    violations.append(c.constraint_id)
                    break
        return violations
