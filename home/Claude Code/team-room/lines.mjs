// ブランドの中のライン（ここちドライ＝女性用／男性用、アルコット＝大人用／キッズ）。data/lines.json を読む（直したらすぐ効く）
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "data/lines.json");
let 表 = {}, 読んだ = 0;
const 読む = () => { try { const t = fs.statSync(FILE).mtimeMs; if (t !== 読んだ) { 表 = JSON.parse(fs.readFileSync(FILE, "utf8")); 読んだ = t; } } catch {} return 表; };
export const linesOf = (brand) => (読む()[brand] || []).map(({ id, name }) => ({ id, name }));
export function lineOf(brand, job_id) {
  const ls = 読む()[brand]; if (!ls?.length) return null;
  const hit = ls.find((l) => (l.jobs || []).includes(job_id)) || ls.find((l) => (l.match || []).some((w) => new RegExp(`(^|[-_])${w}([-_]|$)`, "i").test(job_id))) || ls[0];
  return { id: hit.id, name: hit.name };
}
