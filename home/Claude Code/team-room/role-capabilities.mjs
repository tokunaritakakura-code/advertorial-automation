// Typed local-only capabilities. No subprocess, network, publish or credential API.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { TextDecoder } from 'node:util';

const MAX_CREATE_BYTES = 1024 * 1024;
const MAX_INSPECT_BYTES = 256 * 1024;
const MAX_LIST = 100;
const MIME_EXTENSIONS = Object.freeze({
  'text/markdown':['.md'], 'text/plain':['.txt','.log'], 'application/json':['.json'],
  'text/csv':['.csv'], 'text/html':['.html'], 'text/css':['.css'], 'text/vtt':['.vtt'],
});
const PLANNING = Object.freeze(['text/markdown','text/plain','application/json']);
const RESEARCH = Object.freeze([...PLANNING,'text/csv']);
const COPY = Object.freeze([...PLANNING,'text/vtt']);
const PAGE = Object.freeze([...PLANNING,'text/html','text/css']);
export const ROLE_MIMES = Object.freeze({
  '本部長':PLANNING, 'ブランドマネージャー':RESEARCH, '戦略責任者':RESEARCH,
  '戦略担当':RESEARCH, 'リサーチャー':RESEARCH, 'クリエイティブディレクター':PLANNING,
  'クリエイティブ・ストラテジスト':RESEARCH, 'コピーライター':COPY,
  '吹き替えディレクター':COPY, '生成アーティスト':PLANNING, '映像編集者':COPY,
  'ファネル責任者':PLANNING, '記事ライター':PAGE, 'ストア担当':PAGE,
  'グロース責任者':RESEARCH, 'メディアバイヤー':RESEARCH, 'アナリスト':RESEARCH,
  '仕組み係':RESEARCH, '編集長':Object.freeze([]), '台帳係':Object.freeze([]),
});
const TOOL_TO_OPERATION = Object.freeze({
  'mcp__local__local_artifact_create':'create',
  'mcp__local__local_artifact_inspect':'inspect',
  'mcp__local__local_artifact_list':'list',
});
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const jsonHash = value => hash(Buffer.from(JSON.stringify(value)));
function objectKeys(value, allowed) {
  if (!value || typeof value!=='object' || Array.isArray(value) || Object.keys(value).some(k=>!allowed.includes(k))) throw Error('typed local arguments required; scope overrides forbidden');
}
function childOf(file,root) {
  const relative=path.relative(root,file);
  return relative==='' || (!relative.startsWith('..'+path.sep) && relative!=='..' && !path.isAbsolute(relative));
}
function secretName(file) {
  const segments=file.split(path.sep).map(s=>s.toLowerCase());
  return segments.some(s=>['.secrets','.ssh','.aws','.claude','.codex','node_modules'].includes(s)) ||
    segments.some(s=>s==='.env' || s.startsWith('.env.') || /\.(key|pem|p12|pfx|sqlite|sqlite3|db)$/.test(s) || /^\.?shopify-(mcp|reports)\.json$/.test(s) || /^(credentials?|secrets?|tokens?)\.(json|txt)$/.test(s));
}
function relativeName(value,empty=false) {
  if (typeof value!=='string' || (!value && !empty) || value.length>600 || path.isAbsolute(value) || value.includes('\\') || /[\x00-\x1f\x7f]/.test(value)) throw Error('relative artifact name required');
  if (!value && empty) return '';
  const pieces=value.split('/');
  if (pieces.some(s=>!s || s==='.' || s==='..' || s.startsWith('.') || s.length>180)) throw Error('artifact path traversal/hidden name forbidden');
  return pieces.join(path.sep);
}
function noSymlink(root,target,{createParents=false}={}) {
  if (!childOf(target,root)) throw Error('artifact outside job revision');
  if (fs.lstatSync(root).isSymbolicLink() || !fs.statSync(root).isDirectory()) throw Error('job root must be a real directory');
  const segments=path.relative(root,target).split(path.sep).filter(Boolean);
  let current=root;
  for (let i=0;i<segments.length;i++) {
    current=path.join(current,segments[i]);
    if (!fs.existsSync(current)) {
      if (i===segments.length-1) return;
      if (!createParents) throw Error('artifact parent missing');
      fs.mkdirSync(current);
    }
    const stat=fs.lstatSync(current);
    if (stat.isSymbolicLink()) throw Error('artifact symlink forbidden');
    if (i<segments.length-1 && !stat.isDirectory()) throw Error('artifact parent is not directory');
  }
}
function readableRealPath(file,roots) {
  if (secretName(file)) throw Error('secret/runtime file inspection forbidden');
  if (!path.isAbsolute(file)) throw Error('absolute inspection path required');
  // Check lexical membership before touching a target outside approved roots.
  const allowed=roots.filter(root=>childOf(path.resolve(file),root.path));
  if (!allowed.length) throw Error('inspection outside configured nonsecret roots');
  const real=fs.realpathSync(file);
  if (secretName(real) || !allowed.some(root=>childOf(real,root.real))) throw Error('inspection symlink escape forbidden');
  const stat=fs.statSync(real);
  if (!stat.isFile() || stat.nlink>1) throw Error('inspection requires ordinary unlinked file');
  return real;
}
function readBounded(fd, maximum) {
  const chunks=[];let total=0;
  while (true) {
    const buffer=Buffer.alloc(Math.min(64*1024,maximum-total+1));
    const count=fs.readSync(fd,buffer,0,buffer.length,null);
    if (!count) break;
    total+=count;
    if (total>maximum) throw Error('inspection file grew beyond bound');
    chunks.push(buffer.subarray(0,count));
  }
  return Buffer.concat(chunks,total);
}
function outputMime(file) {
  return Object.entries(MIME_EXTENSIONS).find(([,extensions])=>extensions.includes(path.extname(file).toLowerCase()))?.[0] || null;
}

export function createRoleCapabilities({role,ctx,brandConfig,runId,signal,leaseExpiresAt=Date.now()+30*60*1000,onArtifact=null,reviewArtifacts=null}) {
  if (!Object.hasOwn(ROLE_MIMES,role) || !ctx || typeof ctx.brand!=='string' || !ctx.brand || !/^[A-Za-z0-9_-]{1,100}$/.test(ctx.job_id||'') || !Number.isSafeInteger(ctx.revision) || ctx.revision<1 || typeof runId!=='string' || !runId) throw Error('trusted role/session scope required');
  if (!brandConfig || !Array.isArray(brandConfig.asset_roots) || !brandConfig.asset_roots.length || !Number.isFinite(leaseExpiresAt) || leaseExpiresAt<=Date.now() || leaseExpiresAt>Date.now()+8*24*60*60*1000 /* server.mjs の 既定.total_ms（7日＝上限なしの代わり）より長く。2026-10-05 */) throw Error('bounded local capability lease required');
  if (!signal || typeof signal.aborted!=='boolean') throw Error('server-owned cancellation signal required');
  const frozenCtx=Object.freeze({brand:ctx.brand,job_id:ctx.job_id,revision:ctx.revision});
  const roots=brandConfig.asset_roots.map(root=> {
    if (!path.isAbsolute(root) || secretName(root)) throw Error('nonsecret absolute brand asset root required');
    const brandRoot=fs.realpathSync(root);
    const jobRoot=path.join(root,frozenCtx.job_id,`r${frozenCtx.revision}`);
    const realJobRoot=fs.realpathSync(jobRoot);
    if (!childOf(realJobRoot,brandRoot) || fs.lstatSync(jobRoot).isSymbolicLink()) throw Error('job root escaped brand');
    return realJobRoot;
  });
  const readRoots=Object.freeze([...roots,...brandConfig.asset_roots.map(root=>path.join(root,frozenCtx.job_id,`r${frozenCtx.revision}`)),...(brandConfig.read_roots||[]),...[brandConfig.metrics_path,brandConfig.angle_ledger_path].filter(root=>typeof root==='string' && root && fs.existsSync(root))].map(root=> {
    if (typeof root!=='string' || !path.isAbsolute(root) || secretName(root)) throw Error('nonsecret read roots required');
    // Freeze resolved destinations; swapping an approved path alias cannot widen scope.
    return Object.freeze({path:path.resolve(root),real:fs.realpathSync(root)});
  }));
  const reviewer=role==='編集長';
  const reviewFiles=new Map();
  if (reviewer) {
    if (!Array.isArray(reviewArtifacts) || !reviewArtifacts.length) throw Error('reviewer requires fixed artifact inputs');
    for (const artifact of reviewArtifacts) {
      if (!artifact || typeof artifact.path!=='string' || !path.isAbsolute(artifact.path) || artifact.revision!==frozenCtx.revision || !/^[0-9a-f]{64}$/.test(artifact.sha256||'') || !roots.some(root=>childOf(fs.realpathSync(artifact.path),root))) throw Error('reviewer artifact scope invalid');
      reviewFiles.set(fs.realpathSync(artifact.path),artifact.sha256);
    }
  }
  let active=true;
  const operations=Object.freeze(reviewer ? ['local_artifact_inspect'] : ['local_artifact_create','local_artifact_inspect','local_artifact_list']);
  function live() { if (!active || signal.aborted || Date.now()>=leaseExpiresAt) throw Error('local capability cancelled/expired'); }
  function result(value) { return {schema_version:1,status:'success',...frozenCtx,role,run_id:runId,...value}; }
  function validate(operation,input) {
    live();
    if (operation==='create') {
      if (reviewer) throw Error('independent reviewer is read-only');
      objectKeys(input,['relative_path','mime_type','content_utf8','content_base64']);
      relativeName(input.relative_path);
      if (!ROLE_MIMES[role].includes(input.mime_type) || !MIME_EXTENSIONS[input.mime_type]?.includes(path.extname(input.relative_path).toLowerCase())) throw Error('artifact MIME/extension outside role capability');
      if (secretName(input.relative_path)) throw Error('secret artifact name forbidden');
      if ((typeof input.content_utf8==='string')===(typeof input.content_base64==='string')) throw Error('exactly one typed content encoding required');
    } else if (operation==='inspect') {
      objectKeys(input,['path','expected_sha256','max_bytes']);
      if (typeof input.path!=='string' || !path.isAbsolute(input.path) || secretName(input.path)) throw Error('nonsecret inspection path required');
      if (reviewer && (!reviewFiles.has(fs.realpathSync(input.path)) || (input.expected_sha256!==undefined && input.expected_sha256!==reviewFiles.get(fs.realpathSync(input.path))))) throw Error('reviewer may inspect only fixed artifact inputs');
      if (input.expected_sha256!==undefined && !/^[0-9a-f]{64}$/.test(input.expected_sha256)) throw Error('inspection expected hash invalid');
      if (input.max_bytes!==undefined && (!Number.isSafeInteger(input.max_bytes) || input.max_bytes<1 || input.max_bytes>MAX_INSPECT_BYTES)) throw Error('inspection size must be bounded');
    } else if (operation==='list') {
      if (reviewer) throw Error('reviewer directory listing forbidden');
      objectKeys(input,['relative_dir']);relativeName(input.relative_dir??'',true);
    } else throw Error('unknown local capability');
  }
  function policy(toolName,input) {
    try { const operation=TOOL_TO_OPERATION[toolName];if (!operation) throw Error('unregistered tool');validate(operation,input);return {decision:'allow'}; }
    catch (error) { return {decision:'deny',reason:error.message}; }
  }
  function create(input) {
    validate('create',input);
    const {relative_path,mime_type}=input;
    let bytes;
    if (typeof input.content_utf8==='string') {
      if (Buffer.byteLength(input.content_utf8,'utf8')>MAX_CREATE_BYTES) throw Error('artifact bytes over bound');
      bytes=Buffer.from(input.content_utf8,'utf8');
    }
    else {
      if (input.content_base64.length>MAX_CREATE_BYTES*2 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(input.content_base64)) throw Error('canonical bounded base64 required');
      bytes=Buffer.from(input.content_base64,'base64');
      if (bytes.toString('base64')!==input.content_base64) throw Error('canonical bounded base64 required');
    }
    if (!bytes.length || bytes.length>MAX_CREATE_BYTES) throw Error('artifact bytes empty/over bound');
    const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
    if (text.includes('\0')) throw Error('artifact must be UTF-8 text');
    if (mime_type==='application/json') JSON.parse(text);
    const destination=path.join(roots[0],relativeName(relative_path));
    noSymlink(roots[0],destination,{createParents:true});live();
    let fd=null;
    try {
      fd=fs.openSync(destination,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
      fs.writeFileSync(fd,bytes);fs.fsyncSync(fd);
    } finally { if (fd!==null) fs.closeSync(fd); }
    // A receipt describes durable exact bytes. It is not an approval or publish receipt.
    const artifact={path:destination,relative_path,revision:frozenCtx.revision,sha256:hash(bytes),bytes:bytes.length,mime_type};
    Object.freeze(artifact);
    const receipt=Object.freeze(result({artifact,evidence_receipt:jsonHash({...frozenCtx,role,run_id:runId,artifact})}));
    if (onArtifact) onArtifact(receipt);
    return receipt;
  }
  function inspect(input) {
    validate('inspect',input);
    const file=readableRealPath(input.path,readRoots);const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
    try {
      const stat=fs.fstatSync(fd);
      if (!stat.isFile() || stat.nlink>1 || stat.size>MAX_CREATE_BYTES*4) throw Error('inspection file outside bound');
      const all=readBounded(fd,MAX_CREATE_BYTES*4),sha256=hash(all);
      const expected=input.expected_sha256 || (reviewer ? reviewFiles.get(fs.realpathSync(input.path)) : null);
      if (expected && expected!==sha256) throw Error('inspection artifact changed');
      const maximum=input.max_bytes??64*1024;
      const text=new TextDecoder('utf-8',{fatal:true}).decode(all.subarray(0,maximum),{stream:all.length>maximum});
      live();
      return result({artifact:{path:file,revision:frozenCtx.revision,sha256,bytes:all.length,mime_type:outputMime(file)},content_utf8:text,truncated:all.length>maximum});
    } finally {fs.closeSync(fd);}
  }
  function list(input={}) {
    validate('list',input);const directory=path.join(roots[0],relativeName(input.relative_dir??'',true));noSymlink(roots[0],directory);
    const stat=fs.statSync(directory);if (!stat.isDirectory()) throw Error('artifact directory required');
    const entries=[];
    for (const item of fs.readdirSync(directory,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
      if (item.isSymbolicLink() || secretName(item.name) || item.name.startsWith('.')) continue;
      entries.push({name:item.name,type:item.isDirectory()?'directory':item.isFile()?'file':'other'});if(entries.length>=MAX_LIST) break;
    }
    live();return result({directory,entries,limit:MAX_LIST});
  }
  return Object.freeze({operations,policy,create,inspect,list,close(){active=false;}});
}
