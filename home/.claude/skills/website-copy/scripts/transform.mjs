#!/usr/bin/env node
// transform.mjs <outdir> <sourceOrigin>
// original.html を読み、①トラッキング除去 ②アセットURLを元ドメイン絶対URLに書き換え（ホットリンク）
// → clone.html と、動的ウィジェット検出結果の manifest.json を出力する。
// ホットリンク＝画像/CSS/JSを元サーバーからそのまま借りる＝バイト単位で同一＝ピクセル一致の理由。
import fs from 'fs';
import path from 'path';
import { stripTracking, absolutize, promoteLazyImages } from './lib-clone.mjs';

const outdir = process.argv[2];
const origin = process.argv[3]; // 例: https://example.co （末尾スラッシュなし）
if (!outdir || !origin) { console.error('usage: transform.mjs <outdir> <sourceOrigin>'); process.exit(1); }

let html = fs.readFileSync(path.join(outdir, 'original.html'), 'utf8');
const orig = html.length;

// ① トラッキング/ABテスト/解析スクリプト除去（Intelligems等の価格ABは残すと価格が変わるので必ず除去）
let removed;
({ html, removed } = stripTracking(html));

// ② アセットURLの絶対化（ホットリンク）＋ ③ 遅延読み込み画像の即表示化
html = absolutize(html, origin);
({ html } = promoteLazyImages(html));

// 動的ウィジェット検出（bake.mjs の焼き込み対象を決める手がかり）
const manifest = {
  source: origin,
  loox: /id="looxReviewsFrame"|loox\.io\/widget/.test(html),
  currency: /buckscc|bucks-currency|<span class=money>|<span class="money"/.test(html),
  klaviyo: /klaviyo-form-\w+/.test(html),
  gempages: /<gp-[a-z-]+/.test(html),
  removedCount: removed.length,
};

if (html.includes('{% endraw %}') || html.includes('{%endraw%}')) {
  console.error('WARNING: 本文に {% endraw %} が含まれ {% raw %} 包みが壊れる。手動対処が必要。');
}

fs.writeFileSync(path.join(outdir, 'clone.html'), html);
fs.writeFileSync(path.join(outdir, 'manifest.json'), JSON.stringify(manifest, null, 2));
console.log(JSON.stringify({ orig, out: html.length, removed: removed.length, manifest }, null, 1));
