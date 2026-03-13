"""X-Layer: Constrained interpretive packet generation.

Position in pipeline: FIRST — generates typed transit packets from raw signals.
X is NOT authority. NOT execution. Only typed transit.

signal → [X_LAYER] → XPacket → admissibility_check → ...
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ConfidenceClass(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ConsequenceClass(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TransitionKind(Enum):
    SIGNAL = "signal"
    INTERPRETATION = "interpretation"
    VERIFIED_TRANSITION = "verified_transition"
    REJECTION = "rejection"


class Node(Enum):
    OBSERVE = "OBSERVE"
    INTERPRET_X = "INTERPRET_X"
    VERIFY = "VERIFY"
    ROUTE = "ROUTE"
    STOP = "STOP"


class Sector(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class SignalEnvelope:
    """Raw signal intake — immutable."""
    source_id: str
    timestamp: str
    content: str
    content_type: str
    provenance_hash: str


@dataclass(frozen=True)
class XPacket:
    """Constrained interpretive transit packet — frozen, immutable.

    Every field is explicit. No hidden state, no implicit authority.
    """
    packet_id: str
    signal_id: str
    source_node: str
    target_node: str
    transition_kind: str
    claimed_object: str
    claimed_intent: str
    source_span: str
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    ambiguity_markers: tuple[str, ...] = field(default_factory=tuple)
    omitted_alternatives: tuple[str, ...] = field(default_factory=tuple)
    confidence_class: ConfidenceClass = ConfidenceClass.MEDIUM
    consequence_class: ConsequenceClass = ConsequenceClass.LOW
    provenance_hash: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class WrapLock:
    """Provenance lock from Engine patch §10.

    Verifiable at three points: pre-wrap, post-wrap, on-read.
    """
    claim_hash: str
    provenance_hash: str
    wrapper_id: str
    wrapper_timestamp: str


# ── Mental-state keywords banned without evidence ──
MENTAL_STATE_KEYWORDS: tuple[str, ...] = (
    "believes", "intends", "wants", "fears", "hopes",
    "knows", "thinks", "feels", "motivated by", "trying to",
)

# ── Prohibited inferential jumps ──
PROHIBITED_PATTERNS: tuple[str, ...] = (
    "correlation_to_causation",
    "absence_to_denial",
    "silence_as_agreement",
    "partial_to_universal",
)

# ── Scope-drift expansion markers ──
SCOPE_EXPANSION_MARKERS: tuple[str, ...] = (
    "all ", "every ", "always ", "never ",
)

# ── Temporal-drift markers ──
TEMPORAL_DRIFT_MARKERS: tuple[str, ...] = (
    "historically", "in the past", "will always",
    "has always been", "never was", "forever",
)

ASSUMPTION_COUNT_THRESHOLD = 3


class XLayer:
    """Generates constrained interpretive packets from raw signals.

    Validates minimum structural requirements. Fails closed:
    any missing or invalid field raises ValueError.
    """

    def generate_packet(
        self,
        signal: SignalEnvelope,
        interpretation: dict,
    ) -> XPacket:
        """Generate a typed transit packet from raw signal + interpretation fields.

        Required interpretation keys:
            source_node, target_node, transition_kind,
            claimed_object, claimed_intent, source_span

        Optional interpretation keys:
            assumptions, ambiguity_markers, omitted_alternatives,
            confidence_class, consequence_class
        """
        # ── Fail-closed: require signal ──
        if not signal.source_id:
            raise ValueError("signal.source_id required")
        if not signal.content:
            raise ValueError("signal.content required")
        if not signal.provenance_hash:
            raise ValueError("signal.provenance_hash required")

        # ── Fail-closed: require interpretation fields ──
        required = (
            "source_node", "target_node", "transition_kind",
            "claimed_object", "claimed_intent", "source_span",
        )
        for key in required:
            val = interpretation.get(key, "")
            if not val or not str(val).strip():
                raise ValueError(f"interpretation['{key}'] required")

        # ── Parse enums ──
        confidence = interpretation.get("confidence_class", "MEDIUM")
        if isinstance(confidence, str):
            confidence = ConfidenceClass(confidence)

        consequence = interpretation.get("consequence_class", "LOW")
        if isinstance(consequence, str):
            consequence = ConsequenceClass(consequence)

        # ── Build provenance hash ──
        prov = signal.provenance_hash

        now = datetime.now(timezone.utc).isoformat()

        return XPacket(
            packet_id=str(uuid.uuid4()),
            signal_id=signal.source_id,
            source_node=interpretation["source_node"],
            target_node=interpretation["target_node"],
            transition_kind=interpretation["transition_kind"],
            claimed_object=interpretation["claimed_object"],
            claimed_intent=interpretation["claimed_intent"],
            source_span=interpretation["source_span"],
            assumptions=tuple(interpretation.get("assumptions", ())),
            ambiguity_markers=tuple(interpretation.get("ambiguity_markers", ())),
            omitted_alternatives=tuple(interpretation.get("omitted_alternatives", ())),
            confidence_class=confidence,
            consequence_class=consequence,
            provenance_hash=prov,
            timestamp=now,
        )

    def compute_wrap_lock(self, packet: XPacket) -> WrapLock:
        """Compute a provenance lock for the packet.

        Verifiable at pre-wrap, post-wrap, and on-read.
        """
        claim_data = f"{packet.claimed_object}|{packet.claimed_intent}|{packet.source_span}"
        claim_hash = hashlib.sha256(claim_data.encode()).hexdigest()

        return WrapLock(
            claim_hash=claim_hash,
            provenance_hash=packet.provenance_hash,
            wrapper_id=packet.packet_id,
            wrapper_timestamp=packet.timestamp,
        )

    def verify_wrap_lock(self, packet: XPacket, lock: WrapLock) -> bool:
        """Verify that a wrap lock matches the packet. Returns False on mismatch."""
        claim_data = f"{packet.claimed_object}|{packet.claimed_intent}|{packet.source_span}"
        claim_hash = hashlib.sha256(claim_data.encode()).hexdigest()
        return (
            lock.claim_hash == claim_hash
            and lock.provenance_hash == packet.provenance_hash
            and lock.wrapper_id == packet.packet_id
        )
