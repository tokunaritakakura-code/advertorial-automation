"""Opt-in typed adapters. Importing performs no I/O; transports are supplied by the host.

No credential discovery, shell, Claude invocation, campaign creation or scheduling.
The CLI uses fixture transports only. Paid requests are deliberately NOT retried.
"""
from voice_policy_v4 import payload as v4_payload, require_model, require_voice, require_settings
import base64
import hashlib
import json
import math
import re
import subprocess
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import ec_contract as C


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value, minimum=0):
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


class ReconciliationRequired(RuntimeError):
    pass


class Journal:
    """Persist BEFORE requests. A timeout/crash cannot silently submit a second charge."""
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS adapter_intents (key TEXT PRIMARY KEY, brand TEXT, provider TEXT, request_hash TEXT, reserved REAL, status TEXT, receipt TEXT)')

    def begin(self, key, brand, provider, request, reserved, ceiling):
        digest = hashlib.sha256(C.canonical(request).encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT request_hash,status,receipt FROM adapter_intents WHERE key=?', (key,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError('intent payload changed')
                if row[1] == 'complete':
                    return json.loads(row[2])
                raise ReconciliationRequired('request outcome unknown; reconcile instead of resubmitting: ' + key)
            used = db.execute('SELECT COALESCE(SUM(reserved),0) FROM adapter_intents WHERE brand=? AND provider=?', (brand, provider)).fetchone()[0]
            if not finite(reserved) or not finite(ceiling) or used + reserved > ceiling:
                raise ValueError('provider cumulative approved ceiling exceeded')
            db.execute('INSERT INTO adapter_intents VALUES (?,?,?,?,?,?,?)', (key, brand, provider, digest, reserved, 'intent', None))
        return None

    def finish(self, key, receipt):
        with self.store.connect() as db:
            db.execute("UPDATE adapter_intents SET status='complete',receipt=? WHERE key=? AND status='intent'", (C.canonical(receipt), key))


def authorize(job, config, store, approval_id):
    approval = store.read_approval(approval_id, job)
    review = store.read_review(job['evidence']['reviewer']['review_id'], job)
    result = C.validate_job(job, config, approval, trusted_review=review)
    if result['status'] != 'executable':
        raise ValueError('exact approval/review/input required: ' + C.canonical(result))
    return config['brands'][job['brand']]


def scoped_file(job, cfg, artifact_id):
    artifact = next(a for a in job['artifacts'] if a['id'] == artifact_id)
    path = Path(artifact['path']).resolve()
    if not any(path.is_relative_to(Path(root).resolve()) for root in cfg['asset_roots']) or sha(path) != artifact['sha256']:
        raise ValueError('bound artifact changed/outside brand')
    return artifact, path


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def output_path(job,cfg,name):
    root=Path(cfg['workspace_root']).resolve()
    path=(root/job['job_id']/('r'+str(job['revision']))/name).resolve()
    if not C.TOKEN.fullmatch(job['job_id']) or type(job['revision']) is not int or job['revision']<1 or not path.is_relative_to(root) or not any(path.is_relative_to(Path(r).resolve()) for r in cfg['asset_roots']):
        raise ValueError('brand-scoped output root required before write')
    return path


def trusted_transport(transport, provider, account):
    # Account identity is authenticated by the trusted host's bound connection.
    # Never take it from agent payload or use a fallback environment account.
    if transport.provider != provider or transport.account_id != account or not account:
        raise ValueError('provider/account connection mismatch')


def domain(job, *transports):
    value = job.get('execution_domain')
    if value not in {'simulation','production'} or any(type(t.simulated) is not bool or t.simulated != (value=='simulation') for t in transports):
        raise ValueError('explicit execution domain/transport mismatch')
    return 'mock-' if value=='simulation' else ''


def historical_record(job, config, store, approval_id, supplied, stage):
    """Read-only historical authority: expiry limits writes, not later observation.

    Verify exact registered manifest, stored successful delivery and its approval
    at execution time. Do not accept a caller-supplied delivery assertion.
    """
    prefix=domain(job)
    key=(job['brand'],job['job_id'],job['mode'],job['revision'])
    with store.connect() as db:
        registered=db.execute('SELECT hash FROM jobs WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()
        row=db.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(*key,prefix+stage)).fetchone()
        approved=db.execute('SELECT hash,envelope FROM approvals WHERE id=? AND brand=? AND job=? AND mode=? AND revision=?',(approval_id,*key)).fetchone()
    if not registered or registered[0]!=C.manifest_hash(job) or not row or row[0]!='complete' or not approved or approved[0]!=C.manifest_hash(job) or not store.resumable(job,prefix+stage):
        raise ValueError('stored exact successful delivery/approval required')
    evidence=json.loads(row[1])
    if evidence!=supplied or evidence.get('approval_ref')!=approval_id:
        raise ValueError('stored delivery receipt differs')
    result=C.validate_job(job,config,json.loads(approved[1]),now=C.parse_time(evidence['executed_at']),trusted_review=store.read_review(job['evidence']['reviewer']['review_id'],job))
    if result['status']!='executable':raise ValueError('delivery was not authorized for exact bytes/scope')
    return config['brands'][job['brand']]


def delivery_record(job,config,store,approval_id,supplied):
    return historical_record(job,config,store,approval_id,supplied,'delivery')


def production(job, config, store, approval_id, transport, *, ffmpeg='/opt/homebrew/bin/ffmpeg', ffprobe='/opt/homebrew/bin/ffprobe'):
    if job.get('brand') == 'アルコット':
        from vsl_route import route
        if route(job['brand']):
            raise ValueError('Alcott defaults to existing_non_ai VSL: use non_ai_vsl.py; legacy v3/static-image production is blocked')
    cfg = authorize(job, config, store, approval_id)
    domain(job,transport)
    action, = job['actions']
    if action['operation'] != 'generate_local' or set(action['payload']) != {'production'}:
        raise ValueError('one typed generation action required')
    plan = action['payload']['production']
    fields = {'provider','provider_account','voice_id','script_artifact_id','image_artifact_id','output_revision','spend_ceiling','currency','duration','width','height'}
    if set(plan) != fields or plan['provider'] != 'elevenlabs_v4':
        raise ValueError('unknown production field/provider')
    provider = cfg.get('production', {})
    required = ('provider_account','voice_id','currency','max_price_per_1000_chars','cumulative_spend_ceiling','max_request_spend','max_chars')
    if any(provider.get(k) is None for k in required):
        raise ValueError('production account/voice/price/budget configuration incomplete')
    for key in ('provider_account','voice_id','currency'):
        if plan[key] != provider[key]:
            raise ValueError('approved production/provider configuration mismatch')
    if not re.fullmatch('[A-Za-z0-9_-]{1,100}', plan['voice_id']):
        raise ValueError('invalid voice id')
    if any(not finite(provider[k]) for k in ('max_price_per_1000_chars','cumulative_spend_ceiling','max_request_spend')):
        raise ValueError('invalid production price/ceiling')
    if not finite(plan['spend_ceiling']) or plan['spend_ceiling'] > provider['max_request_spend']:
        raise ValueError('request spend exceeds configured ceiling')
    if type(plan['output_revision']) is not int or plan['output_revision'] != job['revision'] + 1:
        raise ValueError('new artifact revision required')
    if not finite(plan['duration'], .1) or plan['duration'] > 180 or any(type(plan[k]) is not int or not 32 <= plan[k] <= 1920 or plan[k] % 2 for k in ('width','height')) or plan['height'] * 9 != plan['width'] * 16:
        raise ValueError('bounded portrait rendering parameters required')
    trusted_transport(transport, 'elevenlabs', plan['provider_account'])
    script_artifact, script = scoped_file(job, cfg, plan['script_artifact_id'])
    image_artifact, image = scoped_file(job, cfg, plan['image_artifact_id'])
    script_bytes=script.read_bytes()
    image_bytes = image.read_bytes()
    if hashlib.sha256(script_bytes).hexdigest()!=script_artifact['sha256'] or hashlib.sha256(image_bytes).hexdigest()!=image_artifact['sha256']:
        raise ValueError('approved production bytes changed')
    if not (image_bytes.startswith(b'\x89PNG\r\n\x1a\n') or image_bytes.startswith(b'\xff\xd8\xff') or image_bytes.startswith(b'P6\n')):
        raise ValueError('approved still image format required; playlists/SVG forbidden')
    text = script_bytes.decode('utf-8').strip()
    if not text or type(provider['max_chars']) is not int or not len(text) <= min(provider['max_chars'], 10000):
        raise ValueError('nonempty bounded approved script required')
    estimate = len(text) * provider['max_price_per_1000_chars'] / 1000
    if estimate > plan['spend_ceiling']:
        raise ValueError('script price upper bound exceeds approved request')
    output = Path(action['target']).resolve()
    expected = Path(cfg['workspace_root']).resolve() / job['job_id'] / ('r' + str(plan['output_revision']))
    if output != expected or not any(output.is_relative_to(Path(r).resolve()) for r in cfg['asset_roots']):
        raise ValueError('exact brand/job/output revision directory required')
    # Both executable paths must be configured by the host, never from the plan.
    if Path(ffmpeg).name != 'ffmpeg' or Path(ffprobe).name != 'ffprobe' or not all(Path(p).is_absolute() and Path(p).is_file() for p in (ffmpeg, ffprobe)):
        raise ValueError('configured fixed ffmpeg/ffprobe required')
    store.register(job, config)
    holder = uuid.uuid4().hex
    store.acquire(job['brand'], job['job_id'], job['mode'], holder)
    stage = 'mock-production' if transport.simulated else 'production'
    try:
        if store.resumable(job, stage):
            with store.connect() as db:
                saved = db.execute('SELECT evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?', (job['brand'],job['job_id'],job['mode'],job['revision'],stage)).fetchone()
            return json.loads(saved[0])
        key = C.manifest_hash(job) + ':tts'
        body = v4_payload(text, 'eleven_v4', plan['voice_id'], .5, dictionaries=[])
        request = {'method':'POST','path':f"/v1/text-to-speech/{plan['voice_id']}/with-timestamps?output_format=mp3_44100_128",'body':body,'account_id':plan['provider_account'],'currency':plan['currency'],'domain':job['execution_domain']}
        journal = Journal(store)
        cached = journal.begin(key, job['brand'], job['execution_domain']+':elevenlabs:' + plan['provider_account'], request, estimate, provider['cumulative_spend_ceiling'])
        if cached:
            audio_path = Path(cached['audio_path'])
            if not audio_path.is_relative_to(output) or not audio_path.is_file() or sha(audio_path) != cached['audio_sha256']:
                raise ReconciliationRequired('charged audio missing/changed; no new TTS request')
        else:
            authorize(job, config, store, approval_id)
            # Intentionally exactly one provider request; no automatic TTS retry.
            response = transport.request('POST', request['path'], body)
            audio = base64.b64decode(response['audio_base64'], validate=True)
            alignment = response.get('alignment')
            if not audio or len(audio) > 25_000_000 or not isinstance(alignment, dict) or not alignment.get('characters'):
                raise ValueError('TTS bytes/alignment evidence missing')
            if not (audio.startswith(b'ID3') or (len(audio)>1 and audio[0]==255 and audio[1]&224==224) or (audio.startswith(b'RIFF') and audio[8:12]==b'WAVE')):
                raise ValueError('TTS audio format rejected; playlists are forbidden')
            starts=alignment.get('character_start_times_seconds')
            ends=alignment.get('character_end_times_seconds')
            if not isinstance(starts,list) or not isinstance(ends,list) or len(starts)!=len(ends) or len(ends)!=len(alignment['characters']) or any(not finite(x) for x in starts+ends) or any(s>e for s,e in zip(starts,ends)) or any(starts[i]>starts[i+1] for i in range(len(starts)-1)) or max(ends)>plan['duration']:
                raise ValueError('complete bounded speech alignment required')
            audio_path = output / 'voice.mp3'
            atomic(audio_path, audio)
            atomic(output / 'alignment.json', C.canonical(alignment).encode())
            journal.finish(key, {'audio_path':str(audio_path),'audio_sha256':sha(audio_path),'request_key':key,'reserved_cost':estimate,'currency':plan['currency'],'simulated':transport.simulated})
        authorize(job, config, store, approval_id)
        store.acquire(job['brand'],job['job_id'],job['mode'],holder)
        # Fixed argv, local protocols only, approved input bytes; no user filter/command.
        output.mkdir(parents=True, exist_ok=True)
        audio_probe=json.loads(subprocess.run([ffprobe,'-v','error','-protocol_whitelist','file,pipe','-show_format','-of','json',str(audio_path)],check=True,capture_output=True,text=True,timeout=15).stdout)
        audio_duration=float(audio_probe['format']['duration'])
        if not finite(audio_duration,.1) or audio_duration>plan['duration']+.15:
            raise ValueError('voice exceeds approved duration; never truncate speech')
        render_duration=audio_duration
        destination = output / 'video.mp4'
        temporary = output / 'render.partial.mp4'
        snapshot=output/'approved-image.ppm'
        atomic(snapshot,image_bytes)
        argv = [ffmpeg,'-nostdin','-v','error','-y','-protocol_whitelist','file,pipe','-loop','1','-i',str(snapshot),'-protocol_whitelist','file,pipe','-i',str(audio_path),'-t',str(render_duration),'-vf',f"scale={plan['width']}:{plan['height']}:force_original_aspect_ratio=decrease,pad={plan['width']}:{plan['height']}:(ow-iw)/2:(oh-ih)/2",'-r','25','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(temporary)]
        subprocess.run(argv, check=True, capture_output=True, timeout=240)
        probe = json.loads(subprocess.run([ffprobe,'-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(temporary)], check=True, capture_output=True, text=True, timeout=15).stdout)
        video = [s for s in probe['streams'] if s['codec_type'] == 'video']
        audio = [s for s in probe['streams'] if s['codec_type'] == 'audio']
        if len(video) != 1 or len(audio) != 1 or video[0]['width'] != plan['width'] or video[0]['height'] != plan['height'] or abs(float(probe['format']['duration']) - render_duration) > .2:
            raise ValueError('actual encoded video/audio/duration validation failed')
        authorize(job, config, store, approval_id)
        store.acquire(job['brand'],job['job_id'],job['mode'],holder)
        temporary.replace(destination)
        artifact = {'id':'video','revision':plan['output_revision'],'path':str(destination),'sha256':sha(destination)}
        preview=output/'preview.png'
        subprocess.run([ffmpeg,'-nostdin','-v','error','-y','-protocol_whitelist','file,pipe','-i',str(destination),'-frames:v','1',str(preview)],check=True,capture_output=True,timeout=30)
        script_copy=output/'approved-script.txt';atomic(script_copy,script_bytes)
        proof=output/'encoding-proof.json'
        atomic(proof,C.canonical({'brand':job['brand'],'job_id':job['job_id'],'revision':plan['output_revision'],'video_sha256':artifact['sha256'],'input_manifest_hash':C.manifest_hash(job),'approved_script_sha256':script_artifact['sha256'],'approved_image_sha256':image_artifact['sha256'],'streams':probe['streams'],'format':{k:v for k,v in probe['format'].items() if k!='filename'},'audio_duration':audio_duration,'pronunciation_verified':False,'simulated':transport.simulated}).encode())
        bundle=[artifact]+[{'id':name,'revision':plan['output_revision'],'path':str(p),'sha256':sha(p)} for name,p in [('preview',preview),('script',script_copy),('encoding-proof',proof),('alignment',output/'alignment.json')]]
        result = {'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision'],'artifact':artifact,'review_artifacts':bundle,'outputs':bundle+[{'path':str(audio_path),'sha256':sha(audio_path)}],'request_key':key,'reserved_cost':estimate,'currency':plan['currency'],'status':'simulated_produced' if transport.simulated else 'produced','simulated':transport.simulated,'input_manifest_hash':C.manifest_hash(job),'approval_ref':approval_id,'executed_at':datetime.now(timezone.utc).isoformat()}
        store.checkpoint(job, holder, stage, 'complete', result)
        return result
    finally:
        store.release(job['brand'], job['job_id'], job['mode'], holder)


def execute_video(job, config, store, approval_id, transport):
    """Native video upload -> creative -> ad -> effective-status readback.

    Uses an existing adset, an approved page/IG and an approved landing URL.
    Every create has a durable intent. No retries after uncertain remote creation.
    """
    from urllib.parse import urlparse
    cfg = authorize(job,config,store,approval_id)
    domain(job,transport)
    trusted_transport(transport,'meta',cfg['account_id'])
    action, = job['actions']
    if action['operation'] != 'create_ad' or set(action['payload']) != {'order'}:
        raise ValueError('one typed video create order required')
    order = action['payload']['order']
    if set(order) != {'口座','act','page','ig','配信','adset','ads'} or order['配信'] is not True or order['page'] != cfg.get('page_id') or order['ig'] != cfg.get('instagram_id') or set(order['adset']) != {'id'} or str(order['adset']['id']) != action['target']:
        raise ValueError('approved account/page/IG/existing adset/activation required')
    ad, = order['ads']
    if set(ad) != {'name','file','message','title','link','status'} or ad['status'] != 'ACTIVE' or not ad['name'] or len(ad['name']) > 200 or any(not isinstance(ad[k],str) or not ad[k] or len(ad[k]) > 10000 for k in ('message','title','link')):
        raise ValueError('bounded approved video creative fields required')
    url=urlparse(ad['link'])
    if url.scheme!='https' or url.username or url.password or url.hostname not in cfg.get('publication',{}).get('landing_hosts',[]):
        raise ValueError('approved brand landing host required')
    artifact,path=scoped_file(job,cfg,action['artifact_id'])
    if str(path)!=str(Path(ad['file']).resolve()) or not re.fullmatch(r'\d+',action['target']):
        raise ValueError('approved video/adset mismatch')
    holder=uuid.uuid4().hex
    store.acquire(job['brand'],job['job_id'],job['mode'],holder)
    journal=Journal(store)
    stage='mock-delivery' if transport.simulated else 'delivery'
    try:
        member=transport.request('GET','/'+action['target']+'?fields=id,account_id,lifetime_budget,end_time,campaign{daily_budget,lifetime_budget}',None)
        if member.get('id')!=action['target'] or member.get('account_id')!=cfg['account_id']:
            raise ValueError('existing adset account mismatch')
        limits=job.get('order',{}).get('期限/支出上限',{})
        publication=cfg.get('publication',{})
        scale=publication.get('budget_unit_scale')
        if action['target'] not in publication.get('existing_adset_ids',[]) or not finite(scale,.000001) or not finite(limits.get('spend_ceiling')):
            raise ValueError('explicit existing adset/budget unit/job spend ceiling required')
        amount=float(member.get('lifetime_budget') or 0)/scale
        campaign=member.get('campaign',{})
        if not finite(amount,.000001) or amount>limits['spend_ceiling'] or not isinstance(campaign,dict) or any(float(campaign.get(k) or 0)>0 for k in ('daily_budget','lifetime_budget')) or C.parse_time(member['end_time'])>min(C.parse_time(job['expires_at']),C.parse_time(limits['deadline'])) or C.parse_time(member['end_time'])<=time.time():
            raise ValueError('bounded existing adset lifetime budget/end time required; shared campaign budget unsupported')
        def create(part, endpoint, payload, fingerprint=None):
            authorize(job,config,store,approval_id)
            store.acquire(job['brand'],job['job_id'],job['mode'],holder)
            key=C.manifest_hash(job)+':'+part
            cached=journal.begin(key,job['brand'],job['execution_domain']+':meta:'+cfg['account_id'],fingerprint or payload,0,0)
            if cached:return cached['id']
            observed=transport.request('POST',endpoint,payload)
            if not isinstance(observed.get('id'),str) or not re.fullmatch(r'\d+',observed['id']):
                raise ValueError('remote create id missing')
            journal.finish(key,{'id':observed['id']})
            return observed['id']
        # Snapshot exact approved bytes in memory immediately before upload.
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=artifact['sha256'] or len(data)>250_000_000:
            raise ValueError('video changed/exceeds adapter upload bound')
        video_id=create('video','/act_'+cfg['account_id']+'/advideos',{'source_bytes':data,'title':ad['name']},{'artifact_sha256':artifact['sha256'],'title':ad['name']})
        status=transport.request('GET','/'+video_id+'?fields=id,status',None)
        if status.get('id')!=video_id or status.get('status',{}).get('video_status')!='ready':
            return {'status':'video_processing','simulated':transport.simulated,'video_id':video_id}
        thumbnails=transport.request('GET','/'+video_id+'/thumbnails',None)
        if not isinstance(thumbnails.get('data'),list) or not thumbnails['data']:
            raise ValueError('generated video thumbnail unavailable')
        thumbnail=thumbnails['data'][0].get('uri','')
        thumb=urlparse(thumbnail)
        if thumb.scheme!='https' or thumb.username or thumb.password or not thumb.hostname or not thumb.hostname.endswith('.fbcdn.net'):
            raise ValueError('untrusted Meta video thumbnail URI')
        story={'page_id':order['page'],'instagram_user_id':order['ig'],'video_data':{'video_id':video_id,'image_url':thumbnail,'message':ad['message'],'title':ad['title'],'call_to_action':{'type':'LEARN_MORE','value':{'link':ad['link']}}}}
        creative_id=create('creative','/act_'+cfg['account_id']+'/adcreatives',{'name':ad['name'],'object_story_spec':story})
        creative=transport.request('GET','/'+creative_id+'?fields=id,account_id',None)
        if creative.get('id')!=creative_id or creative.get('account_id')!=cfg['account_id']:
            raise ValueError('created creative account mismatch')
        ad_id=create('ad','/act_'+cfg['account_id']+'/ads',{'name':ad['name'],'adset_id':action['target'],'creative':{'creative_id':creative_id},'status':'ACTIVE'})
        observed=transport.request('GET','/'+ad_id+'?fields=id,account_id,adset_id,creative,status,effective_status',None)
        if observed.get('id')!=ad_id or observed.get('account_id')!=cfg['account_id'] or observed.get('adset_id')!=action['target'] or observed.get('creative',{}).get('id')!=creative_id:
            raise ValueError('final ad identity readback mismatch')
        authorize(job,config,store,approval_id)
        if observed.get('status')!='ACTIVE' or observed.get('effective_status')!='ACTIVE':
            return {'status':'configured_only','simulated':transport.simulated,'ad_id':ad_id,'observed':observed}
        result={'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision'],'status':'simulated_delivery' if transport.simulated else 'delivering','simulated':transport.simulated,'ad_id':ad_id,'ad_ids':[ad_id],'video_id':video_id,'creative_id':creative_id,'receipt_id':C.manifest_hash(job)+':ad','artifact_id':artifact['id'],'artifact_sha256':artifact['sha256'],'approval_ref':approval_id,'manifest_hash':C.manifest_hash(job),'observed':observed,'outputs':[artifact],'executed_at':datetime.now(timezone.utc).isoformat()}
        if store.resumable(job,stage):
            with store.connect() as db:
                old=db.execute('SELECT evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(job['brand'],job['job_id'],job['mode'],job['revision'],stage)).fetchone()
            return json.loads(old[0])
        if not store.resumable(job,stage):store.checkpoint(job,holder,stage,'complete',result)
        return result
    finally:
        store.release(job['brand'],job['job_id'],job['mode'],holder)


def measurement(job, config, store, approval_id, delivery, period, meta, shopify, *, now=None):
    """Map raw Meta insights + Shopify orders; refuse missing/incomplete pagination.

    Shopify order note_attributes uses the explicit brand attribution key. No guessing
    by campaign name or equating Meta modeled conversions with observed orders.
    """
    domain(job,meta,shopify)
    cfg = delivery_record(job, config, store, approval_id, delivery)
    trusted_transport(meta, 'meta', cfg['account_id'])
    shop = cfg.get('measurement', {}).get('shop_id')
    attribution = cfg.get('measurement', {}).get('attribution_attribute')
    trusted_transport(shopify, 'shopify', shop)
    if cfg.get('metrics_source') != 'shopify' or not shop or not attribution or cfg.get('measurement',{}).get('revenue_policy') != 'total_less_successful_refunds':
        raise ValueError('configured Shopify source/shop required')
    for key in ('brand','job_id','revision','manifest_hash','approval_ref'):
        expected = C.manifest_hash(job) if key == 'manifest_hash' else approval_id if key == 'approval_ref' else job[key]
        if delivery.get(key) != expected:
            raise ValueError('delivery/measurement lineage mismatch')
    if not isinstance(period,list) or len(period)!=2:
        raise ValueError('exact period required')
    start,end = (date.fromisoformat(p) for p in period)
    if end - start != timedelta(days=6):
        raise ValueError('exact seven-day measurement required')
    jst=timezone(timedelta(hours=9))
    delivered_day=datetime.fromisoformat(delivery['executed_at']).astimezone(jst).date()
    today=datetime.fromtimestamp(time.time() if now is None else now,jst).date()
    if start<delivered_day or end>=today:
        raise ValueError('measurement must be after delivery and a completed period')
    identity = shopify.request('GET','/admin/api/2026-07/shop.json',None)
    if str(identity.get('shop',{}).get('id')) != shop or identity.get('shop',{}).get('iana_timezone')!='Asia/Tokyo':
        raise ValueError('Shopify shop identity mismatch')
    account=meta.request('GET','/act_'+cfg['account_id']+'?fields=account_id,currency,timezone_name',None)
    if account.get('account_id')!=cfg['account_id'] or account.get('currency')!=cfg.get('measurement',{}).get('currency') or account.get('timezone_name')!='Asia/Tokyo':
        raise ValueError('Meta reporting currency/timezone/account mismatch')
    ad_id = delivery['ad_id']
    raw_meta = meta.request('GET','/' + ad_id + '/insights', {'fields':'ad_id,account_id,date_start,date_stop,spend,impressions,clicks','time_range':{'since':period[0],'until':period[1]}})
    orders_response = shopify.request('GET','/admin/api/2026-07/orders.json', {'status':'any','created_at_min':period[0]+'T00:00:00+09:00','created_at_max':(end+timedelta(days=1)).isoformat()+'T00:00:00+09:00','limit':250})
    headers=orders_response.get('_headers')
    if not isinstance(headers,dict) or 'rel="next"' in headers.get('link','') or raw_meta.get('paging',{}).get('next') or not isinstance(raw_meta.get('data'),list) or not isinstance(orders_response.get('orders'),list):
        raise ValueError('missing/truncated measurement page; never infer zero')
    rows = raw_meta['data']
    if len(rows) != 1 or rows[0].get('ad_id') != ad_id or rows[0].get('account_id') != cfg['account_id'] or [rows[0].get('date_start'),rows[0].get('date_stop')] != period:
        raise ValueError('Meta ad/account/period mismatch or no observed target')
    spend = float(rows[0]['spend'])
    if not finite(spend):
        raise ValueError('invalid spend')
    currencies = set()
    attributed = []
    unattributed = []
    seen = set()
    for order in orders_response['orders']:
        oid = str(order['id'])
        if oid in seen:
            raise ValueError('duplicate Shopify order')
        seen.add(oid)
        created = C.parse_time(order['created_at'])
        lower = C.parse_time(period[0]+'T00:00:00+09:00')
        upper = C.parse_time((end+timedelta(days=1)).isoformat()+'T00:00:00+09:00')
        if not lower <= created < upper:
            raise ValueError('Shopify order outside exact period')
        if order.get('cancelled_at') or order.get('financial_status') not in {'paid','partially_refunded','refunded'}:
            continue
        currencies.add(order['currency'])
        transactions=[tx for refund in order.get('refunds',[]) for tx in refund.get('transactions',[]) if tx.get('kind')=='refund' and tx.get('status')=='success']
        if len({tx.get('id') for tx in transactions})!=len(transactions) or any(not tx.get('id') or tx.get('currency')!=order['currency'] for tx in transactions):raise ValueError('refund identity/currency mismatch')
        amounts=[float(tx['amount']) for tx in transactions]
        if any(not finite(amount) for amount in amounts):raise ValueError('invalid refund amount')
        refunds=sum(amounts)
        value = float(order['total_price']) - refunds
        if not finite(value):
            raise ValueError('invalid observed order revenue')
        attr = [a.get('value') for a in order.get('note_attributes',[]) if a.get('name') == attribution]
        if len(attr)>1:
            raise ValueError('ambiguous attribution')
        (attributed if attr == [ad_id] else unattributed).append(value)
    if currencies and currencies != {cfg.get('measurement',{}).get('currency')}:
        raise ValueError('measurement currency mismatch')
    artifact = next(a for a in job['artifacts'] if a['id'] == delivery['artifact_id'])
    if artifact['sha256'] != delivery['artifact_sha256']:
        raise ValueError('measurement artifact revision mismatch')
    result = {'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision'],'account_id':cfg['account_id'],'source':'shopify','period':period,'period_start':period[0]+'T00:00:00+09:00','period_end':(end+timedelta(days=1)).isoformat()+'T00:00:00+09:00','ad_ids':[ad_id],'orders_observed':True,'meta_observed':True,'orders':len(attributed),'revenue':sum(attributed),'spend':spend,'unattributed_orders':len(unattributed),'unattributed_revenue':sum(unattributed),'artifact_id':artifact['id'],'artifact_sha256':artifact['sha256'],'approval_ref':approval_id,'manifest_hash':C.manifest_hash(job),'simulated':meta.simulated or shopify.simulated}
    holder=uuid.uuid4().hex
    store.acquire(job['brand'],job['job_id'],job['mode'],holder)
    try:
        path=output_path(job,cfg,'metrics-'+period[1]+'.json')
        data=C.canonical(result).encode()
        if path.exists() and path.read_bytes()!=data:raise ValueError('immutable measured record differs')
        if not path.exists():atomic(path,data)
        stage=domain(job)+'measurement-'+period[1]
        if not store.resumable(job,stage):store.checkpoint(job,holder,stage,'complete',{'brand':job['brand'],'revision':job['revision'],'outputs':[{'path':str(path),'sha256':sha(path)}],'metrics':result,'delivery_receipt':delivery['receipt_id']})
        return result
    finally:store.release(job['brand'],job['job_id'],job['mode'],holder)


def learn(job, config, store, approval_id, delivery, metrics, weekly):
    """Use the existing weekly decision function. Produce proposal, never auto increase."""
    cfg = delivery_record(job, config, store, approval_id, delivery)
    stage=domain(job)+'measurement-'+metrics['period'][1]
    with store.connect() as db:
        row=db.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(job['brand'],job['job_id'],job['mode'],job['revision'],stage)).fetchone()
    if not row or row[0]!='complete' or not store.resumable(job,stage) or json.loads(row[1]).get('metrics')!=metrics:
        raise ValueError('trusted immutable measured record required')
    for key in ('brand','job_id','revision','manifest_hash','approval_ref','artifact_sha256','ad_ids'):
        if metrics.get(key) != delivery.get(key):
            raise ValueError('experiment lineage mismatch')
    if metrics.get('orders_observed') is not True or metrics.get('meta_observed') is not True:
        raise ValueError('observed metrics required')
    thresholds = cfg.get('thresholds', {})
    retreat, rollout = weekly.運用線(job['brand'], thresholds.get('retreat_roas'), thresholds.get('rollout_roas'))
    angles = job.get('order',{}).get('A/H','').split('/')
    if len(angles)!=2 or not re.fullmatch('A[0-9]{2}',angles[0]) or not re.fullmatch('H[0-9]{2}',angles[1]):
        raise ValueError('explicit experiment A/H required')
    row = {'費用':metrics['spend'],'注文':metrics['orders'],'売上':metrics['revenue'],'ROAS':metrics['revenue']/metrics['spend'] if metrics['spend'] else None}
    period = '〜'.join(metrics['period'])
    rows, _ = weekly.行を作る(period, {'A別':[dict(row,番号=angles[0])], 'H別':[dict(row,番号=angles[1])]}, retreat, rollout)
    # Select an existing permitted next step, without introducing policy or live action.
    for item in rows:
        item['次の手'] = {'勝ち':'続ける','線の間':'続ける','負け':'H を変える','足りない':'続ける'}[item['判定']]
    next_item = {'status':'draft','brand':job['brand'],'parent_job_id':job['job_id'],'parent_revision':job['revision'],'parent_manifest_hash':C.manifest_hash(job),'parent_approval_ref':approval_id,'ad_ids':metrics['ad_ids'],'period':metrics['period'],'A/H':job['order']['A/H'],'decisions':rows,'requires_new_review_and_owner_approval':True,'simulated':metrics['simulated']}
    # delivery_record already requires this exact registered historical revision.
    # Registering it again would incorrectly apply current write expiry to learning.
    holder=uuid.uuid4().hex
    store.acquire(job['brand'],job['job_id'],job['mode'],holder)
    try:
        path=output_path(job,cfg,'learning-'+metrics['period'][1]+'.json')
        data=C.canonical(next_item).encode()
        if path.exists() and path.read_bytes()!=data:
            raise ValueError('existing learning record differs')
        if not path.exists(): atomic(path,data)
        stage='mock-learning-'+metrics['period'][1] if metrics['simulated'] else 'learning-'+metrics['period'][1]
        if not store.resumable(job,stage):
            store.append_lineage(job,holder,'metrics',metrics)
            store.checkpoint(job,holder,stage,'complete',{'brand':job['brand'],'revision':job['revision'],'outputs':[{'path':str(path),'sha256':sha(path)}],'next_item':next_item})
        return {'status':'simulated_learning' if metrics['simulated'] else 'learning_proposal','next_item':next_item,'path':str(path),'sha256':sha(path)}
    finally:
        store.release(job['brand'],job['job_id'],job['mode'],holder)
