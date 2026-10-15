// x-collect.mjs — Xのプロフィール/タイムラインを3媒体(文字・画像・動画)で完全収集する。
//
//   node x-collect.mjs --handle riku720720 [--count 60] [--out timeline.json] [--no-media]
//                      [--no-merge] [--stop-on-known 3]
//
// 差分収集(2026-08-27): --out が既にあれば読み込んでマージし、既知IDばかりが続いたら
// そこで打ち切る。同じアカウントを毎日見る時、過去分を取り直さない。全部取り直すなら --no-merge。
//
// 文字: 本文(GraphQL横取りなら長文全文)+引用RTの中身+外部リンクカード
// 画像: 添付画像を原寸(name=orig)でDL
// 動画: yt-dlpでDL(公開ポスト)。失敗はJSONに正直に記録
// タブ: 既存のx.comタブを再利用(getOrCreateTab)。終了後も標準タブとして残す
// レシピの正は references/recipes/x.md。
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { getOrCreateTab } from './connect.mjs';

const execFileP = promisify(execFile);
const arg = (name, def) => {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : def;
};
const handle = arg('handle');
const target = parseInt(arg('count', '60'), 10);
const out = arg('out', `x-${handle}.json`);
const withMedia = !process.argv.includes('--no-media');
const mediaDir = out.replace(/\.json$/, '') + '-media';
const merge = !process.argv.includes('--no-merge');
const stopOnKnown = parseInt(arg('stop-on-known', '3'), 10);
if (!handle) {
  console.error('usage: node x-collect.mjs --handle <name> [--count N] [--out file] [--no-media]');
  process.exit(1);
}

const seen = new Map();
// 既存ファイルを台帳として読み込む(取り直しの回避)。この中のIDは「既知」。
const known = new Set();
if (merge && fs.existsSync(out)) {
  try {
    for (const it of JSON.parse(fs.readFileSync(out, 'utf8'))) {
      if (it && it.id) { seen.set(it.id, it); known.add(it.id); }
    }
    console.error(`merge: 既存 ${known.size} 件を読み込み(新規だけ取りに行く)`);
  } catch (e) { console.error('merge: 既存ファイルを読めなかった →', e.message); }
}
const freshCount = () => [...seen.keys()].filter((id) => !known.has(id)).length;

// GraphQL応答の中からツイートオブジェクトを再帰回収(スキーマ変更に強い形)
function walk(node) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(walk); return; }
  if (node.rest_id && node.legacy && typeof node.legacy.full_text === 'string') {
    const l = node.legacy;
    const u = node.core?.user_results?.result;
    const user = u?.core?.screen_name || u?.legacy?.screen_name || '';
    const media = (l.extended_entities?.media || l.entities?.media || []).map((m) => ({
      type: m.type, // photo | video | animated_gif
      url: m.type === 'photo'
        ? m.media_url_https + '?name=orig'
        : (m.video_info?.variants || [])
            .filter((v) => v.content_type === 'video/mp4')
            .sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0))[0]?.url || m.media_url_https,
    }));
    const it = {
      id: node.rest_id,
      text: node.note_tweet?.note_tweet_results?.result?.text || l.full_text,
      date: l.created_at ? new Date(l.created_at).toISOString() : '',
      url: `https://x.com/${user || handle}/status/${node.rest_id}`,
      user,
      replies: l.reply_count, reposts: l.retweet_count,
      likes: l.favorite_count, views: node.views?.count || '',
      isRepost: !!l.retweeted_status_result,
      media,
      source: 'graphql',
    };
    const prev = seen.get(it.id);
    if (!prev) seen.set(it.id, it);
    else if (prev.source !== 'graphql') {
      // DOM側が先に取れていたら、DOMにしか無い情報(引用RT・カード・DL済みファイル)は残して全文側を採用
      seen.set(it.id, {
        ...prev, ...it,
        quoted: prev.quoted || '',
        cardLink: prev.cardLink || '',
        media: it.media && it.media.length ? it.media : prev.media,
      });
    }
  }
  for (const v of Object.values(node)) walk(v);
}

const { browser, page, created } = await getOrCreateTab(/https?:\/\/([\w-]+\.)?x\.com/);
console.error(created ? 'x.com tab: 新規作成' : 'x.com tab: 既存を再利用');

// GraphQL横取り(本命): Xはservice worker経由で通信するため page.on('response') には乗らない
// (2026-08-15実測)。ページ内の fetch / XHR をフックし、ページJSが受け取ったJSONを直接録る。
await page.addInitScript(() => {
  window.__gq = [];
  // クエリ名はXがよくリネームする(UserTweets→UserOriginalsTimeline, 2026-08-15確認)ので広めに取る
  const WANT = /Timeline|UserTweets|UserMedia|TweetDetail/;
  const push = (url, text) => {
    try { if (url.includes('/graphql/') && WANT.test(url)) window.__gq.push(text); } catch {}
  };
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
      if (url.includes('/graphql/')) res.clone().text().then((t) => push(url, t)).catch(() => {});
    } catch {}
    return res;
  };
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__url = String(url || '');
    return origOpen.call(this, method, url, ...rest);
  };
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...a) {
    this.addEventListener('load', () => { try { push(this.__url, this.responseText); } catch {} });
    return origSend.apply(this, a);
  };
});
// 予備(フックが効かない環境向け): SWを介さない応答はこちらでも拾う
page.on('response', async (res) => {
  const u = res.url();
  if (!u.includes('/graphql/')) return;
  if (!/Timeline|UserTweets|UserMedia|TweetDetail/.test(u)) return;
  try { walk(await res.json()); } catch { /* 非JSON/中断は無視 */ }
});
const drainHooked = async () => {
  const chunks = await page.evaluate(() => {
    const c = window.__gq || []; window.__gq = []; return c;
  }).catch(() => []);
  for (const c of chunks) { try { walk(JSON.parse(c)); } catch {} }
};

await page.goto(`https://x.com/${handle}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForSelector('article[data-testid="tweet"]', { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(2500);

const loggedIn = await page
  .locator('[data-testid="SideNav_AccountSwitcher_Button"], [data-testid="AppTabBar_Home_Link"]')
  .count();
if (!loggedIn && (await page.locator('article[data-testid="tweet"]').count()) === 0) {
  console.error('LOGIN_NEEDED: 統一ブラウザがx.com未ログイン。このタブでSeiyoにログインを依頼して再実行');
  await page.goto('https://x.com/login').catch(() => {});
  await page.bringToFront().catch(() => {});
  process.exit(2); // タブは残す(ログイン用)
}

// DOMフォールバック(横取りで取れたIDは上書きしない)。引用RT・画像・動画・カードも取る
const collectDom = async () => {
  const items = await page.$$eval('article[data-testid="tweet"]', (arts) =>
    arts.map((a) => {
      const texts = [...a.querySelectorAll('[data-testid="tweetText"]')].map((t) => t.innerText);
      const time = a.querySelector('time');
      const anchor = time ? time.closest('a') : null;
      const url = anchor ? anchor.href : '';
      const m = url.match(/status\/(\d+)/);
      const photos = [...a.querySelectorAll('a[href*="/photo/"] img[src*="pbs.twimg.com/media"]')]
        .map((img) => ({ type: 'photo', url: img.src.replace(/name=[\w]+/, 'name=orig') }));
      const hasVideo = !!a.querySelector('[data-testid="videoPlayer"], video');
      const card = a.querySelector('[data-testid="card.wrapper"] a[href]');
      return {
        id: m ? m[1] : '',
        text: texts[0] || '',
        quoted: texts.slice(1).join('\n') || '',
        date: time ? time.getAttribute('datetime') : '',
        url,
        media: hasVideo ? [...photos, { type: 'video', url: '' }] : photos,
        cardLink: card ? card.href : '',
        source: 'dom',
      };
    })
  ).catch(() => []);
  for (const it of items) {
    if (it.id && !seen.has(it.id)) seen.set(it.id, it);
  }
};

let stale = 0;
let knownStreak = 0;
while (freshCount() < target && stale < 8) {
  const before = seen.size;
  const beforeFresh = freshCount();
  await page.evaluate(() => window.scrollBy(0, 2000));
  await page.waitForTimeout(1200);
  await drainHooked();
  await collectDom();
  if (seen.size === before) stale++; else stale = 0;
  // 既知ばかりが続いたら過去分に入っている → 打ち切る
  if (known.size && stopOnKnown > 0) {
    if (freshCount() === beforeFresh && seen.size !== before) knownStreak++;
    else if (freshCount() > beforeFresh) knownStreak = 0;
    if (knownStreak >= stopOnKnown) {
      console.error(`stop: 既知の投稿が${knownStreak}回続いた → 過去分と判断して打ち切り`);
      break;
    }
  }
}
await drainHooked(); // 取りこぼし回収

const arr = [...seen.values()].sort((a, b) => (b.date || '').localeCompare(a.date || ''));

// --- メディアDL(3媒体を100%取る) ---
let imgOk = 0, imgFail = 0, vidOk = 0, vidFail = 0;
if (withMedia) {
  fs.mkdirSync(mediaDir, { recursive: true });
  for (const it of arr) {
    if (known.has(it.id) && (it.media || []).every((m) => m.file)) continue; // 既にDL済みは飛ばす
    let pi = 0;
    for (const m of it.media || []) {
      if (m.type === 'photo' && m.url) {
        try {
          const res = await fetch(m.url);
          if (!res.ok) throw new Error('http ' + res.status);
          const ext = (m.url.match(/format=(\w+)/) || [, 'jpg'])[1];
          const file = path.join(mediaDir, `${it.id}_p${pi++}.${ext}`);
          fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
          m.file = file; imgOk++;
        } catch (e) { m.error = String(e.message || e); imgFail++; }
      } else if (m.type === 'video' || m.type === 'animated_gif') {
        try {
          if (m.url) { // GraphQL経由: mp4直URL
            const res = await fetch(m.url);
            if (!res.ok) throw new Error('http ' + res.status);
            const file = path.join(mediaDir, `${it.id}_v.mp4`);
            fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
            m.file = file; vidOk++;
          } else { // DOM経由: yt-dlpでポストURLから
            const tmpl = path.join(mediaDir, `${it.id}_v.%(ext)s`);
            await execFileP('yt-dlp', ['-q', '--no-warnings', '-o', tmpl, it.url], { timeout: 120000 });
            const got = fs.readdirSync(mediaDir).find((f) => f.startsWith(`${it.id}_v.`));
            if (!got) throw new Error('no output file');
            m.file = path.join(mediaDir, got); vidOk++;
          }
        } catch (e) { m.error = String(e.message || e).slice(0, 200); vidFail++; }
      }
    }
  }
}

fs.writeFileSync(out, JSON.stringify(arr, null, 1));
const g = arr.filter((x) => x.source === 'graphql').length;
console.error(`collected: ${arr.length} (graphql:${g} dom:${arr.length - g}, 新規:${freshCount()} 既知:${known.size}, target:${target})`);
if (withMedia) console.error(`media: images ${imgOk} ok/${imgFail} fail, videos ${vidOk} ok/${vidFail} fail → ${mediaDir}`);
console.log(out);
// タブは標準x.comタブとして残す(次回getOrCreateTabが再利用する)
browser.close();
