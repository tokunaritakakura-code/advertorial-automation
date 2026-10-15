#!/usr/bin/env node
// bake.mjs <outdir> <pageUrl>
// clone.html + manifest.json を読み、ヘッドレスChromeで「JS実行後のDOM」を取り、
// 動的な穴（価格換算・レビュー・メールフォーム）を静的HTMLに焼き込む → clone-baked.html
// これが完コピの一番の肝。curlの生HTMLでは空欄になる箇所を「実際に動かした結果」で埋める。
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';
import { freezeStatic, revealHidden } from './lib-clone.mjs';

const outdir = process.argv[2];
const pageUrl = process.argv[3];
if (!outdir || !pageUrl) { console.error('usage: bake.mjs <outdir> <pageUrl>'); process.exit(1); }
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

let html = fs.readFileSync(path.join(outdir, 'clone.html'), 'utf8');
const manifest = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8'));
const log = [];

// JS実行後のDOMを取得。CAPTURED=1 なら capture.mjs が保存した original-dom.html を再利用
// （フルスクロール後の完全DOM＋横取りアセットを使うため、再ダンプしない）。
const domPath = path.join(outdir, 'original-dom.html');
if (!(process.env.CAPTURED === '1' && fs.existsSync(domPath))) {
  execFileSync(CHROME, ['--headless=new', '--disable-gpu', '--virtual-time-budget=30000', '--dump-dom', pageUrl],
    { stdio: ['ignore', fs.openSync(domPath, 'w'), 'ignore'], timeout: 90000 });
}
const dom = fs.readFileSync(domPath, 'utf8');

// === フリーズモード（JS重量ページ）===
// サーバーHTMLがほぼ空で、コンテンツがJS実行後にしか無いページ（SPA/ヘッドレスCMS/
// 動的チェックアウト等）は、凍結DOMを土台に「静的フリーズ」する。これをやらないと
// 残存アプリJSが移植先ストアで再実行され、移植先の実データで枠を描き直して汚染する。
const FORCE = process.env.FREEZE === '1';
const NOFREEZE = process.env.FREEZE === '0';
const jsHeavy = dom.length > html.length * 1.25;
if (!NOFREEZE && (FORCE || jsHeavy)) {
  const origin = manifest.source;
  const r = freezeStatic(dom, origin);
  // REVEAL=1: スクロール連動の出現演出を全表示（下部が opacity:0 で空白になるLP向け）
  if (process.env.REVEAL === '1') { r.html = revealHidden(r.html); r.log.reveal = true; }
  if (r.html.includes('{% endraw %}')) console.error('WARNING: {% endraw %} present');
  fs.writeFileSync(path.join(outdir, 'clone-baked.html'), r.html);
  console.log(JSON.stringify({ mode: 'freeze', domLen: dom.length, serverLen: html.length, ...r.log, bytes: r.html.length }, null, 1));
  process.exit(0);
}

// --- 価格換算（bucksCC等の変換済みspan）---
if (manifest.currency) {
  const pairs = {};
  for (const m of dom.matchAll(/<span class="money buckscc-converted buckscc-money" bucks-original="([^"]+)" bucks-init="([^"]+)" bucks-currency="([^"]+)" bucks-current="([^"]+)">/g)) {
    pairs[m[1]] = { init: m[2], cur: m[3], text: m[4] };
  }
  let n = 0;
  html = html.replace(/<span class=money>(\$[\d.,]+)<\/span>/g, (mm, val) => {
    const p = pairs[val]; if (!p) return mm; n++;
    return `<span class="money buckscc-converted buckscc-money" bucks-original="${val}" bucks-init="${p.init}" bucks-currency="${p.cur}" bucks-current="${p.text}">${p.text}</span>`;
  });
  log.push(`currency: ${n} spans / ${Object.keys(pairs).length} rates`);
}

// --- Looxレビュー iframe を srcdoc に焼き込む ---
// Looxは別サーバーのiframe。中身をfetchしてscript除去・URL絶対化・visibility上書きして srcdoc に埋める。
if (manifest.loox) {
  const m = html.match(/<iframe id="looxReviewsFrame"[^>]*\ssrc="([^"]+)"[^>]*>/);
  if (m) {
    try {
      const res = await fetch(m[1], { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': manifest.source + '/' } });
      let lx = await res.text();
      lx = lx.replace(/<script\b[\s\S]*?<\/script>/g, '');            // scriptを止める（静的化）
      lx = lx.replace(/(src|href)="\/(?!\/)/g, '$1="https://loox.io/'); // 相対URL絶対化
      lx = lx.replace('</body>', '<style>body{visibility:visible !important}</style></body>'); // Loox自身の隠しを解除
      const srcdoc = lx.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
      const newTag = m[0].replace(/\ssrc="[^"]+"/, ` srcdoc="${srcdoc}"`);
      html = html.slice(0, m.index) + newTag + html.slice(m.index + m[0].length);
      // iframe高さ自動フィット（同一オリジンなので中身の高さを読める）
      const fit = `<script>(function(){var f=document.getElementById("looxReviewsFrame");if(!f)return;var w=f.closest("#looxReviews");function fit(){try{var d=f.contentDocument;if(!d||!d.body)return;var h=d.body.scrollHeight;if(h>50){f.style.height=h+"px";if(w)w.style.height=h+"px";}}catch(e){}}f.addEventListener("load",fit);fit();var n=0,t=setInterval(function(){fit();if(++n>20)clearInterval(t);},500);})();</script>`;
      const ic = html.indexOf('</iframe>');
      if (ic > 0) html = html.slice(0, ic + 9) + fit + html.slice(ic + 9);
      log.push(`loox: srcdoc ${srcdoc.length}b`);
    } catch (e) { log.push('loox: FETCH FAILED ' + e.message); }
  }
}

// --- Klaviyo等のメールフォーム：描画後のサブツリーでプレースホルダを差し替え ---
if (manifest.klaviyo) {
  const balanced = (s, startRe) => {
    const mm = s.match(startRe); if (!mm) return null;
    let depth = 0;
    for (const t of s.slice(mm.index).matchAll(/<div\b|<\/div>/g)) {
      depth += t[0][1] === '/' ? -1 : 1;
      if (depth === 0) { const end = mm.index + t.index + t[0].length; return { html: s.slice(mm.index, end), start: mm.index, end }; }
    }
    return null;
  };
  const ids = [...new Set([...dom.matchAll(/klaviyo-form-(\w+)/g)].map(x => x[1]))];
  let n = 0;
  for (const id of ids) {
    const src = balanced(dom, new RegExp(`<div class="klaviyo-form-${id}[^"]*"`));
    const dst = balanced(html, new RegExp(`<div class="klaviyo-form-${id}[^"]*"`));
    if (src && dst && src.html.length > dst.html.length) { html = html.slice(0, dst.start) + src.html + html.slice(dst.end); n++; }
  }
  log.push(`klaviyo: ${n}/${ids.length} forms`);
}

if (html.includes('{% endraw %}')) console.error('WARNING: {% endraw %} present');
fs.writeFileSync(path.join(outdir, 'clone-baked.html'), html);
console.log(JSON.stringify({ baked: log, bytes: html.length }, null, 1));
