"""Tests for pressure_monitor.py — pressure tracking and signal quality."""
from __future__ import annotations

import pytest

from pressure_monitor import (
    PressureMonitor,
    PressureAssessment,
    PressureEvent,
    PressureSource,
    SignalQuality,
)


class TestSignalQualityEvaluation:
    def test_good_quality(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.8, 0.9, 0.7)
        assert quality == SignalQuality.GOOD

    def test_degraded_quality(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.5, 0.9, 0.7)
        assert quality == SignalQuality.DEGRADED

    def test_insufficient_quality(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.2, 0.9, 0.7)
        assert quality == SignalQuality.INSUFFICIENT

    def test_all_low_is_insufficient(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.1, 0.1, 0.1)
        assert quality == SignalQuality.INSUFFICIENT

    def test_all_high_is_good(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(1.0, 1.0, 1.0)
        assert quality == SignalQuality.GOOD

    def test_boundary_exactly_0_7_is_good(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.7, 0.7, 0.7)
        assert quality == SignalQuality.GOOD

    def test_boundary_just_below_0_3_is_insufficient(self):
        mon = PressureMonitor()
        quality = mon.evaluate_signal_quality(0.29, 0.9, 0.9)
        assert quality == SignalQuality.INSUFFICIENT

    def test_invalid_axis_raises(self):
        mon = PressureMonitor()
        with pytest.raises(ValueError):
            mon.evaluate_signal_quality(-0.1, 0.5, 0.5)
        with pytest.raises(ValueError):
            mon.evaluate_signal_quality(0.5, 1.1, 0.5)


class TestPressureMonitorInit:
    def test_default_thresholds(self):
        mon = PressureMonitor()
        assert mon.notice_threshold == 0.3
        assert mon.interrupt_threshold == 0.7

    def test_custom_thresholds(self):
        mon = PressureMonitor(notice_threshold=0.2, interrupt_threshold=0.8)
        assert mon.notice_threshold == 0.2
        assert mon.interrupt_threshold == 0.8

    def test_invalid_thresholds(self):
        with pytest.raises(ValueError):
            PressureMonitor(notice_threshold=-0.1)
        with pytest.raises(ValueError):
            PressureMonitor(interrupt_threshold=1.5)
        with pytest.raises(ValueError):
            PressureMonitor(notice_threshold=0.8, interrupt_threshold=0.3)


class TestPressureRecording:
    def test_record_event(self):
        mon = PressureMonitor()
        event = PressureEvent(
            event_id="ev-001",
            source=PressureSource.DEGRADED_SIGNAL,
            score=0.5,
            detail="test",
            timestamp="2025-01-01T00:00:00Z",
        )
        mon.record_pressure(event)
        assert len(mon.events) == 1

    def test_make_event(self):
        mon = PressureMonitor()
        event = mon.make_event(
            source=PressureSource.THRESHOLD_PROXIMITY,
            score=0.6,
            detail="approaching threshold",
        )
        assert event.source == PressureSource.THRESHOLD_PROXIMITY
        assert event.score == 0.6
        assert len(mon.events) == 1

    def test_invalid_score_raises(self):
        mon = PressureMonitor()
        with pytest.raises(ValueError):
            event = PressureEvent("ev", PressureSource.DEGRADED_SIGNAL, 1.5, "bad", "ts")
            mon.record_pressure(event)

    def test_clear(self):
        mon = PressureMonitor()
        mon.make_event(PressureSource.DEGRADED_SIGNAL, 0.5, "test")
        mon.clear()
        assert len(mon.events) == 0


class TestPressureAssessment:
    def test_route_no_pressure(self):
        mon = PressureMonitor()
        assessment = mon.assess()
        assert assessment.recommendation == "route"
        assert assessment.total_pressure == 0.0

    def test_hold_degraded_signal(self):
        mon = PressureMonitor()
        mon.evaluate_signal_quality(0.5, 0.5, 0.5)
        assessment = mon.assess()
        assert assessment.recommendation == "hold"
        assert assessment.signal_quality == SignalQuality.DEGRADED

    def test_hold_insufficient_signal(self):
        mon = PressureMonitor()
        mon.evaluate_signal_quality(0.1, 0.1, 0.1)
        assessment = mon.assess()
        assert assessment.recommendation == "hold"
        assert assessment.signal_quality == SignalQuality.INSUFFICIENT

    def test_rotate_c_high_pressure(self):
        mon = PressureMonitor()
        # Push pressure above interrupt threshold
        for source in PressureSource:
            mon.make_event(source=source, score=0.9, detail="high pressure")
        assessment = mon.assess()
        assert assessment.recommendation == "rotate_c"
        assert assessment.total_pressure >= 0.7

    def test_hold_medium_pressure(self):
        mon = PressureMonitor()
        mon.make_event(PressureSource.DEGRADED_SIGNAL, 0.5, "medium")
        mon.make_event(PressureSource.ROUTE_CONGESTION, 0.4, "medium")
        assessment = mon.assess()
        # total_pressure = (0.5 + 0.4) / 5 = 0.18, but >= notice (0.3)? No, 0.18 < 0.3
        # So should be "route" unless signal quality is degraded
        # Let's verify
        assert assessment.recommendation == "route"

    def test_route_low_pressure(self):
        mon = PressureMonitor()
        mon.make_event(PressureSource.DEGRADED_SIGNAL, 0.1, "low")
        assessment = mon.assess()
        assert assessment.recommendation == "route"

    def test_halt_never_from_pressure_alone(self):
        """CRITICAL INVARIANT: Pressure alone never recommends HALT."""
        mon = PressureMonitor()
        for source in PressureSource:
            mon.make_event(source=source, score=1.0, detail="max pressure")
        assessment = mon.assess()
        assert assessment.recommendation != "halt"

    def test_assessment_is_frozen(self):
        mon = PressureMonitor()
        assessment = mon.assess()
        with pytest.raises(AttributeError):
            assessment.total_pressure = 0.5


class TestPressureEventFrozen:
    def test_event_is_frozen(self):
        event = PressureEvent("ev-001", PressureSource.DEGRADED_SIGNAL, 0.5, "test", "ts")
        with pytest.raises(AttributeError):
            event.score = 0.9
