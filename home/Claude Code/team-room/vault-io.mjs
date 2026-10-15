// Vault（iCloud の「書類」の中）を、固まらずに読み書きする（2026-10-08 本人）。
// 2026-10-08 06:02 に iCloud の同期が詰まり、Vault のファイルを開くと戻ってこなくなった。部屋のサーバーは毎回 Vault を
// 同期で読んでいたので、そこで固まり、全員が止まった。ここを通せば、開けない時は数秒で諦めて最後に読めた写しを使う。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

const 待つ秒 = 4;
let 控えの置き場 = null;
export function 控えを置く(dir) { 控えの置き場 = dir; fs.mkdirSync(dir, { recursive: true }); }
const 控え = p => path.join(控えの置き場, createHash("sha1").update(path.resolve(p)).digest("hex").slice(0, 16) + ".控え");  // .md にしない（文書の検査に拾われる）
let 最後に固まった = 0;
export const 固まった = () => Date.now() - 最後に固まった < 5 * 60 * 1000;

// 開けなければ 待つ秒 で諦める。読めたら控えを残す。読めなければ控え、控えも無ければ null
export function 読む(p) {
  if (固まった() && 控えの置き場 && fs.existsSync(控え(p))) return fs.readFileSync(控え(p), "utf8");  // 詰まっている間は待たずに写しを使う
  try {
    const t = execFileSync("perl", ["-e", `alarm ${待つ秒}; open(F, "<", $ARGV[0]) or exit 2; local $/; print <F>;`, p], { encoding: "utf8", timeout: (待つ秒 + 2) * 1000, maxBuffer: 64 * 1024 * 1024 });
    if (控えの置き場) try { fs.writeFileSync(控え(p), t); } catch {}
    return t;
  } catch (e) {
    if (e.status !== 2) { 最後に固まった = Date.now(); console.error(`Vault が開けない（${待つ秒}秒で諦めた）: ${p}`); }
    if (控えの置き場 && fs.existsSync(控え(p))) return fs.readFileSync(控え(p), "utf8");
    return null;
  }
}
export const ある = p => 読む(p) !== null;

// 書けなければ 待つ秒 で諦めて false。呼び手が待ちの列に回す
export function 書く(p, text) {
  try {
    execFileSync("perl", ["-e", `alarm ${待つ秒}; open(F, ">", $ARGV[0]) or exit 2; local $/; print F <STDIN>; close F or exit 3;`, p], { input: text, timeout: (待つ秒 + 2) * 1000 });
    if (控えの置き場) try { fs.writeFileSync(控え(p), text); } catch {}
    return true;
  } catch { 最後に固まった = Date.now(); console.error(`Vault に書けない（${待つ秒}秒で諦めた）: ${p}`); return false; }
}
