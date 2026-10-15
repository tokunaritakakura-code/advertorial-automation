#!/usr/bin/env node
// upload-gcs.mjs <stagedTargetsJsonFile> <themeDir>
// Shopify MCP の stagedUploadsCreate が返す stagedTargets 配列（JSON）を受け取り、
// theme/ 内の各ファイルを署名付きGCSへPOSTする。→ themeFilesUpsert 用に resourceUrl を出力。
// これで手作業の巨大curlが不要になる。stagedUploadsCreate のファイル名順＝theme内ファイル名で対応。
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';

const targetsFile = process.argv[2];
const themeDir = process.argv[3];
if (!targetsFile || !themeDir) { console.error('usage: upload-gcs.mjs <stagedTargetsJsonFile> <themeDir>'); process.exit(1); }

let targets = JSON.parse(fs.readFileSync(targetsFile, 'utf8'));
// data.stagedUploadsCreate.stagedTargets 形式でも stagedTargets 配列そのままでも受ける
if (targets.data) targets = targets.data.stagedUploadsCreate.stagedTargets;
if (targets.stagedTargets) targets = targets.stagedTargets;

const out = [];
for (const t of targets) {
  const key = t.parameters.find(p => p.name === 'key').value;
  const filename = key.split('/').pop();
  const local = path.join(themeDir, filename);
  if (!fs.existsSync(local)) { out.push({ filename, code: 'NO_LOCAL_FILE' }); continue; }
  const args = ['-s', '-o', '/dev/null', '-w', '%{http_code}', t.url];
  for (const p of t.parameters) args.push('-F', `${p.name}=${p.value}`); // policyフィールド群
  args.push('-F', `file=@${local};type=text/plain`);                     // fileは必ず最後
  const code = execFileSync('curl', args, { encoding: 'utf8' });
  out.push({ filename, code, resourceUrl: t.resourceUrl });
}
console.log(JSON.stringify(out, null, 1));
