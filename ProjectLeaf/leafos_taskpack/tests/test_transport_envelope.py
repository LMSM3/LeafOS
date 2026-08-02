#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "leaf_usb_interceptor_envelope_test",
    ROOT / "core" / "python" / "leaf_usb_interceptor.py",
)
transport = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(transport)


class TransportEnvelopeTests(unittest.TestCase):
    def envelope(self, **overrides):
        values = {
            "direction": "inbound",
            "message_id": "msg-envelope-001",
            "sequence": 1,
            "sender_id": "fixture-device",
            "target_id": "leafos-host",
            "target_run": "active",
            "payload_type": "monitor.snapshot",
            "payload": {"after": 0, "heartbeat_timeout": 90},
        }
        values.update(overrides)
        return transport.make_envelope(**values)

    def test_make_and_validate_round_trip(self):
        envelope = self.envelope()
        self.assertEqual("leafos.transport.envelope", envelope["leafos_object"])
        self.assertEqual(envelope, transport.validate_envelope(envelope))
        self.assertTrue(envelope["payload_sha256"].startswith("sha256:"))

    def test_payload_tampering_is_rejected(self):
        envelope = self.envelope()
        envelope["payload"]["after"] = 9
        with self.assertRaisesRegex(ValueError, "hash"):
            transport.validate_envelope(envelope)

    def test_expired_envelope_is_rejected(self):
        envelope = self.envelope()
        created = datetime.now(timezone.utc) - timedelta(minutes=2)
        envelope["created_utc"] = created.isoformat()
        envelope["expires_utc"] = (created + timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "expired"):
            transport.validate_envelope(envelope)

    def test_unknown_fields_and_direction_types_are_rejected(self):
        envelope = self.envelope()
        envelope["debug"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            transport.validate_envelope(envelope)

        envelope = self.envelope()
        envelope["direction"] = "outbound"
        with self.assertRaisesRegex(ValueError, "direction"):
            transport.validate_envelope(envelope)

        envelope = self.envelope()
        envelope["payload_type"] = "run.stop"
        envelope["payload"] = {"action": "run.stop"}
        envelope["payload_sha256"] = transport.digest_payload(envelope["payload"])
        with self.assertRaisesRegex(ValueError, "payload must contain"):
            transport._validate_payload(envelope)

        envelope = self.envelope()
        envelope["payload_type"] = ["monitor.snapshot"]
        with self.assertRaisesRegex(ValueError, "payload_type must be a string"):
            transport.validate_envelope(envelope)

    def test_outbound_ack_has_an_outbound_only_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            transport.initialize(root, "fixture-usb")
            inbound = self.envelope()
            outbound, _ = transport._write_outbound(root, inbound, "accepted", result={"ok": True})
            self.assertEqual("outbound", outbound["direction"])
            self.assertEqual("transport.ack", outbound["payload_type"])
            transport.validate_envelope(outbound, expected_direction="outbound")
            self.assertNotEqual(copy.deepcopy(inbound), outbound)


if __name__ == "__main__":
    unittest.main()
