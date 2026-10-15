// One-job local path; deliberately does not enable global SDK dispatch or providers.
import {spawn} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
export function localVslDispatcher({root=path.join(os.homedir(),'Claude Code/ec-harness')}={}){
 let busy=false;
 return async function run(request,{signal}={}){
  if(!request||typeof request!=='object'||Array.isArray(request)||Object.keys(request).some(k=>!['brand','job_id','revision','operation','pause_after'].includes(k))||request.brand!=='アルコット'||request.job_id!=='alcott_nonai_vsl_20261002_01'||request.revision!==3||!['status','run','resume'].includes(request.operation))throw Error('fixed authorized Alcott local scope required');
  if(busy)throw Error('local VSL dispatch already running');busy=true;
  try{return await new Promise((resolve,reject)=>{
   const child=spawn('python3',['-B',path.join(root,'lib/local_vsl_dispatch.py')],{cwd:root,stdio:['pipe','pipe','pipe']});let out='',err='',stopped=false;
   const stop=()=>{stopped=true;child.kill('SIGTERM');};const timer=setTimeout(stop,260000);signal?.addEventListener('abort',stop,{once:true});
   child.stdout.on('data',d=>{out+=d;if(out.length>1024*1024)stop();});child.stderr.on('data',d=>{err+=d;for(const line of String(d).split('\n'))if(/^local_vsl_phase:[a-z_]+$/.test(line))console.error(line);if(err.length>1024*1024)stop();});
   child.on('error',e=>{clearTimeout(timer);signal?.removeEventListener('abort',stop);reject(e);});
   child.on('close',code=>{clearTimeout(timer);signal?.removeEventListener('abort',stop);if(stopped)return reject(Error('owned local dispatcher interrupted'));try{const result=JSON.parse(out);if(code!==0)throw Error(result.error||'local dispatcher refused');if(result.provider_calls!==0||result.publication_allowed!==false)throw Error('local scope invariant violated');resolve(result);}catch(e){reject(e);}});
   if(signal?.aborted)stop();else child.stdin.end(JSON.stringify(request));
  });}finally{busy=false;}
 };
}
