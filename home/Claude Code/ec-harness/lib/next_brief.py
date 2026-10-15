"""Evidence-bound local planning outbox. Never grants execution or spends money."""
import hashlib,json,os,re,sqlite3,tempfile,time
from contextlib import contextmanager,closing
from datetime import datetime,timezone
from pathlib import Path
import ec_contract as C

BODY_FIELDS={'ブランド','狙う数字','A と H','参考','本数と種類','着地','締切','使ってよい費用'}
RECORD_FIELDS={'brand','job_id','revision','brief_path','brief_sha256','parent_job_id','parent_revision','parent_manifest_hash','parent_approval_ref','source_job_mode','metrics_path','metrics_sha256','metrics_period','metrics_ad_ids','learning_path','learning_sha256','execution_domain','dispatch_expires_at'}

class ReadStore(C.StateStore):
    def __init__(self,path):self.path=str(path)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(Path(self.path).resolve().as_uri()+'?mode=ro',uri=True)
        try:yield db
        finally:db.close()

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def iso(moment):return datetime.fromtimestamp(moment,timezone.utc).isoformat()
def scoped(cfg,job_id,revision,name):
    if not isinstance(job_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',job_id) or type(revision) is not int or revision<1:raise ValueError('typed next brief scope required')
    root=Path(cfg['workspace_root']).resolve();dest=(root/job_id/('r'+str(revision))/name).resolve()
    if not any(root.is_relative_to(Path(r).resolve()) and dest.is_relative_to(Path(r).resolve()) for r in cfg['asset_roots']):raise ValueError('next brief outside same brand assets')
    return dest

def _stage(store,job,name):
    with store.connect() as db:row=db.execute('SELECT status,evidence FROM stages WHERE brand=? AND job=? AND mode=? AND revision=? AND stage=?',(job['brand'],job['job_id'],job['mode'],job['revision'],name)).fetchone()
    if not row or row[0]!='complete' or not store.resumable(job,name):raise ValueError('trusted completed source stage required')
    return json.loads(row[1])

def sources(job,config,store,approval,metrics,learned):
    import bounded_adapters as A
    cfg=config['brands'][job['brand']];prefix=A.domain(job)
    delivery=_stage(store,job,prefix+'delivery');A.delivery_record(job,config,store,approval,delivery)
    measured=_stage(store,job,prefix+'measurement-'+metrics['period'][1])
    learning=_stage(store,job,prefix+'learning-'+metrics['period'][1])
    if measured.get('metrics')!=metrics or learning.get('next_item')!=learned.get('next_item'):raise ValueError('exact stored metrics and learning required')
    for k in ('brand','job_id','revision','manifest_hash','approval_ref','artifact_sha256','ad_ids'):
        if metrics.get(k)!=delivery.get(k):raise ValueError('next brief source lineage differs')
    mp=scoped(cfg,job['job_id'],job['revision'],'metrics-'+metrics['period'][1]+'.json');lp=scoped(cfg,job['job_id'],job['revision'],'learning-'+metrics['period'][1]+'.json')
    if read(mp)!=metrics or read(lp)!=learned['next_item'] or learned.get('path')!=str(lp) or learned.get('sha256')!=sha(lp):raise ValueError('source file/receipt differs')
    art=next(a for a in job['artifacts'] if a['id']==delivery['artifact_id'])
    if art['sha256']!=delivery['artifact_sha256'] or sha(art['path'])!=art['sha256']:raise ValueError('source artifact differs')
    item=learned['next_item']
    if item.get('status')!='draft' or item.get('requires_new_review_and_owner_approval') is not True or item.get('parent_manifest_hash')!=C.manifest_hash(job) or item.get('period')!=metrics['period']:raise ValueError('source learning is not an unapproved exact draft')
    return {'metrics':{'path':str(mp),'sha256':sha(mp),'period':metrics['period'],'ad_ids':metrics['ad_ids']},'learning':{'path':str(lp),'sha256':sha(lp)},'historical_artifact':{'path':art['path'],'sha256':art['sha256']}}

def build(job,cfg,metrics,item,refs,issued):
    order=job.get('order',{});needed={'ブランド','対象','指標','A/H','参考','本数/種類','着地','期限/支出上限'}
    if set(order)!=needed or order['ブランド']!=job['brand'] or not all(order.get(k) for k in needed):raise ValueError('complete approved eight-field source order required')
    kinds=order['本数/種類']
    if not isinstance(kinds,dict) or type(kinds.get('count')) is not int or kinds['count']<1 or not isinstance(kinds.get('type'),str):raise ValueError('typed source count/type required')
    if not isinstance(order['参考'],str) or not order['参考'].strip() or not isinstance(order['対象'],str) or not order['対象'].strip() or not isinstance(order['着地'],str) or not order['着地'].startswith('https://'):raise ValueError('evidenced audience/reference/destination required')
    if not re.fullmatch('A[0-9]{2}/H[0-9]{2}',order['A/H']) or item.get('A/H')!=order['A/H'] or not item.get('decisions'):raise ValueError('evidenced angle/next action required')
    if any(x.get('次の手') not in {'続ける','H を変える'} for x in item['decisions']):raise ValueError('known existing next action required')
    ttl=cfg.get('approval_max_seconds')
    if type(ttl) not in (int,float) or not 0<ttl<=86400:raise ValueError('bounded registered planning lifetime required')
    job_id=job['job_id'][:60]+'_next_'+metrics['period'][1].replace('-','')+'_'+refs['metrics']['sha256'][:12]
    expiry=iso(C.parse_time(issued)+ttl)
    body={'ブランド':job['brand'],'狙う数字':{'metric':order['指標'],'observed_orders':metrics['orders'],'observed_revenue':metrics['revenue'],'observed_spend':metrics['spend'],'observed_roas':metrics['revenue']/metrics['spend'] if metrics['spend'] else None,'next_actions':[{'axis':x['番号'][0], 'number':x.get('番号'),'decision':x['判定'],'action':x['次の手']}for x in item['decisions']],'audience':order['対象']},'A と H':{'source':order['A/H'],'change_requires_evidence':True},'参考':{'approved_reference':order['参考'],'evidence_refs':refs},'本数と種類':{'count':1,'type':kinds['type'],'scope':'local_preparation_only'},'着地':order['着地'],'締切':{'local_dispatch_expires_at':expiry,'paid_execution_requires_new_deadline_and_owner_approval':True},'使ってよい費用':{'generation':0,'advertising':0,'paid_actions_authorized':False,'previous_order_limits_are_evidence_only':order['期限/支出上限']}}
    return {'schema_version':1,'kind':'next_brief','status':'ready_for_local_dispatch','brand':job['brand'],'job_id':job_id,'revision':1,'execution_domain':job['execution_domain'],'parent':{'job_id':job['job_id'],'revision':job['revision'],'manifest_hash':C.manifest_hash(job),'approval_ref':metrics['approval_ref']},'evidence_refs':refs,'execution_authorized':False,'dispatch_scope':'local_preparation_only','issued_at':issued,'dispatch_expires_at':expiry,'body':body}

def atomic_new(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix='.next-brief-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb')as f:f.write(data);f.flush();os.fsync(f.fileno())
        try:os.link(tmp,p)
        except FileExistsError:pass
    finally:Path(tmp).unlink(missing_ok=True)

def make_record(brief,p):
    refs=brief['evidence_refs'];parent=brief['parent']
    return {'brand':brief['brand'],'job_id':brief['job_id'],'revision':brief['revision'],'brief_path':str(p),'brief_sha256':sha(p),'parent_job_id':parent['job_id'],'parent_revision':parent['revision'],'parent_manifest_hash':parent['manifest_hash'],'parent_approval_ref':parent['approval_ref'],'source_job_mode':'live','metrics_path':refs['metrics']['path'],'metrics_sha256':refs['metrics']['sha256'],'metrics_period':refs['metrics']['period'],'metrics_ad_ids':refs['metrics']['ad_ids'],'learning_path':refs['learning']['path'],'learning_sha256':refs['learning']['sha256'],'execution_domain':brief['execution_domain'],'dispatch_expires_at':brief['dispatch_expires_at']}

def enqueue(root,job,config,store,approval,metrics,learned,*,now=None):
    if job.get('mode')!='live':raise ValueError('source live-mode scoped receipt required (simulation domain is separate)')
    refs=sources(job,config,store,approval,metrics,learned);cfg=config['brands'][job['brand']]
    issued=iso(time.time() if now is None else now);brief=build(job,cfg,metrics,learned['next_item'],refs,issued);p=scoped(cfg,brief['job_id'],1,'next-brief.json')
    if p.exists():brief=build(job,cfg,metrics,learned['next_item'],refs,read(p)['issued_at'])
    atomic_new(p,C.canonical(brief).encode());saved=read(p)
    if saved!=build(job,cfg,metrics,learned['next_item'],refs,saved['issued_at']):raise ValueError('immutable next brief differs')
    record=make_record(saved,p);ident=C.manifest_hash(record);q=Path(root)/'data/automation/queue.sqlite3';q.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(q,timeout=15))as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS next_brief_outbox (id TEXT PRIMARY KEY,brand TEXT,job TEXT,revision INTEGER,path TEXT,hash TEXT,state TEXT,lease_until REAL,record TEXT)')
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT record FROM next_brief_outbox WHERE id=?',(ident,)).fetchone()
        if old and old[0]!=C.canonical(record):raise ValueError('immutable next brief outbox differs')
        db.execute('INSERT OR IGNORE INTO next_brief_outbox VALUES (?,?,?,?,?,?,?,?,?)',(ident,record['brand'],record['job_id'],record['revision'],str(p),record['brief_sha256'],'pending',0,C.canonical(record)))
    return {'status':'next_brief_queued','id':ident,'brief_path':str(p),'brief_sha256':record['brief_sha256'],'brand':record['brand'],'job_id':record['job_id'],'revision':1,'execution_authorized':False,'record':record}

def verify(record,config,store,*,now=None):
    if not isinstance(record,dict) or set(record)!=RECORD_FIELDS or record['brand'] not in config.get('brands',{}) or record['source_job_mode']!='live':raise ValueError('exact typed next brief record required')
    cfg=config['brands'][record['brand']];p=scoped(cfg,record['job_id'],record['revision'],'next-brief.json')
    if str(p)!=record['brief_path'] or not p.is_file() or sha(p)!=record['brief_sha256']:raise ValueError('next brief path/hash changed')
    brief=read(p)
    with store.connect()as db:row=db.execute('SELECT manifest FROM jobs WHERE brand=? AND job=? AND mode=? AND revision=?',(record['brand'],record['parent_job_id'],record['source_job_mode'],record['parent_revision'])).fetchone()
    if not row:raise ValueError('trusted parent job missing')
    job=json.loads(row[0])
    period=record['metrics_period']
    if not isinstance(period,list) or len(period)!=2 or not all(isinstance(x,str) and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',x) for x in period):raise ValueError('typed source period required')
    mp=scoped(cfg,job['job_id'],job['revision'],'metrics-'+period[1]+'.json');lp=scoped(cfg,job['job_id'],job['revision'],'learning-'+period[1]+'.json')
    if record['metrics_path']!=str(mp) or record['learning_path']!=str(lp) or sha(mp)!=record['metrics_sha256'] or sha(lp)!=record['learning_sha256']:raise ValueError('source file scope/hash differs')
    metrics=read(mp);item=read(lp);learned={'path':str(lp),'sha256':record['learning_sha256'],'next_item':item}
    refs=sources(job,config,store,record['parent_approval_ref'],metrics,learned)
    expected=build(job,cfg,metrics,item,refs,brief['issued_at'])
    if brief!=expected or make_record(brief,p)!=record:raise ValueError('next brief does not match protected source evidence')
    moment=time.time() if now is None else now
    if C.parse_time(brief['issued_at'])>moment or C.parse_time(brief['dispatch_expires_at'])<=moment:raise ValueError('next brief local dispatch expired/not yet issued')
    return {'schema_version':1,'status':'eligible','brand':brief['brand'],'job_id':brief['job_id'],'revision':brief['revision'],'brief':brief,'record':record}
