#!/usr/bin/env python3
"""
LeafOS Python Runtime Library -- leaf_runtime.py
Cross-platform: macOS, Linux, WSL, Windows native (pwsh / MSYS2)
Python 3.8+
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from leaf_moe_contract import (  # noqa: E402
    DEFAULT_CANDIDATE,
    DEFAULT_POLICY,
    load_json,
    validate_candidate,
    validate_policy,
)

# ─────────────────────────────────────────────────────────────────────────────
# Platform detection
# ─────────────────────────────────────────────────────────────────────────────

class LeafPlatform:
    """Detect and expose the current execution platform."""

    OS_MAC     = "mac"
    OS_LINUX   = "linux"
    OS_WSL     = "wsl"
    OS_WINDOWS = "windows"

    def __init__(self) -> None:
        self._detect()

    def _detect(self) -> None:
        s = platform.system()
        if s == "Darwin":
            self.os   = self.OS_MAC
            self.arch = platform.machine()          # arm64 on Apple Silicon
            self.name = f"macOS {platform.mac_ver()[0]}"
        elif s == "Windows":
            self.os   = self.OS_WINDOWS
            self.arch = platform.machine()
            self.name = f"Windows {platform.version()}"
        elif s == "Linux":
            try:
                pv = Path("/proc/version").read_text(errors="replace").lower()
                self.os = self.OS_WSL if ("microsoft" in pv or "wsl" in pv) else self.OS_LINUX
            except OSError:
                self.os = self.OS_LINUX
            self.arch = platform.machine()
            try:
                import distro  # type: ignore
                self.name = distro.name(pretty=True)
            except ImportError:
                self.name = f"Linux {platform.release()}"
        else:
            self.os   = s.lower()
            self.arch = platform.machine()
            self.name = s

        self.python_ver       = ".".join(str(v) for v in sys.version_info[:3])
        self.is_windows_native = self.os == self.OS_WINDOWS
        self.supports_ansi    = self._check_ansi()

    def _check_ansi(self) -> bool:
        if self.is_windows_native:
            return (
                os.environ.get("WT_SESSION") is not None
                or os.environ.get("TERM_PROGRAM") is not None
                or os.environ.get("COLORTERM") is not None
            )
        return sys.stdout.isatty()

    @property
    def is_mac(self)   -> bool: return self.os == self.OS_MAC
    @property
    def is_linux(self) -> bool: return self.os == self.OS_LINUX
    @property
    def is_wsl(self)   -> bool: return self.os == self.OS_WSL
    @property
    def is_posix(self) -> bool: return self.os in (self.OS_MAC, self.OS_LINUX, self.OS_WSL)

    def summary(self) -> str:
        return (
            f"os={self.os} arch={self.arch} "
            f'name="{self.name}" python={self.python_ver}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# Brand / colour output
# ─────────────────────────────────────────────────────────────────────────────

_RESET  = "\x1b[0m"
_BOLD   = "\x1b[1m"
_GREEN  = "\x1b[32m"
_YELLOW = "\x1b[33m"
_CYAN   = "\x1b[36m"
_RED    = "\x1b[31m"


class LeafBrand:
    """Project brand helpers: icon, name, coloured output."""

    def __init__(self, plat: LeafPlatform, *, project: str = "LeafOS") -> None:
        self.platform = plat
        self.project  = project
        self._colour  = plat.supports_ansi

    def _c(self, code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if self._colour else text

    def icon(self) -> str:
        return "\U0001f33f" if self.platform.is_posix else "*"

    def say(self, msg: str) -> None:
        print(f"{self.icon()} {self._c(_BOLD + _GREEN, self.project)}: {msg}")

    def warn(self, msg: str) -> None:
        print(f"{self.icon()} {self._c(_YELLOW, 'WARN')}: {msg}", file=sys.stderr)

    def die(self, msg: str, code: int = 1) -> None:
        print(f"{self.icon()} {self._c(_RED, 'ERROR')}: {msg}", file=sys.stderr)
        sys.exit(code)


# ─────────────────────────────────────────────────────────────────────────────
# Structured JSON-lines logger
# ─────────────────────────────────────────────────────────────────────────────

class LeafLog:
    """Structured JSON-lines logger (mirrors core/log/log.sh)."""

    _LEVELS: Dict[str, int] = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}

    def __init__(self, log_path: Path, *, min_level: str = "INFO") -> None:
        self.log_path  = log_path
        self.min_level = min_level
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str) -> None:
        if self._LEVELS.get(level, 0) < self._LEVELS.get(self.min_level, 1):
            return
        entry = {
            "ts":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level,
            "msg":   msg,
            "src":   "leafpy",
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def debug(self, msg: str) -> None: self._write("DEBUG", msg)
    def info(self,  msg: str) -> None: self._write("INFO",  msg)
    def warn(self,  msg: str) -> None: self._write("WARN",  msg)
    def error(self, msg: str) -> None: self._write("ERROR", msg)


# ─────────────────────────────────────────────────────────────────────────────
# Animated loaders
# ─────────────────────────────────────────────────────────────────────────────

LOADER_FRAMES: Dict[str, List[str]] = {
    # Unicode (POSIX / Windows Terminal)
    "orbit":   ["◐", "◓", "◑", "◒"],
    "braille": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "bounce":  ["▁","▂","▃","▄","▅","▆","▇","█","▇","▆","▅","▄","▃","▂"],
    "arrow":   ["←","↖","↑","↗","→","↘","↓","↙"],
    # ASCII (safe everywhere)
    "dots":    [".", "..", "...", "....", "...", ".."],
    "bar":     ["[    ]", "[=   ]", "[==  ]", "[=== ]", "[====]"],
    "spin":    ["|", "/", "-", "\\"],
}

# Fallback map for non-ANSI terminals
_ASCII_FALLBACK: Dict[str, str] = {
    "orbit":   "spin",
    "braille": "dots",
    "bounce":  "bar",
    "arrow":   "spin",
}


class LeafLoader:
    """Cross-platform animated loader with ASCII fallback."""

    def __init__(
        self,
        brand: LeafBrand,
        *,
        name: str = "dots",
        label: str = "loading",
    ) -> None:
        self.brand  = brand
        self.label  = label
        key = name if brand.platform.supports_ansi else _ASCII_FALLBACK.get(name, name)
        self.frames = LOADER_FRAMES.get(key, LOADER_FRAMES["dots"])

    def run(self, duration_ms: int = 1400, frame_ms: int = 60) -> None:
        n     = len(self.frames)
        steps = max(1, duration_ms // frame_ms)
        icon  = self.brand.icon()
        proj  = self.brand.project
        lbl   = self.label
        for i in range(steps):
            sys.stdout.write(f"\r{icon} {proj} [{lbl}] {self.frames[i % n]}  ")
            sys.stdout.flush()
            time.sleep(frame_ms / 1000.0)
        sys.stdout.write(f"\r{icon} {proj} [{lbl}] done       \n")
        sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Version checker
# ─────────────────────────────────────────────────────────────────────────────

class LeafVersionChecker:
    """Detect installed tool versions; compare against requirements."""

    _MIN_DEFAULTS: Dict[str, str] = {
        "python": "3.8",
        "bash":   "4.0",
        "pwsh":   "7.0",
        "gcc":    "9.0",
    }

    @staticmethod
    def _run(*cmd: str) -> str:
        try:
            return subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, timeout=5
            ).decode(errors="replace").strip()
        except Exception:
            return ""

    @staticmethod
    def _parse(raw: str) -> str:
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return m.group(1) if m else "0.0"

    @staticmethod
    def _gte(have: str, need: str) -> bool:
        def parts(v: str) -> List[int]:
            return [int(x) for x in v.split(".")[:2]]
        try:
            return parts(have) >= parts(need)
        except ValueError:
            return False

    def detect(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        out["python"] = ".".join(str(v) for v in sys.version_info[:3])
        out["bash"]   = self._parse(self._run("bash", "--version"))
        raw_pwsh = self._run("pwsh", "--version") or \
                   self._run("powershell", "-Command", "$PSVersionTable.PSVersion.ToString()")
        out["pwsh"]  = self._parse(raw_pwsh)
        cc = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
        out["gcc"]   = self._parse(self._run(cc, "--version")) if cc else "0.0"
        return out

    def report(self, requirements: Optional[Dict[str, str]] = None) -> None:
        req  = {**self._MIN_DEFAULTS, **(requirements or {})}
        vers = self.detect()
        print(f"{'Component':<14} {'Found':<12} {'Required':<12} {'Status'}")
        print("-" * 52)
        for name in sorted(req):
            found  = vers.get(name, "0.0")
            needed = req[name]
            if found == "0.0":
                status = "missing"
            elif self._gte(found, needed):
                status = "ok"
            else:
                status = "WARN"
            print(f"{name:<14} {found:<12} {needed:<12} {status}")


# ─────────────────────────────────────────────────────────────────────────────
# Doctor / health check
# ─────────────────────────────────────────────────────────────────────────────

class LeafDoctor:
    """Validate the leafos_taskpack layout from Python."""

    REQUIRED_DIRS: List[str] = ["bin", "core", "config", "share", "logs", "tests", "docs"]
    REQUIRED_FILES: List[str] = [
        "config/brand.conf",
        "config/loaders.conf",
        "core/brand/brand.sh",
        "core/log/log.sh",
        "core/loaders/loaders.sh",
    ]

    def __init__(self, root: Path, brand: LeafBrand, log: LeafLog) -> None:
        self.root  = root
        self.brand = brand
        self.log   = log

    def run(self) -> bool:
        ok = True
        for d in self.REQUIRED_DIRS:
            if not (self.root / d).is_dir():
                self.brand.warn(f"missing dir: {d}/")
                ok = False
        for f in self.REQUIRED_FILES:
            if not (self.root / f).is_file():
                self.brand.warn(f"missing file: {f}")
                ok = False
        if ok:
            self.brand.say("layout usable")
            self.log.info("doctor passed (python)")
        else:
            self.log.warn("doctor found issues (python)")
        return ok


# ─────────────────────────────────────────────────────────────────────────────
# Runtime selection: main model + coder model + persona
# ─────────────────────────────────────────────────────────────────────────────

class LeafRuntimeSelector:
    """Load config/runtime.json and resolve the runtime defaults."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "config" / "runtime.json"
        if not self.path.exists():
            raise FileNotFoundError(f"runtime config not found: {self.path}")
        self.config: Dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.runtime: Dict[str, Any] = self.config["leafos_runtime"]

    def _find(self, collection: str, key: str, *, repo_ok: bool = True) -> Dict[str, Any]:
        for item in self.runtime[collection]:
            if item.get("key") == key or (repo_ok and item.get("repo") == key):
                return item
        raise KeyError(f"unknown {collection[:-1]}: {key}")

    def medium_moe_status(self) -> Dict[str, Any]:
        """Expose MoE policy readiness without changing the active provider route."""
        policy_path = self.root / "config" / "medium_moe_policy.json"
        candidate_path = Path(os.environ.get("LEAF_MEDIUM_MOE_CANDIDATE", str(DEFAULT_CANDIDATE)))
        if not candidate_path.is_absolute():
            candidate_path = self.root / candidate_path

        policy = load_json(policy_path if policy_path.exists() else DEFAULT_POLICY)
        policy_errors = validate_policy(policy)
        result: Dict[str, Any] = {
            "policy_id": policy.get("policy_id"),
            "preferred_architecture": policy.get("decision", {}).get("preferred_architecture"),
            "parameter_band_billion": policy.get("decision", {}).get("total_parameter_band_billion"),
            "incumbent_route": policy.get("decision", {}).get("incumbent_route"),
            "automatic_promotion": False,
            "active_route": "incumbent",
            "candidate_path": str(candidate_path),
            "candidate_status": "unavailable",
            "candidate_ready": False,
            "policy_errors": policy_errors,
            "candidate_errors": [],
        }
        if not candidate_path.exists():
            result["candidate_errors"] = [f"candidate file not found: {candidate_path}"]
            return result

        candidate = load_json(candidate_path)
        candidate_errors = validate_candidate(candidate, policy)
        result["candidate_status"] = candidate.get("status", "unknown")
        result["candidate_errors"] = candidate_errors
        result["candidate_ready"] = not policy_errors and not candidate_errors and candidate.get("status") == "resolved"
        return result

    def select(
        self,
        *,
        main_model: str = "",
        scheduler_model: str = "",
        coder_model: str = "",
        coding_language: str = "",
        coding_model_choice: str = "",
        coding_tier: str = "",
        persona: str = "",
        mode: str = "",
    ) -> Dict[str, Any]:
        defaults = self.runtime["defaults"]
        main_key = main_model or os.environ.get("LEAF_MAIN_MODEL") or defaults["main_model"]
        scheduler_key = scheduler_model or os.environ.get("LEAF_SCHEDULER_MODEL") or defaults["scheduler_model"]
        coder_key = coder_model or os.environ.get("LEAF_CODER_MODEL") or defaults["coder_model"]
        coding_language_key = coding_language or os.environ.get("LEAF_CODING_LANGUAGE") or defaults.get("coding_language", "python")
        coding_model_key = coding_model_choice or os.environ.get("LEAF_CODING_MODEL_CHOICE") or defaults.get("coding_model_choice", coder_key)
        coding_tier_key = coding_tier or os.environ.get("LEAF_CODING_TIER") or defaults.get("coding_tier", "builder")
        persona_key = persona or os.environ.get("LEAF_PERSONA") or defaults["persona"]
        mode_key = mode or os.environ.get("LEAF_RUNTIME_MODE") or defaults["mode"]

        if mode_key not in self.runtime["modes"]:
            raise KeyError(f"unknown runtime mode: {mode_key}")

        main = self._find("main_models", main_key)
        scheduler = self._find("main_models", scheduler_key)
        coder = self._find("coder_models", coder_key)
        persona_obj = self._find("persona_registry", persona_key, repo_ok=False)
        role_policy = self.runtime.get("role_policy", {})
        coding_model = role_policy.get("coding_model_key", "gemma4-coder")
        allowed_languages = role_policy.get("allowed_coding_languages", ["python"])
        if coder["key"] != coding_model:
            raise KeyError(f"coder model must be {coding_model}")
        if coding_model_key != coding_model:
            raise KeyError(f"coding model choice must be {coding_model}")
        if coding_language_key not in allowed_languages:
            raise KeyError(f"unsupported coding language: {coding_language_key}")
        coding_tier_obj = next(
            (tier for tier in coder.get("tiers", []) if tier.get("name") == coding_tier_key),
            None,
        )
        if coding_tier_obj is None:
            raise KeyError(f"unknown coding tier for {coder['key']}: {coding_tier_key}")
        if main["key"] == coding_model:
            raise KeyError("Fable/Gemma4-Coder cannot be main model")
        if scheduler["key"] == coding_model:
            raise KeyError("Fable/Gemma4-Coder cannot be scheduler model")
        workers = [] if persona_obj["code_policy"] == "avoid_unless_stuck" else coder["tiers"]

        return {
            "schema_version": self.config["schema_version"],
            "selection": {
                "main_model": main,
                "scheduler_model": scheduler,
                "coder_model": coder,
                "coding_choice": {
                    "language": coding_language_key,
                    "model_key": coding_model_key,
                    "tier": coding_tier_key,
                    "tier_config": coding_tier_obj,
                    "backend": "python",
                    "source": "runtime-default-or-env",
                },
                "persona": persona_obj,
                "mode": mode_key,
                "language_hint": coding_language_key,
                "care_mode": persona_obj["care_mode"],
                "contract_version": self.runtime["output_contract"]["version"],
                "role_policy": role_policy,
                "workers": workers,
                "medium_moe": self.medium_moe_status(),
            },
        }

    def event(self, response_type: str, content: str, confidence_score: float) -> Dict[str, str]:
        contract = self.runtime["output_contract"]
        if response_type not in contract["allowed_response_types"]:
            raise ValueError(f"invalid response_type: {response_type}")
        if confidence_score < 0 or confidence_score > 1:
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        return {
            "response_type": response_type,
            "content": content,
            "confidence_score": f"{confidence_score:.3g}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────

def leaf_runtime(root: Optional[Path] = None) -> Tuple[LeafPlatform, LeafBrand, LeafLog]:
    """Return (platform, brand, log) configured for *root*."""
    if root is None:
        for parent in Path(__file__).resolve().parents:
            if (parent / "config" / "brand.conf").exists():
                root = parent
                break
        if root is None:
            root = Path.cwd()
    plat  = LeafPlatform()
    brand = LeafBrand(plat)
    log   = LeafLog(root / "logs" / "session.log")
    return plat, brand, log
