// 案件の名前（画面に出す日本語）。2026-10-07 本人「nightly て何か分からない。俺が見る画面だから一目で全部分かるように」。
// 決め方: ① data/job-names.json に書いた名前 ② 毎晩の発注（nightly-年-月-日）は「毎晩の振り返りと次の広告（月/日）」 ③ それ以外は本人の最初の発注の頭の1句
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "data/job-names.json");
let 表 = {}, 読んだ = 0;
const 読む = () => { try { const t = fs.statSync(FILE).mtimeMs; if (t !== 読んだ) { 表 = JSON.parse(fs.readFileSync(FILE, "utf8")); 読んだ = t; } } catch {} return 表; };
export function jobName(job_id, firstOrder = "") {
  const t = 読む();
  if (t[job_id]) return t[job_id];
  const n = String(job_id).match(/^nightly-(\d{4})-(\d{2})-(\d{2})$/);
  if (n) return `毎晩の振り返りと次の広告（${Number(n[2])}/${Number(n[3])}）`;
  const 句 = String(firstOrder || "").replace(/^[\s#>*\-]+/, "").replace(/（[^）]*）/g, "").split(/[。\n:：]/)[0].trim();
  return 句 ? (句.length > 22 ? 句.slice(0, 22) + "…" : 句) : job_id;
}
