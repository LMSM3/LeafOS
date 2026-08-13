#!/usr/bin/env python3
"""Read-only HTML reporting surface for LeafOS overnight runs."""
from __future__ import annotations
import argparse, html, json, time
from pathlib import Path
from typing import Any

def read_jsonl(path: Path, limit: int = 1000) -> list[dict[str, Any]]:
    if not path.is_file(): return []
    values=[]
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            item=json.loads(line)
            if isinstance(item, dict): values.append(item)
        except json.JSONDecodeError: pass
    return values

def category(event: dict[str, Any]) -> str:
    name=str(event.get("event") or event.get("action") or event.get("event_type") or "event").lower()
    if any(x in name for x in ("fail","reject","error","blocked")): return "failure"
    if any(x in name for x in ("coder","patch")): return "code"
    if any(x in name for x in ("brain","planner","dual")): return "thought"
    if any(x in name for x in ("checkpoint","context")): return "checkpoint"
    return "action"

def render_report(run_root: Path, output: Path|None=None) -> Path:
    run_root=run_root.resolve(); output=output or run_root/"LIVE_REPORT.html"
    events=read_jsonl(run_root/"journal.lje") + read_jsonl(run_root/"telemetry.jsonl") + read_jsonl(run_root/"actions.jsonl")
    cards=[]
    for event in events[-1000:]:
        kind=category(event); name=html.escape(str(event.get("event") or event.get("action") or event.get("event_type") or "event")); stamp=html.escape(str(event.get("time") or event.get("recorded_at") or event.get("ts") or "unknown")); data=html.escape(json.dumps(event.get("data", event.get("metrics", event)), indent=2, ensure_ascii=False))
        cards.append(f'<article class="{kind}"><b>{kind.upper()}</b><strong>{name}</strong><time>{stamp}</time><details><summary>Recorded data</summary><pre>{data}</pre></details></article>')
    body="\n".join(cards) or "<p>Waiting for journaled operational telemetry.</p>"
    page=f'''<!doctype html><meta charset="utf-8"><title>LeafOS Continual Report</title><style>body{{background:#070a10;color:#d7e1ee;font:13px Consolas,monospace;margin:20px}}article{{border-left:4px solid #62a8ff;background:#0e1420;margin:8px 0;padding:10px}}article.code{{border-color:#20e3b2}}article.thought{{border-color:#c084fc}}article.checkpoint{{border-color:#f4e06d}}article.failure{{border-color:#ff5d7a}}b{{display:inline-block;width:100px;color:#77859b}}strong{{margin-right:15px}}time{{color:#77859b}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style><h1>LeafOS continual mixed stream</h1><p>Read-only derived view. Explicit summaries and telemetry only; no hidden reasoning.</p>{body}<footer>Generated {html.escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</footer>'''
    output.parent.mkdir(parents=True, exist_ok=True); tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(page,encoding="utf-8"); tmp.replace(output); return output

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("run_root",type=Path);p.add_argument("--output",type=Path);a=p.parse_args();print(render_report(a.run_root,a.output));return 0
if __name__=="__main__": raise SystemExit(main())
