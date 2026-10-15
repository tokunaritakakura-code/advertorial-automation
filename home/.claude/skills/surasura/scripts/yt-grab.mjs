// yt-grab.mjs — yt-dlpが403で全滅した時の最終フォールバック(映像チャンネル)。
// 動画をダウンロードせず、統一ブラウザの<video>要素をseekしてスクショする。
// プレイヤーが再生できる限りYouTube側の取得規制(POトークン等)に影響されない。
//
//   node yt-grab.mjs <watchUrl> [--points 40 | --times 0.5,45,90 | --times-file f] [--out DIR]
//                     [--width 768] [--embed]
//
// 2026-08-27実測: yt-dlpは360p(format 18)しか降ってこないのに成功扱いになるため、
// 映像チャンネルは黙って360pに劣化していた。この経路はプレイヤーの実解像度(実測1920x1080)で撮れる。
// --times で frames.py --times-only が選んだ場面転換の時刻をそのまま高解像度で撮り直せる(ハイブリッド)。
//
// 出力: DIR/f_<秒6桁>.jpg + stdoutに frames.tsv 形式(秒\tパス) → 既存のbeats.py/merge.pyに直結。
// 統一ブラウザに相乗り(connect.mjs)・YouTubeタブは再利用・終了時は自分の開いたタブだけ閉じる。
// 注意: 共有ブラウザの<video>を占有するためシリアル実行のみ(束で並列に投げない)。
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { getOrCreateTab } from './connect.mjs';

const args = process.argv.slice(2);
const val = (name, def) => {
  const i = args.indexOf('--' + name);
  return i > -1 && args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : def;
};
const url = args.find((a) => /^https?:/i.test(a));
const POINTS = parseInt(val('points', '40'), 10);
const OUT = path.resolve(val('out', './grab-frames'));
const WIDTH = parseInt(val('width', '768'), 10); // 読ませる幅に落とす(0で原寸のまま)
const TIMES = (() => {
  const f = val('times-file', null);
  const raw = f ? fs.readFileSync(f, 'utf8') : val('times', null);
  if (!raw) return null;
  const list = raw.split(/[\s,]+/).map(Number).filter((n) => isFinite(n) && n >= 0);
  return list.length ? [...new Set(list)].sort((a, b) => a - b) : null;
})();
const EMBED = args.includes('--embed');
if (!url) { console.error('usage: node yt-grab.mjs <watchUrl> [--points N] [--out DIR] [--embed]'); process.exit(1); }

const vid = (() => {
  try {
    const u = new URL(url);
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1);
    return u.searchParams.get('v') || u.pathname.split('/').pop();
  } catch { return null; }
})();
const target = EMBED && vid ? `https://www.youtube.com/embed/${vid}?autoplay=1&mute=1` : url;
fs.mkdirSync(OUT, { recursive: true });

// 1080pのまま置くと読む時のトークンが重い → frames.py と同じ768px幅に揃える
async function shrink(file, width) {
  const tmp = file + '.tmp.jpg';
  await new Promise((res) => {
    const p = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-i', file,
      '-vf', `scale=${width}:-2`, '-q:v', '4', '-y', tmp]);
    p.on('close', res);
    p.on('error', res);
  });
  if (fs.existsSync(tmp) && fs.statSync(tmp).size > 0) fs.renameSync(tmp, file);
  else fs.rmSync(tmp, { force: true });
}

const { browser, page, created } = await getOrCreateTab(/https?:\/\/([\w-]+\.)?(youtube\.com|youtu\.be)/);
try {
  await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('video', { state: 'attached', timeout: 30000 });

  // 再生開始(ミュート)。autoplayがジェスチャ待ちならクリックで蹴る
  await page.evaluate(() => { const v = document.querySelector('video'); if (v) { v.muted = true; v.play().catch(() => {}); } });
  for (const sel of ['button.ytp-large-play-button', '.ytp-large-play-button', 'video']) {
    const playing = await page.evaluate(() => { const v = document.querySelector('video'); return v && !v.paused && v.currentTime > 0; });
    if (playing) break;
    try { await page.click(sel, { timeout: 2000 }); } catch {}
    await page.waitForTimeout(400);
  }

  // 広告が流れていたらスキップを試みつつ待つ(最大60秒)
  for (let i = 0; i < 30; i++) {
    const inAd = await page.evaluate(() => !!document.querySelector('.ad-showing, .ad-interrupting')).catch(() => false);
    if (!inAd) break;
    try { await page.click('.ytp-skip-ad-button, .ytp-ad-skip-button, .ytp-ad-skip-button-modern', { timeout: 800 }); } catch {}
    await page.waitForTimeout(2000);
  }

  await page.waitForFunction(() => { const v = document.querySelector('video'); return v && isFinite(v.duration) && v.duration > 0; }, { timeout: 30000 });
  const duration = await page.evaluate(() => document.querySelector('video').duration);

  // プレイヤーUIを消して素の映像ピクセルだけ撮る
  await page.addStyleTag({ content: `
    .ytp-chrome-bottom, .ytp-chrome-top, .ytp-gradient-bottom, .ytp-gradient-top,
    .ytp-ce-element, .ytp-cards-teaser, .ytp-pause-overlay, .ytp-spinner,
    .ytp-watermark, .annotation, .iv-branding, .ytp-paid-content-overlay,
    .ytp-large-play-button, .ytp-endscreen-content { opacity:0 !important; display:none !important; }
  ` }).catch(() => {});

  const vh = await page.$('video');
  // --times があればその時刻(場面転換)を撮る。無ければ等間隔。
  const plan = TIMES
    ? TIMES.filter((t) => t < duration)
    : Array.from({ length: Math.max(2, POINTS) }, (_, i) =>
        +(duration * (i + 0.5) / Math.max(2, POINTS)).toFixed(2));
  const n = plan.length;
  let captured = 0;
  for (const t of plan) {
    await page.evaluate((tt) => { const v = document.querySelector('video'); v.pause(); v.currentTime = tt; }, t);
    await page.waitForFunction((tt) => { const v = document.querySelector('video'); return Math.abs(v.currentTime - tt) < 0.5 && v.readyState >= 2; }, t, { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(120);
    const dest = path.join(OUT, `f_${String(Math.round(t)).padStart(6, '0')}.jpg`);
    try {
      await vh.screenshot({ path: dest, type: 'jpeg', quality: 88 });
      if (WIDTH > 0) await shrink(dest, WIDTH);
      console.log(`${t.toFixed(1)}\t${dest}`);
      captured++;
    } catch {}
  }
  console.error(`grab: ${captured}/${n} frames (duration ${Math.round(duration)}s) → ${OUT}`);
  if (created) await page.close().catch(() => {});
  browser.close();
  process.exit(captured > 0 ? 0 : 1);
} catch (e) {
  console.error('grab FAILED:', e.message);
  if (created) await page.close().catch(() => {});
  browser.close();
  process.exit(1);
}
