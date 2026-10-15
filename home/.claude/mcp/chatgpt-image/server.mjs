#!/usr/bin/env node
// chatgpt-image — ChatGPT の画像生成（gpt-image）を MCP の道具として呼ぶ。
// ブラウザは使わない。中では ChatGPT でログイン済みの Codex CLI（codex exec の組み込み image_gen）を動かす。
// APIキーも課金の追加も要らない（本人の ChatGPT の枠で動く）。
//
// 道具: generate_image { prompt, out_path, reference_images?, aspect? }
//   → out_path に PNG を保存して、パス・縦横・かかった秒数を返す。
// 何枚も作る時は、この道具を同時に何回か呼べばよい（1回ごとに別の codex が走る）。
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const TIMEOUT_MS = 12 * 60 * 1000;
const CODEX = process.env.CODEX_BIN || '/opt/homebrew/bin/codex';

function send(msg) { process.stdout.write(JSON.stringify(msg) + '\n'); }

const TOOLS = [{
  name: 'generate_image',
  description: 'ChatGPTの画像生成（gpt-image）で画像を1枚作り、out_path にPNGで保存する。商品が写る絵は reference_images に実物の写真を必ず渡す。1枚あたり1〜3分。複数枚は同時に呼んでよい（パソコン全体で同時に作るのは3枚までに道具が並ばせる）。',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: '作る絵の指示（日本語でよい）。画像内の文字は一字一句ここに書く' },
      out_path: { type: 'string', description: '保存先の絶対パス（.png）' },
      reference_images: { type: 'array', items: { type: 'string' }, description: '添付する画像の絶対パス（実物の写真・参考レイアウト）。添付1・添付2…の順' },
      aspect: { type: 'string', enum: ['square', 'portrait', 'landscape'], description: '縦横。既定 square' },
    },
    required: ['prompt', 'out_path'],
  },
}];

function isPng(file) {
  try { const b = Buffer.alloc(8); const fd = fs.openSync(file, 'r'); fs.readSync(fd, b, 0, 8, 0); fs.closeSync(fd); return b.toString('hex') === '89504e470d0a1a0a'; } catch { return false; }
}
function pngSize(file) {
  const b = fs.readFileSync(file).subarray(16, 24); return { width: b.readUInt32BE(0), height: b.readUInt32BE(4) };
}

function runCodex(args, cwd) {
  return new Promise((resolve) => {
    // 画像は本人のパーソナルのワークスペースで作る（2026-10-07 本人）。~/.codex-personal にパーソナルでログインしてあればそちらを使う。共有の ~/.codex（チームのワークスペース）は触らない
    const 個人 = path.join(os.homedir(), '.codex-personal');
    const env = fs.existsSync(path.join(個人, 'auth.json')) ? { ...process.env, CODEX_HOME: 個人 } : process.env;
    const p = spawn(CODEX, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    p.stdout.on('data', d => { out += d; if (out.length > 200000) out = out.slice(-100000); });
    p.stderr.on('data', d => { out += d; if (out.length > 200000) out = out.slice(-100000); });
    const t = setTimeout(() => { p.kill('SIGTERM'); }, TIMEOUT_MS);
    p.on('close', code => { clearTimeout(t); resolve({ code, out }); });
    p.on('error', e => { clearTimeout(t); resolve({ code: -1, out: String(e) }); });
  });
}

function 使えるモデル() {
  const 個人 = path.join(os.homedir(), '.codex-personal');
  const home = fs.existsSync(path.join(個人, 'auth.json')) ? 個人 : path.join(os.homedir(), '.codex');
  try {
    const d = JSON.parse(fs.readFileSync(path.join(home, 'models_cache.json'), 'utf8'));
    const ms = (Array.isArray(d) ? d : d.models || []).map(m => m.slug || m.id).filter(x => x && !/review|reserve/.test(x));
    const 好み = ms.find(x => /^gpt-5\.\d+-sol$/.test(x)) || ms[0];
    if (好み) return 好み;
  } catch {}
  return 'gpt-5.6-sol';
}


// 2026-10-15: 3つの会話が同時に十数枚ずつ投げると、codex が「Reconnecting... n/5」で全部落ちた（1枚ずつなら通る）。
// パソコン全体で同時に走る codex を MAX_PARALLEL 本までにする（ロックのファイルを /tmp に置き、空くまで待つ。古いロックは20分で捨てる）
const LOCKDIR = path.join(os.tmpdir(), 'chatgpt-image-locks');
const MAX_PARALLEL = +(process.env.CHATGPT_IMAGE_PARALLEL || 3);
async function 順番を取る() {
  fs.mkdirSync(LOCKDIR, { recursive: true });
  for (;;) {
    const now = Date.now();
    for (const f of fs.readdirSync(LOCKDIR)) { try { if (now - fs.statSync(path.join(LOCKDIR, f)).mtimeMs > 20 * 60 * 1000) fs.rmSync(path.join(LOCKDIR, f), { force: true }); } catch {} }
    for (let i = 0; i < MAX_PARALLEL; i++) {
      const f = path.join(LOCKDIR, 'slot' + i);
      try { fs.writeFileSync(f, String(process.pid), { flag: 'wx' }); return f; } catch {}
    }
    await new Promise(r => setTimeout(r, 3000 + Math.random() * 2000));
  }
}

async function generate({ prompt, out_path, reference_images = [], aspect = 'square' }) {
  if (!path.isAbsolute(out_path)) throw Error('out_path は絶対パスで渡してください');
  for (const f of reference_images) if (!fs.existsSync(f)) throw Error('添付が見つからない: ' + f);
  fs.mkdirSync(path.dirname(out_path), { recursive: true });
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'chatgpt-image-'));
  const target = path.join(work, 'out.png');
  const shape = { square: '正方形（1:1）', portrait: '縦長（2:3）', landscape: '横長（3:2）' }[aspect] || '正方形（1:1）';
  const refs = reference_images.length ? `添付画像は ${reference_images.length} 枚あり、指示の中の「添付1」「添付2」…はこの順番です。\n` : '';
  const task = `組み込みの画像生成ツール（image_gen）を必ず1回だけ使って、次の画像を1枚作ってください。${shape}。
PIL・Python・SVG・HTMLなどで自分で描くことは禁止です。画像生成ツールが使えない場合は、何も作らずに「IMAGE_GEN_UNAVAILABLE」とだけ答えてください。
${refs}生成できたら、出来た画像を ${target} にコピーし、そのパスだけを答えてください。

---- 画像の指示 ----
${prompt}`;
  const lastMsg = path.join(work, 'last.txt');
  // モデルは共有の ~/.codex/config.toml に任せない。そこが今のアカウントで使えないモデル（gpt-6.1-sol）だと絵が1枚も出ない（2026-10-06 実測: このアカウントで通るのは gpt-5.5）
  // 2026-10-15: gpt-5.5 も通らなくなった（「not supported when using Codex with a ChatGPT account」）。名前を決め打ちせず、
  // codex がアカウントから取ってきた使えるモデルの一覧（CODEX_HOME/models_cache.json）の先頭の普通のモデルを使う
  const args = ['exec', '--skip-git-repo-check', '-m', process.env.CHATGPT_IMAGE_MODEL || 使えるモデル(), '--sandbox', 'workspace-write', '-C', work, '-o', lastMsg];
  // --image は後ろの値を全部画像として食うので、指示文を先に置き、画像は最後に並べる
  args.push(task);
  for (const f of reference_images) args.push('--image', f);
  const 札 = await 順番を取る();
  try {
  const started = Date.now();
  let last = null;
  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await runCodex(args, work);
    if (isPng(target)) {
      fs.copyFileSync(target, out_path + '.tmp');
      fs.renameSync(out_path + '.tmp', out_path);  // 途中で読まれても壊れた画像にならないように
      fs.rmSync(work, { recursive: true, force: true });
      return { out_path, ...pngSize(out_path), seconds: Math.round((Date.now() - started) / 1000), attempts: attempt };
    }
    try { last = fs.readFileSync(lastMsg, 'utf8').slice(-800); } catch { last = r.out.slice(-800); }
    if (/IMAGE_GEN_UNAVAILABLE/.test(r.out)) break;
  }
  fs.rmSync(work, { recursive: true, force: true });
  throw Error('画像を作れませんでした。codex の最後の出力:\n' + last);
  } finally { fs.rmSync(札, { force: true }); }
}

let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buf += chunk;
  let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
    if (!line) continue;
    let msg; try { msg = JSON.parse(line); } catch { continue; }
    handle(msg);
  }
});

async function handle(msg) {
  const { id, method, params } = msg;
  if (method === 'initialize') {
    return send({ jsonrpc: '2.0', id, result: { protocolVersion: params?.protocolVersion || '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'chatgpt-image', version: '1.0.0' } } });
  }
  if (method === 'notifications/initialized' || id === undefined) return;
  if (method === 'ping') return send({ jsonrpc: '2.0', id, result: {} });
  if (method === 'tools/list') return send({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
  if (method === 'tools/call') {
    try {
      if (params?.name !== 'generate_image') throw Error('unknown tool ' + params?.name);
      const r = await generate(params.arguments || {});
      return send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify(r) }] } });
    } catch (e) {
      return send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: String(e.message || e) }], isError: true } });
    }
  }
  send({ jsonrpc: '2.0', id, error: { code: -32601, message: 'method not found: ' + method } });
}
