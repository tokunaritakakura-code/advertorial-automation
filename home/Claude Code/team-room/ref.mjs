// 参考の候補（競合の勝ち広告）の最初の場面の絵。デスクトップの原本（ec/<ブランド>/<ライン>/01 商品/完コピの材料/原本/）から ffmpeg で1枚だけ抜く。読むだけ
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { lineOf } from "./lines.mjs";
const ROOT = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(ROOT, "data/ads/ref");
const 探す = (d, id, n = 0) => { if (n > 4) return null; let es; try { es = fs.readdirSync(d, { withFileTypes: true }); } catch { return null; }
  const hit = es.find((e) => e.isFile() && e.name.startsWith(id) && /\.(mp4|mov|webm)$/i.test(e.name)); if (hit) return path.join(d, hit.name);
  for (const e of es) if (e.isDirectory() && !e.name.startsWith("_")) { const r = 探す(path.join(d, e.name), id, n + 1); if (r) return r; } return null; };
export function refImage(brand, job_id, id) {
  if (!/^\d{8,20}$/.test(String(id))) return null;
  const out = path.join(OUT, `${id}.jpg`); if (fs.existsSync(out)) return out;
  const line = lineOf(brand, job_id), base = path.join(process.env.HOME, "Desktop/ec", brand, line?.name || "", "01 商品/完コピの材料/原本");
  const src = 探す(base, String(id)); if (!src) return null;
  fs.mkdirSync(OUT, { recursive: true });
  try { execFileSync("/opt/homebrew/bin/ffmpeg", ["-y", "-loglevel", "error", "-ss", "0.4", "-i", src, "-frames:v", "1", "-vf", "scale=240:-2", "-q:v", "6", out], { timeout: 20000 }); } catch { return null; }
  return fs.existsSync(out) ? out : null;
}

// 参考の候補の GetHookd のリンク（共有リンク）と飛び先。原本と同じフォルダの gethookd_*.json（棚を作った時の取得物）から、Meta の広告ID（ext）で引く
const 棚の記録 = new Map();
export function refInfo(brand, job_id, ids) {
  const line = lineOf(brand, job_id), base = path.join(process.env.HOME, "Desktop/ec", brand, line?.name || "", "01 商品/完コピの材料/原本");
  if (!棚の記録.has(base)) {
    const m = new Map();
    try { for (const f of fs.readdirSync(base).filter((x) => /^gethookd.*\.json$/.test(x))) for (const r of JSON.parse(fs.readFileSync(path.join(base, f), "utf8"))) if (r.ext) m.set(String(r.ext), { share: r.share || null, lp: r.lp || null, title: r.title || null, days: r.days || null }); } catch {}
    棚の記録.set(base, m);
  }
  const m = 棚の記録.get(base);
  return Object.fromEntries(ids.filter((id) => /^\d{8,20}$/.test(id)).map((id) => [id, m.get(id) || null]));
}
