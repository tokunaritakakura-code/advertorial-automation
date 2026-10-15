"""One fixed approved existing-artifact job; no audio/provider/publication operation."""
import hashlib,json,pathlib,subprocess,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from ec_contract import StateStore,CONTROL_DB,validate_job,canonical,manifest_hash
from vsl_route import preflight,route
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def phase(label):print("local_vsl_phase:"+label,file=sys.stderr,flush=True)
def main(request):
 phase("request")
 if not isinstance(request,dict) or set(request)-{'brand','job_id','revision','operation','pause_after'}:raise ValueError('fixed typed local fields required')
 if request.get('operation') not in {'status','run','resume'}:raise ValueError('local operation required; SDK/provider/publication disabled')
 phase('config');cfg=json.loads((ROOT/'config/local-vsl-dispatch.json').read_text())
 identity={k:request.get(k) for k in ('brand','job_id','revision')}
 if cfg.get('schema_version')!=1 or cfg.get('enabled') is not True or cfg.get('provider_calls') is not False or cfg.get('native_sdk_review') is not False or identity!={k:cfg.get(k) for k in identity}:raise ValueError('only explicitly approved one-job local scope allowed')
 brands=json.loads((ROOT/'config/brands.json').read_text());brand=brands['brands'][identity['brand']]
 folder=pathlib.Path(brand['workspace_root']).resolve()/identity['job_id']/('r'+str(identity['revision']))
 jobpath=folder/'central-job-manifest.json';vslpath=folder/'local-vsl-manifest.json'
 if sha(jobpath)!=cfg['central_manifest_file_sha256'] or sha(vslpath)!=cfg['vsl_manifest_file_sha256']:raise ValueError('fixed job manifest changed')
 job=json.loads(jobpath.read_text());vsl=json.loads(vslpath.read_text())
 if manifest_hash(job)!=cfg['central_manifest_sha256'] or job['account_id']!=brand['account_id'] or any(job.get(k)!=identity[k] or vsl.get(k)!=identity[k] for k in identity):raise ValueError('job/account/revision mismatch')
 if any(a['operation']!='verify_artifact' for a in job['actions']):raise ValueError('existing verification actions only')
 phase('registered_artifacts')
 for a in job['artifacts']:
  p=pathlib.Path(a['path']).resolve()
  if not p.is_relative_to(folder) or sha(p)!=a['sha256']:raise ValueError('fixed artifact hash/scope mismatch')
 check=validate_job(job,brands)
 if check['errors']:raise ValueError(';'.join(check['errors']))
 phase('saved_input_verification')
 from vsl_local_edit import verify_cached
 verify_cached(vsl,route(identity['brand']),folder)
 phase('state');store=StateStore(CONTROL_DB)
 stages=[('handoff_reference','クリエイティブ・ストラテジスト',['reference_analysis']),('handoff_script','コピーライター',['script']),('handoff_voice_reuse','吹き替えディレクター',['voice','voice_receipt']),('handoff_edit','映像編集者',['final','edit_receipt','cuts']),('handoff_technical_qc','仕組み係',['independent_local_qc'])]
 pause=request.get('pause_after')
 if pause is not None and pause not in [s[0] for s in stages]:raise ValueError('bounded stage pause required')
 def state():return {name:store.resumable(job,name) for name,_,_ in stages}
 def native_state():
  if not store.resumable(job,'native_review'):return {'native_sdk_review':'pending','native_review_decision':None,'native_review_id':None}
  with store.connect() as c:row=c.execute('SELECT evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(job['brand'],job['job_id'],job['mode'],job['revision'],'native_review')).fetchone()
  evidence=json.loads(row[0]);receipt=next(pathlib.Path(o['path']) for o in evidence['outputs'] if o['path'].endswith('-receipt.json'))
  data=json.loads(receipt.read_text());bound=json.loads(json.dumps(job));bound['evidence']['reviewer']=data['reviewer'];trusted=store.read_review(evidence['review_id'],bound)
  return {'native_sdk_review':'complete','native_review_decision':trusted['decision'],'native_review_id':trusted['review_id']}
 if request['operation']=='status':return {'schema_version':1,**identity,'status':'local_status','stages':state(),**native_state(),'provider_calls':0,'production_completed':False,'publication_allowed':False}
 store.register(job,brands);holder='local_vsl_'+uuid.uuid4().hex;store.acquire(job['brand'],job['job_id'],job['mode'],holder)
 completed=[];skipped=[];prior=None
 try:
  for name,role,ids in stages:
   if store.resumable(job,name):skipped.append(name)
   else:
    if name=='handoff_voice_reuse':
     receipt=json.loads((folder/'voice.receipt.json').read_text())
     if receipt['model_id']!='eleven_v4' or receipt['audio_sha256']!=sha(folder/'voice.wav') or receipt['script_sha256']!=sha(folder/'script.txt'):raise ValueError('existing exact V4 voice required; no TTS fallback')
    if name=='handoff_edit':
     # Existing immutable receipt REQUIRED, so render cannot become a new production call.
     old=json.loads((folder/'edit.receipt.json').read_text())
     if old['manifest_sha256']!=hashlib.sha256(json.dumps(vsl,ensure_ascii=False,sort_keys=True).encode()).hexdigest() or old['video_sha256']!=sha(folder/'final.mp4'):raise ValueError('existing edit receipt required; do not regenerate')
     result=subprocess.run([sys.executable,'-B',str(ROOT/'non_ai_vsl.py'),str(vslpath),'--verify-cached'],capture_output=True,text=True,timeout=240)
     if result.returncode or json.loads(result.stdout).get('edit')!=old:raise ValueError('cached canonical edit reentry failed')
    if name=='handoff_technical_qc':
     p=folder/'final.mp4';info=json.loads(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration:stream=codec_name,width,height','-of','json',str(p)],text=True,timeout=30))
     if abs(float(info['format']['duration'])-28.8)>.1 or not any(s.get('codec_name')=='h264' and s.get('width')==720 and s.get('height')==1280 for s in info['streams']) or not any(s.get('codec_name')=='aac' for s in info['streams']):raise ValueError('actual media technical check failed')
     subprocess.run(['/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(p),'-f','null','-'],check=True,timeout=60,capture_output=True)
    outputs=[{k:next(a for a in job['artifacts'] if a['id']==aid)[k] for k in ('path','sha256')} for aid in ids]
    evidence={'brand':job['brand'],'revision':job['revision'],'outputs':outputs,'assigned_role':role,'execution_kind':'fixed local component validation/reuse; no role SDK called','new_tts_calls':0,'new_visual_calls':0,'publication_allowed':False}
    store.checkpoint(job,holder,name,'complete',evidence,[prior] if prior else [])
    completed.append(name)
   prior=name
   if pause==name:return {'schema_version':1,**identity,'status':'paused_at_stage','paused_after':name,'completed':completed,'reused':skipped,'stages':state(),'provider_calls':0,'publication_allowed':False}
  actual=native_state()
  if actual['native_sdk_review']=='complete':return {'schema_version':1,**identity,'status':'local_handoffs_complete_native_review_'+actual['native_review_decision'].lower(),'completed':completed,'reused':skipped,'stages':state(),**actual,'provider_calls':0,'new_tts_calls':0,'production_completed':False,'publication_allowed':False}
  review_path=folder/'native-review-request.json'
  pending={'schema_version':1,**identity,'requested_role':'編集長','status':'pending_not_dispatched','artifact_hashes':[a['sha256'] for a in job['artifacts']],'central_manifest_sha256':manifest_hash(job),'blocked_reasons':['subscription extra-usage disablement not verified; no new charge allowed','source editing defects remain; local technical PASS is not visual quality PASS'],'native_sdk_review_receipt':None,'publication_allowed':False}
  if review_path.exists():
   if json.loads(review_path.read_text())!=pending:raise ValueError('immutable native review handoff changed')
  else:review_path.write_text(json.dumps(pending,ensure_ascii=False,indent=2))
  return {'schema_version':1,**identity,'status':'local_handoffs_complete_native_review_pending','completed':completed,'reused':skipped,'stages':state(),'native_review_request_path':str(review_path),'native_review_request_sha256':sha(review_path),'native_sdk_review':'not_run','provider_calls':0,'new_tts_calls':0,'publication_allowed':False}
 finally:store.release(job['brand'],job['job_id'],job['mode'],holder)
if __name__=='__main__':
 try:print(json.dumps(main(json.load(sys.stdin)),ensure_ascii=False))
 except Exception as e:print(json.dumps({'schema_version':1,'status':'blocked','error':str(e),'provider_calls':0,'publication_allowed':False},ensure_ascii=False));sys.exit(2)
