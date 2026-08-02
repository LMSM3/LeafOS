#!/usr/bin/env python3
"""Restartable, model-agnostic two-lane LeafOS harness with a chat file bridge."""
from __future__ import annotations
import json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def now(): return datetime.now(timezone.utc).isoformat()
def read(path:Path, default:Any):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):return default
def append(path:Path,item:dict[str,Any]):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a',encoding='utf-8') as f:f.write(json.dumps(item,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
def lines(path:Path):
 if not path.exists():return []
 out=[]
 for line in path.read_text(encoding='utf-8').splitlines():
  try:
   x=json.loads(line)
   if isinstance(x,dict):out.append(x)
  except json.JSONDecodeError:pass
 return out
class Harness:
 def __init__(self,root:Path,config:dict[str,Any]):
  self.root=root.resolve();self.config=config;self.loop_run_dir=self.resolve_loop_run_dir();self.loop_queue_path=self.loop_run_dir/'queue.json' if self.loop_run_dir else None;self.workspace_root=self.resolve_workspace_root();self.state_path=self.root/'harness-state.json';self.events=self.root/'harness-events.jsonl';self.inbox=self.root/config['chat_bridge']['inbox'];self.outbox=self.root/config['chat_bridge']['outbox'];self.state=read(self.state_path,{'schema_version':1,'run_id':config['run_id'],'paused':False,'cancelled':False,'tasks':[],'seen_messages':[]});self.state.setdefault('brain_method',self.methods()[0]['name']);self.state.setdefault('brain_switches',0)
  if self.loop_queue_path:
   queue=read(self.loop_queue_path,{});self.state['tasks']=queue.get('tasks',[]);self.state['task_source']='agent_loop_queue';self.state['agent_loop_run_dir']=str(self.loop_run_dir)
 def resolve_loop_run_dir(self)->Path|None:
  configured=self.config.get('agent_loop_run_dir')
  candidates=[Path(str(configured))] if configured else []
  candidates.append(self.root)
  for candidate in candidates:
   path=candidate.resolve() if candidate.is_absolute() else (self.root/candidate).resolve()
   if (path/'run.json').is_file() and (path/'queue.json').is_file():return path
  return None
 def resolve_workspace_root(self)->Path:
  if self.loop_run_dir:
   run=read(self.loop_run_dir/'run.json',{});target=run.get('target')
   if target:return Path(str(target)).resolve()
  configured=self.config.get('workspace_root')
  if configured:
   path=Path(str(configured))
   return path.resolve() if path.is_absolute() else (self.root/path).resolve()
  if self.root.name=='harness' and self.root.parent.name.startswith('overnight-') and self.root.parent.parent.name=='sandbox':
   return self.root.parent.parent.parent.resolve()
  return self.root.resolve()
 def save(self):
  self.root.mkdir(parents=True,exist_ok=True)
  if self.loop_queue_path:
   queue=read(self.loop_queue_path,{});queue['tasks']=self.state.get('tasks',[]);tmp_queue=self.loop_queue_path.with_suffix('.json.tmp');tmp_queue.write_text(json.dumps(queue,indent=2)+'\n',encoding='utf-8');tmp_queue.replace(self.loop_queue_path)
  persisted=dict(self.state)
  if self.loop_queue_path:persisted.pop('tasks',None)
  tmp=self.state_path.with_suffix('.tmp');tmp.write_text(json.dumps(persisted,indent=2)+'\n',encoding='utf-8');tmp.replace(self.state_path)
 def event(self,kind:str,**data:Any):
  append(self.events,{'time':now(),'event':kind,'data':data})
  if self.loop_run_dir:
   path=self.loop_run_dir/'events.jsonl';existing=lines(path);append(path,{'seq':len(existing)+1,'time':now(),'kind':f'dual_harness.{kind}',**data})
 def say(self,kind:str,message:str,**data:Any):append(self.outbox,{'id':str(uuid.uuid4()),'time':now(),'kind':kind,'message':message,'data':data})
 def post(self,message:str):append(self.inbox,{'id':str(uuid.uuid4()),'time':now(),'kind':'operator','message':message})
 def methods(self):
  methods=self.config.get('brain_runtime',{}).get('methods',[])
  return methods or [{'name':'f16','cache_type_k':'f16','cache_type_v':'f16','gpu_allocation_fraction':0.5},{'name':'q8_0','cache_type_k':'q8_0','cache_type_v':'q8_0','gpu_allocation_fraction':0.5}]
 def switch_method(self,reason:str):
  methods=self.methods();names=[str(method['name']) for method in methods];current=self.state.get('brain_method',names[0]);next_method=methods[(names.index(current)+1)%len(methods)] if current in names else methods[0];self.state['brain_method']=next_method['name'];self.state['brain_switches']=int(self.state.get('brain_switches',0))+1;self.state['last_brain_switch']={'time':now(),'reason':reason,'from':current,'to':next_method['name']};self.event('brain.method_switched',reason=reason,from_method=current,to_method=next_method['name'],decode_tokens_per_second=next_method.get('decode_tokens_per_second'),gpu_allocation_fraction=next_method.get('gpu_allocation_fraction'));self.say('brain',f"brain method switched: {current} -> {next_method['name']}",reason=reason);return next_method
 def clear_conversation(self,reason:str):
  method=self.switch_method(reason);self.state['conversation_clears']=int(self.state.get('conversation_clears',0))+1;self.event('conversation.cleared',reason=reason,active_method=method['name']);return method
 def consume(self):
  for item in lines(self.inbox):
   ident=str(item.get('id',''))
   if not ident or ident in self.state['seen_messages']:continue
   self.state['seen_messages'].append(ident);msg=str(item.get('message','')).strip().lower()
   if msg=='pause':self.state['paused']=True
   elif msg=='resume':self.state['paused']=False
   elif msg=='cancel':self.state['cancelled']=True
   elif msg in ('clear','clear conversation','clear_conversation'):self.clear_conversation('operator_command')
   self.event('chat.command',message=msg);self.say('acknowledgement',f'command processed: {msg}')
 def compact_context(self):
  lane=self.config['lanes']['experimental_brain']; threshold=lane['compaction_threshold_tokens']; items=lines(self.inbox)+lines(self.outbox)
  tokens=sum(int(item.get('token_count',max(1,len(str(item.get('message','')))//4))) for item in items)
  if tokens<threshold:return None
  directory=self.root/self.config['chat_bridge']['compaction_directory'];directory.mkdir(parents=True,exist_ok=True);path=directory/f"CONTEXT_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
  body=[f"# {lane.get('model','Local model')} Context Compaction",'',f'Estimated tokens: {tokens}',f'Threshold: {threshold}','', '## Durable chat bridge transcript','']
  body.extend(f"- {item.get('time','unknown')} [{item.get('kind','event')}]: {item.get('message','')}" for item in items[-200:])
  path.write_text('\n'.join(body)+'\n',encoding='utf-8');self.state['latest_context_checkpoint']=str(path);self.event('context.compacted',path=str(path),estimated_tokens=tokens,threshold=threshold);self.say('context',f'context compacted: {path.name}',estimated_tokens=tokens);self.clear_conversation('context_compaction');return path
 def allowed(self,workdir:str)->bool:
  target=Path(workdir).resolve()
  if self.loop_run_dir:
   run_target=self.workspace_root
   if target==run_target or target.is_relative_to(run_target):return True
  for entry in self.config['workspace_allowlist']:
   base=Path(str(entry))
   allowed=base.resolve() if base.is_absolute() else (self.workspace_root/base).resolve()
   if target==allowed or target.is_relative_to(allowed):return True
  return False
 def task_state(self,task:dict[str,Any])->str:return str(task.get('status' if self.loop_queue_path else 'state',''))
 def set_task_state(self,task:dict[str,Any],value:str):task['status' if self.loop_queue_path else 'state']=value
 def task_id(self,task:dict[str,Any])->str:return str(task.get('task_id' if self.loop_queue_path else 'id','unknown-task'))
 def task_command(self,task:dict[str,Any])->Any:return task.get('validation_command' if self.loop_queue_path else 'command',[])
 def tick(self):
  self.consume();self.event('harness.heartbeat',paused=self.state['paused'],cancelled=self.state['cancelled'])
  self.compact_context()
  if self.state['paused'] or self.state['cancelled']:self.save();return
  for task in self.state['tasks']:
   if self.task_state(task) not in ('queued','repair_queued'):continue
   task_id=self.task_id(task)
   if task.get('requires_approval'):
    self.set_task_state(task,'blocked' if self.loop_queue_path else 'waiting_approval');task['reason']='approval_required';self.say('approval',f"approval required: {task_id}");continue
   if not self.allowed(task['workdir']):self.set_task_state(task,'blocked');task['reason']='workspace_not_allowlisted';self.say('blocked',f"blocked: {task_id}");continue
   task['attempts']=task.get('attempts',0)+1
   try:
    command=self.task_command(task);method=next((item for item in self.methods() if item['name']==self.state['brain_method']),self.methods()[0]);environment=os.environ.copy();environment.update({'LEAF_BRAIN_METHOD':str(method['name']),'LEAF_KV_CACHE_K':str(method['cache_type_k']),'LEAF_KV_CACHE_V':str(method['cache_type_v']),'LEAF_BRAIN_DECODE_TPS':str(method.get('decode_tokens_per_second',''))});result=subprocess.run(command,cwd=task['workdir'],shell=isinstance(command,str),timeout=min(int(task.get('timeout_seconds',self.config['limits']['task_timeout_seconds'])),int(self.config['limits']['task_timeout_seconds'])),capture_output=True,text=True,env=environment)
    final_state='complete' if self.loop_queue_path and result.returncode==0 else ('completed' if result.returncode==0 else ('failed' if task['attempts']>=self.config['limits']['max_attempts'] else 'queued'));self.set_task_state(task,final_state);task['exit_code']=result.returncode
    self.event('task.completed' if result.returncode==0 else 'task.failed',task_id=task_id,attempt=task['attempts'],exit_code=result.returncode,brain_method=method['name']);self.say('task',f"{task_id}: {self.task_state(task)}")
    if result.returncode!=0:self.switch_method(f"task_failure:{task_id}")
   except subprocess.TimeoutExpired:
    self.set_task_state(task,'failed');task['reason']='timeout';self.event('task.failed',task_id=task_id,reason='timeout');self.switch_method(f"task_timeout:{task_id}")
   break
  self.save()
def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('run_root',type=Path);p.add_argument('--config',type=Path,required=True);p.add_argument('command',choices=['init','tick','post','status']);p.add_argument('--message');a=p.parse_args();h=Harness(a.run_root,read(a.config,{}))
 if a.command=='init':h.save();h.say('status','dual harness initialized')
 elif a.command=='tick':h.tick()
 elif a.command=='post':h.post(a.message or '')
 else:print(json.dumps(h.state,indent=2))
if __name__=='__main__':main()
