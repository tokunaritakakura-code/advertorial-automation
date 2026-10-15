// grab.mjs — browser-capture fallback for the 映像脚 when yt-dlp can't fetch the
// bytes (YouTube now 403s media without a PO token). Instead of downloading, it
// drives the ALREADY-RUNNING browser-agent Chromium over CDP, SEEKS the <video>
// to evenly-spaced points, and screenshots each — fast (no real-time playback,
// skips ads) and needs no media download. Frames flow into the same contact.py
// montage as av.mjs, so the output shape matches.
//
// ⚠️ Shared live resource: this uses the one CDP browser, so it is SERIAL — do
// NOT fan a fleet of grab.mjs at the same browser. For downloadable sources
// (local files, Meta/TikTok CDN .mp4) use av.mjs instead (parallel-safe).
//
// Usage:
//   node grab.mjs <watchUrl> [--points N] [--out DIR] [--cols C] [--embed]
//
// Flags:
//   --points N   number of frames to sample across the video (default 24)
//   --cols C     montage columns (default 5)
//   --embed      use youtube.com/embed/<id> (fewer ads, simpler player)
//   --out DIR    output root (default ./av-out)
//
// Env: CDP_URL (default http://127.0.0.1:9222)
//
// Output (stdout JSON, single object):
//   { url, videoId, ok, route, duration, frameCount, frames:[{t,path}], montages:[…], error, ms }

import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// playwright: try the browser-agent skill first, then any local install
const PW_ROOTS = [
  '.claude/skills/browser-agent/package.json',
  'Claude Code/package.json',
  'package.json',
].map(p => path.join(process.env.HOME, p));
let chromium = null, pwErr = null;
for (const root of PW_ROOTS) {
  try { chromium = createRequire(root)('playwright').chromium; break; }
  catch (e) { pwErr = e; }
}
if (!chromium) { console.error('grab: playwright not found. tried:\n  ' + PW_ROOTS.join('\n  ') + '\n' + (pwErr && pwErr.message)); process.exit(2); }

const args = process.argv.slice(2);
const flags = new Set(args.filter(a => a.startsWith('--') && !a.includes('=')));
function val(name, def) {
  const eq = args.find(a => a.startsWith(`--${name}=`));
  if (eq) return eq.split('=').slice(1).join('=');
  const i = args.indexOf(`--${name}`);
  if (i >= 0 && args[i + 1] && !args[i + 1].startsWith('--')) return args[i + 1];
  return def;
}
const POINTS = parseInt(val('points', '24'), 10);
const COLS = parseInt(val('cols', '5'), 10);
const EMBED = flags.has('--embed');
const OUT_ROOT = path.resolve(val('out', 'av-out'));
const CDP = process.env.CDP_URL || 'http://127.0.0.1:9222';
const CONTACT_PY = path.join(__dirname, 'contact.py');
const PYTHON = process.env.PYTHON || 'python3';

const url = args.find(a => !a.startsWith('--') && /^https?:/i.test(a));
if (!url) { console.error('grab: no url. usage: node grab.mjs <watchUrl> [--points N]'); process.exit(2); }

function videoIdOf(u) {
  try { const x = new URL(u); if (x.hostname.includes('youtu.be')) return x.pathname.slice(1); return x.searchParams.get('v') || x.pathname.split('/').pop(); }
  catch { return null; }
}
const vid = videoIdOf(url) || 'vid';
const target = EMBED && vid ? `https://www.youtube.com/embed/${vid}?autoplay=1&mute=1` : url;

function fmtT(t) { const s = Math.floor(t % 60), m = Math.floor(t / 60); return `${m}:${String(s).padStart(2, '0')}`; }
function pyContact(frames, outDir, cols) {
  return new Promise((resolve) => {
    const spec = JSON.stringify({ frames, out_dir: outDir, cols, rows_per_sheet: 6, cell_w: 480, caption_chars: 48 });
    const ch = spawn(PYTHON, [CONTACT_PY]);
    let out = '', err = '';
    ch.stdout.on('data', d => out += d); ch.stderr.on('data', d => err += d);
    ch.on('close', () => { try { resolve(JSON.parse(out.trim().split('\n').pop()).montages || []); } catch { if (err) console.error('grab: contact.py', err.slice(-200)); resolve([]); } });
    ch.stdin.write(spec); ch.stdin.end();
  });
}

const started = Date.now();
const workDir = path.join(OUT_ROOT, String(vid).replace(/[^\w.-]+/g, '_'));
const framesDir = path.join(workDir, 'frames');
fs.mkdirSync(framesDir, { recursive: true });

let browser, ctx, page;
const result = { url, videoId: vid, ok: false, route: 'browser', duration: null, frameCount: 0, frames: [], montages: [], error: null, ms: 0 };
try {
  browser = await chromium.connectOverCDP(CDP);
  ctx = browser.contexts()[0] || await browser.newContext();
  page = await ctx.newPage();
  await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 60000 });

  // wait for a <video> element (attached, not necessarily visible — YT keeps it
  // aria-hidden until playback starts)
  await page.waitForSelector('video', { state: 'attached', timeout: 30000 });
  const vh = await page.$('video');
  // kick playback (muted). Try the JS play() first, then click the big play
  // button / video surface as a fallback (autoplay is often gesture-gated).
  await page.evaluate(() => { const v = document.querySelector('video'); if (v) { v.muted = true; v.play().catch(() => {}); } });
  for (const sel of ['button.ytp-large-play-button', '.ytp-large-play-button', 'video']) {
    const started = await page.evaluate(() => { const v = document.querySelector('video'); return v && !v.paused && v.currentTime > 0; });
    if (started) break;
    try { await page.click(sel, { timeout: 2500 }); } catch {}
    await page.waitForTimeout(400);
  }
  // wait until duration is known and finite
  await page.waitForFunction(() => { const v = document.querySelector('video'); return v && isFinite(v.duration) && v.duration > 0; }, { timeout: 30000 });

  // ⚠️ プリロール広告。これを踏むと「広告の25秒」を24分割したシートができる（実測で発生）。
  // 広告が消えるまでスキップを押し続け、--expect があれば長さが本編と一致するまで待つ。
  const EXPECT = parseFloat(val('expect', '0'));
  const adGone = async () => page.evaluate(() => !document.querySelector('.ad-showing, .ytp-ad-player-overlay, .ytp-ad-player-overlay-layout'));
  const dur = async () => page.evaluate(() => document.querySelector('video').duration);
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const ok = await adGone();
    const d = await dur();
    const matches = EXPECT > 0 ? Math.abs(d - EXPECT) / EXPECT < 0.1 : true;
    if (ok && matches) break;
    for (const sel of ['.ytp-skip-ad-button', '.ytp-ad-skip-button-modern', '.ytp-ad-skip-button', 'button.ytp-ad-skip-button-container']) {
      try { await page.click(sel, { timeout: 800 }); break; } catch {}
    }
    await page.evaluate(() => { const v = document.querySelector('video'); if (v && v.paused) v.play().catch(() => {}); });
    await page.waitForTimeout(1500);
  }
  const duration = await dur();
  result.duration = duration;
  if (EXPECT > 0 && Math.abs(duration - EXPECT) / EXPECT >= 0.1) {
    // 本編に到達していない。中途半端なシートを作る方が危ないので落とす
    result.error = `duration ${Math.round(duration)}s != expected ${Math.round(EXPECT)}s（広告を抜けられていない）`;
    result.ms = Date.now() - started;
    console.log(JSON.stringify(result, null, 2));
    console.error('grab: FAILED', result.error);
    await page.close().catch(() => {});
    process.exit(1);
  }

  // hide YouTube player chrome (controls bar, gradients, end-screen cards, pause
  // overlay) so captured frames are clean video pixels, not UI.
  await page.addStyleTag({ content: `
    .ytp-chrome-bottom, .ytp-chrome-top, .ytp-gradient-bottom, .ytp-gradient-top,
    .ytp-ce-element, .ytp-cards-teaser, .ytp-pause-overlay, .ytp-spinner,
    .ytp-watermark, .annotation, .iv-branding, .ytp-paid-content-overlay,
    .ytp-large-play-button, .ytp-endscreen-content { opacity:0 !important; display:none !important; }
  `}).catch(() => {});

  // evenly-spaced sample points (skip the very start/end)
  const n = Math.max(2, POINTS);
  const pts = [];
  for (let i = 0; i < n; i++) pts.push(+(duration * (i + 0.5) / n).toFixed(2));

  const beats = [];
  for (let i = 0; i < pts.length; i++) {
    const t = pts[i];
    // seek and wait for the frame to settle
    await page.evaluate((tt) => { const v = document.querySelector('video'); v.pause(); v.currentTime = tt; }, t);
    await page.waitForFunction((tt) => { const v = document.querySelector('video'); return Math.abs(v.currentTime - tt) < 0.5 && v.readyState >= 2; }, t, { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(120);
    const dest = path.join(framesDir, `beat_${String(i + 1).padStart(3, '0')}.jpg`);
    try { await vh.screenshot({ path: dest, type: 'jpeg', quality: 85 }); beats.push({ t, path: dest, caption: null }); } catch {}
  }
  await page.close().catch(() => {});
  page = null;

  if (!beats.length) { result.error = 'no frames captured'; result.ms = Date.now() - started; console.log(JSON.stringify(result, null, 2)); process.exit(1); }
  const montages = await pyContact(beats.map(b => ({ path: b.path, t: b.t, caption: null })), workDir, COLS);
  result.ok = true; result.route = null; result.frameCount = beats.length; result.frames = beats; result.montages = montages;
  result.ms = Date.now() - started;
  console.log(JSON.stringify(result, null, 2));
  console.error(`grab: ${beats.length} frames, ${montages.length} sheet(s), ${Math.round(result.ms / 1000)}s → ${workDir}`);
} catch (e) {
  result.error = e.message; result.ms = Date.now() - started;
  console.log(JSON.stringify(result, null, 2));
  console.error('grab: FAILED', e.message);
  try { if (page) await page.close(); } catch {}
  process.exit(1);
} finally {
  try { if (browser) await browser.close(); } catch {} // detaches CDP, does not kill the browser
}
