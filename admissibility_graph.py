"""Upstream admissibility boundary: closed graph topology + 10 named rules.

Position in pipeline: SECOND — after X-layer generates packet, before pressure.
Combines structural graph checks with interpretive admissibility rules.

signal → XPacket → [ADMISSIBILITY_BOUNDARY] → admitted/denied → pressure → ...

Fail-closed: only explicitly declared edges are permitted.
All unspecified states are impermissible by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from x_layer import (
    ConfidenceClass,
    ConsequenceClass,
    Node,
    TransitionKind,
    XPacket,
    MENTAL_STATE_KEYWORDS,
    PROHIBITED_PATTERNS,
    SCOPE_EXPANSION_MARKERS,
    TEMPORAL_DRIFT_MARKERS,
    ASSUMPTION_COUNT_THRESHOLD,
)
from constraint_declaration import Constraint


# ── Rule failure record ──

@dataclass(frozen=True)
class RuleFailure:
    """A single admissibility rule failure."""
    rule: str
    reason: str


# ── Graph topology ──

@dataclass(frozen=True)
class EdgeSpec:
    """Declared edge in the closed admissibility graph."""
    source: Node
    target: Node
    allowed_kinds: frozenset[str]
    allowed_authorities: frozenset[str]


# Default declared edges (fail-closed: only these are permitted)
DECLARED_EDGES: tuple[EdgeSpec, ...] = (
    EdgeSpec(Node.OBSERVE, Node.INTERPRET_X, frozenset({"signal"}), frozenset({"sensor"})),
    EdgeSpec(Node.INTERPRET_X, Node.VERIFY, frozenset({"interpretation"}), frozenset({"x_layer"})),
    EdgeSpec(Node.VERIFY, Node.ROUTE, frozenset({"verified_transition"}), frozenset({"verifier"})),
    EdgeSpec(Node.VERIFY, Node.STOP, frozenset({"rejection"}), frozenset({"verifier"})),
)


class ClosedAdmissibilityGraph:
    """Closed graph where only explicitly declared edges are permitted.

    Any undeclared edge is denied. Fail-closed by design.
    """

    def __init__(self, edges: tuple[EdgeSpec, ...] | None = None) -> None:
        edges = edges if edges is not None else DECLARED_EDGES
        self._edges: dict[tuple[str, str], EdgeSpec] = {}
        for e in edges:
            self._edges[(e.source.value, e.target.value)] = e

    def edge_exists(self, source: str, target: str) -> bool:
        return (source, target) in self._edges

    def check_transit(self, source: str, target: str, kind: str) -> tuple[bool, str]:
        """Check if a transit is allowed on the graph.

        Returns (allowed, reason).
        """
        key = (source, target)
        if key not in self._edges:
            return False, f"No declared edge from {source} to {target}"
        edge = self._edges[key]
        if kind not in edge.allowed_kinds:
            return False, f"Kind '{kind}' not allowed on edge {source}->{target} (allowed: {edge.allowed_kinds})"
        return True, "graph_ok"


# ── The 10 admissibility rules ──

def rule_evidence_anchor_required(packet: XPacket) -> tuple[bool, str]:
    """Rule 1: source_span must be non-empty."""
    if not packet.source_span or not packet.source_span.strip():
        return False, "source_span is empty — no evidence anchor"
    return True, ""


def rule_assumption_count_bound(packet: XPacket) -> tuple[bool, str]:
    """Rule 2: assumptions count must not exceed threshold."""
    if len(packet.assumptions) > ASSUMPTION_COUNT_THRESHOLD:
        return False, f"assumptions count {len(packet.assumptions)} exceeds threshold {ASSUMPTION_COUNT_THRESHOLD}"
    return True, ""


def rule_ambiguity_preservation_required(packet: XPacket) -> tuple[bool, str]:
    """Rule 3: if ambiguity_markers exist, omitted_alternatives must document what was collapsed."""
    if packet.ambiguity_markers and not packet.omitted_alternatives:
        return False, "ambiguity_markers present but omitted_alternatives empty — undocumented collapse"
    return True, ""


def rule_confidence_consequence_match(packet: XPacket) -> tuple[bool, str]:
    """Rule 4: HIGH/CRITICAL consequence cannot pair with LOW confidence."""
    if packet.consequence_class in (ConsequenceClass.HIGH, ConsequenceClass.CRITICAL):
        if packet.confidence_class == ConfidenceClass.LOW:
            return False, f"consequence={packet.consequence_class.value} with confidence=LOW is inadmissible"
    return True, ""


def rule_actor_intent_attribution_ban(packet: XPacket) -> tuple[bool, str]:
    """Rule 5: claimed_intent cannot attribute mental states without evidence in source_span."""
    intent_lower = packet.claimed_intent.lower()
    span_lower = packet.source_span.lower()
    for keyword in MENTAL_STATE_KEYWORDS:
        if keyword in intent_lower and keyword not in span_lower:
            return False, f"mental-state attribution '{keyword}' in claimed_intent without evidence in source_span"
    return True, ""


def rule_scope_drift_fail(packet: XPacket) -> tuple[bool, str]:
    """Rule 6: claimed_object must not expand scope beyond source_span."""
    obj_lower = packet.claimed_object.lower()
    span_lower = packet.source_span.lower()
    for marker in SCOPE_EXPANSION_MARKERS:
        if marker in obj_lower and marker not in span_lower:
            return False, f"scope expansion marker '{marker.strip()}' in claimed_object not present in source_span"
    return True, ""


def rule_temporal_drift_fail(packet: XPacket) -> tuple[bool, str]:
    """Rule 7: no temporal claims not present in source_span."""
    obj_lower = packet.claimed_object.lower()
    intent_lower = packet.claimed_intent.lower()
    span_lower = packet.source_span.lower()
    combined = obj_lower + " " + intent_lower
    for marker in TEMPORAL_DRIFT_MARKERS:
        if marker in combined and marker not in span_lower:
            return False, f"temporal drift marker '{marker}' not present in source_span"
    return True, ""


def rule_prohibited_inferential_jump(packet: XPacket) -> tuple[bool, str]:
    """Rule 8: banned inferential patterns."""
    intent_lower = packet.claimed_intent.lower()
    obj_lower = packet.claimed_object.lower()
    combined = obj_lower + " " + intent_lower
    for pattern in PROHIBITED_PATTERNS:
        readable = pattern.replace("_", " ")
        if readable in combined or pattern in combined:
            return False, f"prohibited inferential jump: {pattern}"
    return True, ""


def rule_provenance_required(packet: XPacket) -> tuple[bool, str]:
    """Rule 9: signal_id and provenance_hash must be non-empty."""
    if not packet.signal_id or not packet.signal_id.strip():
        return False, "signal_id is empty — no provenance"
    if not packet.provenance_hash or not packet.provenance_hash.strip():
        return False, "provenance_hash is empty — no provenance chain"
    return True, ""


def rule_omitted_alternative_detection(packet: XPacket) -> tuple[bool, str]:
    """Rule 10: if ambiguity_markers exist, omitted_alternatives must be non-empty."""
    if packet.ambiguity_markers and not packet.omitted_alternatives:
        return False, "ambiguity_markers present but no omitted_alternatives declared"
    return True, ""


# ── Rule registry ──

RULES: tuple[tuple[str, object], ...] = (
    ("EVIDENCE_ANCHOR_REQUIRED", rule_evidence_anchor_required),
    ("ASSUMPTION_COUNT_BOUND", rule_assumption_count_bound),
    ("AMBIGUITY_PRESERVATION_REQUIRED", rule_ambiguity_preservation_required),
    ("CONFIDENCE_CONSEQUENCE_MATCH", rule_confidence_consequence_match),
    ("ACTOR_INTENT_ATTRIBUTION_BAN", rule_actor_intent_attribution_ban),
    ("SCOPE_DRIFT_FAIL", rule_scope_drift_fail),
    ("TEMPORAL_DRIFT_FAIL", rule_temporal_drift_fail),
    ("PROHIBITED_INFERENTIAL_JUMP", rule_prohibited_inferential_jump),
    ("PROVENANCE_REQUIRED", rule_provenance_required),
    ("OMITTED_ALTERNATIVE_DETECTION", rule_omitted_alternative_detection),
)


def evaluate_rules(packet: XPacket) -> tuple[RuleFailure, ...]:
    """Run all 10 admissibility rules against a packet. Returns tuple of failures."""
    failures = []
    for rule_name, rule_fn in RULES:
        passed, reason = rule_fn(packet)
        if not passed:
            failures.append(RuleFailure(rule=rule_name, reason=reason))
    return tuple(failures)


# ── Admissibility result ──

@dataclass(frozen=True)
class AdmissibilityResult:
    """Result of a full upstream admissibility check."""
    admitted: bool
    packet_id: str
    rule_failures: tuple[RuleFailure, ...] = field(default_factory=tuple)
    graph_failure: str | None = None
    constraint_failures: tuple[str, ...] = field(default_factory=tuple)


class AdmissibilityBoundary:
    """Full upstream admissibility check: graph + 10 rules + constraints.

    Fail-closed: any failure in any layer → denied.
    """

    def __init__(
        self,
        graph: ClosedAdmissibilityGraph,
        active_constraints: list[Constraint] | None = None,
    ) -> None:
        self._graph = graph
        self._constraints = active_constraints or []

    def update_constraints(self, constraints: list[Constraint]) -> None:
        self._constraints = constraints

    def check(self, packet: XPacket) -> AdmissibilityResult:
        """Full upstream admissibility check.

        1. Graph check: declared edge exists, kind allowed
        2. 10 interpretive rules
        3. Active constraints not violated

        Fail-closed: any failure → denied.
        """
        # ── Graph check ──
        graph_ok, graph_reason = self._graph.check_transit(
            packet.source_node, packet.target_node, packet.transition_kind,
        )
        graph_failure = None if graph_ok else graph_reason

        # ── Rule checks ──
        rule_failures = evaluate_rules(packet)

        # ── Constraint checks ──
        constraint_failures = []
        for c in self._constraints:
            trigger_lower = c.trigger_test.lower()
            # Check if the constraint's trigger condition matches packet data
            packet_text = (
                f"{packet.claimed_object} {packet.claimed_intent} "
                f"{packet.source_span} {packet.transition_kind}"
            ).lower()
            if trigger_lower and trigger_lower in packet_text:
                constraint_failures.append(c.constraint_id)

        admitted = (
            graph_failure is None
            and len(rule_failures) == 0
            and len(constraint_failures) == 0
        )

        return AdmissibilityResult(
            admitted=admitted,
            packet_id=packet.packet_id,
            rule_failures=rule_failures,
            graph_failure=graph_failure,
            constraint_failures=tuple(constraint_failures),
        )
