from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.control.context import render_context_packet
from core.control.store import (
    ControlError,
    ProjectStore,
    _FileLock,
    _canonical_bytes,
)
from core.state import utc_now


EPOCH_STATE_SCHEMA = "leafos.epoch-state.v1"
EPOCH_MANIFEST_SCHEMA = "leafos.epoch-manifest.v1"
EVIDENCE_INDEX_SCHEMA = "leafos.epoch-evidence-index.v1"
FAILURES_SCHEMA = "leafos.epoch-failures.v1"
DECISIONS_SCHEMA = "leafos.epoch-decisions.v1"
NEXT_PLAN_SCHEMA = "leafos.epoch-next-plan.v1"
CONTEXT_SCHEMA = "leafos.context-packet.v2"
DEFAULT_EPOCH_MINUTES = 30
MAX_INDEX_TEXT_BYTES = 128 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return _canonical_bytes(value)


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _token_estimate(byte_count: int) -> int:
    return math.ceil(max(0, byte_count) / 4)


def _parse_time(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class EpochManager:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.state_path = store.state_dir / "epochs.json"

    def initialize(self, minutes: int = DEFAULT_EPOCH_MINUTES) -> dict[str, Any]:
        if not 1 <= minutes <= 1440:
            raise ControlError("epoch minutes must be between 1 and 1440")
        self.store._prepare()
        if self.state_path.is_file():
            return self._read_state()
        now = utc_now()
        state = {
            "schema": EPOCH_STATE_SCHEMA,
            "revision": 1,
            "project_id": self.store.project_identity["id"],
            "interval_minutes": minutes,
            "next_epoch": 1,
            "latest_epoch": None,
            "last_review_at": None,
            "indexed_evidence": [],
            "decision_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        return self.store._write_document(self.state_path, state)

    def _read_state(self) -> dict[str, Any]:
        state = self.store._read_document(self.state_path, EPOCH_STATE_SCHEMA)
        if state.get("project_id") != self.store.project_identity["id"]:
            raise ControlError("epoch state belongs to a different project")
        return state

    def configure(self, minutes: int) -> dict[str, Any]:
        if not 1 <= minutes <= 1440:
            raise ControlError("epoch minutes must be between 1 and 1440")
        with _FileLock(self.store.lock_path):
            state = self._read_state() if self.state_path.is_file() else self.initialize(minutes)
            if int(state.get("interval_minutes", DEFAULT_EPOCH_MINUTES)) == minutes:
                return state
            state["interval_minutes"] = minutes
            state["revision"] = int(state.get("revision", 0)) + 1
            state["updated_at"] = utc_now()
            return self.store._write_document(self.state_path, state)

    def status(self) -> dict[str, Any]:
        state = self._read_state() if self.state_path.is_file() else self.initialize()
        last = _parse_time(state.get("last_review_at"))
        due_at = last + timedelta(minutes=int(state["interval_minutes"])) if last else None
        now = datetime.now(timezone.utc)
        return {
            **state,
            "due": due_at is None or now >= due_at,
            "next_due_at": due_at.isoformat() if due_at else "now",
        }

    def _epoch_path(self, epoch_id: str) -> Path:
        return self.store.epochs_dir / epoch_id

    def _write_immutable(self, path: Path, value: dict[str, Any]) -> dict[str, Any]:
        if path.exists():
            raise ControlError(f"immutable epoch record already exists: {path}")
        return self.store._write_document(path, value)

    def _read_epoch_document(self, epoch_id: str, name: str, schema: str) -> dict[str, Any]:
        path = self._epoch_path(epoch_id) / name
        return self.store._read_document(path, schema)

    def _artifact_text(self, artifact: dict[str, Any]) -> str | None:
        path_value = artifact.get("path")
        if not isinstance(path_value, str):
            return None
        path = (self.store.project_root / path_value).resolve()
        try:
            path.relative_to(self.store.project_root)
        except ValueError:
            return None
        if not path.is_file() or path.stat().st_size > MAX_INDEX_TEXT_BYTES:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _collect_inputs(
        self,
        graph: dict[str, Any],
        new_evidence_ids: list[str],
        new_decisions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]], list[dict[str, Any]]]:
        snippets: list[dict[str, Any]] = []
        raw_bytes = 0

        def add(text: str, *, source: str, evidence_id: str | None = None, task_id: str | None = None) -> None:
            nonlocal raw_bytes
            data = text.encode("utf-8")
            raw_bytes += len(data)
            normalized = _normalized_text(text)
            if not normalized:
                return
            snippets.append(
                {
                    "text": normalized,
                    "source": source,
                    "evidence_id": evidence_id,
                    "task_id": task_id,
                }
            )

        objective = self.store.load_objective()
        add(str(objective["text"]), source="objective")
        tasks = graph["tasks"]
        for task in tasks.values():
            add(str(task.get("goal") or ""), source="task-goal", task_id=task["id"])
        evidence_records = []
        for evidence_id in new_evidence_ids:
            record = self.store._read_evidence(evidence_id)
            evidence_records.append(record)
            for claim in record.get("claims", []):
                if isinstance(claim, dict):
                    add(str(claim.get("text") or ""), source="claim", evidence_id=evidence_id, task_id=record["task_id"])
            for contradiction in record.get("contradictions", []):
                add(str(contradiction), source="contradiction", evidence_id=evidence_id, task_id=record["task_id"])
            for artifact in record.get("artifacts", []):
                text = self._artifact_text(artifact)
                if text is not None:
                    add(text, source="artifact", evidence_id=evidence_id, task_id=record["task_id"])
        for decision in new_decisions:
            text = json.dumps(
                {key: value for key, value in decision.items() if key != "integrity"},
                sort_keys=True,
                ensure_ascii=False,
            )
            add(text, source="decision", task_id=decision.get("task_id"))

        groups: dict[str, dict[str, Any]] = {}
        for snippet in snippets:
            digest = _sha256(snippet["text"].encode("utf-8"))
            group = groups.setdefault(
                digest,
                {
                    "digest": f"sha256:{digest}",
                    "text": snippet["text"],
                    "sources": [],
                    "evidence_ids": [],
                    "task_ids": [],
                    "occurrences": 0,
                },
            )
            group["occurrences"] += 1
            if snippet["source"] not in group["sources"]:
                group["sources"].append(snippet["source"])
            if snippet["evidence_id"] and snippet["evidence_id"] not in group["evidence_ids"]:
                group["evidence_ids"].append(snippet["evidence_id"])
            if snippet["task_id"] and snippet["task_id"] not in group["task_ids"]:
                group["task_ids"].append(snippet["task_id"])
        deduplicated = sorted(groups.values(), key=lambda value: value["digest"])

        contradictions = []
        for task in tasks.values():
            for contradiction in task.get("contradictions", []):
                contradictions.append({"task_id": task["id"], **contradiction})
            verdicts = {
                record.get("verdict")
                for record in evidence_records
                if record.get("task_id") == task["id"] and record.get("kind") == "verification"
            }
            if "accept" in verdicts and "reject" in verdicts:
                contradictions.append(
                    {
                        "task_id": task["id"],
                        "reason": "epoch detected opposing verifier verdicts",
                        "evidence_ids": [
                            record["id"] for record in evidence_records
                            if record.get("task_id") == task["id"] and record.get("kind") == "verification"
                        ],
                    }
                )
        return deduplicated, raw_bytes, evidence_records, contradictions

    @staticmethod
    def _accepted_decision_link(decision: dict[str, Any]) -> dict[str, Any]:
        evidence_ids = list(decision.get("verifier_evidence", []))
        for claim in decision.get("claims", []):
            if not isinstance(claim, dict):
                continue
            for evidence_id in claim.get("evidence_ids", []):
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        return {
            "id": decision.get("id"),
            "kind": decision.get("kind"),
            "task_id": decision.get("task_id"),
            "evidence_ids": evidence_ids,
            "observed_at": decision.get("observed_at"),
        }

    def _compact_packet(
        self,
        *,
        epoch_id: str,
        graph: dict[str, Any],
        evidence_records: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        next_actions: list[str],
        raw_bytes: int,
    ) -> tuple[dict[str, Any], dict[str, int | float | str]]:
        objective = self.store.load_objective()
        counts: dict[str, int] = {}
        active = []
        for task in graph["tasks"].values():
            status = str(task.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
            if status not in {"accepted", "failed", "cancelled"}:
                active.append(
                    {
                        "id": task["id"], "status": status, "lane": task["lane"],
                        "dependencies": task.get("dependencies", []), "evidence": task.get("evidence", []),
                        "confidence": task.get("confidence", "unverified"),
                    }
                )
        accepted_links = [
            self._accepted_decision_link(decision)
            for decision in decisions
            if decision.get("kind") == "acceptance"
        ]
        evidence_links = []
        for record in evidence_records:
            artifacts = [
                {key: artifact.get(key) for key in ("path", "sha256", "bytes", "role") if artifact.get(key) is not None}
                for artifact in record.get("artifacts", [])
            ]
            evidence_links.append(
                {
                    "id": record["id"], "task_id": record["task_id"], "kind": record["kind"],
                    "exit_code": record.get("exit_code"), "confidence": record.get("confidence"),
                    "verdict": record.get("verdict"), "artifacts": artifacts,
                }
            )
        unknowns = []
        if contradictions:
            unknowns.append({"kind": "contradiction", "count": len(contradictions), "records": contradictions})
        if any(task.get("status") == "verifying" for task in graph["tasks"].values()):
            unknowns.append({"kind": "unaccepted-worker-output", "count": counts.get("verifying", 0)})
        packet = {
            "schema": CONTEXT_SCHEMA,
            "epoch": epoch_id,
            "generated_at": utc_now(),
            "objective": objective["text"],
            "project": {key: objective["project"][key] for key in ("id", "name", "root")},
            "current_state": {"phase": objective["phase"], "mode": objective["mode"], "tasks": counts},
            "last_decisions": accepted_links[-10:],
            "active_tasks": active,
            "new_evidence": evidence_links,
            "unresolved_failures": failures,
            "unknown_or_conflicting": unknowns,
            "next_recommended_actions": next_actions[:3],
            "provenance": {
                "objective_integrity": objective["integrity"],
                "taskgraph_integrity": graph["integrity"],
                "epoch": epoch_id,
            },
        }
        minimum_packet = {
            **packet,
            "active_tasks": [
                {"id": value["id"], "status": value["status"]}
                for value in active
            ],
            "unresolved_failures": [
                {key: value.get(key) for key in ("id", "task_id", "error") if value.get(key) is not None}
                for value in failures
            ],
            "unknown_or_conflicting": [
                {"kind": value["kind"], "count": value.get("count", 1)}
                for value in unknowns
            ],
        }

        def account(
            body: dict[str, Any], evidence_floor: int, allowed: int, basis: str
        ) -> tuple[dict[str, Any], dict[str, int | float | str]]:
            result = dict(body)
            accounting: dict[str, int | float | str] = {
                "raw_input_bytes": raw_bytes,
                "raw_input_token_estimate": _token_estimate(raw_bytes),
                "packet_bytes": 0,
                "packet_token_estimate": 0,
                "packet_to_raw_ratio": 0.0,
                "target_ratio": 0.20,
                "evidence_floor_bytes": evidence_floor,
                "allowed_packet_bytes": allowed,
                "limit_basis": basis,
            }
            result["accounting"] = accounting
            for _ in range(12):
                size = len(_json_bytes(result))
                before = (
                    accounting["packet_bytes"], accounting["packet_token_estimate"],
                    accounting["packet_to_raw_ratio"],
                )
                accounting["packet_bytes"] = size
                accounting["packet_token_estimate"] = _token_estimate(size)
                accounting["packet_to_raw_ratio"] = round(size / raw_bytes if raw_bytes else 0.0, 6)
                after = (
                    accounting["packet_bytes"], accounting["packet_token_estimate"],
                    accounting["packet_to_raw_ratio"],
                )
                if before == after:
                    break
            return result, accounting

        ratio_target = math.ceil(raw_bytes * 0.20)
        evidence_floor = 0
        for _ in range(12):
            basis = "evidence-floor" if evidence_floor > ratio_target else "20-percent"
            allowed = max(ratio_target, evidence_floor)
            floor_packet, floor_accounting = account(minimum_packet, evidence_floor, allowed, basis)
            measured = int(floor_accounting["packet_bytes"])
            if measured == evidence_floor:
                break
            evidence_floor = measured
        allowed = max(ratio_target, evidence_floor)
        basis = "evidence-floor" if evidence_floor > ratio_target else "20-percent"
        packet, accounting = account(packet, evidence_floor, allowed, basis)
        if int(accounting["packet_bytes"]) > allowed:
            packet, accounting = account(minimum_packet, evidence_floor, allowed, basis)
        if int(accounting["packet_bytes"]) > allowed:
            raise ControlError("context packet could not satisfy its evidence-aware size policy")
        return packet, accounting

    def review(self, *, manual: bool = False) -> dict[str, Any]:
        self.store.audit()
        live_packet = self.store.export_context()
        with _FileLock(self.store.lock_path):
            state = self._read_state() if self.state_path.is_file() else self.initialize()
            last = _parse_time(state.get("last_review_at"))
            due_at = last + timedelta(minutes=int(state["interval_minutes"])) if last else None
            if not manual and due_at is not None and datetime.now(timezone.utc) < due_at:
                raise ControlError(f"epoch review is not due until {due_at.isoformat()}; use --manual to review early")
            graph = self.store.load_taskgraph()
            all_evidence_ids = [
                evidence_id
                for task in graph["tasks"].values()
                for evidence_id in task.get("evidence", [])
            ]
            indexed = set(state.get("indexed_evidence", []))
            new_evidence_ids = [value for value in all_evidence_ids if value not in indexed]
            all_decisions = self.store._read_records(self.store.decisions_path)
            decision_offset = int(state.get("decision_count", 0))
            new_decisions = all_decisions[decision_offset:]
            deduplicated, raw_bytes, evidence_records, contradictions = self._collect_inputs(
                graph, new_evidence_ids, new_decisions
            )
            failures = live_packet["unresolved_failures"]
            next_actions = live_packet["next_recommended_actions"]
            epoch_number = int(state.get("next_epoch", 1))
            epoch_id = f"epoch-{epoch_number:06d}"
            epoch_dir = self._epoch_path(epoch_id)
            if epoch_dir.exists():
                raise ControlError(f"epoch directory already exists: {epoch_dir}")
            epoch_dir.mkdir(parents=True, exist_ok=False)
            observed_at = utc_now()

            evidence_index = self._write_immutable(
                epoch_dir / "evidence-index.json",
                {
                    "schema": EVIDENCE_INDEX_SCHEMA,
                    "epoch": epoch_id,
                    "observed_at": observed_at,
                    "raw_occurrences": sum(int(value["occurrences"]) for value in deduplicated),
                    "unique_entries": len(deduplicated),
                    "entries": deduplicated,
                    "contradictions": contradictions,
                },
            )
            failure_doc = self._write_immutable(
                epoch_dir / "failures.json",
                {"schema": FAILURES_SCHEMA, "epoch": epoch_id, "observed_at": observed_at, "failures": failures},
            )
            decision_doc = self._write_immutable(
                epoch_dir / "decisions.json",
                {
                    "schema": DECISIONS_SCHEMA,
                    "epoch": epoch_id,
                    "observed_at": observed_at,
                    "decisions": [
                        {key: value for key, value in decision.items() if key != "integrity"}
                        for decision in new_decisions
                    ],
                },
            )
            plan_doc = self._write_immutable(
                epoch_dir / "next-plan.json",
                {
                    "schema": NEXT_PLAN_SCHEMA,
                    "epoch": epoch_id,
                    "observed_at": observed_at,
                    "actions": next_actions,
                    "blocked_by_contradictions": bool(contradictions),
                },
            )
            packet, accounting = self._compact_packet(
                epoch_id=epoch_id,
                graph=graph,
                evidence_records=evidence_records,
                decisions=all_decisions,
                failures=failures,
                contradictions=contradictions,
                next_actions=next_actions,
                raw_bytes=raw_bytes,
            )
            context_doc = self._write_immutable(epoch_dir / "context.json", packet)
            context_text = render_context_packet(context_doc)
            context_text_path = epoch_dir / "context.txt"
            if context_text_path.exists():
                raise ControlError(f"immutable epoch record already exists: {context_text_path}")
            self.store._atomic_text(context_text_path, context_text)
            documents = {}
            for name, document in (
                ("evidence-index.json", evidence_index),
                ("failures.json", failure_doc),
                ("decisions.json", decision_doc),
                ("next-plan.json", plan_doc),
                ("context.json", context_doc),
            ):
                data = (epoch_dir / name).read_bytes()
                documents[name] = {"sha256": _sha256(data), "bytes": len(data), "integrity": document["integrity"]}
            text_data = context_text_path.read_bytes()
            documents["context.txt"] = {"sha256": _sha256(text_data), "bytes": len(text_data)}
            manifest = self._write_immutable(
                epoch_dir / "manifest.json",
                {
                    "schema": EPOCH_MANIFEST_SCHEMA,
                    "id": epoch_id,
                    "project_id": self.store.project_identity["id"],
                    "observed_at": observed_at,
                    "manual": manual,
                    "interval_minutes": int(state["interval_minutes"]),
                    "taskgraph_integrity": graph["integrity"],
                    "evidence_ids": new_evidence_ids,
                    "decision_ids": [value.get("id") for value in new_decisions if value.get("id")],
                    "accounting": accounting,
                    "documents": documents,
                },
            )
            state.update(
                {
                    "revision": int(state.get("revision", 0)) + 1,
                    "next_epoch": epoch_number + 1,
                    "latest_epoch": epoch_id,
                    "latest_manifest_integrity": manifest["integrity"],
                    "last_review_at": observed_at,
                    "indexed_evidence": all_evidence_ids,
                    "decision_count": len(all_decisions),
                    "updated_at": observed_at,
                }
            )
            self.store._write_document(self.state_path, state)
            self.store._journal(
                "epoch.reviewed",
                epoch_id=epoch_id,
                manual=manual,
                evidence=len(new_evidence_ids),
                raw_bytes=raw_bytes,
                packet_bytes=accounting["packet_bytes"],
            )
            return {"manifest": manifest, "context": context_doc, "next_plan": plan_doc}

    def verify_epoch(self, epoch_id: str) -> dict[str, Any]:
        manifest = self._read_epoch_document(epoch_id, "manifest.json", EPOCH_MANIFEST_SCHEMA)
        if manifest.get("project_id") != self.store.project_identity["id"]:
            raise ControlError(f"epoch belongs to a different project: {epoch_id}")
        for name, expected in manifest.get("documents", {}).items():
            path = self._epoch_path(epoch_id) / name
            if not path.is_file():
                raise ControlError(f"epoch document is missing: {path}")
            data = path.read_bytes()
            if _sha256(data) != expected.get("sha256") or len(data) != expected.get("bytes"):
                raise ControlError(f"epoch document integrity check failed: {path}")
        self._read_epoch_document(epoch_id, "evidence-index.json", EVIDENCE_INDEX_SCHEMA)
        self._read_epoch_document(epoch_id, "failures.json", FAILURES_SCHEMA)
        self._read_epoch_document(epoch_id, "decisions.json", DECISIONS_SCHEMA)
        self._read_epoch_document(epoch_id, "next-plan.json", NEXT_PLAN_SCHEMA)
        self._read_epoch_document(epoch_id, "context.json", CONTEXT_SCHEMA)
        return manifest

    def export_context(self, epoch_id: str | None = None) -> dict[str, Any]:
        state = self._read_state() if self.state_path.is_file() else self.initialize()
        selected = epoch_id or state.get("latest_epoch")
        if not isinstance(selected, str) or not selected:
            return self.store.export_context()
        self.verify_epoch(selected)
        return self._read_epoch_document(selected, "context.json", CONTEXT_SCHEMA)
