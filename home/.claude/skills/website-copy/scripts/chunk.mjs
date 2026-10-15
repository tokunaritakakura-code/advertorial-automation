#!/usr/bin/env node
// chunk.mjs <outdir> <templateSuffix> [inputFile=clone-baked.html]
// 完コピHTMLを Shopifyテーマの 256KB制限を回避するため 200KBずつの {% raw %} スニペットに分割し、
// {% layout none %}（テーマ外枠を無効化）テンプレートから連結する。→ outdir/theme/ に出力。
import fs from 'fs';
import path from 'path';

const outdir = process.argv[2];
const suffix = process.argv[3] || 'clone';
const input = process.argv[4] || 'clone-baked.html';
if (!outdir) { console.error('usage: chunk.mjs <outdir> <templateSuffix> [inputFile]'); process.exit(1); }

let inPath = path.join(outdir, input);
if (!fs.existsSync(inPath)) inPath = path.join(outdir, 'clone.html'); // bake未実行でも動く
const html = fs.readFileSync(inPath, 'utf8');

const themeDir = path.join(outdir, 'theme');
fs.mkdirSync(themeDir, { recursive: true });

const CHUNK = 200000; // バイト。256KB制限に対する安全マージン
const chunks = []; let pos = 0;
while (pos < html.length) {
  let end = Math.min(pos + CHUNK, html.length);
  while (Buffer.byteLength(html.slice(pos, end), 'utf8') > CHUNK) end -= 1000;
  chunks.push(html.slice(pos, end)); pos = end;
}

const names = [];
chunks.forEach((c, i) => {
  const name = `${suffix}-${i + 1}`;
  fs.writeFileSync(path.join(themeDir, `${name}.liquid`), '{% raw %}' + c + '{% endraw %}');
  names.push(name);
});
const tpl = '{% layout none %}' + names.map(n => `{% render '${n}' %}`).join('') + '\n';
fs.writeFileSync(path.join(themeDir, `product.${suffix}.liquid`), tpl);

console.log(JSON.stringify({
  templateSuffix: suffix,
  snippets: names.length,
  files: names.map(n => `snippets/${n}.liquid`).concat([`templates/product.${suffix}.liquid`]),
  localDir: themeDir,
}, null, 1));
