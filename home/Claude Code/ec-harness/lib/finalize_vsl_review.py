"""Reconcile actual fresh SDK receipt only. Never issue an owner approval."""
import json,pathlib,sys,hashlib,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'lib'))
from ec_contract import StateStore,CONTROL_DB,canonical
def main(request):
 if not isinstance(request,dict) or set(request)!={'receipt_path'}:raise ValueError('app-generated receipt path only')
 plan=json.loads((ROOT/'config/local-vsl-review.json').read_text());folder=pathlib.Path(plan['job_manifest_path']).parent
 p=pathlib.Path(request['receipt_path']).resolve()
 if p.parent!=folder/'native-sdk-review' or not p.name.endswith('-receipt.json'):raise ValueError('fixed scoped review receipt required')
 data=json.loads(p.read_text());job=json.loads(pathlib.Path(plan['job_manifest_path']).read_text())
 if any(data.get(k)!=job[k] for k in ['brand','job_id','revision']) or data['actual_sdk_init']['apiKeySource']!='none' or data['actual_sdk_init']['model']!=plan['model'] or data['actual_sdk_terminal']['subtype']!='success' or set(data['actual_video_inspections'])!={'final','reference'}:raise ValueError('actual native review completion required')
 assessment=pathlib.Path(data['assessment_path']).resolve()
 if assessment.parent!=p.parent or hashlib.sha256(assessment.read_bytes()).hexdigest()!=data['assessment_sha256']:raise ValueError('immutable SDK assessment changed')
 a=json.loads(assessment.read_text())
 if a['decision']!=data['decision'] or a['sdk_session_id']!=data['actual_sdk_init']['session_id']:raise ValueError('native assessment/session mismatch')
 store=StateStore(CONTROL_DB);review_job=json.loads(json.dumps(job));review_job['evidence']['reviewer']=data['reviewer'];trusted=store.read_review(data['reviewer']['review_id'],review_job)
 if trusted['decision']!=data['decision'] or trusted['run_id']!=data['run_id']+'-'+data['actual_sdk_init']['session_id']:raise ValueError('trusted fresh SDK receipt differs')
 holder='native_review_finalize_'+uuid.uuid4().hex;store.acquire(job['brand'],job['job_id'],job['mode'],holder)
 outputs=[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [p,assessment]]
 try:
  evidence={'brand':job['brand'],'revision':job['revision'],'outputs':outputs,'review_id':trusted['review_id'],'decision':trusted['decision'],'actual_native_sdk_session':data['actual_sdk_init']['session_id'],'publication_allowed':False}
  if not store.resumable(job,'native_review'):store.checkpoint(job,holder,'native_review','complete',evidence,['technical_qc'])
  status='complete' if trusted['decision']=='PASS' else 'failed'
  with store.connect() as c:old=c.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(job['brand'],job['job_id'],job['mode'],job['revision'],'editorial_review')).fetchone()
  if not old or old[0]!=status or old[1]!=canonical(evidence):store.checkpoint(job,holder,'editorial_review',status,evidence,['native_review'])
 finally:store.release(job['brand'],job['job_id'],job['mode'],holder)
 marker=folder/'native-review-request.json';historical=folder/'native-review-request-submitted.json'
 if marker.exists() and not historical.exists() and json.loads(marker.read_text()).get('status')=='pending_not_dispatched':historical.write_bytes(marker.read_bytes())
 current={'schema_version':1,'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision'],'status':'completed','decision':trusted['decision'],'review_id':trusted['review_id'],'actual_sdk_session_id':data['actual_sdk_init']['session_id'],'receipt_path':str(p),'receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'assessment_path':str(assessment),'publication_allowed':False}
 encoded=json.dumps(current,ensure_ascii=False,indent=2)
 if not marker.exists() or marker.read_text()!=encoded:
  tmp=marker.with_suffix('.tmp');tmp.write_text(encoded);tmp.replace(marker)
 return {'native_review':'complete','editorial_review':status,'decision':trusted['decision'],'review_id':trusted['review_id'],'publication_allowed':False,'owner_approval_created':False}
if __name__=='__main__':
 try:print(json.dumps(main(json.load(sys.stdin)),ensure_ascii=False))
 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)}));sys.exit(2)
