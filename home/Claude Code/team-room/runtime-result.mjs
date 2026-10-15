import {randomUUID} from 'node:crypto';
import {digest,fileHash,sameContext} from './isolation.mjs';
export const STATUSES=new Set(['success','partial','error','cancelled']);
export function runtimeResult(identity,status,output='',details={}) {
 if(!STATUSES.has(status))throw Error('invalid runtime status');
 return {schema_version:1,...identity,status,output:String(output||''),completed:status==='success',...details};
}
export function handoffResponse(result){return{content:[{type:'text',text:JSON.stringify(result)}],isError:result.status!=='success'};}
export function requestKey(role,channel,c,prompt,review,dispatchId){return digest({role,channel,...c,prompt,review:review||null,dispatch_id:dispatchId||null});}
export function artifactEvidenceIntact(result,identity=result){
 if(!result||!sameContext(result,identity))return false;
 try{return (result.artifacts||[]).every(a=>a.revision===result.revision&&fileHash(a.path)===a.sha256)&&(result.children||[]).every(child=>artifactEvidenceIntact(child,result));}catch{return false;}
}
export function completedResultIntact(result,identity=result){
 if(!result||result.status!=='success'||result.completed!==true||!sameContext(result,identity))return false;
 return artifactEvidenceIntact(result,identity)&&(result.children||[]).every(child=>completedResultIntact(child,result));
}
export function runtimeStore(db){
 db.exec('PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS runtime_requests (id TEXT PRIMARY KEY,identity TEXT,status TEXT,lease_until REAL,owner TEXT,session_id TEXT,result TEXT,request TEXT)');
 if(!db.prepare("PRAGMA table_info(runtime_requests)").all().some(c=>c.name==="request"))db.exec("ALTER TABLE runtime_requests ADD COLUMN request TEXT");
 return {
  begin(id,identity,{resume=false,leaseMs=900000,now=Date.now(),request=null}={}){
   db.exec('BEGIN IMMEDIATE');let failed=false;
   try{
   const old=db.prepare('SELECT * FROM runtime_requests WHERE id=?').get(id);
   if(old){
    const scope=JSON.parse(old.identity);if(!sameContext(scope,identity)||scope.role!==identity.role||scope.channel!==identity.channel)throw Error('resume scope mismatch');
    if(old.status==='running'&&old.lease_until>now)return{cached:runtimeResult(identity,'partial','同じ案件を実行中',{code:'in_progress',request_id:id})};
    if(old.status==='running'){
     const progress=old.result?JSON.parse(old.result):{};const interrupted=runtimeResult(identity,'partial','実行が中断された。明示的な再開が必要',{code:'interrupted',request_id:id,artifacts:progress.artifacts||[],children:progress.children||[]});
     db.prepare('UPDATE runtime_requests SET status=?,result=?,lease_until=0 WHERE id=?').run('partial',JSON.stringify(interrupted),id);
     if(!resume)return{cached:interrupted};
    }else{
     const result=JSON.parse(old.result);
     if(old.status==='success'){
      const intact=completedResultIntact(result,identity);
      return{cached:intact?result:runtimeResult(identity,'partial','保存した成果物の版が変わった',{code:'artifact_changed',request_id:id})};
     }
     if(!resume)return{cached:result};
    }
   }
   const priorResult=resume&&old?.result?JSON.parse(old.result):null;
   if(priorResult&&!artifactEvidenceIntact(priorResult,identity))return{cached:runtimeResult(identity,'partial','再開前に保存した成果物の版が変わった',{code:'artifact_changed',request_id:id,artifacts:priorResult.artifacts||[],children:priorResult.children||[]})};
   const owner=randomUUID();
   db.prepare('INSERT INTO runtime_requests(id,identity,status,lease_until,owner,session_id,result,request) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,lease_until=excluded.lease_until,owner=excluded.owner,result=NULL').run(id,JSON.stringify(identity),'running',now+leaseMs,owner,old?.session_id||null,null,JSON.stringify(request));
   return{owner,resumeSid:resume?old?.session_id:undefined,priorResult};
   }catch(e){failed=true;db.exec("ROLLBACK");throw e;}finally{if(!failed)db.exec("COMMIT");}
  },
  progress(id,owner,result){return db.prepare("UPDATE runtime_requests SET result=? WHERE id=? AND owner=? AND status='running'").run(JSON.stringify(result),id,owner).changes===1;},
  // 動いている間は数分ごとに延ばす。時間の上限ではなく「生きているか」の印（2026-10-05）
  // 起動した直後に呼ぶ。走っていた印のある仕事は、前のプロセスと一緒に止まった物なので印を外して返す
  orphans(){const rows=db.prepare("SELECT id,identity FROM runtime_requests WHERE status='running'").all();db.prepare("UPDATE runtime_requests SET lease_until=0 WHERE status='running'").run();return rows.map(r=>({id:r.id,identity:JSON.parse(r.identity)}));},
  renew(id,owner,leaseMs,now=Date.now()){return db.prepare("UPDATE runtime_requests SET lease_until=? WHERE id=? AND owner=? AND status='running'").run(now+leaseMs,id,owner).changes===1;},
  session(id,owner,sid){db.prepare('UPDATE runtime_requests SET session_id=? WHERE id=? AND owner=?').run(sid,id,owner);},
  finish(id,owner,result){const changed=db.prepare('UPDATE runtime_requests SET status=?,result=?,lease_until=0 WHERE id=? AND owner=? AND status=\'running\'').run(result.status,JSON.stringify(result),id,owner).changes;if(!changed)return runtimeResult(result,'partial','実行leaseが失効した',{code:'lease_lost'});return result;},
  request(id,ctx){const r=db.prepare('SELECT identity,status,request FROM runtime_requests WHERE id=?').get(id);if(!r||!sameContext(JSON.parse(r.identity),ctx))throw Error('resume request/context mismatch');if(r.status==='success')throw Error('completed request cannot be resumed');const request=JSON.parse(r.request||'null');if(!request)throw Error('original request unavailable; cannot resume');return{identity:JSON.parse(r.identity),status:r.status,...request};},
  get(id){const r=db.prepare('SELECT result FROM runtime_requests WHERE id=?').get(id);return r?.result?JSON.parse(r.result):null;}
 };
}
export async function consumeSDK(stream,{signal,abort,totalMs=900000,stallMs=120000,waiting=()=>false,onEvent}){
 const iterator=stream[Symbol.asyncIterator](),started=Date.now();
 try{
  while(true){
   if(signal?.aborted)throw Object.assign(Error('runtime cancelled'),{code:'cancelled'});
   const remaining=totalMs-(Date.now()-started);if(remaining<=0){abort?.();throw Object.assign(Error('runtime timeout'),{code:'timeout'});}
   const delay=Math.min(remaining,waiting()?remaining:stallMs);let timer,onAbort;
   const guard=new Promise((_,reject)=>{
    const check=()=>{const left=totalMs-(Date.now()-started);if(left>0&&waiting()){timer=setTimeout(check,Math.min(left,stallMs));return;}const code=left<=0?'timeout':'stalled';reject(Object.assign(Error('runtime '+code),{code}));abort?.();};
    timer=setTimeout(check,delay);
    onAbort=()=>reject(Object.assign(Error('runtime cancelled'),{code:'cancelled'}));
    if(signal?.aborted)onAbort();else signal?.addEventListener('abort',onAbort,{once:true});
   });
   let next;try{next=await Promise.race([iterator.next(),guard]);}finally{clearTimeout(timer);signal?.removeEventListener('abort',onAbort);}
   if(next.done)break;await onEvent(next.value);
  }
 }finally{if(signal?.aborted)Promise.resolve(iterator.return?.()).catch(()=>{});}
}
