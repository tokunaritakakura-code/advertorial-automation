// connect.mjs — 統一Chrome(CDP 9222)への相乗り接続。surasura全スクリプト共通の足回り。
//
// 使い方:
//   import { connect } from './connect.mjs';
//   const { browser, context, newTab } = await connect();
//   const page = await newTab();          // 新規タブ。同一サイトの既存タブを使い回すなら getOrCreateTab()
//   ...
//   await page.close();                   // 自分のタブだけ閉じる
//   browser.close();                      // 切断のみ(Chrome本体は落とさない)
//
// 9222が生きていなければ chrome.sh で起動して接続を待つ。
import { chromium } from 'playwright-core';
import { execFile } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const CDP = 'http://127.0.0.1:9222';
const HERE = dirname(fileURLToPath(import.meta.url));

async function alive() {
  try {
    const r = await fetch(CDP + '/json/version', { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch { return false; }
}

export async function connect({ launchIfNeeded = true, timeoutMs = 20000 } = {}) {
  if (!(await alive())) {
    if (!launchIfNeeded) throw new Error('unified Chrome (CDP 9222) not running');
    execFile('bash', [join(HERE, 'chrome.sh')]);
    const deadline = Date.now() + timeoutMs;
    while (!(await alive())) {
      if (Date.now() > deadline) throw new Error(
        'CDP 9222 not reachable。プロファイルがCDP無しで起動中の可能性 → 既存ウィンドウを確認し、' +
        '不要なら pkill -f "task-fleet/chrome-profile" 後に chrome.sh で再起動');
      await new Promise(r => setTimeout(r, 500));
    }
  }
  const browser = await chromium.connectOverCDP(CDP);
  const context = browser.contexts()[0];
  const newTab = () => context.newPage();
  return { browser, context, newTab };
}

// タブの鉄則: 同一サイトの既存タブがあれば再利用し、重複タブは閉じて散らかさない。
// 複製タブは並列でコスパが出る時だけ({ forceNew: true })。別サイトのタブには触らない。
export async function getOrCreateTab(pattern, { forceNew = false } = {}) {
  const { browser, context } = await connect();
  const re = typeof pattern === 'string' ? new RegExp(pattern) : pattern;
  const matches = context.pages().filter(p => re.test(p.url()));
  if (!forceNew && matches.length > 0) {
    for (const extra of matches.slice(1)) await extra.close().catch(() => {});
    return { browser, context, page: matches[0], created: false };
  }
  return { browser, context, page: await context.newPage(), created: true };
}

// ログインが必要になった時: 可視タブを開いてSeiyoに依頼する(1回で永続)。
export async function openLoginTab(url) {
  const { context } = await connect();
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.bringToFront();
  return page; // 閉じずに残す(Seiyoがここでログインする)
}
