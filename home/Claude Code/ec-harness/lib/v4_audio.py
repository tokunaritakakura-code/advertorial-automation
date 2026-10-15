"""Explicit existing-credit Eleven v4 audio; one POST, durable ambiguous-outcome stop."""
from voice_policy_v4 import payload as v4_payload, require_model, require_voice, require_settings
import base64,fcntl,hashlib,json,os,subprocess,tempfile,urllib.request
from pathlib import Path
MODEL='eleven_v4'
VOICE='51WoBv13cwDXZGNZ3TLb' # Existing Miki.T Japanese voice; no fallback.
def atomic(p,obj):
 p=Path(p);fd,tmp=tempfile.mkstemp(dir=p.parent)
 with os.fdopen(fd,'w') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def generate(script,expected_sha,out,*,call,max_chars=1200):
 script=Path(script);out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
 text=script.read_text().strip()
 if sha(script)!=expected_sha or not 1<=len(text)<=max_chars:raise ValueError('exact bounded script required')
 with out.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  intent=out.with_suffix('.intent.json');receipt=out.with_suffix('.receipt.json');key=hashlib.sha256(json.dumps([expected_sha,MODEL,VOICE],sort_keys=True).encode()).hexdigest()
  if intent.exists():
   old=json.loads(intent.read_text())
   if old.get('key')!=key:raise ValueError('immutable audio request differs; new revision required')
   if old.get('status')=='complete' and receipt.exists() and out.exists() and sha(out)==json.loads(receipt.read_text())['audio_sha256']:return json.loads(receipt.read_text())
   raise ValueError('prior audio outcome uncertain/missing; reconcile before any retry')
  models=call('GET','/models',None);sub=call('GET','/user/subscription',None)
  match=next((m for m in models if m.get('model_id')==MODEL),None)
  if not match or match.get('can_do_text_to_speech') is not True or match.get('model_rates',{}).get('character_cost_multiplier')!=1.0:raise ValueError('native V4/rate unavailable; no model substitution')
  if sub.get('status')!='active' or sub.get('can_extend_character_limit') is not False or sub.get('allowed_to_extend_character_limit') is not False or sub.get('character_limit',0)-sub.get('character_count',0)<len(text):raise ValueError('existing credits/zero extra payment not verified')
  body=v4_payload(text, MODEL, VOICE, .5, dictionaries=[])
  atomic(intent,{'key':key,'status':'intent','model_id':MODEL,'voice_id':VOICE,'script_sha256':expected_sha,'characters':len(text),'additional_payment_allowed':False})
  # Exactly once. Timeout or crash leaves intent, preventing duplicate credit use.
  r=call('POST',f'/text-to-speech/{VOICE}/with-timestamps?output_format=mp3_44100_128',body)
  atomic(out.with_suffix('.native-response.json'),r)
  audio=base64.b64decode(r['audio_base64'],validate=True);alignment=r.get('alignment')
  if len(audio)<2000 or len(audio)>16*1024*1024 or not (audio.startswith(b'ID3') or (audio[0]==255 and audio[1]&224==224)) or not isinstance(alignment,dict) or ''.join(alignment.get('characters',[]))!=text:raise ValueError('complete native audio/alignment required')
  raw=out.with_suffix('.native.mp3');raw.write_bytes(audio)
  tmp=out.with_name(out.stem+'.render.wav')
  subprocess.run(['/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(raw),'-af','loudnorm=I=-16:TP=-1.5:LRA=11','-ar','48000','-ac','2','-y',str(tmp)],check=True,timeout=60);os.replace(tmp,out)
  proof={'model_id':MODEL,'voice_id':VOICE,'script_sha256':expected_sha,'audio_sha256':sha(out),'native_audio_sha256':sha(raw),'alignment':alignment,'additional_payment':0,'credit_characters_reserved':len(text),'tts_posts':1,'status':'audio_created_not_quality_approved'}
  atomic(receipt,proof);atomic(intent,{'key':key,'status':'complete'});return proof

def native_call(method,path,body):
 # Known existing key: never copied, printed or written to config/evidence.
 key=(Path.home()/'.claude/skills/vsl-jp/.secrets/eleven.key').read_text().strip()
 req=urllib.request.Request('https://api.elevenlabs.io/v1'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'xi-api-key':key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=180 if method=='POST' else 30) as r:return json.loads(r.read(32*1024*1024))
