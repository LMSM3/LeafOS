from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from core.config import load_settings
from core.control.service import ControlService
from core.control.store import ControlError


def _wait_for_lease(service: ControlService, task_id: str, token: str, kind: str) -> None:
    deadline = time.monotonic() + 10.0
    key = "lease" if kind == "worker" else "verification_lease"
    while time.monotonic() < deadline:
        try:
            task = service.store.get_task(task_id)
        except ControlError:
            time.sleep(0.05)
            continue
        lease = task.get(key) if isinstance(task.get(key), dict) else {}
        if lease.get("token") == token and lease.get("pid") == os.getpid():
            return
        time.sleep(0.05)
    raise ControlError(f"worker lease was not granted: {task_id}")


def _heartbeat(service: ControlService, task_id: str, token: str, kind: str, stop: threading.Event) -> None:
    while not stop.wait(5.0):
        try:
            if kind == "worker":
                service.store.heartbeat_task(task_id, token)
            else:
                service.store.heartbeat_verification(task_id, token)
        except ControlError:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LeafOS one-shot scheduler worker")
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--kind", choices=("worker", "verifier"), required=True)
    args = parser.parse_args(argv)
    settings = load_settings()
    service = ControlService(settings, Path(args.project))
    stop = threading.Event()
    heartbeat: threading.Thread | None = None
    try:
        _wait_for_lease(service, args.task, args.token, args.kind)
        heartbeat = threading.Thread(
            target=_heartbeat,
            args=(service, args.task, args.token, args.kind, stop),
            name=f"leaf-heartbeat-{args.task}",
            daemon=True,
        )
        heartbeat.start()
        if args.kind == "worker":
            service.execute_claimed(args.task, args.token)
        else:
            service.verify(args.task, verifier_token=args.token)
        return 0
    except (ControlError, ValueError, OSError) as error:
        print(f"worker: {error}", file=sys.stderr)
        if args.kind == "worker":
            try:
                task = service.store.get_task(args.task)
                lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
                if task.get("status") == "running" and lease.get("token") == args.token:
                    service.store.release_task(args.task, args.token, str(error))
            except ControlError:
                pass
        return 1
    finally:
        stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1.0)


if __name__ == "__main__":
    raise SystemExit(main())
