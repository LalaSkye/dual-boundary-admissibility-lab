"""Pressure tracking and signal quality evaluation.

Position in pipeline: THIRD — after admissibility check, informs routing.
Tracks five pressure sources and evaluates signal quality on three axes.

... → admissibility_result → [PRESSURE_MONITOR] → assessment → {route|rotate|hold|halt}

CRITICAL INVARIANT: Weak signal alone does not justify HALT.
HALT requires boundary evidence, not merely fuzziness.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SignalQuality(Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class PressureSource(Enum):
    DEGRADED_SIGNAL = "DEGRADED_SIGNAL"
    THRESHOLD_PROXIMITY = "THRESHOLD_PROXIMITY"
    ROUTE_CONGESTION = "ROUTE_CONGESTION"
    CONFLICTING_C = "CONFLICTING_C"
    EMERGENT_CONSTRAINT = "EMERGENT_CONSTRAINT"


@dataclass(frozen=True)
class PressureEvent:
    """A single pressure event — frozen, immutable."""
    event_id: str
    source: PressureSource
    score: float  # 0.0 to 1.0
    detail: str
    timestamp: str


@dataclass(frozen=True)
class PressureAssessment:
    """Current pressure state and recommended action."""
    total_pressure: float
    recommendation: str  # "route" | "rotate_c" | "hold" | "halt"
    active_sources: tuple[PressureEvent, ...]
    signal_quality: SignalQuality


class PressureMonitor:
    """Tracks pressure from five sources and evaluates signal quality.

    Sentinel thresholds from Engine patch §9:
    - anomaly_score < notice_threshold → continue
    - notice_threshold ≤ anomaly_score < interrupt_threshold → HOLD-style check
    - anomaly_score ≥ interrupt_threshold → C assertion candidate

    Signal quality routing from Engine patch §6:
    - GOOD → normal processing ("route")
    - DEGRADED → HOLD + sentinel check
    - INSUFFICIENT → HOLD with signal request
    """

    def __init__(
        self,
        notice_threshold: float = 0.3,
        interrupt_threshold: float = 0.7,
    ) -> None:
        if notice_threshold < 0.0 or notice_threshold > 1.0:
            raise ValueError("notice_threshold must be in [0.0, 1.0]")
        if interrupt_threshold < 0.0 or interrupt_threshold > 1.0:
            raise ValueError("interrupt_threshold must be in [0.0, 1.0]")
        if notice_threshold >= interrupt_threshold:
            raise ValueError("notice_threshold must be < interrupt_threshold")

        self._notice_threshold = notice_threshold
        self._interrupt_threshold = interrupt_threshold
        self._events: list[PressureEvent] = []
        self._signal_quality: SignalQuality = SignalQuality.GOOD

    @property
    def notice_threshold(self) -> float:
        return self._notice_threshold

    @property
    def interrupt_threshold(self) -> float:
        return self._interrupt_threshold

    @property
    def events(self) -> list[PressureEvent]:
        return list(self._events)

    def evaluate_signal_quality(
        self,
        completeness: float,
        coherence: float,
        provenance_confidence: float,
    ) -> SignalQuality:
        """Evaluate signal quality on three axes.

        Each axis is [0.0, 1.0]. Quality classification:
        - All >= 0.7 → GOOD
        - Any < 0.3 → INSUFFICIENT
        - Otherwise → DEGRADED
        """
        axes = [completeness, coherence, provenance_confidence]
        for val in axes:
            if val < 0.0 or val > 1.0:
                raise ValueError(f"Signal quality axis must be in [0.0, 1.0], got {val}")

        if any(v < 0.3 for v in axes):
            quality = SignalQuality.INSUFFICIENT
        elif all(v >= 0.7 for v in axes):
            quality = SignalQuality.GOOD
        else:
            quality = SignalQuality.DEGRADED

        self._signal_quality = quality
        return quality

    def record_pressure(self, event: PressureEvent) -> None:
        """Record a pressure event."""
        if event.score < 0.0 or event.score > 1.0:
            raise ValueError(f"Pressure score must be in [0.0, 1.0], got {event.score}")
        self._events.append(event)

    def make_event(
        self,
        source: PressureSource,
        score: float,
        detail: str,
    ) -> PressureEvent:
        """Convenience: create and record a pressure event."""
        event = PressureEvent(
            event_id=str(uuid.uuid4()),
            source=source,
            score=score,
            detail=detail,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.record_pressure(event)
        return event

    def assess(self) -> PressureAssessment:
        """Returns current pressure state and recommended action.

        Routing logic:
        - INSUFFICIENT signal → "hold" (signal request)
        - total_pressure >= interrupt_threshold → "rotate_c" (C rotation candidate)
        - DEGRADED signal or total_pressure >= notice_threshold → "hold"
        - Otherwise → "route" (normal processing)

        INVARIANT: HALT is never recommended by pressure alone.
        HALT requires boundary evidence (constraint trigger), not just fuzziness.
        """
        # Compute total pressure as max of recent scores per source
        source_max: dict[PressureSource, float] = {}
        for ev in self._events:
            if ev.source not in source_max or ev.score > source_max[ev.source]:
                source_max[ev.source] = ev.score

        total = sum(source_max.values()) / max(len(PressureSource), 1)
        # Normalize: cap at 1.0
        total = min(total, 1.0)

        active = tuple(self._events)
        quality = self._signal_quality

        # Routing decision
        if quality == SignalQuality.INSUFFICIENT:
            recommendation = "hold"
        elif total >= self._interrupt_threshold:
            recommendation = "rotate_c"
        elif quality == SignalQuality.DEGRADED or total >= self._notice_threshold:
            recommendation = "hold"
        else:
            recommendation = "route"

        return PressureAssessment(
            total_pressure=round(total, 4),
            recommendation=recommendation,
            active_sources=active,
            signal_quality=quality,
        )

    def clear(self) -> None:
        """Reset pressure state."""
        self._events.clear()
        self._signal_quality = SignalQuality.GOOD
