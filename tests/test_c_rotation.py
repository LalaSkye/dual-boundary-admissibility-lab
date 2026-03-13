"""Tests for c_rotation.py — C-sector rotation with defensive routing."""
from __future__ import annotations

import pytest

from pressure_monitor import PressureMonitor, PressureSource
from c_rotation import CRotationEngine, CAssertion, MultiCResolution, RotationEvent


def _make_pressure_monitor(pressure_score: float = 0.0) -> PressureMonitor:
    mon = PressureMonitor()
    if pressure_score > 0.0:
        for source in PressureSource:
            mon.make_event(source=source, score=pressure_score, detail="test pressure")
    return mon


class TestCRotationBasic:
    def test_no_rotation_low_pressure(self):
        mon = _make_pressure_monitor(0.1)
        engine = CRotationEngine(mon)
        event = engine.check_and_rotate()
        assert event is None
        assert engine.c_active is False

    def test_rotation_on_high_pressure(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        event = engine.check_and_rotate(trigger_node="node_B")
        assert event is not None
        assert isinstance(event, RotationEvent)
        assert engine.c_active is True
        assert engine.active_c_node == "node_B"

    def test_rotation_emits_prior_and_new_maps(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        event = engine.check_and_rotate()
        assert "C" in event.prior_role_map
        assert "C" in event.new_role_map
        assert event.prior_role_map["C"] != event.new_role_map["C"]

    def test_no_re_rotation_without_halt(self):
        """No mid-claim rotation unless HALT or HOLD active."""
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        event1 = engine.check_and_rotate()
        assert event1 is not None

        event2 = engine.check_and_rotate()
        assert event2 is None  # Already rotated, no HALT/HOLD

    def test_re_rotation_with_halt(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        engine.check_and_rotate()
        engine.set_halt_active(True)
        event2 = engine.check_and_rotate()
        assert event2 is not None

    def test_re_rotation_with_hold(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        engine.check_and_rotate()
        engine.set_hold_active(True)
        event2 = engine.check_and_rotate()
        assert event2 is not None


class TestForceRotation:
    def test_force_rotate(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        event = engine.force_rotate(
            trigger_type="halt_reconfiguration",
            authorising_source="admin",
            rationale="forced for test",
        )
        assert engine.c_active is True
        assert event.trigger_type == "halt_reconfiguration"
        assert event.self_recusal is False

    def test_force_rotate_self_recusal(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        event = engine.force_rotate(
            trigger_type="manual_reassignment",
            authorising_source="node_C",
            rationale="C self-recusing",
            self_recusal=True,
        )
        assert event.self_recusal is True

    def test_rotation_log(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        engine.check_and_rotate()
        engine.set_halt_active(True)
        engine.check_and_rotate()
        assert len(engine.rotation_log) == 2


class TestMultiCResolution:
    def test_single_assertion(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        a = CAssertion("a1", "node_A", "2025-01-01T00:00:00Z", 0.8, "test")
        result = engine.resolve_multi_c([a])
        assert result.active_c == "node_A"
        assert result.halt_required is False

    def test_earliest_timestamp_wins(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:02Z", 0.8, "test"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:01Z", 0.8, "test"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.active_c == "node_B"  # earlier timestamp
        assert result.resolution_method == "earliest_timestamp"
        assert result.halt_required is True

    def test_signal_relevance_tiebreak(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:00Z", 0.5, "test"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:00Z", 0.9, "test"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.active_c == "node_B"  # higher relevance
        assert result.resolution_method == "signal_relevance"
        assert result.halt_required is True

    def test_timestamp_collision_same_relevance(self):
        """Multi-C timestamp collision → HOLD_FOR_RESOLUTION."""
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        assertions = [
            CAssertion("a1", "node_A", "2025-01-01T00:00:00Z", 0.8, "test"),
            CAssertion("a2", "node_B", "2025-01-01T00:00:00Z", 0.8, "test"),
        ]
        result = engine.resolve_multi_c(assertions)
        assert result.resolution_method == "HOLD_FOR_RESOLUTION"
        assert result.halt_required is True

    def test_empty_assertions_raises(self):
        mon = PressureMonitor()
        engine = CRotationEngine(mon)
        with pytest.raises(ValueError):
            engine.resolve_multi_c([])


class TestCRotationReset:
    def test_reset(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        engine.check_and_rotate()
        assert engine.c_active is True
        engine.reset()
        assert engine.c_active is False
        assert engine.active_c_node == ""


class TestRotationEventFrozen:
    def test_event_is_frozen(self):
        mon = _make_pressure_monitor(0.9)
        engine = CRotationEngine(mon)
        event = engine.check_and_rotate()
        with pytest.raises(AttributeError):
            event.trigger_type = "modified"
