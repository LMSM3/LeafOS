#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TUI = ROOT / "core" / "ui" / "tui"
if str(TUI) not in sys.path:
    sys.path.insert(0, str(TUI))

import inlet_pipe
import native_bridge
from tests.test_tui_skeleton import HOME, fixture_run


MSYS_BASH = pathlib.Path("C:/msys64/usr/bin/bash.exe")
BASH = str(MSYS_BASH) if MSYS_BASH.is_file() else shutil.which("bash")


def native_toolchain_available() -> bool:
    if not BASH:
        return False
    prefix = "export PATH=/ucrt64/bin:/usr/bin; " if MSYS_BASH.is_file() else ""
    command = prefix + "printf '#include <ncursesw/ncurses.h>\\n' | gcc -x c -fsyntax-only - >/dev/null 2>&1"
    return subprocess.run([BASH, "-c", command], cwd=ROOT, check=False).returncode == 0


@unittest.skipUnless(native_toolchain_available(), "gcc and ncursesw headers are required")
class NativeTuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [BASH, "-c", ("export PATH=/ucrt64/bin:/usr/bin; " if MSYS_BASH.is_file() else "") + "bash ./bin/build_tui.sh"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

    def test_native_sources_follow_renderer_state_input_json_split(self):
        expected = {
            "leaf_tui.c", "leaf_tui_json.c", "leaf_tui_json.h", "leaf_tui_state.c", "leaf_tui_state.h",
            "leaf_tui_pages.c", "leaf_tui_pages.h", "leaf_tui_input.c", "leaf_tui_input.h",
        }
        self.assertTrue(expected.issubset({path.name for path in (ROOT / "core" / "tui").iterdir()}))
        self.assertIsNotNone(native_bridge.native_binary())

    def test_native_plain_renderer_consumes_normalized_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME):
                snapshot = inlet_pipe.build_snapshot(str(run_dir))
            snapshot_path = pathlib.Path(tmp) / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            result = subprocess.run(
                [str(native_bridge.native_binary()), "--snapshot", str(snapshot_path), "--plain", "--page", "7"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Page 7 Results", result.stdout)
            self.assertIn("tui-fixture", result.stdout)
            self.assertIn("FlowerOS | LeafOS engine", result.stdout)

    def test_native_parser_fails_closed_on_malformed_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = pathlib.Path(tmp) / "snapshot.json"
            snapshot_path.write_text('{"run":', encoding="utf-8")
            result = subprocess.run(
                [str(native_bridge.native_binary()), "--snapshot", str(snapshot_path), "--plain"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("invalid", result.stderr)

    def test_atomic_bridge_retries_windows_sharing_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "snapshot.json"
            path.write_text("old", encoding="utf-8")
            real_replace = os.replace
            attempts = []

            def sharing_race(source, target):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError("fixture sharing race")
                return real_replace(source, target)

            with mock.patch.object(native_bridge.os, "replace", side_effect=sharing_race), mock.patch.object(native_bridge.time, "sleep"):
                native_bridge._atomic_text(path, "new")
            self.assertEqual(3, len(attempts))
            self.assertEqual("new", path.read_text(encoding="utf-8"))

    def test_unknown_controller_action_fails_without_subprocess(self):
        with mock.patch.object(inlet_pipe.subprocess, "run") as run:
            ok, detail = inlet_pipe.controller_action({"run": {}}, "shell")
        self.assertFalse(ok)
        self.assertIn("unsupported", detail)
        run.assert_not_called()

    def test_allowed_control_translates_to_inlet_command(self):
        result = mock.Mock(returncode=0, stdout="paused\n", stderr="")
        snapshot = {"run": {"state": "running", "dir": "C:/safe/run", "approval": {"status": "pending"}}}
        with mock.patch.object(inlet_pipe.subprocess, "run", return_value=result) as run:
            ok, detail = inlet_pipe.controller_action(snapshot, "pause_toggle")
        self.assertTrue(ok)
        self.assertEqual("paused", detail)
        command = run.call_args.args[0]
        self.assertEqual("pause", command[2])
        self.assertEqual("C:/safe/run", command[3])

    def test_typed_task_control_reaches_inlet_without_shell_command(self):
        snapshot = {"run": {"dir": "C:/safe/run"}}
        task = {"task_id": "TASK-0042", "status": "queued"}
        with mock.patch.object(inlet_pipe.inlet, "apply_task_control", return_value=task) as apply, mock.patch.object(
            inlet_pipe.inlet, "_pid_alive", return_value=True
        ), mock.patch.object(inlet_pipe.subprocess, "run") as shell:
            ok, detail = inlet_pipe.controller_request(snapshot, {
                "action": "task_prioritize", "task_id": "TASK-0042", "priority": 0,
            })
        self.assertTrue(ok, detail)
        self.assertEqual("prioritize", apply.call_args.args[1]["action"])
        self.assertEqual(0, apply.call_args.args[1]["priority"])
        shell.assert_not_called()

    def test_live_command_reaches_general_project_inlet_without_shell(self):
        snapshot = {"run": {"dir": "C:/safe/run"}}
        with mock.patch.object(
            inlet_pipe.live_projects, "execute_active_command",
            return_value={"action": "improve", "message": "queued iteration 1 as TASK-0001"},
        ) as execute, mock.patch.object(inlet_pipe.subprocess, "run") as shell:
            ok, detail = inlet_pipe.controller_request(snapshot, {
                "action": "live_command", "command": ":improve make bots trade",
            })
        self.assertTrue(ok, detail)
        self.assertIn("TASK-0001", detail)
        self.assertEqual(":improve make bots trade", execute.call_args.args[0])
        shell.assert_not_called()

    def test_python_native_bridge_plain_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME):
                snapshot = inlet_pipe.build_snapshot(str(run_dir))
            args = argparse.Namespace(
                refresh=0.25, page_index=2, once=True, plain=True, stdin_tty=False, stdout_tty=False,
                width_value=100, height_value=30, run=str(run_dir), event_limit=100,
            )
            self.assertEqual(0, native_bridge.run_native(args, snapshot))


if __name__ == "__main__":
    unittest.main()
