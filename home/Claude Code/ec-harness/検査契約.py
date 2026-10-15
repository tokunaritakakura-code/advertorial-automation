"""共通検査境界。executableは材料の準備完了であり、配信の承認ではない。
終了コード: 0 材料準備完了 / 1 構造不正 / 2 証拠不足 / 3 構造のみ。
context・config・全入力の版とブランドを確認してから旧検査を呼ぶ。
"""
import contextlib,hashlib,importlib.util,io,json,os,re,sys
from pathlib import Path

def core():
    path=Path(os.environ.get('EC_CONTRACT_MODULE',str(Path(__file__).parent/'lib/ec_contract.py')))
    spec=importlib.util.spec_from_file_location('ec_contract',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def identity(material,job):
    return [f'identity mismatch: {k}' for k in ('brand','job_id','revision','account_id') if material.get(k)!=job.get(k)] + ([] if material.get('schema_version')==1 else ['unsupported material schema'])

def load_context(argv):
    args=list(argv);context=None;cfg=None
    for flag in ('--context','--config'):
        if flag not in args: raise ValueError(flag+' required')
        i=args.index(flag)
        if i+1>=len(args): raise ValueError(flag+' value required')
        v=args[i+1];del args[i:i+2]
        if flag=='--context':context=json.loads(Path(v).read_text())
        else:cfg=json.loads(Path(v).read_text())
    result=core().validate_job(context,cfg,verify_files=True)
    if result['errors']:raise ValueError('; '.join(result['errors']))
    return args,context,cfg['brands'][context['brand']]

def bound(path,job,seen=None):
    p=Path(path).resolve()
    if seen is None: seen=set()
    if p in seen:return p
    seen.add(p)
    artifact=next((a for a in job['artifacts'] if Path(a['path']).resolve()==p),None)
    if not artifact:raise ValueError('unregistered input artifact: '+str(p))
    if hashlib.sha256(p.read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('input changed: '+str(p))
    # 文書が自己識別を持つ場合は必ず一致する。旧文書は版付きbrand-root manifestで識別。
    if p.suffix.lower()=='.json':
        data=json.loads(p.read_text())
        if isinstance(data,dict) and any(k in data for k in ('brand','job_id','revision')):
            errors=identity(data,job)
            if errors:raise ValueError('; '.join(errors))
    elif p.suffix.lower()=='.md':
        text=p.read_text()
        for key in ('brand','job_id','revision'):
            match=re.search(r'^'+key+r':\s*(.+)$',text,re.M)
            if match and match.group(1).strip()!=str(job[key]):raise ValueError('document '+key+' mismatch')
        for match in re.finditer(r'^(反論台帳|ペルソナ|アングル台帳):\s*(.+)$',text,re.M):
            ref=match.group(2).strip().strip('`')
            if not Path(ref).is_absolute():raise ValueError('reference requires explicit absolute path')
            # アングル台帳は工程3で作る。工程2の出口でまだ無いのは順番どおりなので照らさない（中身の検査が「まだ無い」と知らせる。2026-10-05）
            if match.group(1)=='アングル台帳' and not Path(ref).exists():continue
            bound(ref,job,seen)
    return p

def emit(status,job,errors=None,details=''):
    result={'schema_version':1,'status':status,'authorization':False,'brand':job.get('brand'),'job_id':job.get('job_id'),'revision':job.get('revision'),'errors':errors or [],'details':details}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False));return {'executable':0,'rejected':1,'insufficient_evidence':2,'valid_structure':3}[status]

def cli(kind,callback,argv):
    job={}
    try:
        args,job,cfg=load_context(argv)
        lengths={'割':(2,2),'店':(2,99),'記事':(2,4),'客':(2,2),'商品':(2,2),'段':(3,3),'週':(4,6),'数字':(3,99)}
        low,high=lengths[kind]
        if not low<=len(args)<=high:raise ValueError('invalid validator arguments')
        if kind=='数字' and any(a.startswith('--') and a not in ('--広告','--記事','--店') for a in args[1:]):raise ValueError('unknown number flag')
        inputs=[a for a in args[1:] if not a.startswith('--')]
        if kind in ('段','週'):inputs=[args[2]] if kind=='段' else [args[3]]
        if kind=='商品':inputs=[args[1]]
        for path in inputs:
            if re.match(r'https?://',path):raise ValueError('unversioned URL input: export into registered artifact first')
            if Path(path).is_file():bound(path,job)
            elif kind not in ('段','週'):raise ValueError('input file missing: '+path)
        if kind=='週':
            if len(args) not in (4,6) or (len(args)==6 and args[4]!='--output'):raise ValueError('weekly --output requires exactly one path')
            if args[2]!=job['brand']:raise ValueError('weekly brand mismatch')
        global CURRENT_JOB, CURRENT_CONFIG
        CURRENT_JOB, CURRENT_CONFIG = job, cfg
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            rc=callback(args,job,cfg)
        status='executable' if rc in (None,0) else ('valid_structure' if rc==3 else 'insufficient_evidence')
        return emit(status,job,details=output.getvalue())
    except SystemExit as e:return emit('insufficient_evidence',job,[str(e)],locals().get('output',io.StringIO()).getvalue())
    except (ValueError,KeyError,TypeError,IndexError,OSError) as e:return emit('rejected',job,[str(e)])
