#!/usr/bin/env python3
"""Bounded JSONL pipe for one Flower-authenticated web model lane.

The pipe is transport only.  It does not schedule work, execute model output,
or accept endpoints and credentials from requests.  A separately configured
FlowerOS broker must issue a short-lived credential for the exact endpoint.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "web-model.json"
REQUEST_SCHEMA = "leafos.web-model.request.v1"
RESPONSE_SCHEMA = "leafos.web-model.response.v1"
BROKER_REQUEST_SCHEMA = "floweros.credential-request.v1"
BROKER_RESPONSE_SCHEMA = "floweros.credential-response.v1"
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
SECRET_CONFIG_KEYS = {
    "api_key", "apikey", "authorization", "credential", "password",
    "secret", "token",
}


class PipeError(RuntimeError):
    """A sanitized contract error suitable for a public JSON response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class WebModelConfig:
    provider: str
    endpoint: str
    endpoint_host: str
    model: str
    allowed_models: tuple[str, ...]
    timeout_seconds: float
    max_request_bytes: int
    max_response_bytes: int
    max_messages: int
    max_output_tokens: int
    broker_command: tuple[str, ...]
    broker_audience: str
    broker_timeout_seconds: float
    max_credential_ttl_seconds: int
    auth_header_name: str
    auth_scheme: str


Broker = Callable[[WebModelConfig], tuple[str, str]]
Transport = Callable[[WebModelConfig, dict[str, Any], str, str], dict[str, Any]]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipeError("config_invalid", "web model configuration is unreadable") from error
    if not isinstance(value, dict):
        raise PipeError("config_invalid", "web model configuration must be an object")
    return value


def _reject_embedded_secrets(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in SECRET_CONFIG_KEYS:
                raise PipeError("config_secret_forbidden", "credentials must come from the FlowerOS broker")
            _reject_embedded_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _reject_embedded_secrets(child)


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PipeError("config_invalid", f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= float(value) <= maximum:
        raise PipeError("config_invalid", f"{name} must be between {minimum:g} and {maximum:g}")
    return float(value)


def _absolute_command(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def load_config(path: Path = DEFAULT_CONFIG) -> WebModelConfig:
    raw = _read_json_object(path)
    _reject_embedded_secrets(raw)
    if raw.get("schema") != "leafos.web-model.config.v1":
        raise PipeError("config_invalid", "unsupported web model configuration schema")
    if raw.get("enabled") is not True:
        raise PipeError("web_model_disabled", "web model lane is disabled")

    provider = raw.get("provider")
    endpoint = raw.get("endpoint")
    model = raw.get("model")
    allowed_hosts = raw.get("allowed_hosts")
    allowed_models = raw.get("allowed_models")
    limits = raw.get("limits")
    auth = raw.get("auth")
    if not isinstance(provider, str) or not provider or len(provider) > 64:
        raise PipeError("config_invalid", "provider must be a short non-empty string")
    if not isinstance(endpoint, str) or not endpoint:
        raise PipeError("config_invalid", "endpoint is required")
    if not isinstance(model, str) or not model or len(model) > 128:
        raise PipeError("config_invalid", "model is required")
    if not isinstance(allowed_hosts, list) or not allowed_hosts or not all(isinstance(item, str) for item in allowed_hosts):
        raise PipeError("config_invalid", "allowed_hosts must be a non-empty string array")
    if not isinstance(allowed_models, list) or not allowed_models or not all(isinstance(item, str) for item in allowed_models):
        raise PipeError("config_invalid", "allowed_models must be a non-empty string array")
    if model not in allowed_models:
        raise PipeError("config_invalid", "configured model is not allowlisted")
    if not isinstance(limits, dict) or not isinstance(auth, dict):
        raise PipeError("config_invalid", "limits and auth objects are required")

    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PipeError("endpoint_forbidden", "web model endpoint must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PipeError("endpoint_forbidden", "endpoint credentials, query, and fragment are forbidden")
    if parsed.port not in (None, 443):
        raise PipeError("endpoint_forbidden", "web model endpoint must use port 443")
    endpoint_host = parsed.hostname.casefold().rstrip(".")
    normalized_hosts = tuple(item.casefold().rstrip(".") for item in allowed_hosts)
    if endpoint_host not in normalized_hosts:
        raise PipeError("endpoint_forbidden", "web model endpoint host is not allowlisted")
    try:
        ipaddress.ip_address(endpoint_host)
    except ValueError:
        pass
    else:
        raise PipeError("endpoint_forbidden", "IP-literal web model endpoints are forbidden")
    if not parsed.path.startswith("/") or parsed.path == "/":
        raise PipeError("endpoint_forbidden", "web model endpoint requires an explicit API path")

    command = auth.get("broker_command")
    audience = auth.get("audience")
    header_name = auth.get("header_name")
    scheme = auth.get("scheme")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise PipeError("config_invalid", "auth.broker_command must be a non-empty argv array")
    if not _absolute_command(command[0]):
        raise PipeError("config_invalid", "auth broker executable must be an absolute path")
    forbidden_argument_names = {"--api-key", "--authorization", "--credential", "--password", "--secret", "--token"}
    if any(item.casefold().split("=", 1)[0] in forbidden_argument_names for item in command[1:]):
        raise PipeError("config_secret_forbidden", "credentials must not appear in broker arguments")
    if not isinstance(audience, str) or not audience or len(audience) > 128:
        raise PipeError("config_invalid", "auth audience is required")
    if header_name not in {"Authorization", "X-API-Key"}:
        raise PipeError("config_invalid", "auth header_name is not allowlisted")
    if scheme not in {"Bearer", ""}:
        raise PipeError("config_invalid", "auth scheme must be Bearer or empty")
    if header_name == "Authorization" and scheme != "Bearer":
        raise PipeError("config_invalid", "Authorization credentials must use Bearer")

    return WebModelConfig(
        provider=provider,
        endpoint=endpoint,
        endpoint_host=endpoint_host,
        model=model,
        allowed_models=tuple(allowed_models),
        timeout_seconds=_bounded_number(limits.get("timeout_seconds"), "timeout_seconds", 1, 120),
        max_request_bytes=_bounded_int(limits.get("max_request_bytes"), "max_request_bytes", 1024, 1_048_576),
        max_response_bytes=_bounded_int(limits.get("max_response_bytes"), "max_response_bytes", 1024, 4_194_304),
        max_messages=_bounded_int(limits.get("max_messages"), "max_messages", 1, 128),
        max_output_tokens=_bounded_int(limits.get("max_output_tokens"), "max_output_tokens", 1, 65_536),
        broker_command=tuple(command),
        broker_audience=audience,
        broker_timeout_seconds=_bounded_number(auth.get("timeout_seconds"), "auth.timeout_seconds", 1, 15),
        max_credential_ttl_seconds=_bounded_int(
            auth.get("max_credential_ttl_seconds"), "auth.max_credential_ttl_seconds", 30, 900
        ),
        auth_header_name=header_name,
        auth_scheme=scheme,
    )


def validate_request(value: Any, config: WebModelConfig) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipeError("request_invalid", "request must be a JSON object")
    allowed = {"schema", "request_id", "messages", "model", "max_tokens", "temperature", "pack_id"}
    if set(value) - allowed:
        raise PipeError("request_invalid", "request contains unsupported fields")
    if value.get("schema") != REQUEST_SCHEMA:
        raise PipeError("request_invalid", "unsupported request schema")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise PipeError("request_invalid", "request_id is invalid")
    pack_id = value.get("pack_id")
    if pack_id is not None and (not isinstance(pack_id, str) or not REQUEST_ID.fullmatch(pack_id)):
        raise PipeError("request_invalid", "pack_id is invalid")
    model = value.get("model", config.model)
    if not isinstance(model, str) or model not in config.allowed_models:
        raise PipeError("model_forbidden", "requested model is not allowlisted")
    messages = value.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= config.max_messages:
        raise PipeError("request_invalid", "messages count is outside the configured limit")
    total_chars = 0
    clean_messages: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise PipeError("request_invalid", "each message requires only role and content")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str) or not content:
            raise PipeError("request_invalid", "message role or content is invalid")
        total_chars += len(content)
        clean_messages.append({"role": role, "content": content})
    if total_chars > config.max_request_bytes:
        raise PipeError("request_too_large", "message content exceeds the configured limit")
    max_tokens = value.get("max_tokens", config.max_output_tokens)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= config.max_output_tokens:
        raise PipeError("request_invalid", "max_tokens is outside the configured limit")
    temperature = value.get("temperature", 0.2)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= float(temperature) <= 2:
        raise PipeError("request_invalid", "temperature must be between 0 and 2")
    return {
        "model": model,
        "messages": clean_messages,
        "max_tokens": max_tokens,
        "temperature": float(temperature),
        "stream": False,
    }


def _broker_environment() -> dict[str, str]:
    names = (
        "COMSPEC", "HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT",
        "TEMP", "TMP", "USERPROFILE", "WINDIR",
    )
    return {name: os.environ[name] for name in names if name in os.environ}


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PipeError("auth_invalid", "broker credential expiry is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PipeError("auth_invalid", "broker credential expiry is invalid") from error
    if parsed.tzinfo is None:
        raise PipeError("auth_invalid", "broker credential expiry must include a timezone")
    return parsed.astimezone(timezone.utc)


def acquire_flower_credential(config: WebModelConfig) -> tuple[str, str]:
    broker_path = Path(config.broker_command[0])
    if not broker_path.is_file():
        raise PipeError("auth_unavailable", "configured FlowerOS credential broker is unavailable")
    request = {
        "schema": BROKER_REQUEST_SCHEMA,
        "audience": config.broker_audience,
        "endpoint_host": config.endpoint_host,
        "provider": config.provider,
    }
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        result = subprocess.run(
            list(config.broker_command),
            input=json.dumps(request, separators=(",", ":")),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=config.broker_timeout_seconds,
            env=_broker_environment(),
            shell=False,
            close_fds=True,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise PipeError("auth_unavailable", "FlowerOS credential broker failed") from error
    if result.returncode != 0 or len(result.stdout.encode("utf-8")) > 65_536:
        raise PipeError("auth_unavailable", "FlowerOS credential broker refused the request")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PipeError("auth_invalid", "FlowerOS credential broker returned invalid JSON") from error
    if not isinstance(response, dict) or response.get("schema") != BROKER_RESPONSE_SCHEMA:
        raise PipeError("auth_invalid", "FlowerOS credential broker returned an unsupported response")
    if response.get("ok") is not True or response.get("session_verified") is not True:
        raise PipeError("auth_required", "a verified FlowerOS login session is required")
    if response.get("audience") != config.broker_audience or response.get("endpoint_host") != config.endpoint_host:
        raise PipeError("auth_invalid", "broker credential scope does not match this endpoint")
    credential = response.get("credential")
    if not isinstance(credential, str) or not credential or len(credential) > 8192 or "\n" in credential or "\r" in credential:
        raise PipeError("auth_invalid", "broker credential is invalid")
    now = datetime.now(timezone.utc)
    expires = _parse_utc(response.get("expires_at"))
    if expires <= now or expires > now + timedelta(seconds=config.max_credential_ttl_seconds):
        raise PipeError("auth_invalid", "broker credential lifetime is outside policy")
    header_value = f"{config.auth_scheme} {credential}".strip()
    return config.auth_header_name, header_value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def call_web_model(
    config: WebModelConfig,
    payload: dict[str, Any],
    header_name: str,
    header_value: str,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > config.max_request_bytes:
        raise PipeError("request_too_large", "encoded request exceeds the configured limit")
    request = urllib.request.Request(
        config.endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LeafOS/0.2.3 web-model-pipe/1",
            header_name: header_value,
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=config.timeout_seconds) as response:
            if not 200 <= int(response.status) < 300:
                raise PipeError("provider_refused", "web model provider refused the request")
            raw = response.read(config.max_response_bytes + 1)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise PipeError("redirect_forbidden", "web model redirects are forbidden") from error
        raise PipeError("provider_refused", "web model provider refused the request") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PipeError("provider_unavailable", "web model provider is unavailable") from error
    if len(raw) > config.max_response_bytes:
        raise PipeError("response_too_large", "web model response exceeds the configured limit")
    try:
        value = json.loads(raw.decode("utf-8"))
        content = value["choices"][0]["message"]["content"]
    except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise PipeError("response_invalid", "web model response is not OpenAI-compatible JSON") from error
    if not isinstance(content, str) or not content:
        raise PipeError("response_invalid", "web model response content is empty")
    usage_raw = value.get("usage", {}) if isinstance(value, dict) else {}
    usage = {
        key: usage_raw[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if isinstance(usage_raw, dict) and isinstance(usage_raw.get(key), int) and usage_raw[key] >= 0
    }
    return {"content": content, "usage": usage}


def process_request(
    value: Any,
    config: WebModelConfig,
    broker: Broker = acquire_flower_credential,
    transport: Transport = call_web_model,
) -> dict[str, Any]:
    request_id = value.get("request_id", "unknown") if isinstance(value, dict) else "unknown"
    payload = validate_request(value, config)
    header_name, header_value = broker(config)
    provider_response = transport(config, payload, header_name, header_value)
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id,
        "ok": True,
        "provider": config.provider,
        "model": payload["model"],
        "authority": "proposal-only",
        "content": provider_response["content"],
        "usage": provider_response.get("usage", {}),
    }


def error_response(request_id: str, error: PipeError) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id if REQUEST_ID.fullmatch(request_id) else "unknown",
        "ok": False,
        "authority": "none",
        "error": {"code": error.code, "message": error.message},
    }


def write_jsonl(stream: BinaryIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    stream.flush()


def run_stream(config: WebModelConfig, input_stream: BinaryIO, output_stream: BinaryIO, once: bool = False) -> int:
    failed = False
    line_number = 0
    while True:
        raw = input_stream.readline(config.max_request_bytes + 1)
        if not raw:
            break
        line_number += 1
        if len(raw) > config.max_request_bytes:
            while raw and not raw.endswith(b"\n"):
                raw = input_stream.readline(config.max_request_bytes + 1)
            write_jsonl(output_stream, error_response("unknown", PipeError("request_too_large", "JSONL request exceeds the configured limit")))
            failed = True
            if once:
                break
            continue
        if not raw.strip():
            continue
        request_id = "unknown"
        try:
            value = json.loads(raw.decode("utf-8"))
            if isinstance(value, dict) and isinstance(value.get("request_id"), str):
                request_id = value["request_id"]
            response = process_request(value, config)
        except (UnicodeError, json.JSONDecodeError):
            response = error_response(request_id, PipeError("request_invalid", "request is not valid UTF-8 JSON"))
            failed = True
        except PipeError as error:
            response = error_response(request_id, error)
            failed = True
        except Exception:
            response = error_response(request_id, PipeError("internal_error", "web model pipe failed safely"))
            failed = True
        write_jsonl(output_stream, response)
        if once:
            break
    return 1 if failed else 0


def doctor(path: Path) -> dict[str, Any]:
    raw = _read_json_object(path)
    _reject_embedded_secrets(raw)
    if raw.get("schema") != "leafos.web-model.config.v1":
        raise PipeError("config_invalid", "unsupported web model configuration schema")
    enabled = raw.get("enabled") is True
    result: dict[str, Any] = {
        "schema": "leafos.web-model.doctor.v1",
        "status": "disabled" if not enabled else "attention",
        "config": str(path.resolve()),
        "enabled": enabled,
        "network_probe_performed": False,
        "credential_requested": False,
    }
    if not enabled:
        return result
    try:
        config = load_config(path)
    except PipeError as error:
        result["error"] = {"code": error.code, "message": error.message}
        return result
    broker_present = Path(config.broker_command[0]).is_file()
    result.update({
        "status": "ready" if broker_present else "attention",
        "provider": config.provider,
        "endpoint_host": config.endpoint_host,
        "model": config.model,
        "broker_present": broker_present,
        "authority": "proposal-only",
    })
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--doctor", action="store_true", help="validate configuration without network or credential access")
    parser.add_argument("--once", action="store_true", help="process one non-empty JSONL request")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.doctor:
        try:
            report = doctor(args.config)
        except PipeError as error:
            report = {"schema": "leafos.web-model.doctor.v1", "status": "invalid", "error": {"code": error.code, "message": error.message}}
        print(json.dumps(report, indent=2))
        return 0 if report.get("status") in {"disabled", "ready"} else 1
    try:
        config = load_config(args.config)
    except PipeError as error:
        write_jsonl(sys.stdout.buffer, error_response("unknown", error))
        return 2
    return run_stream(config, sys.stdin.buffer, sys.stdout.buffer, args.once)


if __name__ == "__main__":
    raise SystemExit(main())
