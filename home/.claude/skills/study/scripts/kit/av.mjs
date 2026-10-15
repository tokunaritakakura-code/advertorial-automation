// av.mjs — the "映像インプット脚"(audio-visual ingest) machine path for task-fleet.
// ⚠️ 発火条件を絞る武器：動画の"映像そのもの"を広告制作/解体のインプットに畳み込む
// タスクが来た時だけ使う（例: EC勝ち広告のカット割り・テロップ・見せ方を9ビートに分解、
// 競合クリエイティブの骨格抽出）。喋りだけ要るなら yt.mjs で足りる——ここは呼ばない。
//
// 何をするか: 動画URL（またはチャンネル/ハンドル/プレイリスト）を渡すと、
//   1) 映像本体を yt-dlp で取得（解像度は既定720pに制限＝速さ優先）
//   2) ffmpeg のシーン変化検出で"カットの変わり目フレームだけ"抽出（畳む。全フレームは取らない）
//      カットが少ない静的動画は N秒間隔サンプリングに自動フォールバック
//   3) 各フレームに、その時刻の字幕を紐付けて 1ビート = {t, frame, caption} を作る
//   4) フレームを時刻ラベル付きの contact sheet(モンタージュ)に連結（下流のvision解析の入力）
// OCR は積まない：テロップは下流の vision 解析エージェントがモンタージュを読む（binary非依存）。
//
// Usage:
//   node av.mjs <videoUrl> [videoUrl2 ...]
//   node av.mjs --channel https://www.youtube.com/@handle --limit 10
//   echo '[{"id":"a","url":"https://youtu.be/…"}]' | node av.mjs
//   node av.mjs jobs.json
//
// Flags:
//   --channel        入力をチャンネル/プレイリスト扱いにして動画一覧へ展開
//   --limit N        チャンネル展開時に先頭N本だけ
//   --scene F        シーン変化しきい値 0..1（既定 0.30。小さいほど多くのカットを拾う）
//   --max-frames N   1本あたりのフレーム上限（既定 40。超えたら等間隔に間引く）
//   --every S        カットが少ない時のフォールバック間隔秒（既定 4）
//   --min-frames N   これ未満しかカットが無ければ--every間隔サンプリングに切替（既定 6）
//   --height H       ダウンロード解像度上限（既定 720）
//   --cols C         モンタージュの列数（既定 5）
//   --lang a,b       字幕言語の優先順（既定 ja,en。ビート紐付け用）
//   --out DIR        出力ルート（既定 ./av-out）
//   --keep-video     抽出後も動画ファイルを残す（既定は消す）
//
// Env:
//   YT_DLP / FFMPEG / FFPROBE  各バイナリのパス上書き
//   POOL       同時処理本数（既定 3。映像DLは重いので yt.mjs より控えめ）
//   TIMEOUT    1本あたりの上限ms（既定 300000）
//
// Output (stdout JSON):
//   [{ id, url, videoId, title, channel, ok, route, duration, width, height,
//      frameCount, source, frames:[{t, path, caption}], montages:[path…],
//      transcriptChars, error, ms }]
//     route:"browser" に降格するのは動画取得不能や字幕/フレーム0の時。

import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const flagSet = new Set(args.filter(a => a.startsWith('--') && !a.includes('=')));
const VAL_FLAGS = new Set(['limit', 'scene', 'max-frames', 'every', 'min-frames', 'height', 'cols', 'lang', 'out']);
function flagVal(name, def) {
  const eq = args.find(a => a.startsWith(`--${name}=`));
  if (eq) return eq.split('=').slice(1).join('=');
  const idx = args.indexOf(`--${name}`);
  if (idx >= 0) { const nxt = args[idx + 1]; if (nxt && !nxt.startsWith('--')) return nxt; }
  return def;
}
const positional = args.filter((a, i) => {
  if (a.startsWith('--')) return false;
  const prev = args[i - 1];
  if (prev && prev.startsWith('--') && VAL_FLAGS.has(prev.slice(2))) return false;
  return true;
});

const AS_CHANNEL = flagSet.has('--channel');
const LIMIT = parseInt(flagVal('limit', '0'), 10) || 0;
const SCENE = parseFloat(flagVal('scene', '0.30'));
const MAX_FRAMES = parseInt(flagVal('max-frames', '40'), 10);
const EVERY = parseFloat(flagVal('every', '4'));
const MIN_FRAMES = parseInt(flagVal('min-frames', '6'), 10);
const HEIGHT = parseInt(flagVal('height', '720'), 10);
const COLS = parseInt(flagVal('cols', '5'), 10);
const LANGS = (flagVal('lang', 'ja,en') || 'ja,en').split(',').map(s => s.trim()).filter(Boolean);
const OUT_ROOT = path.resolve(flagVal('out', 'av-out'));
const KEEP_VIDEO = flagSet.has('--keep-video');
const POOL = parseInt(process.env.POOL || '3', 10);
const TIMEOUT = parseInt(process.env.TIMEOUT || '300000', 10);

// ---- resolve binaries -----------------------------------------------------
function resolveBin(env, name, moduleFallback) {
  if (process.env[env]) return { cmd: process.env[env], pre: [] };
  const which = spawnSync('bash', ['-lc', `command -v ${name}`], { encoding: 'utf8' });
  if (which.status === 0 && which.stdout.trim()) return { cmd: which.stdout.trim(), pre: [] };
  const globs = spawnSync('bash', ['-lc', `ls ~/Library/Python/*/bin/${name} ~/.local/bin/${name} /opt/homebrew/bin/${name} 2>/dev/null | head -1`], { encoding: 'utf8' });
  if (globs.stdout.trim()) return { cmd: globs.stdout.trim(), pre: [] };
  return moduleFallback || { cmd: name, pre: [] };
}
const YTDLP = resolveBin('YT_DLP', 'yt-dlp', { cmd: 'python3', pre: ['-m', 'yt_dlp'] });
const FFMPEG = resolveBin('FFMPEG', 'ffmpeg');
const FFPROBE = resolveBin('FFPROBE', 'ffprobe');
const PYTHON = process.env.PYTHON || 'python3';
const TILE_PY = path.join(__dirname, 'tile.py'); // reserved for downstream crop&zoom

const EXTRACTOR_ARGS = 'youtube:player_client=default,android,web';

function run(bin, extra, { timeout = TIMEOUT, wantJson = false, input = null } = {}) {
  return new Promise((resolve) => {
    const argv = [...bin.pre, ...extra];
    const child = spawn(bin.cmd, argv, { encoding: 'utf8' });
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
    if (input != null) { child.stdin.write(input); child.stdin.end(); }
  });
}
const ytdlp = (extra, opts) => run(YTDLP, ['--extractor-args', EXTRACTOR_ARGS, ...extra], opts);
const ffmpeg = (extra, opts) => run(FFMPEG, ['-hide_banner', '-nostdin', ...extra], opts);

// ---- input ----------------------------------------------------------------
function readStdin() {
  try { if (process.stdin.isTTY) return ''; return fs.readFileSync(0, 'utf8').trim(); } catch { return ''; }
}
const VIDEO_EXT_RE = /\.(mp4|mkv|webm|mov|m4v|avi)$/i;
function loadJobs() {
  // a single local .json (not a video) = a jobs file
  if (positional.length === 1 && fs.existsSync(positional[0]) && !/^https?:/i.test(positional[0]) && !VIDEO_EXT_RE.test(positional[0])) {
    return JSON.parse(fs.readFileSync(positional[0], 'utf8'));
  }
  if (positional.length) return positional.map((u, i) => ({ id: String(i), url: u }));
  const stdin = readStdin();
  if (stdin) { const p = JSON.parse(stdin); return Array.isArray(p) ? p : [p]; }
  return [];
}
// A local video file or a direct media URL (Meta/TikTok CDN .mp4) — fed straight
// to ffmpeg, no yt-dlp download (which YouTube now 403s without a PO token).
function isLocalVideo(u) { return !/^https?:/i.test(u) && VIDEO_EXT_RE.test(u) && fs.existsSync(u); }
function isDirectMedia(u) { return /^https?:/i.test(u) && VIDEO_EXT_RE.test(u.split('?')[0]); }

const CHANNEL_RE = /(\/@|\/channel\/|\/c\/|\/user\/|[?&]list=|\/playlist)/i;
function looksLikeChannel(url) { return AS_CHANNEL || CHANNEL_RE.test(url); }
function videoIdOf(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1);
    return u.searchParams.get('v') || null;
  } catch { return null; }
}
function safeName(s) { return String(s || 'vid').replace(/[^\w.-]+/g, '_').slice(0, 60); }

// ---- channel -> video list (same normalization as yt.mjs) -----------------
function normalizeChannelUrl(url) {
  try {
    const u = new URL(url);
    if (u.searchParams.get('list')) return url;
    if (/\/(videos|shorts|streams|playlists|featured)\/?$/i.test(u.pathname)) return url;
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
  const { json } = await ytdlp(extra, { wantJson: true, timeout: 90000 });
  if (!json || !json.length) return [];
  return json.map(e => ({
    id: e.id,
    url: e.url || `https://www.youtube.com/watch?v=${e.id}`,
    title: e.title || null,
    channel: e.channel || e.uploader || null,
  }));
}

// ---- VTT -> timed cues (for pairing captions to frames) -------------------
function tsToSec(ts) {
  const m = ts.match(/(\d{2}):(\d{2}):(\d{2})\.(\d{3})/);
  if (!m) return null;
  return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / 1000;
}
function parseVttCues(vtt) {
  const lines = vtt.split(/\r?\n/);
  const cues = [];
  let cur = null;
  for (let raw of lines) {
    if (raw.includes('-->')) {
      const m = raw.match(/(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})/);
      if (m) { if (cur) cues.push(cur); cur = { start: tsToSec(m[1]), end: tsToSec(m[2]), text: '' }; }
      continue;
    }
    if (!cur) continue;
    if (/^WEBVTT|^(Kind|Language):|^NOTE\b/.test(raw)) continue;
    if (/^\d+$/.test(raw.trim())) continue;
    let t = raw.replace(/<\d{2}:\d{2}:\d{2}\.\d{3}>/g, '').replace(/<\/?c[^>]*>/g, '').replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"')
      .replace(/\s+/g, ' ').trim();
    if (!t) continue;
    cur.text = cur.text ? (cur.text.endsWith(t) || t === cur.text ? cur.text : cur.text + ' ' + t) : t;
  }
  if (cur) cues.push(cur);
  // de-dup rolling captions
  const seen = new Set(); const out = [];
  for (const c of cues) { const k = c.text; if (seen.has(k)) continue; seen.add(k); out.push(c); }
  return out;
}
function captionAt(cues, t) {
  if (!cues.length) return null;
  // nearest cue whose window contains t, else closest by start
  let best = null, bestD = Infinity;
  for (const c of cues) {
    if (t >= c.start && t <= c.end) return c.text;
    const d = Math.min(Math.abs(t - c.start), Math.abs(t - c.end));
    if (d < bestD) { bestD = d; best = c; }
  }
  return bestD <= 3 ? best.text : null; // only attach if within 3s
}

// ---- ffprobe: duration/size ----------------------------------------------
async function probe(file) {
  const { out } = await run(FFPROBE, ['-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'format=duration:stream=width,height', '-of', 'json', file], { timeout: 30000 });
  try {
    const j = JSON.parse(out);
    const s = (j.streams && j.streams[0]) || {};
    return { duration: parseFloat((j.format && j.format.duration) || 0) || null, width: s.width || null, height: s.height || null };
  } catch { return { duration: null, width: null, height: null }; }
}

// ---- scene-cut frame extraction ------------------------------------------
// Emit frames at scene changes; showinfo gives pts_time per emitted frame, in
// output order, so frame N's timestamp = the Nth pts_time line.
async function extractScenes(video, framesDir, thr) {
  const patt = path.join(framesDir, 'f_%04d.jpg');
  const { err } = await ffmpeg(['-i', video, '-vf', `select='gt(scene,${thr})',showinfo`,
    '-vsync', 'vfr', '-q:v', '3', patt]);
  const times = [];
  const re = /pts_time:([0-9.]+)/g; let m;
  while ((m = re.exec(err)) !== null) times.push(parseFloat(m[1]));
  const files = fs.readdirSync(framesDir).filter(f => /^f_\d+\.jpg$/.test(f)).sort();
  return files.map((f, i) => ({ path: path.join(framesDir, f), t: times[i] != null ? times[i] : null }));
}
// Fallback: sample one frame every `every` seconds.
async function extractInterval(video, framesDir, duration, every) {
  const patt = path.join(framesDir, 'g_%04d.jpg');
  const fps = 1 / Math.max(0.5, every);
  await ffmpeg(['-i', video, '-vf', `fps=${fps}`, '-q:v', '3', patt]);
  const files = fs.readdirSync(framesDir).filter(f => /^g_\d+\.jpg$/.test(f)).sort();
  return files.map((f, i) => ({ path: path.join(framesDir, f), t: +(i * every).toFixed(2) }));
}
// Evenly thin a frame list down to <= max, keeping first & last.
function thin(frames, max) {
  if (frames.length <= max) return frames;
  const step = frames.length / max;
  const out = [];
  for (let i = 0; i < max; i++) out.push(frames[Math.min(frames.length - 1, Math.round(i * step))]);
  // ensure last frame present
  if (out[out.length - 1] !== frames[frames.length - 1]) out[out.length - 1] = frames[frames.length - 1];
  return out;
}

// ---- montage (contact sheet) via ffmpeg tile ------------------------------
function fmtT(t) {
  if (t == null) return '?';
  const s = Math.floor(t % 60), m = Math.floor(t / 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}
// Build labelled contact-sheets via contact.py (PIL) — reliable across ffmpeg
// builds that lack drawtext/libfreetype. Each cell = frame + "#n  m:ss" + caption.
const CONTACT_PY = path.join(__dirname, 'contact.py');
async function buildMontages(frames, outDir, cols) {
  if (!frames.length) return [];
  const spec = JSON.stringify({
    frames: frames.map(f => ({ path: f.path, t: f.t, caption: f.caption || null })),
    out_dir: outDir, cols, rows_per_sheet: 6, cell_w: 480, caption_chars: 48,
  });
  const { out, err } = await run({ cmd: PYTHON, pre: [] }, [CONTACT_PY], { input: spec, timeout: 120000 });
  try { const j = JSON.parse(out.trim().split('\n').pop()); return j.montages || []; }
  catch { if (err) console.error('av: contact.py err:', err.split('\n').slice(-3).join(' ')); return []; }
}

// ---- per-video pipeline ---------------------------------------------------
async function processOne(job) {
  const started = Date.now();
  const url = job.url;
  const vid = job.id || videoIdOf(url) || 'vid';
  const base = {
    id: job.id ?? url, url, videoId: videoIdOf(url), title: job.title || null, channel: job.channel || null,
    ok: false, route: null, duration: null, width: null, height: null, frameCount: 0, source: null,
    frames: [], montages: [], transcriptChars: 0, error: null,
  };
  if (!url || (!/^https?:/i.test(url) && !isLocalVideo(url))) return { ...base, error: 'invalid url or missing local file', ms: 0 };

  const workDir = path.join(OUT_ROOT, safeName(videoIdOf(url) || (isLocalVideo(url) ? path.basename(url).replace(VIDEO_EXT_RE, '') : vid)));
  const framesDir = path.join(workDir, 'frames');
  fs.mkdirSync(framesDir, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'av-'));
  try {
    let videoFile = null;
    let cues = [];

    if (isLocalVideo(url)) {
      // local file: no fetch, straight to ffmpeg
      videoFile = url;
      base.title = base.title || path.basename(url);
      base.source = 'local';
    } else if (isDirectMedia(url)) {
      // direct CDN media (Meta/TikTok mp4): plain download, no yt-dlp/PO-token
      const dest = path.join(tmp, 'media' + (path.extname(url.split('?')[0]) || '.mp4'));
      const dl = await run({ cmd: 'curl', pre: [] }, ['-sL', '--max-time', String(Math.floor(TIMEOUT / 1000)), '-o', dest, url]);
      if (fs.existsSync(dest) && fs.statSync(dest).size > 1024) { videoFile = dest; base.source = 'direct'; }
      else return { ...base, route: 'browser', error: 'direct media download failed', ms: Date.now() - started };
    } else {
      // 1) metadata (title/channel/duration) — one light call
      if (!base.title || !base.channel) {
        const { json } = await ytdlp(['--skip-download', '--dump-json', '--no-warnings', url], { wantJson: true, timeout: 60000 });
        const meta = json && json[0];
        if (meta) { base.title = base.title || meta.title || null; base.channel = base.channel || meta.channel || meta.uploader || null; }
      }
      // 2) download the video (capped height for speed) + subtitles
      const outTmpl = path.join(tmp, '%(id)s.%(ext)s');
      const fmt = `bv*[height<=${HEIGHT}]+ba/b[height<=${HEIGHT}]/best[height<=${HEIGHT}]/best`;
      const langArg = LANGS.map(l => `${l}.*`).concat(LANGS).join(',');
      // cookies from the browser-agent Chromium profile help YouTube's PO-token wall
      const cookieArgs = process.env.AV_COOKIES_BROWSER ? ['--cookies-from-browser', process.env.AV_COOKIES_BROWSER]
        : (process.env.AV_COOKIES_FILE ? ['--cookies', process.env.AV_COOKIES_FILE] : []);
      await ytdlp([...cookieArgs, '-f', fmt, '--merge-output-format', 'mp4',
        '--write-subs', '--write-auto-subs', '--sub-langs', langArg, '--sub-format', 'vtt/best',
        '--no-warnings', '-o', outTmpl, url]);
      let vids = fs.readdirSync(tmp).filter(f => /\.(mp4|mkv|webm|mov)$/i.test(f));
      if (!vids.length) {
        await new Promise(r => setTimeout(r, 1500));
        await ytdlp([...cookieArgs, '-f', fmt, '--merge-output-format', 'mp4', '--no-warnings', '-o', outTmpl, url]);
        vids = fs.readdirSync(tmp).filter(f => /\.(mp4|mkv|webm|mov)$/i.test(f));
      }
      if (!vids.length) return { ...base, route: 'browser', error: 'could not download video (YouTube PO-token/403; use browser-capture or feed a direct .mp4)', ms: Date.now() - started };
      videoFile = path.join(tmp, vids[0]);
      // captions (optional pairing)
      const vttFiles = fs.readdirSync(tmp).filter(f => f.endsWith('.vtt'));
      if (vttFiles.length) {
        const manual = vttFiles.find(f => !/auto/i.test(f)) || vttFiles[0];
        try { cues = parseVttCues(fs.readFileSync(path.join(tmp, manual), 'utf8')); } catch {}
      }
    }
    const transcriptChars = cues.reduce((a, c) => a + c.text.length, 0);

    // 3) probe + frame extraction
    const meta = await probe(videoFile);
    base.duration = meta.duration; base.width = meta.width; base.height = meta.height;

    let frames = await extractScenes(videoFile, framesDir, SCENE);
    let source = 'scene-cut';
    if (frames.length < MIN_FRAMES && meta.duration) {
      // static video (talking head / single shot): sample by interval instead
      for (const f of frames) { try { fs.rmSync(f.path); } catch {} }
      frames = await extractInterval(videoFile, framesDir, meta.duration, EVERY);
      source = 'interval';
    }
    if (!frames.length) return { ...base, route: 'browser', error: 'no frames extracted', transcriptChars, ms: Date.now() - started };
    frames = thin(frames, MAX_FRAMES);

    // 4) pair captions + copy frames into stable workDir
    const beats = frames.map((f, i) => {
      const dest = path.join(framesDir, `beat_${String(i + 1).padStart(3, '0')}.jpg`);
      try { fs.copyFileSync(f.path, dest); } catch {}
      return { t: f.t, path: dest, caption: captionAt(cues, f.t) };
    });
    // remove the raw extractor frames, keep only beat_*.jpg
    for (const f of frames) { if (!/beat_\d+\.jpg$/.test(f.path)) { try { fs.rmSync(f.path); } catch {} } }

    // 5) montages
    const montages = await buildMontages(beats, workDir, COLS);

    if (KEEP_VIDEO) { try { fs.copyFileSync(videoFile, path.join(workDir, 'video' + path.extname(videoFile))); } catch {} }

    return {
      ...base, ok: true, source, frameCount: beats.length,
      frames: beats, montages, transcriptChars, ms: Date.now() - started,
    };
  } catch (e) {
    return { ...base, route: 'browser', error: e.message, ms: Date.now() - started };
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
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
  console.error('av: no input. usage: node av.mjs <videoUrl…>  |  node av.mjs --channel <url> [--limit N]');
  process.exit(2);
}
fs.mkdirSync(OUT_ROOT, { recursive: true });

const expanded = [];
for (const j of jobs) {
  if (looksLikeChannel(j.url)) {
    console.error(`av: expanding channel ${j.url} …`);
    const vids = await expandChannel(j.url);
    if (!vids.length) console.error(`av: WARN channel expanded to 0 videos: ${j.url}`);
    expanded.push(...vids);
  } else expanded.push(j);
}
if (!expanded.length) { console.error('av: nothing to process after expansion'); process.exit(2); }
console.error(`av: processing ${expanded.length} video(s) POOL=${POOL} scene=${SCENE} maxFrames=${MAX_FRAMES} height=${HEIGHT} → ${OUT_ROOT}`);

const results = await runPool(expanded, processOne);
console.log(JSON.stringify(results, null, 2));

const failed = results.filter(r => !r.ok).length;
for (const r of results) {
  const head = r.ok
    ? `${r.source} ${r.frameCount}frames ${r.montages.length}sheet ${Math.round(r.ms / 1000)}s`
    : `FAILED -> ${r.route}: ${r.error}`;
  console.error(`  • ${(r.title || r.videoId || r.url || '').slice(0, 50)} — ${head}`);
}
console.error(`av: done. ${results.length - failed}/${results.length} processed. output under ${OUT_ROOT}`);
process.exit(failed === results.length ? 1 : 0);
