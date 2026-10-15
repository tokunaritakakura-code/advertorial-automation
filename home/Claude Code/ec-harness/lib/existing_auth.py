"""Reuse explicitly configured existing credentials; no discovery, writes or grants.

Import is inert. Secret files are opened only when resolver is invoked at runtime.
Provider native identity must still be verified by HTTPTransport before mutation.
"""
import hashlib
import hmac
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PROVIDERS = {'elevenlabs', 'meta', 'shopify'}
ENV_NAME = re.compile(r'^[A-Z][A-Z0-9_]{0,99}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
SHOP_DOMAIN = re.compile(r'^[a-z0-9][a-z0-9-]*\.myshopify\.com$')
DEFAULT_ALLOWED_FILES = frozenset({
    str(Path.home() / '.claude/skills/vsl-jp/.secrets/eleven.key'),
    str(Path.home() / 'Claude Code/arukoto-track/.env.local'),
    str(Path.home() / '.shopify-mcp.json'),
    str(Path.home() / '.shopify-reports.json'),
})

class AuthError(ValueError):
    """Messages never contain provider body, file contents or credential values."""

@dataclass(frozen=True)
class ResolvedAuth:
    brand: str
    provider: str
    account_id: str
    source_fingerprint: str
    token: str = field(repr=False)


def credential_fingerprint(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def client_credentials_fingerprint(client_id, client_secret, shop_domain):
    body=json.dumps({'client_id':client_id,'client_secret':client_secret,'shop_domain':shop_domain},sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def parse_dotenv(text):
    """Parse data only; never source shell or expand interpolation/commands."""
    values={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].strip()
        if '=' not in line:raise AuthError('existing env file has unsupported syntax')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not ENV_NAME.fullmatch(key):raise AuthError('existing env file has unsupported syntax')
        if key in values:raise AuthError('existing env file has duplicate key')
        if value.startswith(('"',"'")):
            quote=value[0]
            if len(value)<2 or value[-1]!=quote:raise AuthError('existing env file has unsupported syntax')
            value=value[1:-1]
        else:
            value=value.split(' #',1)[0].rstrip()
        # Treat shell syntax as unsupported rather than accidentally using it.
        if '$' in value or '`' in value or '\x00' in value:raise AuthError('existing env file has unsupported syntax')
        values[key]=value
    return values


def _json_select(data, selector):
    if not isinstance(selector,list) or not selector or not all(isinstance(k,str) and k for k in selector):raise AuthError('explicit JSON credential selector required')
    for key in selector:
        if not isinstance(data,dict) or key not in data:raise AuthError('existing credential selector unavailable')
        data=data[key]
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise AuthError('credential exchange redirect forbidden')


def bounded_shopify_oauth(url, body):
    """Single runtime token exchange. Exact Shopify endpoint, no retry/redirect."""
    if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]*\.myshopify\.com/admin/oauth/access_token',url):raise AuthError('credential exchange endpoint invalid')
    if set(body)!={'client_id','client_secret','grant_type'} or body['grant_type']!='client_credentials':raise AuthError('credential exchange body invalid')
    request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request,timeout=20) as response:
            if response.status!=200:raise AuthError('existing credential exchange rejected')
            raw=response.read(65537)
            if len(raw)>65536:raise AuthError('credential exchange response exceeds bound')
            result=json.loads(raw)
            if not isinstance(result,dict):raise AuthError('credential exchange response invalid')
            return result
    except Exception:
        pass
    raise AuthError('existing credential exchange failed')


class ExistingAuthResolver:
    def __init__(self, brand, *, env=None, read_text=None, oauth_post=None, allowed_files=None):
        if not isinstance(brand,str) or not brand:raise AuthError('explicit resolver brand required')
        self.brand=brand
        self.env=os.environ if env is None else env
        self.read_text=(lambda path:Path(path).read_text(encoding='utf-8')) if read_text is None else read_text
        self.oauth_post=bounded_shopify_oauth if oauth_post is None else oauth_post
        # Override is test/application constructor only, never from connection JSON.
        self.allowed_files=DEFAULT_ALLOWED_FILES if allowed_files is None else frozenset(str(Path(p).absolute()) for p in allowed_files)

    def _reference(self, reference):
        if not isinstance(reference,dict):raise AuthError('explicit credential reference required')
        kind=reference.get('kind')
        if kind=='existing_env':
            name=reference.get('env')
            if not isinstance(name,str) or not ENV_NAME.fullmatch(name):raise AuthError('explicit credential environment reference required')
            value=self.env.get(name)
        elif kind=='existing_file':
            supplied=reference.get('path')
            if not isinstance(supplied,str) or not Path(supplied).is_absolute():raise AuthError('absolute existing credential path required')
            path=Path(supplied)
            # Both configured spelling and resolved destination must be allowlisted.
            if str(path.absolute()) not in self.allowed_files or str(path.resolve()) not in self.allowed_files:raise AuthError('credential path outside existing allowlist')
            try:text=self.read_text(str(path))
            except Exception:text=None
            if text is None:raise AuthError('existing credential file unavailable')
            if not isinstance(text,str) or len(text)>1024*1024:raise AuthError('existing credential file exceeds bound')
            fmt=reference.get('format')
            if fmt=='raw':value=text.strip()
            elif fmt=='dotenv':
                key=reference.get('key')
                if not isinstance(key,str) or not ENV_NAME.fullmatch(key):raise AuthError('explicit env-file credential key required')
                value=parse_dotenv(text).get(key)
            elif fmt=='json':
                try:data=json.loads(text)
                except Exception:data=None
                if data is None:raise AuthError('existing credential JSON invalid')
                value=_json_select(data,reference.get('selector'))
            else:raise AuthError('explicit credential file format required')
        else:raise AuthError('unsupported existing credential reference')
        if not isinstance(value,str) or not value.strip() or '\x00' in value or len(value)>65536:raise AuthError('existing credential value unavailable')
        return value.strip()

    def __call__(self, provider, account, connection):
        try:return self._resolve(provider,account,connection)
        except AuthError:raise
        except Exception:pass
        raise AuthError('existing authentication resolution failed')

    def _resolve(self, provider, account, connection):
        if provider not in PROVIDERS or not isinstance(account,str) or not account or not isinstance(connection,dict):raise AuthError('explicit provider/account required')
        auth=connection.get('auth')
        if not isinstance(auth,dict) or auth.get('brand')!=self.brand or auth.get('provider')!=provider or auth.get('account_id')!=account:raise AuthError('credential brand/provider/account binding mismatch')
        expected=connection.get('credential_sha256')
        if not isinstance(expected,str) or not SHA256.fullmatch(expected):raise AuthError('configured credential fingerprint required')
        kind=auth.get('kind')
        if kind in {'existing_env','existing_file'}:
            token=self._reference(auth)
            if auth.get('account_reference') is not None and self._reference(auth['account_reference'])!=account:raise AuthError('existing credential account reference mismatch')
            if auth.get('shop_reference') is not None and self._reference(auth['shop_reference'])!=connection.get('shop_domain'):raise AuthError('existing credential shop reference mismatch')
            actual=credential_fingerprint(token)
        elif kind=='shopify_client_credentials':
            domain=connection.get('shop_domain')
            if provider!='shopify' or not isinstance(domain,str) or not SHOP_DOMAIN.fullmatch(domain):raise AuthError('explicit Shopify client-credential domain required')
            if auth.get('shop_domain')!=domain:raise AuthError('client credential shop binding mismatch')
            client_id=self._reference(auth.get('client_id_reference'))
            secret=self._reference(auth.get('client_secret_reference'))
            if auth.get('shop_reference') is not None and self._reference(auth['shop_reference'])!=domain:raise AuthError('existing client credential shop reference mismatch')
            actual=client_credentials_fingerprint(client_id,secret,domain)
            if not hmac.compare_digest(actual,expected):raise AuthError('configured credential fingerprint mismatch')
            try:response=self.oauth_post('https://'+domain+'/admin/oauth/access_token',{'client_id':client_id,'client_secret':secret,'grant_type':'client_credentials'})
            except Exception:response=None
            if response is None:raise AuthError('existing credential exchange failed')
            token=response.get('access_token') if isinstance(response,dict) else None
            expiry=response.get('expires_in') if isinstance(response,dict) else None
            if not isinstance(token,str) or not token or '\x00' in token or len(token)>65536 or type(expiry) not in (int,float) or not 0<expiry<=86400:raise AuthError('existing credential exchange response invalid')
        else:raise AuthError('unsupported existing authentication kind')
        if not hmac.compare_digest(actual,expected):raise AuthError('configured credential fingerprint mismatch')
        return ResolvedAuth(self.brand,provider,account,actual,token)
