import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {randomUUID} from 'node:crypto';import {DatabaseSync} from 'node:sqlite';
import {fileHash,inside,context} from './isolation.mjs';
import {completedResultIntact} from './runtime-result.mjs';
const ROOT=path.join(os.homedir(),'Claude Code/ec-harness');
export function nextBriefIntake({root=ROOT,contract,verifyBrief,dispatch,lookupResult,allowSimulation=false,now=()=>Date.now()}){
 let busy=false;
 const enabled=()=>{try{return JSON.parse(fs.readFileSync(path.join(root,'config/automation.json'))).enabled===true;}catch{return false;}};
 const drain=async()=>{
  if(busy)return[];busy=true;let db;
  try{
   if(!enabled()||!fs.existsSync(path.join(root,'data/automation/queue.sqlite3')))return[];
   const cfg=JSON.parse(fs.readFileSync(path.join(root,'config/automation.json'))),brands=JSON.parse(fs.readFileSync(path.join(root,'config/brands.json'))).brands;
   db=new DatabaseSync(path.join(root,'data/automation/queue.sqlite3'));db.exec('PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS next_dispatch_events (id TEXT PRIMARY KEY,owner TEXT,result TEXT)');
   const exists=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='next_brief_outbox'").get();if(!exists)return[];
   const rows=db.prepare("SELECT * FROM next_brief_outbox WHERE state IN ('pending','dispatch_started') AND lease_until<=? ORDER BY id LIMIT 8").all(now()/1000),results=[];
   for(const row of rows){
    const entry=cfg.brands?.[row.brand];if(entry?.enabled!==true)continue;
    const d=entry.dispatch,token=randomUUID();
    if(!d||d.channel!=='hq'||!Number.isSafeInteger(d.max_turns)||d.max_turns<1||d.max_turns>20||!Number.isSafeInteger(d.timeout_seconds)||d.timeout_seconds<1||d.timeout_seconds>300)continue;
    const finish=(state,result)=>{const owner=db.prepare('SELECT owner FROM next_dispatch_events WHERE id=?').get(row.id);if(owner&&owner.owner!==token)return;db.prepare('UPDATE next_brief_outbox SET state=?,lease_until=0 WHERE id=?').run(state,row.id);db.prepare('INSERT INTO next_dispatch_events VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET result=excluded.result').run(row.id,token,JSON.stringify(result));results.push({id:row.id,state,result});};
    try{
     const c=context({brand:row.brand,job_id:row.job,revision:row.revision},brands),roots=brands[c.brand].asset_roots.map(r=>path.join(r,c.job_id,`r${c.revision}`));
     if(!inside(row.path,roots)||fileHash(row.path)!==row.hash)throw Error('next brief file/root/hash mismatch');
     const record=JSON.parse(row.record);
     if(contract('hash',{job:record}).manifest_hash!==row.id||record.brand!==c.brand||record.job_id!==c.job_id||record.revision!==c.revision||record.brief_path!==row.path||record.brief_sha256!==row.hash)throw Error('outbox scope/record identity mismatch');
     const verified=verifyBrief(record);if(verified.status!=='eligible')throw Error('protected next-brief evidence not eligible: '+JSON.stringify(verified));
     const brief=verified.brief;if(brief.brand!==c.brand||brief.job_id!==c.job_id||brief.revision!==c.revision||brief.execution_authorized!==false||brief.dispatch_scope!=='local_preparation_only')throw Error('next brief must be local preparation only');
     if(brief.execution_domain!=='production'&&!(allowSimulation===true&&brief.execution_domain==='simulation'))throw Error('simulation outbox cannot invoke production SDK');
    db.exec('BEGIN IMMEDIATE');let claimed;
    try{claimed=db.prepare("UPDATE next_brief_outbox SET state='dispatch_started',lease_until=? WHERE id=? AND state IN ('pending','dispatch_started') AND lease_until<=?").run(now()/1000+d.timeout_seconds+60,row.id,now()/1000).changes;
     if(claimed)db.prepare('INSERT INTO next_dispatch_events VALUES(?,?,NULL) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner').run(row.id,token);db.exec('COMMIT');
    }catch(e){db.exec('ROLLBACK');throw e;}
    if(!claimed)continue;

     let response=lookupResult(row.id,c);
     if(row.state==='dispatch_started'&&!response)throw Error('dispatcher interrupted; explicit resume required, no automatic retry');
     if(!response){
      if(fileHash(row.path)!==row.hash)throw Error('brief changed before dispatch');
      response=await dispatch(c,brief,{dispatch_id:row.id,max_turns:d.max_turns,total_ms:d.timeout_seconds*1000,stall_ms:Math.min(120000,d.timeout_seconds*1000),force_lead:true,source:'next_brief'});
     }
     const all=Array.isArray(response)?response:[response];
     if(!all.length||all.some(r=>!completedResultIntact(r,c)))throw Object.assign(Error('dispatcher not completed'),{result:response});
     finish('dispatched',{status:'success',execution_authorized:false,results:all});
    }catch(e){finish('failed',{status:'error',error:String(e.message||e),runtime_result:e.result||null,execution_authorized:false});}
   }
   return results;
  }finally{db?.close();busy=false;}
 };
 drain.canResume=(dispatchId,ctx)=>{
  if(!enabled())throw Error('controlled dispatch disabled');
  const id=String(dispatchId).split('/')[0],cfg=JSON.parse(fs.readFileSync(path.join(root,'config/automation.json'))),entry=cfg.brands?.[ctx.brand],d=entry?.dispatch;
  if(entry?.enabled!==true||!d||d.channel!=='hq'||!Number.isSafeInteger(d.max_turns)||d.max_turns<1||d.max_turns>20||!Number.isSafeInteger(d.timeout_seconds)||d.timeout_seconds<1||d.timeout_seconds>300)throw Error('controlled dispatch configuration invalid');
  const db=new DatabaseSync(path.join(root,'data/automation/queue.sqlite3'));
  try{const row=db.prepare('SELECT * FROM next_brief_outbox WHERE id=? AND brand=? AND job=? AND revision=?').get(id,ctx.brand,ctx.job_id,ctx.revision);if(!row)throw Error('controlled resume outbox/context mismatch');
   const record=JSON.parse(row.record),brands=JSON.parse(fs.readFileSync(path.join(root,'config/brands.json'))).brands,roots=brands[ctx.brand].asset_roots.map(r=>path.join(r,ctx.job_id,`r${ctx.revision}`));
   if(contract('hash',{job:record}).manifest_hash!==id||!inside(row.path,roots)||record.brief_path!==row.path||record.brief_sha256!==row.hash||fileHash(row.path)!==row.hash)throw Error('controlled resume identity/artifact mismatch');
   const verified=verifyBrief(record),b=verified.brief;if(verified.status!=='eligible'||b?.brand!==ctx.brand||b.job_id!==ctx.job_id||b.revision!==ctx.revision||b.execution_authorized!==false||b.dispatch_scope!=='local_preparation_only'||(b.execution_domain!=='production'&&!(allowSimulation===true&&b.execution_domain==='simulation')))throw Error('controlled resume evidence/expiry/domain invalid');
   return {max_turns:d.max_turns,total_ms:d.timeout_seconds*1000,stall_ms:Math.min(120000,d.timeout_seconds*1000)};
  }finally{db.close();}
 };
 drain.resumeCompleted=async(id,ctx,result)=>{
  if(!enabled()||!completedResultIntact(result,ctx))return false;
  const db=new DatabaseSync(path.join(root,'data/automation/queue.sqlite3'));
  try{const exists=db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='next_brief_outbox'").get();if(!exists)return false;
   const row=db.prepare("SELECT * FROM next_brief_outbox WHERE id=? AND brand=? AND job=? AND revision=? AND state IN ('failed','dispatch_started')").get(id,ctx.brand,ctx.job_id,ctx.revision);if(!row)return false;
   const record=JSON.parse(row.record);if(contract('hash',{job:record}).manifest_hash!==id||fileHash(row.path)!==row.hash)return false;
   const verified=verifyBrief(record);if(verified.status!=='eligible'||(verified.brief.execution_domain!=='production'&&!(allowSimulation===true&&verified.brief.execution_domain==='simulation')))return false;
   db.prepare("UPDATE next_brief_outbox SET state='pending',lease_until=0 WHERE id=? AND state IN ('failed','dispatch_started')").run(id);return true;
  }finally{db.close();}
 };
 drain.enabled=enabled;return drain;
}
