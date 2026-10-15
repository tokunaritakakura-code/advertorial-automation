// yt.mjs — the "YTクリエイター動画インプット脚" machine path for task-fleet.
// ⚠️ 発火条件を絞る武器：YTクリエイターの動画を"インプット素材"として取り込む
// タスクが来た時だけ使う（例: あるチャンネルの全動画を解析して型を抽出）。
// 一般の調査で YouTube を1本読むだけなら reader.mjs / browser で足りる——ここは呼ばない。
//
// 何をするか: 動画URL（またはチャンネル/ハンドル/プレイリスト）を渡すと、字幕を
// ブラウザ描画なしで機械経路(yt-dlp)で取得し、VTTを"クリーンなプレーン文字起こし"に
// 畳んで JSON で返す。reader.mjs と同じく並列プール・降格シグナルを内蔵。
// チャンネルを渡せば動画一覧に展開してから各本を並列で文字起こしする。
//
// Usage:
//   node yt.mjs <videoUrl> [videoUrl2 ...]
//   node yt.mjs --channel https://www.youtube.com/@handle          # チャンネル→全動画に展開
//   node yt.mjs --channel https://youtube.com/@handle --limit 20   # 直近N本だけ
//   echo '[{"id":"a","url":"https://youtu.be/…"}]' | node yt.mjs   # JSON array in
//   node yt.mjs jobs.json                                          # or a file
//
// Flags:
//   --channel       入力をチャンネル/プレイリスト扱いにして動画一覧へ展開
//   --limit N       チャンネル展開時に先頭N本だけ（既定: 全部）
//   --lang a,b,c    優先字幕言語（既定: "en,ja"。手動字幕→自動字幕の順で探す）
//   --text          文字起こしを人間可読で連結出力（JSONでなく）
//   --keep-vtt      デバッグ用に生VTTを残す（既定は消す）
//
// Env:
//   YT_DLP     yt-dlp のパス（既定: PATH→~/Library/Python/*/bin→python3 -m yt_dlp）
//   POOL       同時文字起こし数（既定: 4）
//   TIMEOUT    1本あたりの上限ms（既定: 120000）
//
// Output (stdout JSON):
//   [{ id, url, videoId, title, channel, ok, source, lang, chars, words, ms, transcript, error }]
//     source: "manual-sub" | "auto-sub" | null   （ok:false のとき route:"browser"）

import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const flagSet = new Set(args.filter(a => a.startsWith('--') && !a.includes('=')));
function flagVal(name, def) {
  const hit = args.find(a => a.startsWith(`--${name}=`) || a === `--${name}`);
  if (!hit) return def;
  if (hit.includes('=')) return hit.split('=').slice(1).join('=');
  // support "--limit 20" style
  const idx = args.indexOf(hit);
  const nxt = args[idx + 1];
  return nxt && !nxt.startsWith('--') ? nxt : def;
}
const positional = args.filter((a, i) => {
  if (a.startsWith('--')) return false;
  // drop a value that belongs to a preceding "--flag value"
  const prev = args[i - 1];
  if (prev && (prev === '--limit' || prev === '--lang')) return false;
  return true;
});

const AS_CHANNEL = flagSet.has('--channel');
const LIMIT = parseInt(flagVal('limit', '0'), 10) || 0;
const LANGS = (flagVal('lang', 'en,ja') || 'en,ja').split(',').map(s => s.trim()).filter(Boolean);
const KEEP_VTT = flagSet.has('--keep-vtt');
const POOL = parseInt(process.env.POOL || '4', 10);
const TIMEOUT = parseInt(process.env.TIMEOUT || '120000', 10);

// ---- resolve yt-dlp -------------------------------------------------------
function resolveYtDlp() {
  if (process.env.YT_DLP) return { cmd: process.env.YT_DLP, pre: [] };
  // on PATH?
  const which = spawnSync('bash', ['-lc', 'command -v yt-dlp'], { encoding: 'utf8' });
  if (which.status === 0 && which.stdout.trim()) return { cmd: which.stdout.trim(), pre: [] };
  // common pip user install
  const globs = spawnSync('bash', ['-lc', 'ls ~/Library/Python/*/bin/yt-dlp ~/.local/bin/yt-dlp 2>/dev/null | head -1'], { encoding: 'utf8' });
  if (globs.stdout.trim()) return { cmd: globs.stdout.trim(), pre: [] };
  // python module fallback
  return { cmd: 'python3', pre: ['-m', 'yt_dlp'] };
}
const YTDLP = resolveYtDlp();

// YouTube auto-sub extraction is flaky through the default web client; the
// android player client is the known-good workaround.
const EXTRACTOR_ARGS = 'youtube:player_client=default,android,web';

function runYtDlp(extra, { timeout = TIMEOUT, wantJson = false } = {}) {
  return new Promise((resolve) => {
    const argv = [...YTDLP.pre, '--extractor-args', EXTRACTOR_ARGS, ...extra];
    const child = spawn(YTDLP.cmd, argv, { encoding: 'utf8' });
    let out = '', err = '';
    const timer = setTimeout(() => { child.kill('SIGKILL'); }, timeout);
    child.stdout.on('data', d => out += d);
    child.stderr.on('data', d => err += d);
    child.on('error', e => { clearTimeout(timer); resolve({ code: -1, out, err: err + e.message }); });
    child.on('close', code => {
      clearTimeout(timer);
      if (wantJson) {
        const items = out.split('\n').filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
        resolve({ code, out, err, json: items });
      } else resolve({ code, out, err });
    });
  });
}

// ---- input ----------------------------------------------------------------
function readStdin() {
  try { if (process.stdin.isTTY) return ''; return fs.readFileSync(0, 'utf8').trim(); } catch { return ''; }
}
function loadJobs() {
  if (positional.length === 1 && fs.existsSync(positional[0]) && !/^https?:/i.test(positional[0])) {
    return JSON.parse(fs.readFileSync(positional[0], 'utf8'));
  }
  if (positional.length) return positional.map((url, i) => ({ id: String(i), url }));
  const stdin = readStdin();
  if (stdin) { const p = JSON.parse(stdin); return Array.isArray(p) ? p : [p]; }
  return [];
}

const CHANNEL_RE = /(\/@|\/channel\/|\/c\/|\/user\/|[?&]list=|\/playlist)/i;
function looksLikeChannel(url) { return AS_CHANNEL || CHANNEL_RE.test(url); }
function videoIdOf(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1);
    return u.searchParams.get('v') || null;
  } catch { return null; }
}

// ---- channel -> video list ------------------------------------------------
// Normalize a bare channel/handle URL to its uploads (/videos) tab so --limit N
// is honest — otherwise a /@handle URL fans out across Videos+Shorts+Streams tabs
// and --limit counts unpredictably. Leave playlists (list=) and explicit tabs alone.
function normalizeChannelUrl(url) {
  try {
    const u = new URL(url);
    if (u.searchParams.get('list')) return url;                       // playlist: as-is
    if (/\/(videos|shorts|streams|playlists|featured)\/?$/i.test(u.pathname)) return url; // explicit tab
    if (/(\/@[^/]+|\/channel\/[^/]+|\/c\/[^/]+|\/user\/[^/]+)\/?$/i.test(u.pathname)) {
      u.pathname = u.pathname.replace(/\/$/, '') + '/videos';
      return u.toString();
    }
    return url;
  } catch { return url; }
}
async function expandChannel(url) {
  url = normalizeChannelUrl(url);
  const extra = ['--flat-playlist', '--dump-json'];
  if (LIMIT) extra.push('--playlist-end', String(LIMIT));
  extra.push(url);
  const { json } = await runYtDlp(extra, { wantJson: true, timeout: 90000 });
  if (!json || !json.length) return [];
  return json.map(e => ({
    id: e.id,
    url: e.url || `https://www.youtube.com/watch?v=${e.id}`,
    title: e.title || null,
    channel: e.channel || e.uploader || null,
  }));
}

// ---- VTT -> clean transcript ----------------------------------------------
function cleanVtt(vtt) {
  const lines = vtt.split(/\r?\n/);
  const out = [];
  let last = '';
  for (let raw of lines) {
    let line = raw;
    if (!line.trim()) continue;
    if (/^WEBVTT/.test(line)) continue;
    if (/^(Kind|Language):/i.test(line)) continue;
    if (/^NOTE\b/.test(line)) continue;
    if (line.includes('-->')) continue;          // timestamp cue line
    if (/^\d+$/.test(line.trim())) continue;      // numeric cue index
    // strip inline timing tags <00:00:01.000> and <c> ... </c> styling
    line = line.replace(/<\d{2}:\d{2}:\d{2}\.\d{3}>/g, '');
    line = line.replace(/<\/?c[^>]*>/g, '');
    line = line.replace(/<[^>]+>/g, '');
    line = line.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
    line = line.replace(/\s+/g, ' ').trim();
    if (!line) continue;
    if (line === last) continue;                  // rolling-caption dupe
    // auto-subs often repeat previous line as a prefix of the next
    if (last && line.startsWith(last) && line.length > last.length) {
      out[out.length - 1] = line;                 // upgrade the growing line
    } else if (last && last.endsWith(line)) {
      // fragment already contained — skip
    } else {
      out.push(line);
    }
    last = line;
  }
  return out.join(' ').replace(/\s+/g, ' ').trim();
}

// ---- per-video transcription (the ladder) ---------------------------------
async function transcribeOne(job) {
  const started = Date.now();
  const url = job.url;
  const vid = job.id || videoIdOf(url) || 'vid';
  const base = { id: job.id ?? url, url, videoId: videoIdOf(url), title: job.title || null, channel: job.channel || null, source: null, route: null, lang: null, chars: 0, words: 0, transcript: null, error: null };
  if (!url || !/^https?:/i.test(url)) return { ...base, ok: false, error: 'invalid url', ms: 0 };

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yt-'));
  const outTmpl = path.join(tmp, '%(id)s.%(ext)s');
  try {
    const langArg = LANGS.map(l => `${l}.*`).concat(LANGS).join(',');
    const extra = [
      '--skip-download',
      '--write-subs', '--write-auto-subs',
      '--sub-langs', langArg,
      '--sub-format', 'vtt/best',
      '--no-warnings',
      '-o', outTmpl,
      url,
    ];
    await runYtDlp(extra);

    // find the best VTT: prefer a manual sub in preferred lang order, else auto
    let files = fs.readdirSync(tmp).filter(f => f.endsWith('.vtt'));
    if (!files.length) {
      // one structured retry — an empty result is usually a transient YT throttle
      // under concurrency, not a genuinely caption-less video (proven by re-run).
      await new Promise(r => setTimeout(r, 1500));
      await runYtDlp(extra);
      files = fs.readdirSync(tmp).filter(f => f.endsWith('.vtt'));
    }
    if (!files.length) {
      return { ...base, ok: false, route: 'browser', error: 'no subtitles after retry (try browser/whisper)', ms: Date.now() - started };
    }
    const pick = (pred) => files.find(pred);
    let chosen = null, source = null, lang = null;
    for (const l of LANGS) {
      const manual = pick(f => f.includes(`.${l}`) && !f.includes('.auto') || new RegExp(`\\.${l}(\\.|-)`).test(f) && !/auto/i.test(f));
      if (manual) { chosen = manual; source = 'manual-sub'; lang = l; break; }
    }
    if (!chosen) {
      // any manual (non-auto) file
      const anyManual = pick(f => !/auto/i.test(f) && !/orig/i.test(f));
      if (anyManual) { chosen = anyManual; source = 'manual-sub'; }
    }
    if (!chosen) { chosen = files[0]; source = 'auto-sub'; }
    if (!lang) { const m = chosen.match(/\.([a-z]{2}(?:-[A-Za-z]+)?)\./); lang = m ? m[1] : null; }

    const vtt = fs.readFileSync(path.join(tmp, chosen), 'utf8');
    const transcript = cleanVtt(vtt);
    if (!transcript) return { ...base, ok: false, route: 'browser', error: 'empty transcript after clean', ms: Date.now() - started };
    const words = transcript.split(/\s+/).filter(Boolean).length;
    return { ...base, ok: true, source, lang, chars: transcript.length, words, transcript, ms: Date.now() - started };
  } catch (e) {
    return { ...base, ok: false, route: 'browser', error: e.message, ms: Date.now() - started };
  } finally {
    if (!KEEP_VTT) { try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} }
  }
}

// ---- concurrency pool -----------------------------------------------------
async function runPool(jobs, fn) {
  const results = new Array(jobs.length);
  let next = 0;
  async function worker() { while (next < jobs.length) { const i = next++; results[i] = await fn(jobs[i]); } }
  await Promise.all(Array.from({ length: Math.min(POOL, jobs.length) }, worker));
  return results;
}

// ---- main -----------------------------------------------------------------
let jobs = loadJobs();
if (!jobs.length) {
  console.error('yt: no input. usage: node yt.mjs <videoUrl…>  |  node yt.mjs --channel <channelUrl> [--limit N]');
  process.exit(2);
}

// expand any channel/playlist inputs into video jobs
const expanded = [];
for (const j of jobs) {
  if (looksLikeChannel(j.url)) {
    console.error(`yt: expanding channel ${j.url} …`);
    const vids = await expandChannel(j.url);
    if (!vids.length) console.error(`yt: WARN channel expanded to 0 videos: ${j.url}`);
    expanded.push(...vids);
  } else {
    expanded.push(j);
  }
}
if (!expanded.length) { console.error('yt: nothing to transcribe after expansion'); process.exit(2); }
console.error(`yt: transcribing ${expanded.length} video(s) with POOL=${POOL} …`);

const results = await runPool(expanded, transcribeOne);

if (flagSet.has('--text')) {
  for (const r of results) {
    const head = r.ok ? `${r.source}/${r.lang}, ${r.words}w, ${r.ms}ms` : `FAILED -> ${r.route}: ${r.error}`;
    console.log(`\n===== ${r.title || r.videoId || r.url} (${head}) =====\n`);
    if (r.ok) console.log(r.transcript);
  }
} else {
  console.log(JSON.stringify(results, null, 2));
}

const failed = results.filter(r => !r.ok).length;
console.error(`yt: done. ${results.length - failed}/${results.length} transcribed.`);
process.exit(failed === results.length ? 1 : 0);
