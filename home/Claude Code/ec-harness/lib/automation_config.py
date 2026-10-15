"""Explicit configuration overlay; never infer accounts, credentials or budgets."""
import copy
import hashlib
import math
import re
from pathlib import Path

REQUIRED={
 'production':('provider_account','voice_id','currency','max_price_per_1000_chars','cumulative_spend_ceiling','max_request_spend','max_chars'),
 'publication':('existing_adset_ids','budget_unit_scale','landing_hosts'),
 'measurement':('shop_id','currency','attribution_attribute','revenue_policy'),
}


def configuration(base, overlay, brand, *, live=False):
    if overlay.get('schema_version')!=1 or set(overlay)!={'schema_version','enabled','brands'} or type(overlay['enabled']) is not bool:
        raise ValueError('automation configuration schema invalid')
    if brand not in base.get('brands',{}) or brand not in overlay['brands']:
        raise ValueError('explicit registered automation brand required')
    entry=overlay['brands'][brand]
    if set(entry)!={'enabled','production','publication','measurement','connections','review','dispatch'} or type(entry['enabled']) is not bool:
        raise ValueError('brand automation configuration schema invalid')
    if live and (overlay['enabled'] is not True or entry['enabled'] is not True):
        raise ValueError('automation activation disabled')
    dispatch=entry.get('dispatch',{})
    if set(dispatch)!={'channel','max_turns','timeout_seconds'} or dispatch.get('channel')!='hq' or type(dispatch.get('max_turns')) is not int or not 1<=dispatch['max_turns']<=20 or type(dispatch.get('timeout_seconds')) is not int or not 1<=dispatch['timeout_seconds']<=300:
        raise ValueError('explicit bounded hq dispatch required')
    missing=[]
    review=entry.get('review',{})
    if set(review)!={'rules_path','rules_sha256','max_turns'}:raise ValueError('explicit review settings required')
    missing += ['review.'+key for key in review if review[key] is None]
    for section,keys in REQUIRED.items():
        if set(entry.get(section,{}))!=set(keys):raise ValueError('unknown/missing configuration field: '+section)
        missing += [section+'.'+k for k in keys if entry[section][k] is None or entry[section][k]=='' or entry[section][k]==[]]
    if set(entry.get('connections',{}))!={'elevenlabs','meta','shopify'}:raise ValueError('three explicit provider connections required')
    for provider,conn in entry['connections'].items():
        if set(conn)-{'credential_env','credential_sha256','api_version','shop_domain','auth'} or not {'credential_env','credential_sha256','api_version','shop_domain'}<=set(conn):raise ValueError('unknown connection setting')
        required=('credential_sha256',) if conn.get('auth') else ('credential_env','credential_sha256')
        missing += ['connections.'+provider+'.'+k for k in required if not conn.get(k)]
        auth=conn.get('auth')
        if auth:
            fields={'kind','brand','provider','account_id','env','path','format','key','selector','account_reference','shop_reference','shop_domain','client_id_reference','client_secret_reference'}
            expected={'elevenlabs':entry['production']['provider_account'],'meta':base['brands'][brand]['account_id'],'shopify':entry['measurement']['shop_id']}[provider]
            if not isinstance(auth,dict) or set(auth)-fields or auth.get('kind') not in {'existing_env','existing_file','shopify_client_credentials'} or auth.get('brand')!=brand or auth.get('provider')!=provider or auth.get('account_id')!=expected:raise ValueError('explicit existing authentication scope required')
        if provider=='meta' and not conn.get('api_version'):missing.append('connections.meta.api_version')
        if provider=='shopify' and not conn.get('shop_domain'):missing.append('connections.shopify.shop_domain')
    if missing:raise ValueError('required values unresolved: '+', '.join(missing))
    p=entry['production'];pub=entry['publication'];m=entry['measurement']
    for key in ('max_price_per_1000_chars','cumulative_spend_ceiling','max_request_spend'):
        if type(p[key]) not in (float,int) or not math.isfinite(p[key]) or p[key]<=0:raise ValueError('positive finite production ceilings required')
    if p['max_request_spend']>p['cumulative_spend_ceiling'] or type(p['max_chars']) is not int or not 1<=p['max_chars']<=10000:raise ValueError('bounded character/request ceiling required')
    if not re.fullmatch('[A-Za-z0-9_-]{1,100}',p['voice_id']) or not isinstance(p['provider_account'],str) or not p['provider_account'] or not re.fullmatch('[A-Z]{3}',p['currency']):raise ValueError('explicit voice/account/currency required')
    if not isinstance(pub['existing_adset_ids'],list) or not all(isinstance(x,str) and re.fullmatch('[0-9]+',x) for x in pub['existing_adset_ids']) or type(pub['budget_unit_scale']) not in (int,float) or not math.isfinite(pub['budget_unit_scale']) or pub['budget_unit_scale']<=0:raise ValueError('explicit existing adsets/budget scale required')
    if not isinstance(pub['landing_hosts'],list) or not all(isinstance(x,str) and re.fullmatch('[a-z0-9.-]+',x) for x in pub['landing_hosts']):raise ValueError('explicit brand landing hosts required')
    if not isinstance(m['shop_id'],str) or not m['shop_id'] or m['revenue_policy']!='total_less_successful_refunds' or not re.fullmatch('[A-Z]{3}',m['currency']) or not isinstance(m['attribution_attribute'],str) or not m['attribution_attribute']:raise ValueError('explicit shop/currency/attribution/revenue policy required')
    for provider,conn in entry['connections'].items():
        if (not conn.get('auth') and not re.fullmatch('[A-Z][A-Z0-9_]{0,99}',conn['credential_env'])) or not re.fullmatch('[0-9a-f]{64}',conn['credential_sha256']):raise ValueError('explicit credential reference/fingerprint required')
        if provider=='meta' and not re.fullmatch('v[0-9]+\\.0',conn['api_version']):raise ValueError('explicit Meta API version required')
        if provider=='shopify' and not re.fullmatch('[a-z0-9-]+\\.myshopify\\.com',conn['shop_domain']):raise ValueError('exact Shopify domain required')
    result=copy.deepcopy(base)
    result['brands'][brand].update({k:copy.deepcopy(entry[k]) for k in REQUIRED})
    cfg=result['brands'][brand]
    rules=Path(review['rules_path']).resolve() if isinstance(review['rules_path'],str) else None
    allowed=[Path(r).resolve() for r in cfg['asset_roots']+cfg.get('read_roots',[])]+[Path(__file__).resolve().parents[1]/'config/review',Path.home()/'Documents/Obsidian Vault/ec/構造/ハーネス']
    if not rules or not any(rules.is_relative_to(root) for root in allowed) or not rules.is_file() or not re.fullmatch('[0-9a-f]{64}',review['rules_sha256']) or hashlib.sha256(rules.read_bytes()).hexdigest()!=review['rules_sha256'] or type(review['max_turns']) is not int or not 1<=review['max_turns']<=20:
        raise ValueError('bounded canonical review rules/hash required')
    root=Path(cfg['workspace_root']).resolve()
    if not any(root.is_relative_to(Path(r).resolve()) for r in cfg['asset_roots']):raise ValueError('workspace root outside same brand assets')
    for other,other_cfg in base['brands'].items():
        if other==brand:continue
        if any(root.is_relative_to(Path(r).resolve()) or Path(r).resolve().is_relative_to(root) for r in other_cfg['asset_roots']):raise ValueError('brand workspaces overlap')
    return result
