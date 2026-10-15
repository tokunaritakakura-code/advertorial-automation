#!/usr/bin/env python3
"""Offline EC v1 contract. Validation never creates approval or performs network I/O."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
CONTROL_DB = Path(__file__).resolve().parents[1] / 'data' / 'control.sqlite3'
CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config' / 'brands.json'
MODES = {'dry-run', 'live'}
OPERATIONS = {'create_ad', 'activate', 'pause', 'set_budget', 'publish', 'generate_local', 'validate_local', 'verify_artifact'}
TOKEN = re.compile(r'^[A-Za-z0-9_\-\u3000-\u9fff]{1,100}$')

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def manifest_hash(job):
    return hashlib.sha256(canonical(job).encode()).hexdigest()

def parse_time(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return d.timestamp()

def load_config(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def validate_job(job, config, approval=None, now=None, verify_files=True, trusted_review=None):
    """approval must be supplied by trusted owner-event storage, NEVER from job/agent text.
    This function checks authorization scope; caller authenticates the owner's identity.
    A missing/unknown brand always rejects; dry-run can never authorize a live write.
    """
    errors = []
    missing = []
    def bad(condition, message):
        if not condition:
            errors.append(message)
    if not isinstance(job, dict) or not isinstance(config, dict):
        return {'schema_version': VERSION, 'status': 'rejected', 'errors': ['job/config must be objects']}
    brand = job.get('brand')
    cfg = config.get('brands', {}).get(brand) if isinstance(brand, str) else None
    bad(cfg is not None, 'explicit registered brand required')
    bad(config.get('schema_version') == VERSION and job.get('schema_version') == VERSION, 'unsupported schema_version')
    bad(isinstance(job.get('job_id'), str) and bool(TOKEN.fullmatch(job['job_id'])), 'invalid job_id')
    bad(job.get('mode') in MODES, 'explicit dry-run/live mode required')
    if job.get('mode') == 'live':
        try:
            bad(parse_time(job['expires_at']) > (time.time() if now is None else now), 'job expired')
        except (ValueError, KeyError, TypeError, AttributeError):
            errors.append('live job expires_at required')
    if job.get('scheduled_at') is not None:
        try:
            scheduled=parse_time(job['scheduled_at'])
            if job.get('mode')=='live': bad(scheduled<parse_time(job['expires_at']),'scheduled_at must precede job expiry')
        except (ValueError, KeyError, TypeError, AttributeError):
            errors.append('scheduled_at requires timezone and valid job expiry')
    bad(type(job.get('revision')) is int and job['revision'] > 0, 'positive integer revision required')
    if not cfg:
        return {'schema_version': VERSION, 'status': 'rejected', 'errors': errors}
    bad(isinstance(cfg.get('owners'),list) and bool(cfg['owners']) and all(isinstance(x,str) and x for x in cfg['owners']), 'brand owners required')
    bad(isinstance(cfg.get('asset_roots'),list) and bool(cfg['asset_roots']) and all(isinstance(x,str) and Path(x).is_absolute() for x in cfg['asset_roots']), 'absolute brand asset roots required')
    # 工程1・2のリサーチ（まだブランドも広告口座も無い商品）は口座が空で正しい。読むだけの枠で、案件側も空の時だけ通す（2026-10-05）
    no_account = cfg.get('read_only') is True and not cfg.get('account_id') and not job.get('account_id')
    bad(no_account or (bool(cfg.get('account_id')) and job.get('account_id') == cfg.get('account_id')), 'brand/account mismatch')
    artifacts = job.get('artifacts')
    bad(isinstance(artifacts, list) and len(artifacts) > 0, 'nonempty artifacts required')
    seen_artifacts = set()
    for artifact in artifacts if isinstance(artifacts, list) else []:
        if not isinstance(artifact, dict):
            errors.append('artifact must be object'); continue
        aid = artifact.get('id')
        bad(isinstance(aid, str) and aid not in seen_artifacts, 'unique artifact id required')
        if isinstance(aid, str): seen_artifacts.add(aid)
        bad(type(artifact.get('revision')) is int and artifact['revision'] > 0, 'artifact revision required')
        sha = artifact.get('sha256')
        bad(isinstance(sha, str) and bool(re.fullmatch('[0-9a-f]{64}', sha)), 'artifact sha256 required')
        p = artifact.get('path')
        if not isinstance(p, str):
            errors.append('artifact path required'); continue
        path = Path(p).resolve()
        roots = [Path(r).resolve() for r in cfg.get('asset_roots', [])]
        bad(any(path.is_relative_to(root) for root in roots), 'artifact outside brand asset roots')
        if verify_files:
            if not path.is_file():
                errors.append('artifact missing')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                errors.append('artifact content/revision mismatch')
    actions = job.get('actions')
    bad(isinstance(actions, list) and len(actions) > 0, 'nonempty actions required')
    ids = set()
    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, dict):
            errors.append('action must be object'); continue
        aid = action.get('id')
        bad(isinstance(aid, str) and bool(TOKEN.fullmatch(aid)) and aid not in ids, 'unique valid action id required')
        if isinstance(aid, str): ids.add(aid)
        bad(action.get('operation') in OPERATIONS, 'unsupported action operation')
        bad(isinstance(action.get('payload'), dict) and bool(action['payload']), 'nonempty typed action payload required')
        bad(action.get('account_id') == cfg.get('account_id'), 'action account mismatch')
        bad(isinstance(action.get('target'), str) and bool(action['target']), 'action target required')
        deps = action.get('depends_on')
        bad(isinstance(deps, list) and all(isinstance(d, str) and d in ids and d != aid for d in deps), 'dependencies must reference prior actions')
        if action.get('operation') in {'generate_local','validate_local','verify_artifact'}:
            target = Path(action.get('target') or '').resolve()
            bad(any(target.is_relative_to(Path(r).resolve()) for r in cfg.get('asset_roots', [])), 'local target outside brand asset roots')
        if action.get('operation') == 'set_budget':
            bad(type(action.get('amount')) in (int, float) and 0 < action['amount'] <= cfg.get('max_daily_budget', 0), 'budget exceeds brand ceiling or is missing')
        if action.get('operation') == 'create_ad':
            bad(action.get('artifact_id') in seen_artifacts, 'create_ad must bind artifact')
        payload=action.get('payload') if isinstance(action.get('payload'),dict) else {}
        step=payload.get('step')
        if action.get('operation') in {'activate','pause','set_budget'}: bad(isinstance(step,dict),'typed execution step required')
        if action.get('operation')=='create_ad': bad(isinstance(step,dict) or isinstance(payload.get('order'),dict),'typed create_ad step/order required')
        if isinstance(step,dict):
            op={'足す':'create_ad','動かす':'activate','止める':'pause','予算':'set_budget','最低消化':'set_budget','最低消化額':'set_budget'}.get(step.get('する'))
            bad(op==action.get('operation'), 'operation/step mismatch')
            target=step.get('id') if action.get('operation')!='create_ad' else (step.get('セット') or step.get('id'))
            bad(str(target)==action.get('target'), 'target/step mismatch')
            if action.get('operation')=='set_budget': bad(step.get('額')==action.get('amount'),'budget/step amount mismatch')
        order=payload.get('order')
        if isinstance(order,dict):
            bad(action.get('operation')=='create_ad','order requires create_ad operation')
            bad(str(order.get('act'))==cfg.get('account_id') and order.get('口座')==brand,'order brand/account mismatch')
            bypath={str(Path(a['path']).resolve()):a for a in artifacts if isinstance(a,dict) and isinstance(a.get('path'),str)} if isinstance(artifacts,list) else {}
            ads=order.get('ads')
            bad(isinstance(ads,list) and bool(ads),'order ads required')
            for ad in ads if isinstance(ads,list) else []:
                bad(isinstance(ad,dict),'order ad must be object')
                if isinstance(ad,dict) and ad.get('file'): bad(str(Path(ad['file']).resolve()) in bypath,'order file not bound to artifact')
    evidence = job.get('evidence')
    if not isinstance(evidence, dict):
        missing.append('evidence required')
    else:
        bad(evidence.get('brand') == brand and evidence.get('revision') == job.get('revision'), 'evidence brand/version mismatch')
        if evidence.get('status') != 'executable': missing.append('evidence not executable')
        else:
            checks=evidence.get('checks')
            if not isinstance(checks,list) or not checks or not all(isinstance(c,dict) and c.get('name') and c.get('status')=='pass' for c in checks):
                missing.append('substantive passed checks required')
            reviewer=evidence.get('reviewer')
            hashes=[a.get('sha256') for a in artifacts if isinstance(a,dict)] if isinstance(artifacts,list) else []
            if not isinstance(reviewer,dict) or reviewer.get('status')!='pass' or not isinstance(reviewer.get('context'),str) or not reviewer['context'].startswith(f'{brand}/{job.get("job_id")}/{job.get("revision")}/review/') or sorted(reviewer.get('artifact_hashes',[]))!=sorted(hashes):
                missing.append('fresh reviewer PASS bound to all artifact hashes required')
        bad(evidence.get('status') in {'valid_structure', 'insufficient_evidence', 'executable'}, 'unknown evidence status')
    try:
        digest = manifest_hash(job)
    except (ValueError, TypeError):
        errors.append('manifest must be finite JSON'); digest = None
    if job.get('mode') == 'live':
        reviewer=job.get('evidence',{}).get('reviewer',{}) if isinstance(job.get('evidence'),dict) else {}
        if not isinstance(trusted_review,dict):
            missing.append('trusted independent review receipt required')
        else:
            expected={'brand':brand,'job_id':job.get('job_id'),'revision':job.get('revision'),'context':reviewer.get('context'),'rules_hash':reviewer.get('rules_hash'),'review_id':reviewer.get('review_id'),'decision':'PASS'}
            for key,value in expected.items(): bad(trusted_review.get(key)==value,'trusted review '+key+' mismatch')
            bad(sorted(trusted_review.get('artifact_hashes',[]))==sorted(a.get('sha256') for a in artifacts if isinstance(a,dict)),'trusted review artifact hashes mismatch')
        if not isinstance(approval, dict):
            missing.append('trusted exact owner approval required')
        else:
            bad(approval.get('decision') == 'approve', 'explicit approve decision required')
            for key in ('brand', 'job_id', 'revision'):
                bad(approval.get(key) == job.get(key), 'approval '+key+' mismatch')
            bad(approval.get('manifest_hash') == digest, 'approval manifest hash mismatch')
            bad(approval.get('owner') in cfg.get('owners', []), 'unregistered approving owner')
            try:
                moment = time.time() if now is None else now
                start, end = parse_time(approval['approved_at']), parse_time(approval['expires_at'])
                bad(start <= moment < end and end-start <= cfg.get('approval_max_seconds', 86400), 'approval expired/future/invalid lifetime')
                bad(parse_time(job['expires_at'])<=end,'job execution window exceeds approval expiry')
                if job.get('scheduled_at') is not None: bad(parse_time(job['scheduled_at'])<end,'scheduled_at exceeds approval expiry')
            except (ValueError, KeyError, TypeError, AttributeError):
                errors.append('approval timestamps invalid')
    status = 'rejected' if errors else ('insufficient_evidence' if missing else ('valid_structure' if job.get('mode') == 'dry-run' else 'executable'))
    return {'schema_version': VERSION, 'status': status, 'brand': brand, 'job_id': job.get('job_id'), 'manifest_hash': digest, 'errors': errors, 'missing': missing, 'authorization_expires_at': approval.get('expires_at') if isinstance(approval,dict) else None}

def reviewer_context(brand, job_id, revision):
    """Every invocation is fresh. Caller must NOT resume prior reviewer session."""
    if not all(isinstance(s, str) and TOKEN.fullmatch(s) for s in (brand, job_id)) or type(revision) is not int or revision < 1:
        raise ValueError('invalid reviewer scope')
    return f'{brand}/{job_id}/{revision}/review/{uuid.uuid4().hex}'

class StateStore:
    """Atomic stage commits + leases. Only use a private application DB, no live APIs."""
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (brand TEXT, job TEXT, mode TEXT, revision INTEGER, hash TEXT NOT NULL, manifest TEXT NOT NULL, PRIMARY KEY(brand,job,mode,revision));
            CREATE TABLE IF NOT EXISTS scopes (brand TEXT, job TEXT, mode TEXT, revision INTEGER, roots TEXT, metric_source TEXT, PRIMARY KEY(brand,job,mode,revision));
            CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, brand TEXT, job TEXT, revision INTEGER, context TEXT, hashes TEXT, run_id TEXT UNIQUE, rules_hash TEXT, decision TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, brand TEXT, job TEXT, mode TEXT, revision INTEGER, hash TEXT, envelope TEXT);
            CREATE TABLE IF NOT EXISTS leases (brand TEXT, job TEXT, mode TEXT, holder TEXT, expires REAL, PRIMARY KEY(brand,job,mode));
            CREATE TABLE IF NOT EXISTS stages (brand TEXT, job TEXT, mode TEXT, revision INTEGER, stage TEXT, status TEXT, evidence TEXT, PRIMARY KEY(brand,job,mode,revision,stage));
            CREATE TABLE IF NOT EXISTS lineage (id INTEGER PRIMARY KEY, brand TEXT, job TEXT, mode TEXT, revision INTEGER, kind TEXT, payload TEXT, created REAL);
            ''')
    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.execute('PRAGMA busy_timeout=15000')
        try:
            with c:
                yield c
        finally:
            c.close()
    def register(self, job, config):
        result = validate_job(job, config)
        if result['errors']: raise ValueError('; '.join(result['errors']))
        key = (job['brand'],job['job_id'],job['mode'],job['revision'])
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT hash FROM jobs WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()
            if old and old[0] != result['manifest_hash']: raise ValueError('immutable revision changed')
            c.execute('INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?)', (*key,result['manifest_hash'],canonical(job)))
            c.execute('INSERT OR IGNORE INTO scopes VALUES (?,?,?,?,?,?)',(*key,canonical(config['brands'][job['brand']]['asset_roots']),config['brands'][job['brand']].get('metrics_source')))
        return result['manifest_hash']
    def record_review(self, scope, artifact_hashes, run_id, rules_hash, decision):
        """Trusted fresh SDK review callback ONLY, never an agent tool or public API."""
        brand,job,revision,context=(scope.get(k) for k in ('brand','job_id','revision','context'))
        if not all(isinstance(x,str) and TOKEN.fullmatch(x) for x in (brand,job)) or type(revision) is not int or revision<1:
            raise ValueError('review scope invalid')
        if not isinstance(context,str) or not context.startswith(f'{brand}/{job}/{revision}/review/') or not context.split('/')[-1]: raise ValueError('fresh review context required')
        if not isinstance(artifact_hashes,list) or not artifact_hashes or not all(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for h in artifact_hashes): raise ValueError('review artifact hashes required')
        if not isinstance(rules_hash,str) or not re.fullmatch('[0-9a-f]{64}',rules_hash) or not isinstance(run_id,str) or not run_id or decision not in {'PASS','FAIL'}: raise ValueError('review run/rules/decision invalid')
        review_id=uuid.uuid4().hex
        with self.connect() as c:
            c.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?)',(review_id,brand,job,revision,context,canonical(sorted(artifact_hashes)),run_id,rules_hash,decision,time.time()))
        return {'schema_version':VERSION,'review_id':review_id,'brand':brand,'job_id':job,'revision':revision,'decision':decision}
    def read_review(self, review_id, job):
        if not isinstance(review_id,str) or not re.fullmatch('[0-9a-f]{32}',review_id): raise ValueError('trusted review receipt required')
        with self.connect() as c:
            row=c.execute('SELECT brand,job,revision,context,hashes,run_id,rules_hash,decision FROM reviews WHERE id=?',(review_id,)).fetchone()
        reviewer=job.get('evidence',{}).get('reviewer',{})
        hashes=sorted(a['sha256'] for a in job.get('artifacts',[]))
        if not row or tuple(row[:3])!=(job.get('brand'),job.get('job_id'),job.get('revision')) or row[3]!=reviewer.get('context') or json.loads(row[4])!=hashes or row[6]!=reviewer.get('rules_hash'):
            raise ValueError('review receipt scope/artifacts/rules mismatch')
        return {'review_id':review_id,'brand':row[0],'job_id':row[1],'revision':row[2],'context':row[3],'artifact_hashes':json.loads(row[4]),'run_id':row[5],'rules_hash':row[6],'decision':row[7]}
    def approve(self, job, config, owner, expires_at):
        """TRUSTED OWNER UI ONLY; never expose this capability to agents."""
        review=self.read_review(job.get('evidence',{}).get('reviewer',{}).get('review_id'),job)
        result=validate_job(job,config,trusted_review=review)
        if result['errors'] or result.get('missing') != ['trusted exact owner approval required']:
            raise ValueError('only otherwise-executable live manifest can be approved')
        now=datetime.now(timezone.utc)
        approval={'decision':'approve','owner':owner,'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision'],'manifest_hash':manifest_hash(job),'approved_at':now.isoformat(),'expires_at':expires_at}
        verified=validate_job(job,config,approval,trusted_review=review)
        if verified['status']!='executable': raise ValueError('invalid approval: '+canonical(verified))
        approval_id=uuid.uuid4().hex
        self.register(job,config)
        with self.connect() as c:
            c.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,?)',(approval_id,job['brand'],job['job_id'],job['mode'],job['revision'],manifest_hash(job),canonical(approval)))
        return {'schema_version':VERSION,'approval_id':approval_id,'manifest_hash':manifest_hash(job),'brand':job['brand'],'job_id':job['job_id'],'revision':job['revision']}
    def read_approval(self, approval_id, job):
        if not isinstance(approval_id,str) or not re.fullmatch('[0-9a-f]{32}',approval_id): raise ValueError('invalid approval receipt')
        with self.connect() as c:
            row=c.execute('SELECT brand,job,mode,revision,hash,envelope FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if not row or tuple(row[:5])!=(job.get('brand'),job.get('job_id'),job.get('mode'),job.get('revision'),manifest_hash(job)):
            raise ValueError('approval receipt scope/hash mismatch')
        approval=json.loads(row[5])
        if not parse_time(approval['approved_at']) <= time.time() < parse_time(approval['expires_at']): raise ValueError('approval receipt expired')
        return approval
    def acquire(self, brand, job, mode, holder, ttl=300, now=None):
        if mode not in MODES or not holder or ttl <= 0 or ttl > 3600: raise ValueError('invalid lease')
        moment = time.time() if now is None else now
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM jobs WHERE brand=? AND job=? AND mode=?',(brand,job,mode)).fetchone(): raise ValueError('unknown job scope')
            old = c.execute('SELECT holder,expires FROM leases WHERE brand=? AND job=? AND mode=?',(brand,job,mode)).fetchone()
            if old and old[1] > moment and old[0] != holder: raise RuntimeError('job leased by another worker')
            c.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?,?,?)',(brand,job,mode,holder,moment+ttl))
    def _scope(self, c, job, holder):
        key = (job['brand'],job['job_id'],job['mode'],job['revision'])
        stored = c.execute('SELECT hash FROM jobs WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()
        if not stored or stored[0] != manifest_hash(job): raise ValueError('unregistered/changed manifest')
        lease = c.execute('SELECT holder,expires FROM leases WHERE brand=? AND job=? AND mode=?',key[:3]).fetchone()
        if not lease or lease[0] != holder or lease[1] <= time.time(): raise RuntimeError('current lease required')
        return key
    def checkpoint(self, job, holder, stage, status, evidence, dependencies=()):
        if status not in {'complete','failed','insufficient_evidence'}: raise ValueError('invalid stage state')
        if not isinstance(stage,str) or not TOKEN.fullmatch(stage) or not isinstance(evidence,dict) or not evidence: raise ValueError('stage/evidence required')
        if evidence.get('brand') != job['brand'] or evidence.get('revision') != job['revision']: raise ValueError('checkpoint evidence scope mismatch')
        if stage == 'delivery' and status == 'complete':
            if job['mode'] != 'live' or not evidence.get('receipt_id'): raise ValueError('live delivery receipt required')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            key = self._scope(c,job,holder)
            roots=json.loads(c.execute('SELECT roots FROM scopes WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()[0])
            outputs=evidence.get('outputs',[])
            if not isinstance(outputs,list): raise ValueError('outputs must be list')
            for output in outputs:
                if not isinstance(output,dict) or not isinstance(output.get('path'),str): raise ValueError('output path/hash required')
                p=Path(output['path']).resolve()
                if not any(p.is_relative_to(Path(r).resolve()) for r in roots) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=output.get('sha256'): raise ValueError('output missing/changed/outside brand root')
            for dependency in dependencies:
                row=c.execute('SELECT status FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(*key,dependency)).fetchone()
                if not row or row[0] != 'complete': raise ValueError('dependency incomplete: '+dependency)
            old=c.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(*key,stage)).fetchone()
            if old and old[0]=='complete' and (status!='complete' or old[1]!=canonical(evidence)): raise ValueError('completed checkpoint immutable')
            c.execute('INSERT OR REPLACE INTO stages VALUES (?,?,?,?,?,?,?)',(*key,stage,status,canonical(evidence)))
            if not old or old[0]!='complete': c.execute('INSERT INTO lineage (brand,job,mode,revision,kind,payload,created) VALUES (?,?,?,?,?,?,?)',(*key,'stage:'+stage,canonical({'status':status,'evidence':evidence}),time.time()))
    def resumable(self, job, stage):
        key=(job['brand'],job['job_id'],job['mode'],job['revision'])
        with self.connect() as c:
            old=c.execute('SELECT hash,manifest FROM jobs WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()
            row=c.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(*key,stage)).fetchone()
            if not (old and old[0]==manifest_hash(job) and row and row[0]=='complete'): return False
            roots=json.loads(c.execute('SELECT roots FROM scopes WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()[0])
            inputs=json.loads(old[1]).get('artifacts',[])
            outputs=json.loads(row[1]).get('outputs',[])
            for artifact in inputs+outputs:
                path=Path(artifact.get('path','')).resolve()
                if not any(path.is_relative_to(Path(r).resolve()) for r in roots): return False
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=artifact.get('sha256'): return False
            return True
    def append_lineage(self, job, holder, kind, payload):
        if not isinstance(payload,dict) or payload.get('brand')!=job['brand'] or payload.get('revision')!=job['revision']: raise ValueError('lineage scope mismatch')
        if kind=='metrics':
            start,end=parse_time(payload['period_start']),parse_time(payload['period_end'])
            if start>=end or not payload.get('ad_ids') or not payload.get('source'): raise ValueError('metric period/ad/source required')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE'); key=self._scope(c,job,holder)
            if kind=='metrics':
                expected=c.execute('SELECT metric_source FROM scopes WHERE brand=? AND job=? AND mode=? AND revision=?',key).fetchone()[0]
                if expected and payload.get('source')!=expected: raise ValueError('brand metric source mismatch')
            c.execute('INSERT INTO lineage (brand,job,mode,revision,kind,payload,created) VALUES (?,?,?,?,?,?,?)',(*key,kind,canonical(payload),time.time()))
    def release(self, brand, job, mode, holder):
        with self.connect() as c: c.execute('DELETE FROM leases WHERE brand=? AND job=? AND mode=? AND holder=?',(brand,job,mode,holder))

def independent_periods(periods):
    intervals=sorted((parse_time(p['start']),parse_time(p['end'])) for p in periods)
    return bool(intervals) and all(s<e for s,e in intervals) and all(intervals[i-1][1]<=intervals[i][0] for i in range(1,len(intervals)))

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['validate','hash','reviewer-context','trusted-owner-approve','read-approval','trusted-review-record']); args=p.parse_args()
    data=json.load(sys.stdin)
    if args.command=='hash': result={'schema_version':VERSION,'manifest_hash':manifest_hash(data['job'])}
    elif args.command=='reviewer-context': result={'schema_version':VERSION,'context':reviewer_context(data['brand'],data['job_id'],data['revision'])}
    elif args.command=='trusted-review-record':
        scope=data.get('scope') or {k:data.get(k) for k in ('brand','job_id','revision','context')}
        result=StateStore(CONTROL_DB).record_review(scope,data['artifact_hashes'],data['run_id'],data['rules_hash'],data['decision'])
    elif args.command=='trusted-owner-approve':
        result=StateStore(CONTROL_DB).approve(data['job'],load_config(CONFIG_PATH),data['owner'],data['expires_at'])
    elif args.command=='read-approval':
        if not CONTROL_DB.is_file(): raise ValueError('trusted approval store missing')
        result={'schema_version':VERSION,'approval':StateStore(CONTROL_DB).read_approval(data['approval_id'],data['job'])}
    else:
        if 'approval' in data or 'state_path' in data or 'state_db' in data:
            raise ValueError('inline approval/custom approval store forbidden')
        approval=None
        if data.get('approval_id'):
            if not CONTROL_DB.is_file(): raise ValueError('trusted approval store missing')
            approval=StateStore(CONTROL_DB).read_approval(data['approval_id'],data['job'])
        config_path=CONFIG_PATH if data['job'].get('mode')=='live' else data.get('config_path',CONFIG_PATH)
        if data['job'].get('mode')=='live' and data.get('config_path') and Path(data['config_path']).resolve()!=CONFIG_PATH:
            raise ValueError('live config override forbidden')
        review=None
        review_id=data['job'].get('evidence',{}).get('reviewer',{}).get('review_id')
        if data['job'].get('mode')=='live' and review_id:
            if not CONTROL_DB.is_file(): raise ValueError('trusted review store missing')
            review=StateStore(CONTROL_DB).read_review(review_id,data['job'])
        result=validate_job(data['job'],load_config(config_path),approval,trusted_review=review)
    print(canonical(result))
    if result.get('status') in {'rejected','insufficient_evidence'}: return 2
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,KeyError,TypeError,OSError,AttributeError,sqlite3.Error) as e:
        print(canonical({'schema_version':VERSION,'status':'rejected','errors':[str(e)]})); sys.exit(2)
