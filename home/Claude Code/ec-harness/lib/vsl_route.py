"""Explicit VSL media branch. No model calls, generation, publication or licensing guesses."""
import hashlib,json,math
from pathlib import Path
POLICY=Path(__file__).resolve().parents[1]/'config/vsl_routes.json'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def route(brand,path=POLICY):
 d=read(path);p=d.get('brands',{}).get(brand)
 if p is None:return None
 if d.get('schema_version')!=1 or p.get('visual_route')!='existing_non_ai' or p.get('image_generation') is not False or p.get('video_generation') is not False:raise ValueError('fixed non-AI visual branch required')
 return p

def provenance(record):
 # Reviewed publisher/owner documentation, never a visual heuristic or guessed field.
 e=record.get('ai_origin_evidence',{})
 if record.get('ai_origin')!='verified_non_ai' or e.get('basis') not in {'publisher_statement','owner_original_capture','licensed_provider_statement'}:raise ValueError('AI origin unconfirmed; appearance is not proof')
 p=e.get('path')
 if not p or sha(p)!=e.get('sha256'):raise ValueError('AI origin evidence changed/missing')

def preflight(job,policy):
 if job.get('brand')!=policy['brand'] or job.get('visual_route')!='existing_non_ai' or job.get('image_generation') is not False or job.get('video_generation') is not False:raise ValueError('scope/non-AI branch differs')
 ref=job.get('reference',{})
 if ref.get('source')!='GetHookd' or not str(ref.get('ad_id','')).isdigit() or not ref.get('share_url','').startswith('https://app.gethookd.ai/share/ad/') or ref.get('usage')!='analysis_only':raise ValueError('GetHookd exact reference provenance required')
 reference_confirmed=True
 try:provenance(ref)
 except ValueError:
  e=ref.get('ai_origin_evidence') or {}
  if not policy.get('allow_assessed_reference_local_review') or ref.get('ai_origin')!='unknown' or e.get('basis')!='visual_assessment' or not e.get('path') or sha(e['path'])!=e.get('sha256'):raise
  reference_confirmed=False
 assets=job.get('assets')
 if not isinstance(assets,list) or not assets:raise ValueError('rights-confirmed existing assets required')
 paths=set()
 for a in assets:
  if a.get('known_generated') or a.get('ai_origin')=='known_ai_generated':raise ValueError('known AI visuals excluded')
  p=Path(a['path']).resolve()
  if not any(p.is_relative_to(Path(r).resolve()) for r in policy['asset_read_roots']) or sha(p)!=a.get('sha256') or str(p) in paths:raise ValueError('unique same-brand asset path/hash required')
  paths.add(str(p));rights=a.get('rights',{})
  if rights.get('status')=='owner_authorized_library':
   accepted=policy.get('approved_owner_assets',{})
   if a.get('source_kind')!='owner_library' or accepted.get(str(p))!=a.get('sha256'):raise ValueError('explicit approved own library asset required; competitor excluded')
   if not rights.get('evidence_path') or sha(rights['evidence_path'])!=rights.get('evidence_sha256'):raise ValueError('owner source instruction changed')
  else:
   provenance(a)
   if rights.get('status') not in {'owner_original','licensed_commercial'} or not rights.get('evidence_path') or sha(rights['evidence_path'])!=rights.get('evidence_sha256'):raise ValueError('asset reuse license missing/changed; competitor save is not license')
  if a.get('source_kind')=='competitor_ad' and rights['status']!='licensed_commercial':raise ValueError('competitor ad requires explicit commercial reuse license')
 audio=job.get('audio',{})
 if audio.get('model_id')!=policy['audio_model'] or audio.get('additional_payment_allowed') is not False:raise ValueError('explicit V4 existing-credit audio only')
 return {'status':'eligible_for_local_edit','brand':job['brand'],'visual_route':'existing_non_ai','asset_count':len(assets),'reference_non_ai_confirmed':reference_confirmed,'reference_review_required':not reference_confirmed,'execution_authorized':False,'publication_allowed':False}
