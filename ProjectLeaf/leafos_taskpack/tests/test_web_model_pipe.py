#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "python"))

import leaf_web_model_pipe as pipe  # noqa: E402


def config_document(broker: Path, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "leafos.web-model.config.v1",
        "enabled": True,
        "provider": "flower-web",
        "endpoint": "https://models.flower.example/v1/chat/completions",
        "allowed_hosts": ["models.flower.example"],
        "model": "leaf-small",
        "allowed_models": ["leaf-small"],
        "limits": {
            "timeout_seconds": 10,
            "max_request_bytes": 8192,
            "max_response_bytes": 16384,
            "max_messages": 8,
            "max_output_tokens": 512,
        },
        "auth": {
            "broker_command": [str(broker.resolve())],
            "audience": "leafos.web-model",
            "timeout_seconds": 3,
            "max_credential_ttl_seconds": 300,
            "header_name": "Authorization",
            "scheme": "Bearer",
        },
    }
    value.update(overrides)
    return value


def request_document(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": pipe.REQUEST_SCHEMA,
        "request_id": "req-001",
        "pack_id": "ficus",
        "messages": [{"role": "user", "content": "Propose a plan."}],
        "max_tokens": 128,
    }
    value.update(overrides)
    return value


class WebModelPipeTests(unittest.TestCase):
    def write_config(self, directory: str, value: dict[str, object]) -> Path:
        path = Path(directory) / "web-model.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_default_config_is_disabled_without_probing_or_requesting_credentials(self) -> None:
        config_path = ROOT / "config" / "web-model.json"
        report = pipe.doctor(config_path)
        self.assertEqual("disabled", report["status"])
        self.assertFalse(report["network_probe_performed"])
        self.assertFalse(report["credential_requested"])
        configured = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual("https://api.openai.com/v1/chat/completions", configured["endpoint"])
        self.assertEqual(["api.openai.com"], configured["allowed_hosts"])
        self.assertEqual("gpt-4o", configured["model"])
        self.assertEqual(
            "C:/FlowerOS/bin/flower-credential-broker.ps1",
            configured["auth"]["broker_command"][-1],
        )

    def test_config_rejects_non_https_and_ip_literal_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            for endpoint, host in (
                ("http://models.flower.example/v1/chat/completions", "models.flower.example"),
                ("https://127.0.0.1/v1/chat/completions", "127.0.0.1"),
            ):
                value = config_document(broker, endpoint=endpoint, allowed_hosts=[host])
                with self.subTest(endpoint=endpoint), self.assertRaises(pipe.PipeError) as raised:
                    pipe.load_config(self.write_config(directory, value))
                self.assertEqual("endpoint_forbidden", raised.exception.code)

    def test_config_rejects_host_drift_and_embedded_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            value = config_document(broker, allowed_hosts=["other.flower.example"])
            with self.assertRaises(pipe.PipeError) as raised:
                pipe.load_config(self.write_config(directory, value))
            self.assertEqual("endpoint_forbidden", raised.exception.code)

            value = config_document(broker)
            value["api_key"] = "must-not-live-here"
            with self.assertRaises(pipe.PipeError) as raised:
                pipe.load_config(self.write_config(directory, value))
            self.assertEqual("config_secret_forbidden", raised.exception.code)

    def test_request_cannot_supply_endpoint_headers_credentials_or_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            config = pipe.load_config(self.write_config(directory, config_document(broker)))
            for field in ("endpoint", "headers", "credential", "shell", "command"):
                with self.subTest(field=field), self.assertRaises(pipe.PipeError) as raised:
                    pipe.validate_request(request_document(**{field: "bad"}), config)
                self.assertEqual("request_invalid", raised.exception.code)

    def test_success_is_proposal_only_and_never_echoes_credential(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            config = pipe.load_config(self.write_config(directory, config_document(broker)))
            seen: dict[str, object] = {}

            def fake_broker(_config: pipe.WebModelConfig) -> tuple[str, str]:
                return "Authorization", "Bearer super-secret"

            def fake_transport(
                _config: pipe.WebModelConfig,
                payload: dict[str, object],
                header_name: str,
                header_value: str,
            ) -> dict[str, object]:
                seen.update(payload=payload, header_name=header_name, header_value=header_value)
                return {"content": "A bounded proposal.", "usage": {"total_tokens": 9}}

            result = pipe.process_request(request_document(), config, fake_broker, fake_transport)
            self.assertTrue(result["ok"])
            self.assertEqual("proposal-only", result["authority"])
            self.assertEqual("A bounded proposal.", result["content"])
            self.assertNotIn("super-secret", json.dumps(result))
            self.assertEqual("leaf-small", seen["payload"]["model"])  # type: ignore[index]

    def test_broker_receives_scope_on_stdin_with_a_reduced_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / ("broker.py" if os.name == "nt" else "broker")
            expires = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
            broker.write_text(
                "#!/usr/bin/env python3\n"
                "import json,os,sys\n"
                "assert 'OPENAI_API_KEY' not in os.environ\n"
                "r=json.load(sys.stdin)\n"
                f"print(json.dumps({{'schema':'{pipe.BROKER_RESPONSE_SCHEMA}','ok':True,'session_verified':True,'audience':r['audience'],'endpoint_host':r['endpoint_host'],'credential':'ephemeral-test','expires_at':'{expires}'}}))\n",
                encoding="utf-8",
                newline="\n",
            )
            broker.chmod(broker.stat().st_mode | stat.S_IXUSR)
            command = [str(broker.resolve())]
            if os.name == "nt":
                command = [str(Path(sys.executable).resolve()), str(broker.resolve())]
            value = config_document(broker)
            value["auth"]["broker_command"] = command  # type: ignore[index]
            config = pipe.load_config(self.write_config(directory, value))
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "ambient-secret"}, clear=False):
                name, credential = pipe.acquire_flower_credential(config)
            self.assertEqual("Authorization", name)
            self.assertEqual("Bearer ephemeral-test", credential)

    def test_broker_rejects_unverified_or_overlong_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            config = pipe.load_config(self.write_config(directory, config_document(broker)))
            base = {
                "schema": pipe.BROKER_RESPONSE_SCHEMA,
                "ok": True,
                "session_verified": False,
                "audience": config.broker_audience,
                "endpoint_host": config.endpoint_host,
                "credential": "secret",
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
            }
            completed = subprocess_result(json.dumps(base))
            with mock.patch.object(pipe.subprocess, "run", return_value=completed), self.assertRaises(pipe.PipeError) as raised:
                pipe.acquire_flower_credential(config)
            self.assertEqual("auth_required", raised.exception.code)

            base["session_verified"] = True
            base["expires_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            completed = subprocess_result(json.dumps(base))
            with mock.patch.object(pipe.subprocess, "run", return_value=completed), self.assertRaises(pipe.PipeError) as raised:
                pipe.acquire_flower_credential(config)
            self.assertEqual("auth_invalid", raised.exception.code)

    def test_jsonl_errors_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = Path(directory) / "broker"
            broker.touch()
            config = pipe.load_config(self.write_config(directory, config_document(broker)))
            source = io.BytesIO(b'{"schema":"bad","request_id":"req-002"}\n')
            target = io.BytesIO()
            exit_code = pipe.run_stream(config, source, target, once=True)
            response = json.loads(target.getvalue())
            self.assertEqual(1, exit_code)
            self.assertFalse(response["ok"])
            self.assertEqual("request_invalid", response["error"]["code"])
            self.assertNotIn("traceback", target.getvalue().decode().casefold())


def subprocess_result(stdout: str) -> object:
    return type("Completed", (), {"returncode": 0, "stdout": stdout})()


if __name__ == "__main__":
    unittest.main()
