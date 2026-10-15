"""Bounded native HTTP transport. Nothing connects until explicitly constructed.

No token files or implicit environment names. Configured credential fingerprint
must match; no redirects/retries. All tests replace HTTP with offline responses.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('provider redirects forbidden')


class HTTPTransport:
    simulated=False
    def __init__(self,provider,account,connection,*,auth_resolver=None):
        self.provider=provider;self.account_id=account;self.connection=connection
        if auth_resolver is not None:
            resolved=auth_resolver(provider,account,connection)
            binding=connection.get('auth',{})
            if resolved.provider!=provider or resolved.account_id!=account or resolved.brand!=binding.get('brand') or resolved.source_fingerprint!=connection['credential_sha256']:
                raise ValueError('existing authentication identity/fingerprint mismatch')
            self.token=resolved.token
        else:
            self.token=os.environ.get(connection['credential_env'])
            if not self.token or hashlib.sha256(self.token.encode()).hexdigest()!=connection['credential_sha256']:
                raise ValueError('explicit provider credential/fingerprint mismatch')
        self.opener=urllib.request.build_opener(NoRedirect())
        if provider=='elevenlabs':self.base='https://api.elevenlabs.io'
        elif provider=='meta':self.base='https://graph.facebook.com/'+connection['api_version']
        elif provider=='shopify':self.base='https://'+connection['shop_domain']
        else:raise ValueError('unknown HTTP provider')
        # Read-only identity check before any paid or publishing request.
        if provider=='elevenlabs':
            if self.request('GET','/v1/user',None).get('user_id')!=account:raise ValueError('ElevenLabs native account identity unverified')
        elif provider=='meta':
            if self.request('GET','/act_'+account+'?fields=account_id',None).get('account_id')!=account:raise ValueError('Meta native account identity mismatch')
        elif str(self.request('GET','/admin/api/2026-07/shop.json',None).get('shop',{}).get('id'))!=account:
            raise ValueError('Shopify native account identity mismatch')

    def request(self,method,path,body):
        failure=None
        try:return self._request(method,path,body)
        except TimeoutError:failure='timeout'
        except Exception:failure='request'
        # Raise outside the except block so raw headers/provider bodies do not
        # survive in __context__ or logs, including malformed secret headers.
        if failure=='timeout':raise TimeoutError('bounded provider request timed out')
        raise ValueError('bounded provider request failed')

    def _request(self,method,path,body):
        if method not in {'GET','POST'} or not isinstance(path,str) or not path.startswith('/') or path.startswith('//') or '#' in path:
            raise ValueError('bounded provider request required')
        bare=path.split('?',1)[0]
        if self.provider=='elevenlabs':
            allowed=(method=='GET' and bare=='/v1/user') or (method=='POST' and re.fullmatch('/v1/text-to-speech/[A-Za-z0-9_-]+/with-timestamps',bare))
        elif self.provider=='shopify':allowed=method=='GET' and bare in {'/admin/api/2026-07/shop.json','/admin/api/2026-07/orders.json'}
        else:
            allowed=(method=='GET' and re.fullmatch('/(?:act_)?[0-9]+(?:/(?:insights|thumbnails))?',bare)) or (method=='POST' and bare in {'/act_'+self.account_id+'/'+s for s in ('advideos','adcreatives','ads')})
        if not allowed:raise ValueError('endpoint/method outside adapter allowlist')
        headers={};data=None
        if self.provider=='elevenlabs':headers['xi-api-key']=self.token
        elif self.provider=='shopify':headers['X-Shopify-Access-Token']=self.token
        else:headers['Authorization']='Bearer '+self.token
        if method=='GET' and body:
            query=urllib.parse.urlencode({k:json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in body.items()})
            path+=('&' if '?' in path else '?')+query
        elif method=='POST':
            if body and 'source_bytes' in body:
                if self.provider!='meta' or set(body)!={'source_bytes','title'}:raise ValueError('typed video upload only')
                boundary='EC'+uuid.uuid4().hex
                data=(f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n'.encode()+body['title'].encode()+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="approved.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode()+body['source_bytes']+f'\r\n--{boundary}--\r\n'.encode())
                headers['Content-Type']='multipart/form-data; boundary='+boundary
            elif self.provider=='meta':
                data=urllib.parse.urlencode({k:json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in body.items()}).encode();headers['Content-Type']='application/x-www-form-urlencoded'
            else:data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode();headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base+path,data=data,headers=headers,method=method)
        with self.opener.open(request,timeout=20) as response:
            raw=response.read(25_000_001)
            if len(raw)>25_000_000:raise ValueError('provider response exceeds bound')
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('error') or result.get('errors'):raise ValueError('provider rejected request')
            if self.provider=='shopify':result['_headers']={'link':response.headers.get('Link','')}
            return result


def fingerprint(body):
    def encode(value):
        if isinstance(value,bytes):return {'bytes_sha256':hashlib.sha256(value).hexdigest()}
        if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
        if isinstance(value,list):return [encode(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(encode(body),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class FixtureTransport:
    simulated=True
    def __init__(self,data,provider,account):
        if data.get('schema_version')!=1 or data.get('provider')!=provider or data.get('account_id')!=account or not isinstance(data.get('responses'),list):raise ValueError('scoped fixture transport required')
        self.data=data;self.provider=provider;self.account_id=account
    def request(self,method,path,body):
        matched=[r for r in self.data['responses'] if r.get('method')==method and r.get('path')==path and r.get('request_sha256')==fingerprint(body)]
        if len(matched)!=1:raise ValueError('missing/ambiguous exact request fixture')
        if matched[0].get('fault')=='timeout':raise TimeoutError('fixture uncertain provider result')
        return matched[0]['response']
