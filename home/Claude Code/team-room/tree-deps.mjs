// 木を作る時の材料（部屋 server.mjs と見るだけの share-server.mjs の両方が使う）。読むだけ
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { lineOf } from "./lines.mjs";
const ROOT = path.dirname(fileURLToPath(import.meta.url));
const VAULT = path.join(process.env.HOME, "Documents/Obsidian Vault");
const 読むJSON = (f) => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, f), "utf8")); } catch { return {}; } };
// 部屋ができる前に済ませた工程を Vault で確かめる。工程 → 番号フォルダ（毎回くり返す 4 広告・5 記事・7〜9 は入れない）
const 工程のフォルダ = { 1: "01 商品", 2: "02 客", 3: "04 設計", 6: "09 店" };
const 中身がある = (d) => { try { return fs.readdirSync(d, { withFileTypes: true }).some((e) => e.isDirectory() ? 中身がある(path.join(d, e.name)) : e.name.endsWith(".md") || e.name.endsWith(".canvas")); } catch { return false; } };
export function makeDeps({ read, channels, auto, jobs }) {
  const links = 読むJSON("data/job-links.json");
  return {
    read, channels, auto, links,
    name: (j) => jobs().find((x) => x.brand === j.brand && x.job_id === j.job_id && x.revision === j.revision)?.name,
    vault: (ctx) => (n) => {
      const f = 工程のフォルダ[n]; if (!f) return null;
      const line = lineOf(ctx.brand, ctx.job_id);
      const base = line && fs.existsSync(path.join(VAULT, "ec", ctx.brand, line.name)) ? path.join("ec", ctx.brand, line.name) : path.join("ec", ctx.brand);
      return 中身がある(path.join(VAULT, base, f)) ? path.join(base, f) : null;
    },
  };
}
