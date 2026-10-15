"""Local existing-owner footage edit through inspected existing renderer. No provider calls."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from vsl_route import preflight,sha

def probe(p):return json.loads(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration:stream=codec_name,width,height,duration','-of','json',str(p)],text=True,timeout=30))
def write(p,x):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2));os.replace(tmp,p)
def render(job,policy,root):
 root=Path(root);preflight(job,policy);audio=root/'voice.wav';receipt=json.loads((root/'voice.receipt.json').read_text())
 if receipt['model_id']!='eleven_v4' or receipt['audio_sha256']!=sha(audio) or receipt['script_sha256']!=job['script']['sha256']:raise ValueError('same exact V4/script/audio receipt required')
 duration=float(probe(audio)['format']['duration']);alignment=receipt['alignment'];chars=alignment['characters'];starts=alignment['character_start_times_seconds'];ends=alignment['character_end_times_seconds']
 if len(chars)!=len(starts) or len(chars)!=len(ends) or ''.join(chars)!=Path(job['script']['path']).read_text().strip() or any(not 0<=a<=b<=duration+.1 for a,b in zip(starts,ends)):raise ValueError('exact monotone full script alignment required')
 # The existing owner UGC catalogue defines these physical demo cuts; no competitor frames.
 order=[1,0,7,8,3,4,2,6,5,10,11,12,9]
 assets=job['assets'];indices=job.get('edit_asset_indices',order)
 if not indices or len(indices)!=len(set(indices)) or any(type(i) is not int or not 0<=i<len(assets) for i in indices):raise ValueError('each selected fixed own asset at most once required')
 available=sum(float(probe(assets[i]['path'])['format']['duration']) for i in indices);speed=available/duration
 targets=job.get('edit_cut_durations')
 if targets is not None and (not isinstance(targets,list) or len(targets)!=len(indices) or any(type(d) not in (int,float) or not .5<=d<=6 for d in targets) or abs(sum(targets)-duration)>.01):raise ValueError('bounded exact full-audio edit durations required')
 if not .65<=speed<=1.35:raise ValueError('voice/footage duration mismatch requires edit; no padding/cutting audio')
 output=root/'final.mp4';planpath=root/'cuts.json';done=root/'edit.receipt.json';jobhash=hashlib.sha256(json.dumps(job,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 if done.exists():
  old=json.loads(done.read_text())
  if old['manifest_sha256']!=jobhash or not output.exists() or sha(output)!=old['video_sha256']:raise ValueError('prior final/manifest changed; do not overwrite')
  return old
 folder=root/'edit-inputs';folder.mkdir(exist_ok=True);cuts=[];t=0
 for n,i in enumerate(indices):
  a=assets[i];dest=folder/(str(i).zfill(2)+'.mp4')
  if not dest.exists():shutil.copyfile(a['path'],dest)
  if sha(dest)!=a['sha256']:raise ValueError('snapshot input changed')
  source_duration=float(probe(dest)['format']['duration'])
  d=targets[n] if targets is not None else source_duration/speed
  cut_speed=source_duration/d
  if not .45<=cut_speed<=1.5:raise ValueError('physical footage speed out of range')
  cuts.append({'file':str(dest),'t_in':t,'dur':d,'src_in':0,'speed':cut_speed,'場面':'自社UGC実物実演','寄り':'足元' if i in [0,1] else '商品寄り','動作':a['label'],'印':'source-cut-'+str(i),'source_original':a['path'],'source_sha256':a['sha256']});t+=d
 subtitles=[]
 requested=job.get('edit_subtitle_chunks')
 if not isinstance(requested,list) or not requested or any(not isinstance(c,str) or not c.strip() or len(c)>18 for c in requested):raise ValueError('bounded natural subtitle chunks required')
 flat=[(c,starts[i],ends[i]) for i,c in enumerate(chars) if not c.isspace()]
 if ''.join(requested)!=''.join(c for c,_,_ in flat):raise ValueError('subtitle text must exactly match full actual voice script')
 pos=0
 for text in requested:
  subtitles.append({'text':text,'t_in':flat[pos][1],'t_out':min(duration,flat[pos+len(text)-1][2])});pos+=len(text)
 plan={'名前':'A01_H06_アルコット自社実演','画':{'横':720,'縦':1280},'声':str(audio),'カット':cuts,'字幕':subtitles,'字幕の見た目':{'型':'帯','位置':.52,'最低高さ':.10,'字の大きさ':36},'reference':job['reference'],'publication_allowed':False}
 write(planpath,plan)
 renderer=Path.home()/'Claude Code/video-common/素材/並べる.py'
 p=subprocess.run([sys.executable,str(renderer),str(planpath),'--out',str(output)],text=True,capture_output=True,timeout=240)
 (root/'render.log').write_text(p.stdout+p.stderr)
 if p.returncode:raise ValueError('existing renderer failed; see local render.log')
 info=probe(output);vd=float(info['format']['duration']);vs=[s for s in info['streams'] if s.get('codec_name')=='h264'];audio_stream=[s for s in info['streams'] if s.get('codec_name')=='aac']
 if len(vs)!=1 or len(audio_stream)!=1 or (vs[0]['width'],vs[0]['height'])!=(720,1280) or abs(vd-duration)>.15:raise ValueError('final codec/audio/complete duration quality failed')
 subprocess.run(['/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(output),'-f','null','-'],check=True,timeout=60)
 result={'status':'local_video_created_technical_checks_pass','manifest_sha256':jobhash,'video_path':str(output),'video_sha256':sha(output),'audio_sha256':sha(audio),'audio_model':'eleven_v4','duration':vd,'cuts':len(cuts),'subtitles':len(subtitles),'source_visuals':'fixed user-approved Alcott UGC clips only','new_visual_generation_calls':0,'reference_non_ai_confirmed':False,'independent_quality_review':'pending','publication_allowed':False,'evidence_paths':[str(planpath),str(root/'voice.receipt.json'),str(root/'render.log')],'technical_checks':['h264720x1280','aac_audio','full_voice_duration','decode_all_frames','unique_selected_owner_assets','exactscript_alignment','input_hash_snapshots']}
 write(done,result);return result


def verify_cached(job,policy,root):
 """Verify sealed prior preflight + selected local snapshots; never reopen Desktop originals."""
 root=Path(root).resolve();engine=Path(__file__).resolve().parents[1];cfg=json.loads((engine/'config/local-vsl-dispatch.json').read_text())
 if cfg.get('provider_calls') is not False or any(job.get(k)!=cfg.get(k) for k in ['brand','job_id','revision']):raise ValueError('fixed approved existing job required')
 registered=json.loads((engine/'config/brands.json').read_text())['brands'][job['brand']]
 expected=Path(registered['workspace_root']).resolve()/job['job_id']/('r'+str(job['revision']))
 if root!=expected or job.get('visual_route')!='existing_non_ai' or job.get('image_generation') is not False or job.get('video_generation') is not False or job.get('publication_allowed') is not False:raise ValueError('cached scope/route changed')
 receipt=json.loads((root/'edit.receipt.json').read_text());jobhash=hashlib.sha256(json.dumps(job,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 proof=root/'preflight.receipt.json'
 if sha(proof)!=cfg['original_preflight_receipt_sha256']:raise ValueError('prior confirmed preflight proof changed')
 prior=json.loads(proof.read_text())
 if prior.get('status')!='eligible_for_local_edit' or prior.get('edit',{}).get('manifest_sha256')!=jobhash or receipt['manifest_sha256']!=jobhash:raise ValueError('exact prior original-input preflight required')
 assets=job['assets'];indices=job['edit_asset_indices']
 if len(indices)!=len(set(indices)) or any(type(i)is not int or not 0<=i<len(assets) for i in indices):raise ValueError('unique fixed selected clips required')
 for a in assets:
  if a.get('known_generated') or a.get('ai_origin')=='known_ai_generated' or a.get('source_kind')!='owner_library' or policy['approved_owner_assets'].get(str(Path(a['path']).resolve()))!=a['sha256']:raise ValueError('fixed previously approved owner assets only')
 for i in indices:
  if sha(root/'edit-inputs'/(str(i).zfill(2)+'.mp4'))!=assets[i]['sha256']:raise ValueError('selected input snapshot changed')
 voice=json.loads((root/'voice.receipt.json').read_text())
 if voice['model_id']!='eleven_v4' or voice['audio_sha256']!=sha(root/'voice.wav') or voice['script_sha256']!=sha(root/'script.txt') or job['script']['sha256']!=sha(root/'script.txt'):raise ValueError('same cached voice/script required')
 if Path(receipt['video_path']).resolve()!=root/'final.mp4' or sha(root/'final.mp4')!=receipt['video_sha256'] or receipt['audio_sha256']!=voice['audio_sha256']:raise ValueError('same exact existing final required')
 return receipt
