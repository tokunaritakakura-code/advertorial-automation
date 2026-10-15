#!/usr/bin/env node
// capture.mjs <outdir> <pageUrl>
// ページの内部データを実ブラウザで横取り保存し、スクロール連動の動きを実測する。
//  ① 全アセット(連番フレーム画像/.riv/動画/wasm/フォント等)を assets/ に保存(assets-manifest.json)
//  ② drawImage フックで「スクロール位置→canvas(安定セレクタ)→フレーム番号」を実測 → scrollmap.json
//  ③ GSAP等がスクロールで inline の transform/opacity を変える要素を実測 → stylemap.json(scroll-style)
//  ④ スクロール前 opacity≈0 → 後 可視 の要素クラス(reveal) → reveal.json
//  ⑤ desktop(1440)/mobile(390) の両ビューポートで撮る
// canvasは通し番号でなく安定セレクタ(cssPath)で識別し、駆動区間の親要素セレクタも記録(モバイル堅牢化)。
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import os from 'os';

// playwright-core はマシンごとに置き場が違うので実在するものを拾う（env PLAYWRIGHT_CORE で上書き可）
const HOME = os.homedir();
const PW_CANDIDATES = [
  process.env.PLAYWRIGHT_CORE,
  `${HOME}/Claude Code/node_modules/playwright-core/index.mjs`,
  `${HOME}/.claude/skills/surasura/scripts/node_modules/playwright-core/index.mjs`,
].filter(Boolean);
const pwPath = PW_CANDIDATES.find(p => fs.existsSync(p));
if (!pwPath) { console.error('playwright-core が見つからない。npm i playwright-core するか PLAYWRIGHT_CORE を指定'); process.exit(1); }
const { chromium } = await import(pwPath);

const outdir = process.argv[2];
const pageUrl = process.argv[3];
if (!outdir || !pageUrl) { console.error('usage: capture.mjs <outdir> <pageUrl>'); process.exit(1); }
const assetsDir = path.join(outdir, 'assets');
fs.mkdirSync(assetsDir, { recursive: true });

const SKIP_HOST = ['google-analytics', 'googletagmanager', 'facebook.', 'tiktok.', 'hotjar', 'clarity.ms', 'doubleclick', 'bing.com', 'snapchat'];
const MEDIA_EXT = /\.(riv|wasm|mp4|webm|mov|m4v|ogg|png|jpe?g|gif|webp|avif|svg|woff2?|ttf|otf|json|glb|gltf|hdr|ktx2|basis|bin|mp3|wav|m4a)(\?|$)/i;
function localName(url) {
  const u = new URL(url);
  const base = (u.pathname.split('/').pop() || 'index').slice(0, 80).replace(/[^a-zA-Z0-9._-]/g, '_') || 'asset';
  return `${crypto.createHash('sha1').update(url).digest('hex').slice(0, 10)}_${base}`;
}

// headless shell もバージョン番号がマシンごとに違うので、入っている最新版を拾う
const PW_CACHE = `${HOME}/Library/Caches/ms-playwright`;
const SHELL = (() => {
  if (!fs.existsSync(PW_CACHE)) return undefined;
  const dirs = fs.readdirSync(PW_CACHE)
    .filter(d => d.startsWith('chromium_headless_shell-'))
    .sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]));
  for (const d of dirs) {
    const p = path.join(PW_CACHE, d, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell');
    if (fs.existsSync(p)) return p;
  }
  return undefined;
})();
const exe = SHELL;

// ページ実行前に注入: cssPath / drawImageフック / scroll-styleサンプラ
const HOOK = () => {
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id);
    const parts = [];
    let n = el, depth = 0;
    while (n && n.nodeType === 1 && n !== document.body && depth < 7) {
      let sel = n.tagName.toLowerCase();
      const cls = n.classList && [].find.call(n.classList, c => /^[A-Za-z][\w-]*$/.test(c) && !/^svelte|^w-|active|current|visible/.test(c));
      if (cls) sel += '.' + cls;
      const p = n.parentElement;
      if (p) {
        const same = [].filter.call(p.children, c => c.tagName === n.tagName && (!cls || c.classList.contains(cls)));
        if (same.length > 1) sel += ':nth-of-type(' + ([].indexOf.call(p.children, n) + 1) + ')';
      }
      parts.unshift(sel); n = p; depth++;
    }
    return parts.join('>');
  }
  window.__cssPath = cssPath;
  window.__frames = [];
  window.__styles = [];
  const P = CanvasRenderingContext2D.prototype, od = P.drawImage;
  P.drawImage = function (img) {
    try {
      const s = img && (img.currentSrc || img.src);
      if (s) { const m = s.match(/(\d{2,6})\.(?:avif|webp|jpe?g|png)(?:\?|$)/i); if (m) window.__frames.push({ y: window.scrollY, k: cssPath(this.canvas), f: +m[1], src: s }); }
    } catch (e) { } return od.apply(this, arguments);
  };
  let lastY = -1e9;
  window.__sampleNow = function () {
    const y = window.scrollY; if (Math.abs(y - lastY) < 18) return; lastY = y;
    const els = document.querySelectorAll('[style*="transform"],[style*="opacity"]');
    for (let i = 0; i < els.length; i++) {
      const el = els[i], st = el.style, t = st.transform, o = st.opacity;
      if ((t && t !== 'none') || (o !== '' && o !== '1')) {
        let top = 0, m = el; while (m) { top += m.offsetTop; m = m.offsetParent; }
        window.__styles.push({ y, k: window.__cssPath(el), top, t: t || '', o: o || '' });
      }
    }
  };
  addEventListener('scroll', window.__sampleNow, { passive: true });
};

const manifest = {};
const scrollmap = {};   // key -> { desktop:{driverH,vh,base,pad,ext,samples,driverSel}, mobile:{...} }
const stylemap = {};    // key -> { desktop:{top,vh,samples:[{rel,t,o}]}, mobile:{...} }
const revealCls = { desktop: [], mobile: [] };

const browser = await chromium.launch(exe ? { headless: true, executablePath: exe } : { headless: true, channel: 'chrome' });

for (const vp of [{ name: 'desktop', width: 1440, height: 900, mobile: false }, { name: 'mobile', width: 390, height: 844, mobile: true }]) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1, isMobile: vp.mobile, hasTouch: vp.mobile,
    userAgent: vp.mobile ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' : undefined,
  });
  await context.addInitScript(HOOK);
  const page = await context.newPage();
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (!/^https?:/.test(url) || url === pageUrl || SKIP_HOST.some(s => url.includes(s))) return;
      const ct = (resp.headers()['content-type'] || '').toLowerCase();
      if (!(MEDIA_EXT.test(url) || /image|video|font|octet-stream|wasm|json|riv/.test(ct))) return;
      if (manifest[url]) return;
      const body = await resp.body().catch(() => null); if (!body || !body.length) return;
      const file = localName(url); fs.writeFileSync(path.join(assetsDir, file), body);
      manifest[url] = { file, type: ct || 'application/octet-stream', bytes: body.length };
    } catch (e) { }
  });

  await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
  await page.evaluate(() => { document.querySelectorAll('*').forEach(el => { if (parseFloat(getComputedStyle(el).opacity) < 0.05) el.setAttribute('data-cap-hid', '1'); }); }).catch(() => {});
  const H = await page.evaluate(() => document.body.scrollHeight).catch(() => 8000);
  for (let y = 0; y <= H + vp.height; y += 55) {
    await page.evaluate((yy) => window.scrollTo(0, yy), y).catch(() => {});
    await page.waitForTimeout(65);
    await page.evaluate(() => window.__sampleNow && window.__sampleNow()).catch(() => {});
  }
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await page.waitForTimeout(1000);

  revealCls[vp.name] = await page.evaluate(() => {
    const out = {};
    document.querySelectorAll('[data-cap-hid]').forEach(el => {
      const cs = getComputedStyle(el);
      if (parseFloat(cs.opacity) > 0.5 && cs.display !== 'none' && el.className && typeof el.className === 'string')
        el.className.trim().split(/\s+/).forEach(c => { if (c && !/^w-|^svelte|active|current|visible/.test(c)) out[c] = 1; });
      el.removeAttribute('data-cap-hid');
    });
    return Object.keys(out);
  }).catch(() => []);

  const raw = await page.evaluate(() => {
    function driverOf(canvas) {
      const vh = innerHeight; let el = canvas.parentElement, best = null;
      while (el && el !== document.body) { if (el.offsetHeight > vh * 1.3) { best = el; break; } el = el.parentElement; }
      if (!best) best = canvas.closest('section') || canvas.parentElement || canvas;
      let top = 0, n = best; while (n) { top += n.offsetTop; n = n.offsetParent; }
      return { top, height: best.offsetHeight, vh, sel: window.__cssPath(best) };
    }
    const cs = [].slice.call(document.querySelectorAll('canvas'));
    const geo = {}; cs.forEach(c => { const k = window.__cssPath(c); if (k) geo[k] = driverOf(c); });
    return { cap: window.__cap || window.__frames || [], geo, styles: window.__styles || [] };
  }).catch(() => ({ cap: [], geo: {}, styles: [] }));

  // フレーム: key ごとに (p, f)
  const byK = {};
  for (const s of raw.cap) { const g = raw.geo[s.k]; if (!g || g.height <= g.vh) continue; const p = Math.max(0, Math.min(1, (s.y - g.top) / (g.height - g.vh))); (byK[s.k] ||= { samples: [], srcs: [], g }).samples.push({ p, f: s.f }); byK[s.k].srcs.push(s.src); }
  for (const k of Object.keys(byK)) {
    const o = byK[k]; o.samples.sort((a, b) => a.p - b.p);
    const thin = []; let lb = -1; for (const s of o.samples) { const b = Math.round(s.p / 0.004); if (b !== lb) { thin.push(s); lb = b; } else thin[thin.length - 1] = s; }
    const sample = o.srcs[o.srcs.length - 1]; const m = sample.match(/^(.*?)(\d{2,6})(\.(?:avif|webp|jpe?g|png))(?:\?.*)?$/i);
    (scrollmap[k] ||= {})[vp.name] = { driverH: o.g.height, vh: o.g.vh, driverSel: o.g.sel, base: m ? m[1] : '', pad: m ? m[2].length : 5, ext: m ? m[3] : '.avif', samples: thin };
  }
  // scroll-style: key ごとに (rel=y-top, t, o) を変化ありのみ
  const byS = {};
  for (const s of raw.styles) { if (!s.k) continue; (byS[s.k] ||= { top: s.top, vh: vp.height, arr: [] }).arr.push({ rel: s.y - s.top, t: s.t, o: s.o }); }
  for (const k of Object.keys(byS)) {
    const o = byS[k]; const vals = new Set(o.arr.map(a => a.t + '|' + a.o)); if (vals.size < 2) continue; // 変化しない要素は除外
    o.arr.sort((a, b) => a.rel - b.rel);
    const thin = []; let lb = -1; for (const a of o.arr) { const b = Math.round(a.rel / 20); if (b !== lb) { thin.push(a); lb = b; } else thin[thin.length - 1] = a; }
    (stylemap[k] ||= {})[vp.name] = { top: o.top, vh: o.vh, samples: thin };
  }

  const dom = await page.content().catch(() => '');
  if (vp.name === 'desktop') fs.writeFileSync(path.join(outdir, 'original-dom.html'), dom);
  await context.close();
}

await browser.close();
fs.writeFileSync(path.join(outdir, 'assets-manifest.json'), JSON.stringify(manifest, null, 1));
fs.writeFileSync(path.join(outdir, 'scrollmap.json'), JSON.stringify(scrollmap));
fs.writeFileSync(path.join(outdir, 'stylemap.json'), JSON.stringify(stylemap));
fs.writeFileSync(path.join(outdir, 'reveal.json'), JSON.stringify(revealCls));

console.log(JSON.stringify({
  assets: Object.keys(manifest).length, canvasKeys: Object.keys(scrollmap).length, styleKeys: Object.keys(stylemap).length,
  frames: Object.keys(scrollmap).map(k => ({ d: scrollmap[k].desktop?.samples.length || 0, m: scrollmap[k].mobile?.samples.length || 0, base: (scrollmap[k].desktop || scrollmap[k].mobile)?.base.split('/').pop() })),
  revealDesktop: revealCls.desktop.length, revealMobile: revealCls.mobile.length,
}, null, 1));
