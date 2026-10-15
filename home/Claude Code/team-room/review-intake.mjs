// Fixed-config opt-in bridge: production outbox -> fresh reviewer -> owner card.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {inside,fileHash,context} from './isolation.mjs';
const FIXED_ROOT=path.join(os.homedir(),'Claude Code/ec-harness');
function readJSON(p){return JSON.parse(fs.readFileSync(p,'utf8'));}
function atomicNew(p,data){
 if(fs.existsSync(p)){if(fs.readFileSync(p,'utf8')!==data)throw Error('immutable reviewed manifest differs');return;}
 const temp=p+'.'+randomUUID()+'.tmp';fs.writeFileSync(temp,data,{flag:'wx'});
 try{fs.linkSync(temp,p);}catch(e){if(e.code!=='EEXIST'||fs.readFileSync(p,'utf8')!==data)throw e;}finally{fs.unlinkSync(temp);}
}
export function reviewIntake({root=FIXED_ROOT,contract,reviewJob,findReview,ownerCard,now=()=>Date.now()}){
 let busy=false;
 const enabled=()=>{try{return readJSON(path.join(root,'config/automation.json')).enabled===true;}catch{return false;}};
 const drain=async function(){
  if(busy)return [];busy=true;let db;
  try{
   const configPath=path.join(root,'config/automation.json'),queuePath=path.join(root,'data/automation/queue.sqlite3');
   if(!fs.existsSync(configPath)||!fs.existsSync(queuePath))return [];
   const automation=readJSON(configPath);if(automation.schema_version!==1||automation.enabled!==true)return [];
   const brands=readJSON(path.join(root,'config/brands.json')).brands;
   db=new DatabaseSync(queuePath);db.exec("PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS team_review_intake (id TEXT PRIMARY KEY, phase TEXT, lease_until REAL, lease_owner TEXT, result TEXT)");
   const rows=db.prepare("SELECT * FROM handoffs WHERE state IN ('review_requested','review_claimed') ORDER BY id LIMIT 8").all();
   const results=[];
   for(const row of rows){
    const enabled=automation.brands?.[row.brand];if(enabled?.enabled!==true)continue;
    const token=randomUUID();let claimed=false,phase;
    db.exec('BEGIN IMMEDIATE');
    try{
     const old=db.prepare('SELECT * FROM team_review_intake WHERE id=?').get(row.id);
     if(old&&['awaiting_owner_approval','failed'].includes(old.phase)){db.exec('COMMIT');continue;}
     if(old&&old.lease_until>now()/1000){db.exec('COMMIT');continue;}
     phase=old?.phase||'claimed';
     db.prepare('INSERT INTO team_review_intake VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET lease_until=excluded.lease_until,lease_owner=excluded.lease_owner').run(row.id,phase,now()/1000+900,token,old?.result||null);
     db.prepare("UPDATE handoffs SET state='review_claimed' WHERE id=?").run(row.id);db.exec('COMMIT');claimed=true;
    }catch(e){db.exec('ROLLBACK');throw e;}
    if(!claimed)continue;
    const owns=()=>{const r=db.prepare('SELECT phase,lease_owner,lease_until FROM team_review_intake WHERE id=?').get(row.id);return r?.lease_owner===token&&r.lease_until>now()/1000&&!['failed','awaiting_owner_approval'].includes(r.phase);};
    const finish=(state,result)=>{const changed=db.prepare('UPDATE team_review_intake SET phase=?,lease_until=0,result=? WHERE id=? AND lease_owner=?').run(state,JSON.stringify(result),row.id,token).changes;if(changed){db.prepare('UPDATE handoffs SET state=? WHERE id=?').run(state,row.id);results.push({id:row.id,state,...result});}};
    try{
     const c=context({brand:row.brand,job_id:row.job,revision:row.to_revision},brands),cfg=brands[c.brand],r=enabled.review;
     if(!r||Object.keys(r).sort().join(',')!=='max_turns,rules_path,rules_sha256'||!Number.isSafeInteger(r.max_turns)||r.max_turns<1||r.max_turns>20||!path.isAbsolute(r.rules_path||'')||!/^[a-f0-9]{64}$/.test(r.rules_sha256||''))throw Error('explicit bounded review configuration required');
     const roots=(cfg.asset_roots||[]).map(p=>path.join(p,c.job_id,`r${c.revision}`));
     if(!inside(row.path,roots))throw Error('handoff path outside brand/job/revision');
     const proposed=readJSON(row.path),record=JSON.parse(row.record);
     const hashed=contract('hash',{job:proposed}).manifest_hash;
     if(contract('hash',{job:record}).manifest_hash!==row.id||record.brand!==c.brand||record.job_id!==c.job_id||record.revision!==c.revision||hashed!==row.hash||record.manifest_hash!==hashed||record.manifest_path!==row.path||proposed.brand!==c.brand||proposed.job_id!==c.job_id||proposed.revision!==c.revision||proposed.account_id!==cfg.account_id||proposed.revision<=row.from_revision)throw Error('handoff identity/hash mismatch');
     if(!proposed.artifacts?.length||proposed.evidence?.reviewer?.status!=='pending'||proposed.evidence?.status!=='insufficient_evidence')throw Error('pending reviewer evidence required');
     for(const a of proposed.artifacts)if(a.revision!==c.revision||!inside(a.path,roots)||fileHash(a.path)!==a.sha256)throw Error('handoff artifact changed or crossed brand');
     if(JSON.stringify([...record.artifact_hashes].sort())!==JSON.stringify(proposed.artifacts.map(a=>a.sha256).sort()))throw Error('outbox artifact hashes differ');
     const ruleRoots=[...(cfg.asset_roots||[]),...(cfg.read_roots||[]),path.join(root,'config/review'),path.join(os.homedir(),'Documents/Obsidian Vault/ec/構造/ハーネス')];
     if(!inside(r.rules_path,ruleRoots)||fileHash(r.rules_path)!==r.rules_sha256)throw Error('review rules scope/hash mismatch');
     const review={artifacts:proposed.artifacts,rules:fs.readFileSync(r.rules_path,'utf8'),max_turns:r.max_turns};
     let reviewer=await findReview(c,review);
     if(!reviewer&&phase==='review_started')throw Error('review interrupted: no receipt; manual recovery required, no automatic SDK retry');
     if(!reviewer){
      db.prepare("UPDATE team_review_intake SET phase='review_started' WHERE id=? AND lease_owner=?").run(row.id,token);
      const response=await reviewJob(c,review);if(response?.status!=="success")throw Error("review runtime incomplete: "+JSON.stringify(response));try{reviewer=JSON.parse(response.output);}catch{throw Error('review SDK did not produce trusted receipt');}
     }
     if(!owns())throw Error('review claim expired or superseded');
     if(reviewer?.status!=='pass'||!reviewer.review_id)throw Error('review failed or incomplete; no owner approval card');
     if(contract('hash',{job:readJSON(row.path)}).manifest_hash!==row.hash)throw Error('proposal changed during review');
     const finalized=structuredClone(proposed);finalized.evidence={...finalized.evidence,status:'executable',reviewer};
     const check=contract('validate',{job:finalized});
     if(check.errors?.length||check.missing?.length!==1||check.missing[0]!=='trusted exact owner approval required')throw Error('reviewed manifest not eligible for owner approval: '+JSON.stringify(check));
     const finalPath=path.join(path.dirname(row.path),'publication-reviewed.json');atomicNew(finalPath,JSON.stringify(finalized));
     const card=await ownerCard(row.id,c,finalized);
     finish('awaiting_owner_approval',{reviewed_manifest_path:finalPath,reviewed_manifest_hash:check.manifest_hash,review_id:reviewer.review_id,owner_card_id:card.id});
    }catch(e){finish('failed',{error:String(e.message||e)});}
   }
   return results;
  }finally{db?.close();busy=false;}
 };
 drain.enabled=enabled;return drain;
}
