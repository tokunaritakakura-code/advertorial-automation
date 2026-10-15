import fs from 'node:fs';
import {parseEnv} from 'node:util';
import {requireThat} from './contracts.mjs';
export const JEV_MODEL='typesafe/jev-1.13';
export function existingJevKey(file){if(process.env.OPENROUTER_API_KEY)return process.env.OPENROUTER_API_KEY;const st=fs.lstatSync(file);requireThat(st.isFile()&&!st.isSymbolicLink()&&st.nlink===1&&st.size<=10000,'ordinary bounded Jev key file required');const key=parseEnv(fs.readFileSync(file,'utf8')).OPENROUTER_API_KEY;requireThat(typeof key==='string'&&key.trim().length>0,'OPENROUTER_API_KEY missing from existing configuration');return key;}
const ENDPOINT='https://openrouter.ai/api/alpha/decisions';
// Native fetch only: no package install, credential persistence, or automatic retries.
export function openRouterJev({apiKey=process.env.OPENROUTER_API_KEY,budgetUsd=0,maxCalls=10,fetchImpl=fetch,timeoutMs=15000}={}){
 requireThat(typeof apiKey==='string'&&apiKey.trim().length>0,'OPENROUTER_API_KEY required (server-side only)');
 requireThat(Number.isFinite(budgetUsd)&&budgetUsd>0&&budgetUsd<=1,'explicit Jev invocation budget required (0 < USD <= 1)');
 requireThat(Number.isSafeInteger(maxCalls)&&maxCalls>0&&maxCalls<=10,'bounded Jev calls required');
 const stats={attempts:0,completed:0,cost_usd:0,uncertain_cost:false,disabled:false};
 const provider=async request=>{
  requireThat(!stats.disabled&&stats.attempts<maxCalls,'Jev call bound or uncertainty stop');
  const body=JSON.stringify({...request,model:JEV_MODEL});
  requireThat(Buffer.byteLength(body)<=12000,'Jev decision state too large');
  // Conservative reservation above the documented input price for this bounded body.
  requireThat(stats.cost_usd+0.001<=budgetUsd,'Jev invocation budget exhausted');
  stats.attempts++;const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  let dispatched=false;
  try{
   dispatched=true;const response=await fetchImpl(ENDPOINT,{method:'POST',headers:{Authorization:'Bearer '+apiKey,'Content-Type':'application/json'},body,signal:controller.signal,redirect:'error'});
   requireThat(response.ok,'Jev HTTP '+response.status);const raw=await response.text();requireThat(Buffer.byteLength(raw)<=100000,'Jev response too large');const result=JSON.parse(raw);
   requireThat(result.model===JEV_MODEL||/^typesafe\/jev-1\.13-\d{8}$/.test(result.model||''),'unexpected resolved Jev model');
   requireThat(Number.isFinite(result.usage?.cost)&&result.usage.cost>=0,'Jev cost receipt required');
   stats.completed++;stats.cost_usd+=result.usage.cost;if(stats.cost_usd>budgetUsd)stats.disabled=true;
   return {...result,resolved_model:result.model,model:JEV_MODEL};
  }catch(e){if(dispatched){stats.uncertain_cost=true;stats.disabled=true;}throw Error('Jev request failed; no automatic retry ('+(controller.signal.aborted?'timeout':String(e.message).replaceAll(apiKey,'[redacted]'))+')');}
  finally{clearTimeout(timer);}
 };
 provider.stats=stats;return provider;
}

export function configuredJev(opts,{defaultKeyFile,fetchImpl=fetch}={}){return openRouterJev({apiKey:existingJevKey(opts['--jev-key-file']||defaultKeyFile),budgetUsd:Number(opts['--jev-budget-usd']||0),fetchImpl});}

// One explicitly authorized research validation envelope, shared across restarts.
export const RESEARCH_JEV_SCOPE={brand:'research_only_menopause',job_id:'menopause-own-pains-20261004',revision:1};
export function researchJevSetting(job){
 const v=job.jev_validation;if(!v)return null;
 requireThat(job.mode==='isolated_research'&&JSON.stringify(v.scope)===JSON.stringify(RESEARCH_JEV_SCOPE)&&Object.entries(RESEARCH_JEV_SCOPE).every(([k,x])=>job[k]===x),'Jev validation scope is not authorized');
 requireThat(v.schema_version===1&&v.mode==='gate'&&v.total_budget_usd===.01&&v.max_calls===3&&v.authorization==='explicit_isolated_validation_20261004','exact bounded Jev validation setting required');
 return v;
}
export async function boundedResearchJev({job,apiKey,ledgerRoot,priorReceipt,fetchImpl=fetch}){
 const setting=researchJevSetting(job);requireThat(setting,'explicit job Jev setting required');
 const path=await import('node:path');
 const prior=JSON.parse(fs.readFileSync(priorReceipt,'utf8'));const spent=prior.response?.usage?.cost;
 requireThat(Number.isFinite(spent)&&spent>=0&&Math.abs(spent-.000018186)<1e-12,'unexpected prior Jev spending; no POST');
 const pricingURL='https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints';
 const catalogue=await fetchImpl(pricingURL,{headers:{Authorization:'Bearer '+apiKey},signal:AbortSignal.timeout(15000),redirect:'error'});requireThat(catalogue.ok,'current Jev endpoint pricing unavailable');
 const numericPrice=v=>typeof v==='number'?Number.isFinite(v):typeof v==='string'&&/^[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$/i.test(v)&&Number.isFinite(Number(v));
 const model=(await catalogue.json()).data;requireThat(model?.id===JEV_MODEL&&Array.isArray(model.endpoints)&&model.endpoints.length>0&&model.endpoints.every(e=>e.provider_name==='TypeSafe'&&numericPrice(e.pricing?.prompt)&&numericPrice(e.pricing?.completion)&&Number(e.pricing.prompt)>=0&&Number(e.pricing.completion)===0&&Number.isSafeInteger(e.context_length)&&e.context_length>0),'pinned Jev current price/context unavailable');
 const price=Math.max(...model.endpoints.map(e=>Number(e.pricing.prompt))),context=Math.max(...model.endpoints.map(e=>e.context_length));
 const reservation=price*context;requireThat(reservation*setting.max_calls+spent<=setting.total_budget_usd,'full-context reservation exceeds total authorized Jev ceiling');
 const root=path.resolve(ledgerRoot);let ancestor=path.parse(root).root;for(const part of root.slice(ancestor.length).split(path.sep).filter(Boolean)){ancestor=path.join(ancestor,part);if(fs.existsSync(ancestor))requireThat(!fs.lstatSync(ancestor).isSymbolicLink(),'Jev ledger ancestor symlink forbidden');}
 fs.mkdirSync(root,{recursive:true});function syncDir(dir){const fd=fs.openSync(dir,'r');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
 syncDir(path.dirname(root));function write(file,value){const fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);try{fs.writeFileSync(fd,JSON.stringify(value,null,2));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}syncDir(root);}
 const config={scope:setting.scope,total_budget_usd:setting.total_budget_usd,max_calls:setting.max_calls,prior_spent_usd:spent};const configFile=path.join(root,'envelope.json');
 if(fs.existsSync(configFile)){const st=fs.lstatSync(configFile);requireThat(st.isFile()&&!st.isSymbolicLink()&&st.nlink===1&&JSON.stringify(JSON.parse(fs.readFileSync(configFile)))===JSON.stringify(config),'existing Jev envelope changed; HUMAN');}else write(configFile,config);
 const stats={attempts:0,completed:0,cost_usd:0,uncertain_cost:false,disabled:false};
 const provider=async request=>{
  requireThat(!stats.disabled,'HUMAN: uncertain Jev request; no retry');
  requireThat(JSON.stringify(request.state.scope)===JSON.stringify(setting.scope)&&request.state.pending_task?.stage==='brand_dispatch','Jev validation only permits this job initial brand dispatch');
  const body={...request,model:JEV_MODEL};requireThat(Buffer.byteLength(JSON.stringify(body))<=12000,'bounded Jev decision request required');
  const lock=path.join(root,'.lock');try{fs.mkdirSync(lock);syncDir(root);}catch{throw Error('HUMAN: Jev envelope busy or prior uncertain dispatch; no retry');}
  let admitted=false;
  try{
   const {hash}=await import('./contracts.mjs');const requestHash=hash(body);
   const files=fs.readdirSync(root).filter(n=>/^call-\d+-pending\.json$/.test(n));let reserved=spent;
   for(const name of files){const file=path.join(root,name),st=fs.lstatSync(file);requireThat(st.isFile()&&!st.isSymbolicLink()&&st.nlink===1,'ordinary Jev reservation required');const r=JSON.parse(fs.readFileSync(file));requireThat(Number.isFinite(r.reserved_usd)&&r.reserved_usd>=0,'invalid durable Jev reservation');requireThat(r.request_hash!==requestHash,'HUMAN: identical Jev request already admitted; no reroll');reserved+=r.reserved_usd;}
   requireThat(files.length<setting.max_calls&&reserved+reservation<=setting.total_budget_usd,'HUMAN: total Jev call/budget bound reached');
   const call=files.length+1;write(path.join(root,'call-'+call+'-pending.json'),{scope:setting.scope,request_hash:requestHash,reserved_usd:reservation,pricing:{model:JEV_MODEL,input_per_token:price,output_per_token:0,context_tokens:context},at:new Date().toISOString(),uncertain_reservations_never_released:true});admitted=true;stats.attempts++;
   const single=openRouterJev({apiKey,budgetUsd:setting.total_budget_usd-spent,maxCalls:1,fetchImpl});
   try{const result=await single(request);requireThat(result.usage.cost<=reservation,'HUMAN: provider cost exceeds reserved price ceiling');write(path.join(root,'call-'+call+'-result.json'),result);stats.completed++;stats.cost_usd+=result.usage.cost;return result;}catch(e){stats.uncertain_cost=true;stats.disabled=true;write(path.join(root,'call-'+call+'-failure.json'),{reason:e.message,no_retry:true,reservation_retained:true,at:new Date().toISOString()});throw e;}
  }finally{if(!admitted||!stats.uncertain_cost){fs.rmdirSync(lock);syncDir(root);}}
 };
 provider.stats=stats;provider.validationScope=setting.scope;provider.validationMode='gate';provider.preflight={pricing_source:pricingURL,checked_at:new Date().toISOString(),model:JEV_MODEL,total_budget_usd:setting.total_budget_usd,prior_spent_usd:spent,full_context_reservation_usd:reservation,max_total_calls:setting.max_calls};return provider;
}
