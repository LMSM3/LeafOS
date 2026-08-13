#!/usr/bin/env python3
"""Model-free Monday affect PDF checkpoints for LeafOS overnight runs."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, time, webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from leaf_live_report import read_jsonl, render_report

CHANNELS=["persona_positive_terms","persona_caution_terms","persona_urgency_terms","persona_clarity_terms","planner_events","coder_events","validation_passes","validation_failures","checkpoint_valid","accepted_changes","rejected_changes","generation_rate","gpu_utilization","gpu_vram_used","cpu_utilization","recovery_events"]
PALETTE="viridis"; SCALE="normalized_0_to_1"

def chrome() -> str|None:
    candidates=[os.environ.get("LEAF_CHROME"),shutil.which("chrome"),shutil.which("chromium"),str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))/"Google/Chrome/Application/chrome.exe"),str(Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))/"Google/Chrome/Application/chrome.exe")]
    return next((p for p in candidates if p and Path(p).is_file()),None)

def event_name(e:dict[str,Any])->str: return str(e.get("event") or e.get("action") or e.get("event_type") or "").lower()
def metric(e:dict[str,Any], key:str)->float:
    d=e.get("data") if isinstance(e.get("data"),dict) else e.get("metrics") if isinstance(e.get("metrics"),dict) else e
    v=d.get(key) if isinstance(d,dict) else None
    return float(v) if isinstance(v,(int,float)) else 0.0

def values(e:dict[str,Any])->list[float]:
    name=event_name(e); text=json.dumps(e.get("data",e),ensure_ascii=False).lower(); m=e.get("metrics",{}) if isinstance(e.get("metrics"),dict) else {}
    return [float(any(x in text for x in ("good","pass","accepted","complete"))),float(any(x in text for x in ("caution","warn","risk"))),float(any(x in text for x in ("urgent","deadline","blocked"))),float(any(x in text for x in ("clear","ready","validated"))),float(any(x in name for x in ("brain","planner"))),float(any(x in name for x in ("coder","patch"))),float(any(x in name for x in ("validation","verify")) and not any(x in name for x in ("fail","reject"))),float(any(x in name for x in ("fail","reject","error","blocked"))),float(m.get("checkpoint_valid") is True),metric(e,"accepted_changes"),metric(e,"rejected_changes"),metric(e,"generation_tokens_per_second"),metric(e,"gpu_utilization_percent"),metric(e,"gpu_vram_used_gb"),metric(e,"cpu_utilization_percent"),float(any(x in name for x in ("recovery","recover")))]

def heatmap(events:list[dict[str,Any]])->list[list[float]]:
    slices=events[-16:]; rows=[[0.0]*16 for _ in range(16)]
    for col,event in enumerate(slices):
        for row,value in enumerate(values(event)): rows[row][16-len(slices)+col]=value
    for row in rows:
        peak=max(row)
        if peak: row[:]=[round(v/peak,4) for v in row]
    return rows

def color(v:float)->str:
    stops=[(68,1,84),(59,82,139),(33,145,140),(94,201,98),(253,231,37)]; x=max(0,min(1,v))*(len(stops)-1); i=min(int(x),len(stops)-2); f=x-i; a,b=stops[i],stops[i+1]; return "#%02x%02x%02x"%tuple(round(a[n]+(b[n]-a[n])*f) for n in range(3))
def heatmap_html(matrix:list[list[float]])->str:
    cells="".join(f'<div class="label">{CHANNELS[i]}</div>'+"".join(f'<i style="background:{color(v)}" title="{v}"></i>' for v in row) for i,row in enumerate(matrix)); return f'<div class="grid">{cells}</div>'
def journal(path:Path,event:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps(event,separators=(",",":"))+"\n");f.flush();os.fsync(f.fileno())
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def report_once(root:Path,open_chrome:bool=True)->Path:
    root=root.resolve(); events=read_jsonl(root/"journal.lje")+read_jsonl(root/"telemetry.jsonl")+read_jsonl(root/"actions.jsonl"); html=render_report(root); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); out=root/"reports"/"monday_affect"/f"MONDAY_AFFECT_{stamp}.pdf"; out.parent.mkdir(parents=True,exist_ok=True); affect=out.with_suffix(".html"); affect.write_text(f'<meta charset="utf-8"><style>body{{font-family:Arial}}.grid{{display:grid;grid-template-columns:210px repeat(16,28px);gap:2px}}.label{{font-size:10px;padding:6px 2px}}i{{height:28px}} </style><h1>Monday Affect Checkpoint</h1><p>16 channels × 16 recent journaled time slices; palette={PALETTE}; scale={SCALE}; no hidden reasoning.</p>{heatmap_html(heatmap(events))}',encoding="utf-8")
    exe=chrome(); generated=False; error=""
    if exe:
        result=subprocess.run([exe,"--headless","--disable-gpu",f"--print-to-pdf={out}",affect.as_uri()],capture_output=True,text=True,timeout=120); generated=result.returncode==0 and out.is_file(); error=result.stderr[-500:] if not generated else ""
    else:error="chrome_not_found"
    opened=False; open_error=""
    if generated and open_chrome:
        try: opened=webbrowser.open(out.as_uri())
        except Exception as exc: open_error=str(exc)
    event={"event":"report.monday_affect","time":datetime.now(timezone.utc).isoformat(),"data":{"path":str(out),"sha256":sha(out) if generated else None,"palette":PALETTE,"scale":SCALE,"generation_result":"success" if generated else "failed","generation_error":error,"chrome_open_result":"success" if opened else "recoverable_failure","chrome_open_error":open_error,"channels":CHANNELS,"source_policy":"journaled_persona_summaries_and_operational_telemetry_only"}}
    journal(root/"journal.lje",event)
    if not generated: raise RuntimeError(f"PDF generation failed: {error}")
    return out
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("run_root",type=Path);p.add_argument("--watch",action="store_true");p.add_argument("--interval-minutes",type=float,default=30);p.add_argument("--no-open",action="store_true");a=p.parse_args()
 try:
  while True:
   print(report_once(a.run_root,not a.no_open),flush=True)
   if not a.watch:return 0
   time.sleep(max(1,a.interval_minutes*60))
 except (OSError,RuntimeError,subprocess.SubprocessError) as e: print(f"reporting failure: {e}");return 1
if __name__=="__main__":raise SystemExit(main())
