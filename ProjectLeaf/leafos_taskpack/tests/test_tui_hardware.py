#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import socket
import sys
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TUI = ROOT / "core" / "ui" / "tui"
if str(TUI) not in sys.path:
    sys.path.insert(0, str(TUI))

import hardware_sampler
import native_bridge


def collected(gpu_percent: float = 71.0) -> dict:
    return {
        "hardware": {
            "cpu": {"utilization_percent": 18.5},
            "memory": {"ram_used_gb": 12.25, "ram_total_gb": 31.75},
            "gpu": {
                "name": "Test Vulkan GPU",
                "utilization_percent": gpu_percent,
                "vram_used_gb": 6.5,
                "vram_total_gb": 16.0,
                "temperature_celsius": 54.0,
                "power_watts": 112.0,
            },
        },
        "availability": {"cpu_counters": "collected", "gpu_counters": "collected"},
    }


class HardwareSamplerTests(unittest.TestCase):
    def test_sample_overlays_live_hardware_without_replacing_throughput(self):
        sampler = hardware_sampler.HardwareSampler(0.25, collector=lambda **_kwargs: collected())
        snapshot = {
            "hardware": {
                "brain_generation_tk_s": 37.89,
                "gpu": {"utilization_percent": 1.0},
            }
        }
        sample = sampler.sample_once()
        result = hardware_sampler.apply_live_hardware(snapshot, sample)

        self.assertTrue(result["hardware"]["live"])
        self.assertEqual(71.0, result["hardware"]["gpu"]["utilization_percent"])
        self.assertEqual(18.5, result["hardware"]["cpu_percent"])
        self.assertEqual(37.89, result["hardware"]["brain_generation_tk_s"])
        self.assertGreaterEqual(result["hardware"]["sample_age_seconds"], 0.0)

    def test_background_sampler_advances_sequence_and_stops(self):
        sampler = hardware_sampler.HardwareSampler(0.1, collector=lambda **_kwargs: collected())
        sampler.start()
        time.sleep(0.24)
        sampler.stop()

        self.assertGreaterEqual(sampler.latest()["sequence"], 2)
        self.assertFalse(sampler._thread.is_alive())


class ControlSocketTests(unittest.TestCase):
    @staticmethod
    def send(endpoint: str, payload: bytes) -> None:
        host, port = endpoint.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=1.0) as connection:
            connection.sendall(payload)

    def test_socket_requires_session_token_and_allowlisted_action(self):
        with native_bridge.ControlSocketServer() as server:
            self.send(server.endpoint, json.dumps({"token": "wrong", "action": "pause_toggle"}).encode() + b"\n")
            self.send(server.endpoint, json.dumps({"token": server.token, "action": "shell"}).encode() + b"\n")
            self.send(server.endpoint, b"{malformed\n")
            self.assertEqual([], server.poll())

            self.send(server.endpoint, json.dumps({"token": server.token, "action": "approve"}).encode() + b"\n")
            self.assertEqual([{"action": "approve"}], server.poll())

    def test_socket_validates_typed_task_request_fields(self):
        with native_bridge.ControlSocketServer() as server:
            self.send(server.endpoint, json.dumps({"token": server.token, "action": "task_retry", "task_id": "bad id"}).encode() + b"\n")
            self.send(server.endpoint, json.dumps({"token": server.token, "action": "task_prioritize", "task_id": "TASK-0042", "priority": 0}).encode() + b"\n")
            self.assertEqual([{"action": "task_prioritize", "task_id": "TASK-0042", "priority": 0}], server.poll())

            self.send(server.endpoint, json.dumps({"token": server.token, "action": "live_command", "command": ":improve add trading"}).encode() + b"\n")
            self.send(server.endpoint, json.dumps({"token": server.token, "action": "live_command", "command": "bad\ncommand"}).encode() + b"\n")
            self.assertEqual([{"action": "live_command", "command": ":improve add trading"}], server.poll())

    def test_socket_drops_oversized_payload(self):
        with native_bridge.ControlSocketServer() as server:
            self.send(server.endpoint, b"x" * (native_bridge.MAX_CONTROL_BYTES + 1))
            self.assertEqual([], server.poll())


if __name__ == "__main__":
    unittest.main()
