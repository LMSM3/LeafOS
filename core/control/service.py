from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import Settings
from core.models.inventory import load_inventory
from core.routing.packs import PackError, find_pack, route_lane, validate_pack
from core.runtime.llama import run_model_capture
from core.state import read_json

from core.control.context import render_context_packet
from core.control.epochs import EpochManager
from core.control.store import CURRENT_CONTROL_PHASE, ControlError, ProjectStore
from core.control.tools import execute_tool


def discover_project(start: Path | None = None, explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise ControlError(f"project directory is missing: {root}")
        return root
    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    lineage = (current, *current.parents)
    for candidate in lineage:
        if (candidate / ".leaf" / "state" / "objective.json").is_file():
            return candidate
    for candidate in lineage:
        if (
            (candidate / "VERSION").is_file()
            and (candidate / "core").is_dir()
            and ((candidate / "bin" / "leafctl").is_file() or (candidate / "bin" / "leafctl.cmd").is_file())
        ):
            return candidate
    for candidate in lineage:
        if (candidate / ".git").exists():
            return candidate
    return current


def _parse_verifier_response(response: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for position, value in enumerate(response):
        if value != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(response[position:])
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        required = {"verdict", "confidence", "claims", "contradictions"}
        if not required.issubset(parsed):
            continue
        claims = []
        for claim in parsed.get("claims", []):
            if not isinstance(claim, dict):
                continue
            evidence_ids = claim.get("evidence_ids")
            if not isinstance(evidence_ids, list):
                evidence_ids = []
            claims.append(
                {
                    "text": str(claim.get("text") or "").strip(),
                    "evidence_ids": [str(item) for item in evidence_ids if isinstance(item, str)],
                }
            )
        contradictions = parsed.get("contradictions")
        return {
            "verdict": str(parsed.get("verdict") or "invalid").casefold(),
            "confidence": str(parsed.get("confidence") or "unverified").casefold(),
            "claims": claims,
            "contradictions": [str(item) for item in contradictions] if isinstance(contradictions, list) else [],
            "parse_error": None,
        }
    return {
        "verdict": "invalid",
        "confidence": "unverified",
        "claims": [],
        "contradictions": [],
        "parse_error": "verifier response did not contain a JSON object",
    }


class ControlService:
    def __init__(self, settings: Settings, project_root: Path) -> None:
        self.settings = settings
        self.store = ProjectStore(project_root)

    def _active_pack(self) -> tuple[dict[str, Any], dict[str, Any]]:
        inventory = load_inventory(self.settings.inventory_path)
        runtime_state = read_json(self.settings.state_path, {})
        active_pack = runtime_state.get("active_pack")
        if not isinstance(active_pack, str) or not active_pack:
            raise ControlError("no active pack; run 'leafctl pack use <pack>'")
        try:
            _, pack = find_pack(self.settings.packs_dir, active_pack)
            errors = validate_pack(pack, inventory)
        except PackError as error:
            raise ControlError(str(error)) from error
        if errors:
            raise ControlError("active pack is not usable: " + "; ".join(errors))
        return pack, inventory

    def plan(self, objective: str, *, replace: bool = False) -> dict[str, Any]:
        pack, _ = self._active_pack()
        record = self.store.initialize(objective, replace=replace)
        record = self.store.advance_phase(CURRENT_CONTROL_PHASE)
        epoch = EpochManager(self.store).initialize()
        return {
            "project": record["project"],
            "objective": record["text"],
            "phase": record["phase"],
            "mode": record["mode"],
            "pack": pack["id"],
            "lanes": sorted(pack["lanes"]),
            "state": str(self.store.leaf_dir),
            "epoch_interval_minutes": epoch["interval_minutes"],
        }

    def submit(
        self,
        goal: str,
        lane: str,
        *,
        prompt: str | None = None,
        input_paths: list[str] | None = None,
        dependencies: list[str] | None = None,
        tokens: int = 128,
        context: int | None = None,
        timeout_seconds: int = 300,
        attempts: int = 2,
        tool_attempts: int = 3,
        verifier_attempts: int = 2,
        priority: int = 50,
        schedule_class: str = "critical",
        cpu: bool = False,
        defer: bool = False,
    ) -> dict[str, Any]:
        pack, inventory = self._active_pack()
        try:
            model = route_lane(pack, lane, inventory)
        except PackError as error:
            raise ControlError(str(error)) from error
        effective_context = context or self.settings.context
        task = self.store.create_task(
            goal,
            lane,
            prompt=prompt,
            input_paths=input_paths,
            dependencies=dependencies,
            tokens=tokens,
            context=effective_context,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
            tool_attempts=tool_attempts,
            verifier_attempts=verifier_attempts,
            priority=priority,
            schedule_class=schedule_class,
        )
        if defer or task["status"] != "ready":
            return task
        sources = self.store.source_contents(task)
        if sources:
            sections = []
            for source in sources:
                sections.append(
                    f"--- SOURCE {source['path']} sha256:{source['sha256']} ---\n{source['content']}"
                )
            worker_prompt = (
                "You are a bounded LeafOS read-only repository-analysis worker.\n"
                f"Task: {goal}\n"
                f"Requested focus: {prompt or goal}\n"
                "Use only the attached project sources for project-specific claims. Cite their relative paths.\n\n"
                + "\n\n".join(sections)
            )
        else:
            worker_prompt = prompt or (
                "You are a bounded LeafOS local inference worker.\n"
                f"Task: {goal}\n"
                "Return a concise evidence-oriented result. Do not claim that tools, files, or tests were used unless the task input contains their output."
            )
        available_prompt_bytes = (effective_context - tokens - 128) * 3
        if len(worker_prompt.encode("utf-8")) > available_prompt_bytes:
            raise ControlError("task prompt exceeds the selected context policy")
        claimed = self.store.claim_task(task["id"])
        lease_token = str(claimed.get("lease", {}).get("token"))
        result = run_model_capture(
            self.settings,
            model,
            worker_prompt,
            int(claimed["budget"]["tokens"]),
            claimed["budget"]["context"],
            cpu,
            timeout_seconds=int(claimed["budget"]["timeout_seconds"]),
            process_started=lambda pid: self.store.bind_runtime_process(task["id"], lease_token, pid),
        )
        return self.store.finalize_execution(
            task["id"],
            result,
            lane=lane,
            model=model,
            input_sources=sources,
            lease_token=lease_token,
        )

    def execute_claimed(self, task_id: str, lease_token: str, *, cpu: bool = False) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
        if task.get("status") != "running" or lease.get("token") != lease_token:
            raise ControlError(f"task is not held by this worker lease: {task_id}")
        pack, inventory = self._active_pack()
        lane = str(task.get("lane") or pack.get("default_lane") or "fast")
        try:
            model = route_lane(pack, lane, inventory)
        except PackError as error:
            raise ControlError(str(error)) from error
        sources = self.store.source_contents(task)
        if sources:
            sections = [
                f"--- SOURCE {source['path']} sha256:{source['sha256']} ---\n{source['content']}"
                for source in sources
            ]
            worker_prompt = (
                "You are a bounded LeafOS read-only repository-analysis worker.\n"
                f"Task: {task['goal']}\n"
                f"Requested focus: {task.get('inputs', {}).get('prompt') or task['goal']}\n"
                "Use only the attached project sources for project-specific claims. Cite their relative paths.\n\n"
                + "\n\n".join(sections)
            )
        else:
            worker_prompt = task.get("inputs", {}).get("prompt") or (
                "You are a bounded LeafOS local inference worker.\n"
                f"Task: {task['goal']}\n"
                "Return a concise evidence-oriented result. Do not claim that tools, files, or tests were used unless the task input contains their output."
            )
        effective_context = int(task.get("budget", {}).get("context") or self.settings.context)
        tokens = int(task.get("budget", {}).get("tokens", 128))
        available_prompt_bytes = (effective_context - tokens - 128) * 3
        if len(worker_prompt.encode("utf-8")) > available_prompt_bytes:
            raise ControlError("task prompt exceeds the selected context policy")
        result = run_model_capture(
            self.settings,
            model,
            worker_prompt,
            tokens,
            effective_context,
            cpu,
            timeout_seconds=int(task.get("budget", {}).get("timeout_seconds", 300)),
            process_started=lambda pid: self.store.bind_runtime_process(task_id, lease_token, pid),
        )
        return self.store.finalize_execution(
            task_id,
            result,
            lane=lane,
            model=model,
            input_sources=sources,
            lease_token=lease_token,
        )

    def run_tool(
        self,
        task_id: str,
        tool: str,
        *,
        path: str | None = None,
        query: str | None = None,
        selector: str | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task.get("status") != "verifying":
            raise ControlError(f"tool evidence requires a verifying task: {task_id} ({task.get('status')})")
        result = execute_tool(
            self.store.project_root,
            tool,
            path=path,
            query=query,
            selector=selector,
            timeout_seconds=timeout_seconds,
        )
        task = self.store.record_tool_execution(task_id, result)
        evidence = self.store.evidence_records(task_id)[-1]
        return {"task": task, "evidence": evidence}

    def verify(
        self,
        task_id: str,
        *,
        lane: str = "verifier",
        tokens: int = 256,
        context: int | None = None,
        timeout_seconds: int = 300,
        cpu: bool = False,
        verifier_token: str | None = None,
    ) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task.get("status") != "verifying":
            raise ControlError(f"verification requires a verifying task: {task_id} ({task.get('status')})")
        pack, inventory = self._active_pack()
        try:
            model = route_lane(pack, lane, inventory)
        except PackError as error:
            raise ControlError(str(error)) from error
        records = self.store.evidence_records(task_id)
        worker_model_ids = {
            record.get("source", {}).get("model_id")
            for record in records
            if record.get("kind") == "local-model-inference"
        }
        if not worker_model_ids:
            raise ControlError("task has no worker inference evidence to verify")
        if model.get("id") in worker_model_ids:
            raise ControlError("verifier lane resolves to the worker model; choose an independent lane")
        self.store.audit()
        output = task.get("output") if isinstance(task.get("output"), dict) else {}
        output_path = self.store.project_root / str(output.get("path") or "")
        worker_output = output_path.read_text(encoding="utf-8")
        summaries = []
        for record in records:
            summary = {
                "id": record["id"],
                "kind": record["kind"],
                "producer": record["producer"],
                "exit_code": record["exit_code"],
                "source": record.get("source"),
                "input_sources": record.get("input_sources", []),
                "command": record.get("command"),
                "next_action": record.get("next_action"),
                "artifacts": [
                    {key: artifact.get(key) for key in ("role", "path", "source_path", "sha256", "bytes")}
                    for artifact in record.get("artifacts", [])
                ],
            }
            for artifact in record.get("artifacts", []):
                if artifact.get("role") != "tool-stdout":
                    continue
                path = self.store.project_root / artifact["path"]
                if artifact.get("bytes", 0) <= 64 * 1024:
                    summary["tool_stdout"] = path.read_text(encoding="utf-8")
            summaries.append(summary)
        effective_context = context or self.settings.context
        verifier_prompt = (
            "You are the independent LeafOS verifier. You did not produce the worker result.\n"
            "Judge only the supplied task output and evidence. A model claim without source, command, test, or captured artifact evidence is not verified.\n"
            "Return exactly one JSON object and no markdown using this schema:\n"
            '{"verdict":"accept|reject|conflict","confidence":"low|medium|high",'
            '"claims":[{"text":"claim","evidence_ids":["evidence-NNNNNN"]}],'
            '"contradictions":["description"]}\n'
            f"TASK ID: {task_id}\nTASK GOAL: {task['goal']}\n"
            f"WORKER OUTPUT:\n{worker_output}\n"
            f"EVIDENCE INDEX:\n{json.dumps(summaries, ensure_ascii=False)}\n"
        )
        available_prompt_bytes = (effective_context - tokens - 128) * 3
        if available_prompt_bytes < 1 or len(verifier_prompt.encode("utf-8")) > available_prompt_bytes:
            raise ControlError("verifier packet exceeds the selected context policy")
        result = run_model_capture(
            self.settings,
            model,
            verifier_prompt,
            tokens,
            effective_context,
            cpu,
            timeout_seconds=timeout_seconds,
            process_started=(
                (lambda pid: self.store.bind_runtime_process(task_id, verifier_token, pid, verifier=True))
                if verifier_token is not None else None
            ),
        )
        parsed = _parse_verifier_response(str(result.get("response") or ""))
        if int(result.get("return_code", 1)) != 0:
            parsed.update(
                {
                    "verdict": "invalid",
                    "confidence": "unverified",
                    "claims": [],
                    "parse_error": f"verifier runtime exited with code {result.get('return_code')}",
                }
            )
        parsed.update({"tokens": tokens, "context": effective_context, "timeout_seconds": timeout_seconds})
        task = self.store.record_verification(
            task_id, result, parsed, lane=lane, model=model, verifier_token=verifier_token
        )
        evidence = self.store.evidence_records(task_id)[-1]
        return {"task": task, "evidence": evidence}

    def accept(self, task_id: str, reason: str) -> dict[str, Any]:
        return self.store.accept_task(task_id, reason)

    def dispute(self, task_id: str, evidence_ids: list[str], reason: str) -> dict[str, Any]:
        return self.store.dispute_task(task_id, evidence_ids, reason)

    def cancel(self, task_id: str, reason: str) -> dict[str, Any]:
        return self.store.cancel_task(task_id, reason)

    def inspect(self, task_id: str) -> dict[str, Any]:
        return self.store.get_task(task_id)

    def summary(self) -> dict[str, Any] | None:
        return self.store.summary() if self.store.initialized else None

    def export_context(self) -> dict[str, Any]:
        if not self.store.initialized:
            raise ControlError("project control state is not initialized; run 'leafctl swarm plan --objective ...'")
        return EpochManager(self.store).export_context()

    def epoch_status(self) -> dict[str, Any]:
        if not self.store.initialized:
            raise ControlError("project control state is not initialized; run 'leafctl swarm plan --objective ...'")
        return EpochManager(self.store).status()

    def configure_epoch(self, minutes: int) -> dict[str, Any]:
        if not self.store.initialized:
            raise ControlError("project control state is not initialized; run 'leafctl swarm plan --objective ...'")
        return EpochManager(self.store).configure(minutes)

    def review_epoch(self, *, manual: bool = False) -> dict[str, Any]:
        if not self.store.initialized:
            raise ControlError("project control state is not initialized; run 'leafctl swarm plan --objective ...'")
        return EpochManager(self.store).review(manual=manual)
