"""Tests for x_layer.py — X-Layer packet generation."""
from __future__ import annotations

import pytest

from x_layer import (
    XLayer,
    XPacket,
    SignalEnvelope,
    ConfidenceClass,
    ConsequenceClass,
    WrapLock,
)


def _make_signal(**overrides) -> SignalEnvelope:
    defaults = {
        "source_id": "sig-001",
        "timestamp": "2025-01-01T00:00:00Z",
        "content": "The system observed anomalous behavior",
        "content_type": "text/plain",
        "provenance_hash": "abc123hash",
    }
    defaults.update(overrides)
    return SignalEnvelope(**defaults)


def _make_interpretation(**overrides) -> dict:
    defaults = {
        "source_node": "OBSERVE",
        "target_node": "INTERPRET_X",
        "transition_kind": "signal",
        "claimed_object": "anomalous behavior",
        "claimed_intent": "flagging for review",
        "source_span": "The system observed anomalous behavior",
    }
    defaults.update(overrides)
    return defaults


class TestXLayerPacketGeneration:
    """Happy path: valid signal + interpretation → XPacket."""

    def test_basic_packet_generation(self):
        layer = XLayer()
        signal = _make_signal()
        interp = _make_interpretation()
        packet = layer.generate_packet(signal, interp)

        assert isinstance(packet, XPacket)
        assert packet.signal_id == "sig-001"
        assert packet.source_node == "OBSERVE"
        assert packet.target_node == "INTERPRET_X"
        assert packet.transition_kind == "signal"
        assert packet.claimed_object == "anomalous behavior"
        assert packet.claimed_intent == "flagging for review"
        assert packet.provenance_hash == "abc123hash"
        assert packet.packet_id  # non-empty
        assert packet.timestamp  # non-empty

    def test_default_confidence_consequence(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        assert packet.confidence_class == ConfidenceClass.MEDIUM
        assert packet.consequence_class == ConsequenceClass.LOW

    def test_explicit_confidence_consequence(self):
        layer = XLayer()
        interp = _make_interpretation(
            confidence_class="HIGH",
            consequence_class="CRITICAL",
        )
        packet = layer.generate_packet(_make_signal(), interp)
        assert packet.confidence_class == ConfidenceClass.HIGH
        assert packet.consequence_class == ConsequenceClass.CRITICAL

    def test_enum_confidence_consequence(self):
        layer = XLayer()
        interp = _make_interpretation(
            confidence_class=ConfidenceClass.LOW,
            consequence_class=ConsequenceClass.HIGH,
        )
        packet = layer.generate_packet(_make_signal(), interp)
        assert packet.confidence_class == ConfidenceClass.LOW
        assert packet.consequence_class == ConsequenceClass.HIGH

    def test_assumptions_and_markers(self):
        layer = XLayer()
        interp = _make_interpretation(
            assumptions=["a1", "a2"],
            ambiguity_markers=["m1"],
            omitted_alternatives=["alt1"],
        )
        packet = layer.generate_packet(_make_signal(), interp)
        assert packet.assumptions == ("a1", "a2")
        assert packet.ambiguity_markers == ("m1",)
        assert packet.omitted_alternatives == ("alt1",)

    def test_empty_optional_fields(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        assert packet.assumptions == ()
        assert packet.ambiguity_markers == ()
        assert packet.omitted_alternatives == ()


class TestXLayerFailClosed:
    """Fail-closed: missing data → ValueError."""

    def test_empty_source_id_raises(self):
        layer = XLayer()
        with pytest.raises(ValueError, match="source_id"):
            layer.generate_packet(
                _make_signal(source_id=""),
                _make_interpretation(),
            )

    def test_empty_content_raises(self):
        layer = XLayer()
        with pytest.raises(ValueError, match="content"):
            layer.generate_packet(
                _make_signal(content=""),
                _make_interpretation(),
            )

    def test_empty_provenance_hash_raises(self):
        layer = XLayer()
        with pytest.raises(ValueError, match="provenance_hash"):
            layer.generate_packet(
                _make_signal(provenance_hash=""),
                _make_interpretation(),
            )

    def test_missing_source_node_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["source_node"]
        with pytest.raises(ValueError, match="source_node"):
            layer.generate_packet(_make_signal(), interp)

    def test_missing_target_node_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["target_node"]
        with pytest.raises(ValueError, match="target_node"):
            layer.generate_packet(_make_signal(), interp)

    def test_missing_transition_kind_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["transition_kind"]
        with pytest.raises(ValueError, match="transition_kind"):
            layer.generate_packet(_make_signal(), interp)

    def test_missing_claimed_object_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["claimed_object"]
        with pytest.raises(ValueError, match="claimed_object"):
            layer.generate_packet(_make_signal(), interp)

    def test_missing_claimed_intent_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["claimed_intent"]
        with pytest.raises(ValueError, match="claimed_intent"):
            layer.generate_packet(_make_signal(), interp)

    def test_missing_source_span_raises(self):
        layer = XLayer()
        interp = _make_interpretation()
        del interp["source_span"]
        with pytest.raises(ValueError, match="source_span"):
            layer.generate_packet(_make_signal(), interp)

    def test_whitespace_only_source_span_raises(self):
        layer = XLayer()
        interp = _make_interpretation(source_span="   ")
        with pytest.raises(ValueError, match="source_span"):
            layer.generate_packet(_make_signal(), interp)


class TestXPacketFrozen:
    """XPacket is frozen — immutable."""

    def test_frozen_packet(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        with pytest.raises(AttributeError):
            packet.signal_id = "modified"


class TestWrapLock:
    """Provenance lock from Engine patch §10."""

    def test_compute_wrap_lock(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        lock = layer.compute_wrap_lock(packet)

        assert isinstance(lock, WrapLock)
        assert lock.claim_hash  # non-empty
        assert lock.provenance_hash == packet.provenance_hash
        assert lock.wrapper_id == packet.packet_id

    def test_verify_wrap_lock_valid(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        lock = layer.compute_wrap_lock(packet)
        assert layer.verify_wrap_lock(packet, lock) is True

    def test_verify_wrap_lock_tampered(self):
        layer = XLayer()
        packet = layer.generate_packet(_make_signal(), _make_interpretation())
        lock = layer.compute_wrap_lock(packet)

        # Tamper with lock
        tampered = WrapLock(
            claim_hash="tampered",
            provenance_hash=lock.provenance_hash,
            wrapper_id=lock.wrapper_id,
            wrapper_timestamp=lock.wrapper_timestamp,
        )
        assert layer.verify_wrap_lock(packet, tampered) is False

    def test_wrap_lock_different_packets(self):
        layer = XLayer()
        p1 = layer.generate_packet(_make_signal(), _make_interpretation())
        p2 = layer.generate_packet(
            _make_signal(),
            _make_interpretation(claimed_object="different claim"),
        )
        lock1 = layer.compute_wrap_lock(p1)
        assert layer.verify_wrap_lock(p2, lock1) is False
