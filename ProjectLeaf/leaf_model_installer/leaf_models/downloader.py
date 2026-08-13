"""Legacy single-model helpers.

The supported command surface is leaf_models.install_cli. New orchestration
must go through a resolved InstallPlan in leaf_models.orchestrator.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from huggingface_hub import HfApi, hf_hub_url, snapshot_download

from .catalog import ModelEntry


class DownloadError(RuntimeError):
    pass


# Default number of files Hugging Face may fetch concurrently. Large GGUF repos
# often ship a single quant file, so the real speed win comes from the Xet
# high-performance transport rather than file-level fan-out, but more workers
# still helps multi-file repos like Oracle.
DEFAULT_MAX_WORKERS = 8


def enable_fast_transfer(high_performance: bool = True) -> dict[str, str]:
    """Turn on the fastest available transport before any download starts.

    huggingface_hub 1.x downloads Xet-backed repositories through the Rust ``hf_xet``
    backend. That backend reads ``HF_XET_HIGH_PERFORMANCE`` straight from the process
    environment when its session is first created, which is lazily, on the first
    download. The Python ``constants`` module only snapshots the flag at import time,
    so we set both: the environment (for the Rust session) and the already-imported
    constant (for any Python-side checks and diagnostics).

    The legacy ``hf_transfer`` accelerator was fully retired in huggingface_hub 1.x and
    now only emits a deprecation warning, so we proactively clear its env var to keep
    output clean. For plain LFS repositories the gains come from per-file concurrency
    (``max_workers``) rather than this flag, but enabling it is free and ensures any
    Xet-backed file in the allowlist transfers at full speed. This is the knob WO-007
    needed: without it, Xet transfers crawl near the ~2.8 MB/s floor.
    """
    applied: dict[str, str] = {}
    if high_performance:
        os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
        applied["HF_XET_HIGH_PERFORMANCE"] = "1"
        # Never let the deprecated hf_transfer path fight the Xet backend.
        os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
        try:
            from huggingface_hub import constants as hf_constants

            hf_constants.HF_XET_HIGH_PERFORMANCE = True
        except Exception:  # noqa: BLE001 - diagnostics only, never fatal
            pass
    return applied


@dataclass(frozen=True)
class LocalFileReport:
    repo_file: str
    local_path: str
    exists: bool
    bytes: int
    sha256: Optional[str] = None


@dataclass(frozen=True)
class DownloadReport:
    repo_id: str
    revision: str
    target_dir: str
    patterns: list[str]
    expected_files: list[str]
    local_files: list[LocalFileReport]
    missing_files: list[str]
    tiny_files: list[str]
    manifest_path: str
    success: bool
    nickname: str = ""
    role: str = ""
    elapsed_seconds: Optional[float] = None
    downloaded_bytes: int = 0
    high_performance: bool = False
    max_workers: Optional[int] = None

    @property
    def mbps(self) -> Optional[float]:
        """Measured throughput in MB/s, or None when we have nothing to measure."""
        if not self.elapsed_seconds or self.elapsed_seconds <= 0:
            return None
        if self.downloaded_bytes <= 0:
            return None
        return (self.downloaded_bytes / (1024 ** 2)) / self.elapsed_seconds


def resolve_patterns(model: ModelEntry, quant: Optional[str]) -> tuple[str, ...]:
    if quant:
        if quant not in model.quant_options:
            valid = ", ".join(model.quant_options)
            raise DownloadError(f"Model '{model.key}' does not support quant '{quant}'. Valid: {valid or 'none'}")
        return (model.quant_options[quant].pattern,)
    return model.default_patterns


def estimate_size_gb(model: ModelEntry, quant: Optional[str]) -> Optional[float]:
    if quant and quant in model.quant_options:
        return model.quant_options[quant].size_gb
    return None


def check_disk_space(destination: Path, estimated_gb: Optional[float], safety_multiplier: float = 1.25) -> tuple[bool, str]:
    destination.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(destination)
    free_gb = usage.free / (1024 ** 3)
    if estimated_gb is None:
        return True, f"Free space: {free_gb:.1f} GB. No exact estimate for this model pattern."
    needed = estimated_gb * safety_multiplier
    ok = free_gb >= needed
    return ok, f"Free space: {free_gb:.1f} GB. Estimated need with buffer: {needed:.1f} GB."


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(report: DownloadReport) -> Path:
    manifest = Path(report.manifest_path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_id": report.repo_id,
        "revision": report.revision,
        "nickname": report.nickname,
        "role": report.role,
        "target_dir": report.target_dir,
        "patterns": report.patterns,
        "expected_files": report.expected_files,
        "local_files": [asdict(item) for item in report.local_files],
        "missing_files": report.missing_files,
        "tiny_files": report.tiny_files,
        "success": report.success,
        "elapsed_seconds": report.elapsed_seconds,
        "downloaded_bytes": report.downloaded_bytes,
        "throughput_mb_s": round(report.mbps, 2) if report.mbps is not None else None,
        "high_performance": report.high_performance,
        "max_workers": report.max_workers,
    }
    manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest


def list_matching_files(
    model: ModelEntry,
    patterns: Iterable[str],
    revision: str = "main",
    excludes: Iterable[str] = (),
) -> List[str]:
    api = HfApi()
    try:
        files = api.list_repo_files(repo_id=model.repo_id, revision=revision)
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(str(exc)) from exc
    matches: list[str] = []
    pattern_list = list(patterns)
    exclude_list = list(excludes)
    for name in files:
        if any(fnmatch.fnmatch(name, pattern) for pattern in pattern_list):
            if any(fnmatch.fnmatch(name, exclude) for exclude in exclude_list):
                continue
            matches.append(name)
    return sorted(matches)


def matching_urls(model: ModelEntry, patterns: Iterable[str], revision: str = "main") -> list[str]:
    return [hf_hub_url(model.repo_id, filename=f, revision=revision) for f in list_matching_files(model, patterns, revision)]


@dataclass(frozen=True)
class BenchmarkResult:
    repo_id: str
    nickname: str
    sample_file: str
    sampled_bytes: int
    requested_bytes: int
    elapsed_seconds: float
    high_performance: bool
    http_status: int
    range_honored: bool

    @property
    def mbps(self) -> Optional[float]:
        if self.elapsed_seconds <= 0 or self.sampled_bytes <= 0:
            return None
        return (self.sampled_bytes / (1024 ** 2)) / self.elapsed_seconds


def benchmark_download(
    model: ModelEntry,
    patterns: Iterable[str],
    revision: str = "main",
    sample_bytes: int = 48 * 1024 * 1024,
    high_performance: bool = True,
) -> BenchmarkResult:
    """Measure real transfer speed by fetching a bounded byte range, not the whole model.

    WO-007 demands measured throughput instead of guesses, but the catalog models are
    multi-gigabyte. This grabs only the first ``sample_bytes`` of the first matching
    file via an HTTP Range request, so we get an honest MB/s reading in seconds without
    committing to a full download. It deliberately reuses the same accelerator toggle as
    the real download path so the number reflects production behaviour.
    """
    if sample_bytes <= 0:
        raise DownloadError("Benchmark sample size must be greater than zero bytes.")
    enable_fast_transfer(high_performance=high_performance)

    matches = list_matching_files(model, patterns, revision=revision)
    if not matches:
        raise DownloadError(
            f"No remote files matched {list(patterns)!r} in {model.repo_id}@{revision}. Nothing to benchmark."
        )
    sample_file = matches[0]
    url = hf_hub_url(model.repo_id, filename=sample_file, revision=revision)

    try:
        import httpx
    except Exception as exc:  # noqa: BLE001 - httpx ships with huggingface_hub
        raise DownloadError(f"Cannot benchmark without httpx: {exc}") from exc

    headers = {"Range": f"bytes=0-{max(sample_bytes - 1, 0)}"}
    received = 0
    status_code = 0
    range_honored = False
    started = time.perf_counter()
    try:
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                status_code = int(response.status_code)
                range_honored = status_code == 206 or bool(response.headers.get("content-range"))
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    remaining = sample_bytes - received
                    if remaining <= 0:
                        break
                    received += min(len(chunk), remaining)
                    if received >= sample_bytes:
                        break
    except Exception as exc:  # noqa: BLE001 - keep CLI readable
        raise DownloadError(f"Benchmark transfer failed: {exc}") from exc
    elapsed = time.perf_counter() - started

    return BenchmarkResult(
        repo_id=model.repo_id,
        nickname=model.nickname or model.key,
        sample_file=sample_file,
        sampled_bytes=received,
        requested_bytes=sample_bytes,
        elapsed_seconds=elapsed,
        high_performance=bool(high_performance),
        http_status=status_code,
        range_honored=range_honored,
    )


def benchmark_to_dict(result: BenchmarkResult) -> dict[str, object]:
    return {
        "schema": "leafos.model-download-benchmark.v1",
        "repo_id": result.repo_id, "nickname": result.nickname,
        "sample_file": result.sample_file, "requested_bytes": result.requested_bytes,
        "sampled_bytes": result.sampled_bytes,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "throughput_mb_s": round(result.mbps, 3) if result.mbps is not None else None,
        "high_performance": result.high_performance,
        "http_status": result.http_status, "range_honored": result.range_honored,
    }


def verify_local_files(
    model: ModelEntry,
    destination_root: Path,
    patterns: Iterable[str],
    revision: str = "main",
    expected_files: Optional[list[str]] = None,
    min_bytes: int = 1024 * 1024,
    compute_hash: bool = False,
) -> DownloadReport:
    """Verify that remote-matching files exist under the exact local target.

    This deliberately checks the local directory after download instead of trusting
    a happy return code from a library call. Humanity forced this feature.
    """
    pattern_list = list(patterns)
    target = (destination_root / model.local_dir).expanduser().resolve()
    if expected_files is None:
        expected_files = list_matching_files(model, pattern_list, revision=revision)

    local_reports: list[LocalFileReport] = []
    missing: list[str] = []
    tiny: list[str] = []

    for repo_file in expected_files:
        local_path = target / repo_file
        exists = local_path.is_file()
        size = local_path.stat().st_size if exists else 0
        digest = _sha256_file(local_path) if exists and compute_hash else None
        if not exists:
            missing.append(repo_file)
        elif size < min_bytes:
            tiny.append(repo_file)
        local_reports.append(
            LocalFileReport(
                repo_file=repo_file,
                local_path=str(local_path),
                exists=exists,
                bytes=size,
                sha256=digest,
            )
        )

    success = bool(expected_files) and not missing and not tiny
    manifest_path = str(target / "leaf_download_manifest.json")
    report = DownloadReport(
        repo_id=model.repo_id,
        revision=revision,
        target_dir=str(target),
        patterns=pattern_list,
        expected_files=expected_files,
        local_files=local_reports,
        missing_files=missing,
        tiny_files=tiny,
        manifest_path=manifest_path,
        success=success,
        nickname=model.nickname,
        role=model.role,
    )
    _write_manifest(report)
    return report


def download_model(
    model: ModelEntry,
    destination_root: Path,
    patterns: Iterable[str],
    revision: str = "main",
    min_bytes: int = 1024 * 1024,
    compute_hash: bool = False,
    max_workers: Optional[int] = DEFAULT_MAX_WORKERS,
    high_performance: bool = True,
) -> DownloadReport:
    pattern_list = list(patterns)
    target = (destination_root / model.local_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    expected = list_matching_files(model, pattern_list, revision=revision)
    if not expected:
        raise DownloadError(
            f"No remote files matched {pattern_list!r} in {model.repo_id}@{revision}. Refusing fake success."
        )

    # Flip on the fast transport before the Rust Xet session is created.
    enable_fast_transfer(high_performance=high_performance)

    common_kwargs = {
        "repo_id": model.repo_id,
        "revision": revision,
        "allow_patterns": pattern_list,
        "local_dir": str(target),
    }
    if max_workers and max_workers > 0:
        common_kwargs["max_workers"] = max_workers

    started = time.perf_counter()
    try:
        try:
            snapshot_download(local_dir_use_symlinks=False, **common_kwargs)
        except TypeError:
            # Newer huggingface_hub removed local_dir_use_symlinks (and may also
            # reject max_workers on very old builds); fall back progressively.
            try:
                snapshot_download(**common_kwargs)
            except TypeError:
                common_kwargs.pop("max_workers", None)
                snapshot_download(**common_kwargs)
    except Exception as exc:  # noqa: BLE001 - keep CLI readable
        raise DownloadError(str(exc)) from exc
    elapsed = time.perf_counter() - started

    report = verify_local_files(
        model,
        destination_root,
        pattern_list,
        revision=revision,
        expected_files=expected,
        min_bytes=min_bytes,
        compute_hash=compute_hash,
    )

    downloaded_bytes = sum(item.bytes for item in report.local_files if item.exists)
    report = replace(
        report,
        elapsed_seconds=elapsed,
        downloaded_bytes=downloaded_bytes,
        high_performance=bool(high_performance),
        max_workers=max_workers if (max_workers and max_workers > 0) else None,
    )
    _write_manifest(report)

    if not report.success:
        missing = ", ".join(report.missing_files) or "none"
        tiny = ", ".join(report.tiny_files) or "none"
        raise DownloadError(
            "Downloaded call returned, but verification failed. "
            f"Missing: {missing}. Tiny/suspicious: {tiny}. Manifest: {report.manifest_path}"
        )
    return report
