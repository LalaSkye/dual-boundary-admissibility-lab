"""Tests for constraint_declaration.py — constraint objects + emergency declarations."""
from __future__ import annotations

import pytest

from constraint_declaration import (
    Constraint,
    ConstraintRegistry,
    SeverityClass,
)


def _make_constraint(constraint_id: str = "c-001", **overrides) -> Constraint:
    defaults = {
        "constraint_id": constraint_id,
        "label": "test_constraint",
        "description": "A test constraint",
        "trigger_test": "anomaly_detected",
        "severity_class": SeverityClass.ADVISORY,
        "allowed_response_set": ("CONTINUE",),
        "release_test": "anomaly_resolved",
        "provenance_source": "test_source",
        "version": "1",
        "provisional": False,
        "provisional_expiry": "",
    }
    defaults.update(overrides)
    return Constraint(**defaults)


class TestConstraintRegistry:
    def test_add_and_get(self):
        reg = ConstraintRegistry()
        c = _make_constraint()
        reg.add(c)
        assert reg.get("c-001") is c

    def test_get_nonexistent(self):
        reg = ConstraintRegistry()
        assert reg.get("nonexistent") is None

    def test_duplicate_id_raises(self):
        reg = ConstraintRegistry()
        reg.add(_make_constraint("c-001"))
        with pytest.raises(ValueError, match="Duplicate"):
            reg.add(_make_constraint("c-001"))

    def test_get_all_active(self):
        reg = ConstraintRegistry()
        reg.add(_make_constraint("c-001"))
        reg.add(_make_constraint("c-002"))
        active = reg.get_all_active()
        assert len(active) == 2

    def test_get_all_active_excludes_rejected(self):
        reg = ConstraintRegistry()
        reg.add(_make_constraint("c-001", provisional=True))
        reg.add(_make_constraint("c-002"))
        reg.reject_provisional("c-001")
        active = reg.get_all_active()
        assert len(active) == 1
        assert active[0].constraint_id == "c-002"


class TestEmergencyDeclaration:
    """Adversarial review §4 fix: emergency constraint declaration."""

    def test_declare_emergency(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency(
            trigger_test="immediate_damage_detected",
            asserting_node="node_C",
            halt_event_id="halt-001",
        )
        assert c.provisional is True
        assert c.provisional_expiry == "halt-001"
        assert c.severity_class == SeverityClass.HALT_REQUIRED
        assert c.constraint_id.startswith("EMERGENCY-")
        assert c.label == "EMERGENCY_CONSTRAINT_DECLARATION"

    def test_emergency_requires_trigger_test(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="trigger_test"):
            reg.declare_emergency("", "node_C", "halt-001")

    def test_emergency_requires_halt_event_id(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="halt_event_id"):
            reg.declare_emergency("trigger", "node_C", "")

    def test_emergency_retrievable(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")
        assert reg.get(c.constraint_id) is c

    def test_emergency_in_active_list(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")
        active = reg.get_all_active()
        assert c in active


class TestRatification:
    def test_ratify_provisional(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")
        reg.ratify_provisional(c.constraint_id)
        ratified = reg.get(c.constraint_id)
        assert ratified.provisional is False
        assert ratified.provisional_expiry == ""

    def test_ratify_non_provisional_raises(self):
        reg = ConstraintRegistry()
        reg.add(_make_constraint("c-001", provisional=False))
        with pytest.raises(ValueError, match="not provisional"):
            reg.ratify_provisional("c-001")

    def test_ratify_nonexistent_raises(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="not found"):
            reg.ratify_provisional("nonexistent")


class TestRejection:
    def test_reject_provisional(self):
        reg = ConstraintRegistry()
        c = reg.declare_emergency("trigger", "node_C", "halt-001")
        reg.reject_provisional(c.constraint_id)
        assert reg.get(c.constraint_id) is None

    def test_reject_non_provisional_raises(self):
        reg = ConstraintRegistry()
        reg.add(_make_constraint("c-001", provisional=False))
        with pytest.raises(ValueError, match="not provisional"):
            reg.reject_provisional("c-001")

    def test_reject_nonexistent_raises(self):
        reg = ConstraintRegistry()
        with pytest.raises(ValueError, match="not found"):
            reg.reject_provisional("nonexistent")


class TestHaltExpiry:
    def test_expire_for_halt(self):
        reg = ConstraintRegistry()
        c1 = reg.declare_emergency("trigger1", "node_A", "halt-001")
        c2 = reg.declare_emergency("trigger2", "node_B", "halt-001")
        c3 = reg.declare_emergency("trigger3", "node_C", "halt-002")

        expired = reg.expire_for_halt("halt-001")
        assert len(expired) == 2
        assert c1.constraint_id in expired
        assert c2.constraint_id in expired

        # c3 should still be active
        assert reg.get(c3.constraint_id) is not None

    def test_expire_returns_empty_for_no_match(self):
        reg = ConstraintRegistry()
        expired = reg.expire_for_halt("halt-999")
        assert expired == []


class TestConstraintFrozen:
    def test_constraint_is_frozen(self):
        c = _make_constraint()
        with pytest.raises(AttributeError):
            c.label = "modified"


class TestSeverityClassEnum:
    def test_all_values(self):
        assert SeverityClass.ADVISORY.value == "ADVISORY"
        assert SeverityClass.HOLD_REQUIRED.value == "HOLD_REQUIRED"
        assert SeverityClass.HALT_REQUIRED.value == "HALT_REQUIRED"
