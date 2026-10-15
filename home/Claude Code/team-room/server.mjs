import { execFile } from "node:child_process";
// チームの部屋: 役（AIエージェント）がチャンネルで会話しながら働く。本人は同じ画面で割り込み・承認する。
//   起動: npm start → http://localhost:3200
//   頭脳は Claude Agent SDK（Claude Code のログイン＝Max のまま。APIキーは使わない）。
//   役の仕事の正本は Vault の 00 組織図.md と 役/<名前>.md。ここには写さない。
import http from "node:http";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { query, createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import { nextBriefIntake } from "./next-brief-intake.mjs";
import { reviewIntake } from "./review-intake.mjs";
import { localVslDispatcher } from "./local-vsl-intake.mjs";
import { fixedNativeVslReview } from "./native-vsl-review.mjs";
import { runtimeResult, handoffResponse, requestKey, runtimeStore, consumeSDK, completedResultIntact } from "./runtime-result.mjs";
import { createRoleCapabilities } from "./role-capabilities.mjs";
import { context, contextKey, sessionKey, sameContext, delegationChannel, toolPolicy, approvalMatches, runContext, inside, fileHash, verifiedReviewResult, approvalWindow, digest } from "./isolation.mjs";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const HOME = os.homedir();
const VAULT = path.join(HOME, "Documents/Obsidian Vault");
const ORG = path.join(VAULT, "ec/構造/ハーネス/00 組織図.md");
const ROLE_DIR = path.join(VAULT, "ec/構造/ハーネス/役");
// 本人の直しの台帳（2026-10-07 本人「俺が言う事を全部の工程に効かせたい」）。節の見出しの次の「役:」の行に名前がある役へ、毎回の指示に節ごと付けて渡す
const VIO = await import(pathToFileURL(path.join(ROOT, "vault-io.mjs")).href);
const VERIFICATION = process.env.EC_VERIFICATION === "1";
const STATE_ROOT = path.join(ROOT, "data", ...(VERIFICATION ? ["verification"] : []));
const LEDGER = path.join(VAULT, "ec/構造/毎日の制作/_直しの台帳.md");
const 台帳の節たち = () => { try { return (VIO.読む(LEDGER) ?? "").split(/\n(?=### )/).slice(1).map(t => ({ 名: t.split("\n")[0].replace(/^### /, "").trim(), 役: (t.match(/^役: (.+)$/m) || [])[1] || "", 本文: t.split(/\n(?=## )/)[0] })); } catch { return []; } };
function 台帳の節(role) {
  const 全部 = role === "編集長" || role === "台帳係";
  const 節 = 台帳の節たち().filter(x => 全部 || x.役.includes(role) || x.役.includes("全員"));
  if (!節.length) return "";
  const 先 = role === "編集長" ? "審査では、作った役に当たる節の行を1行ずつ照らし、守れていない行は行の文を引いて、ずれとして全部 reasons に書く（台帳に反するずれは、後でコードが必ず戻す側に振り分ける）。"
    : role === "台帳係" ? "下は今の台帳の全部。本人の書き込みが、どの節のどの行と同じかを照らすのに使う。"
    : "全部守る。守れない行がある時は、推測で進めずチャンネルに1行書いて止まる。";
  return `本人の直しの台帳（${LEDGER}）の、あなたに当たる節。${先}\n---\n${節.map(x => x.本文.trim()).join("\n\n")}\n---`;
}
// 戻しから学ぶ（2026-10-07 本人「今あったエラーが起こらない仕組み。次から一回でできるように。全部の工程で」）
// 編集長が戻した理由を、作った役ごとに一般化した決まりにして溜め、その役が次に動く時に毎回渡して、出す前に自分で照らさせる
const 戻しの決まりの置き場 = path.join(STATE_ROOT, "戻しの決まり.json");
const 戻しの決まり = () => { try { return JSON.parse(fs.readFileSync(戻しの決まりの置き場, "utf8")); } catch { return {}; } };
const 最後の作り手 = new Map(); // ブランド×案件×版×チャンネル -> 編集長の前に頼まれた役
function 戻しの節(role) {
  // 本人が承認した決まりだけを渡す（2026-10-08 本人。記事 @polydao 14段目「自分で決まりを書き換えさせない。必ず人が承認」）。承認は data/決まりの案.txt で本人に出す
  const 行 = (戻しの決まり()[role] || []).filter(x => x.承認 === true).sort((a, b) => b.回数 - a.回数 || String(b.最後).localeCompare(String(a.最後))).slice(0, 25);
  if (!行.length) return "";
  return `あなたの成果物が編集長に戻された理由を一般化した決まり（多い順。数字は戻された回数）。出す前に1行ずつ自分で照らし、守れていない物を直してから渡す。1回で通すため:\n${行.map((x, i) => `${i + 1}. ${x.決まり}（${x.回数}回）`).join("\n")}`;
}
// 編集長の前に頼まれた役。サーバーの覚え（入れ直すと消える）に無ければ、部屋の記録（room.db の引き継ぎ）から引く（2026-10-08: 入れ直しの直後の戻しが黙って捨てられた）
function 作り手を引く(ctx, channelId) {
  const m = 最後の作り手.get(contextKey(ctx) + channelId); if (m) return m;
  try {
    const r = db.prepare("SELECT json_extract(meta,'$.to') AS who FROM messages WHERE kind='handoff' AND json_extract(meta,'$.to') IS NOT NULL AND json_extract(meta,'$.to') != '編集長' AND json_extract(meta,'$.context.brand')=? AND json_extract(meta,'$.context.job_id')=? AND json_extract(meta,'$.context.revision')=? AND (json_extract(meta,'$.targetChannel')=? OR channel=?) ORDER BY id DESC LIMIT 1").get(ctx.brand, ctx.job_id, ctx.revision, channelId, channelId);
    return r?.who || null;
  } catch { return null; }
}
async function 戻しを学ぶ(role, reasons, ctx) {
  if (!role) { console.error(`戻しを学ぶ: 作り手がわからないので溜められなかった（${ctx.job_id}・戻し${reasons?.length || 0}件）`); return; }
  if (!reasons?.length) return;
  const 全部 = 戻しの決まり(); const 今 = 全部[role] || [];
  const prompt = `あなたは審査の差し戻しを、次から同じ間違いをしないための決まりに直す係。ファイルは読まない・書かない。\n役: ${role}\n今ある決まり:\n${今.map((x, i) => `${i + 1}. ${x.決まり}`).join("\n") || "（無し）"}\n\n今回戻された理由:\n${reasons.map((r, i) => `- ${r}`).join("\n")}\n\n理由1件につき1行で返す。今ある決まりと同じ意味なら「同じ: <番号>」。違えば「新しい: <決まり>」。決まりは、この案件の固有の秒・ファイル名・数字を外して、次の別の案件でも効く1文にする（例: 「台本の段の秒は ja_src.json の秒と同じにする」）。これ以外の文は書かない。`;
  let text = "";
  try { for await (const m of query({ prompt, options: { model: "claude-opus-5-5", maxTurns: 1, tools: [], allowedTools: [], settingSources: [], permissionMode: "dontAsk", strictMcpConfig: true, mcpServers: {} } })) if (m.type === "result") text = m.result || ""; } catch (e) { console.error("戻しを学ぶ:", e.message); return; }
  const 日 = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" }); let 新 = 0, 同 = 0;
  for (const l of text.split("\n").map(x => x.trim())) {
    const a = l.match(/^同じ[:：]\s*(\d+)/), b = l.match(/^新しい[:：]\s*(.+)$/);
    if (a && 今[+a[1] - 1]) { 今[+a[1] - 1].回数++; 今[+a[1] - 1].最後 = 日; 同++; }
    else if (b) { 今.push({ 決まり: b[1].trim(), 回数: 1, 最初: 日, 最後: 日, 案件: ctx.job_id, 承認: false }); 新++; }
  }
  全部[role] = 今; fs.writeFileSync(戻しの決まりの置き場, JSON.stringify(全部, null, 1));
  console.log(`戻しを学ぶ: ${role} 戻し${reasons.length}件 → 新しい決まりの案${新}・同じ${同}`);
  if (新) 通知(`決まりの案が${新}件増えた（${role}）。承認するまで役には渡さない。Claude に「決まりの案を見せて」と言えば一覧が出る`);
}

// 速い道（2026-10-07 本人「もっと早く。正確さは保って」）: 審査を通った回の実際のやり方を、役×小工程ごとに残し、次の回の指示に付ける
const 速い道の置き場 = path.join(STATE_ROOT, "速い道.json");
const 速い道 = () => { try { return JSON.parse(fs.readFileSync(速い道の置き場, "utf8")); } catch { return {}; } };
const 最後の道 = new Map(); // ブランド×案件×版×チャンネル -> { role, 道, 依頼, 分 }
const 小工程を読む = t => { const m = String(t).match(/工程\s*(\d)\s*[-・ ]?\s*(\d?[a-z])?/); return m ? `工程${m[1]}${m[2] ? " " + m[2] : ""}` : "その他"; };
function 速い道の節(role) {
  const 行 = 速い道()[role] || [];
  if (!行.length) return "";
  return `前に審査を通った回のやり方（役×小工程ごと）。同じ小工程の仕事なら、まずこの道で進め、道具の使い方や手順書を読み直さない。道が今回に合わない所だけ変える:\n${行.map(x => `■ ${x.小工程}（${x.日}・${x.分}分で通った）\n${x.道}`).join("\n")}`;
}
async function 速い道を学ぶ(rec, ctx) {
  if (!rec?.role || !rec.道?.length) return;
  const 小工程 = 小工程を読む(rec.依頼);
  const prompt = `あなたは、審査を通った仕事の実際の操作の記録から、次に同じ仕事を一番速く正確にやる手順を書く係。ファイルは読まない・書かない。\n役: ${rec.role}\n頼まれた事: ${rec.依頼}\n実際の操作（順番どおり）:\n${rec.道.slice(-150).join("\n")}\n\n次の回に同じ仕事を1回で通すための手順を、10行以内の番号付きで書く。試して捨てたやり方・読み直しは入れない。最後にうまくいったコマンドと道具はそのまま（引数の固有のファイル名は <参考> <声> のように置き換える）書く。手順以外の文は書かない。`;
  let text = "";
  try { for await (const m of query({ prompt, options: { model: "claude-opus-5-5", maxTurns: 1, tools: [], allowedTools: [], settingSources: [], permissionMode: "dontAsk", strictMcpConfig: true, mcpServers: {} } })) if (m.type === "result") text = m.result || ""; } catch (e) { console.error("速い道:", e.message); return; }
  if (!text.trim()) return;
  const 全部 = 速い道(); const 今 = (全部[rec.role] || []).filter(x => x.小工程 !== 小工程);
  今.unshift({ 小工程, 道: text.trim().slice(0, 2500), 日: new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" }), 分: rec.分, 案件: ctx.job_id });
  全部[rec.role] = 今.slice(0, 6); fs.writeFileSync(速い道の置き場, JSON.stringify(全部, null, 1));
  console.log(`速い道: ${rec.role} ${小工程}（${rec.分}分）を残した`);
}

// 審査に出す写しが正本と同じか（2026-10-07 本人「絶対にないようにして」。台本の古い写しで動画を審査し、8段のうち7段が違うと戻された）
// 作業フォルダの成果物と同じ名前の正本が Vault のブランドの置き場にあれば、中身が同じでなければ審査に入れない
function 写しが古くないか(査読, ctx) {
  if (VIO.固まった() || VIO.読む(LEDGER) === null) { console.error("写しの確かめ: Vault が開けないので今回は飛ばす"); return; }
  const roots = (ブランド設定()[ctx.brand]?.vault_write_roots || []).filter(r => fs.existsSync(r));
  for (const a of 査読?.artifacts || []) {
    const 名 = path.basename(a.path); if (!/\.(md|json|txt|html)$/i.test(名)) continue;
    const 正本 = [];
    const 探す = (d, n = 0) => { if (n > 6) return; for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory() && !e.name.startsWith(".")) 探す(p, n + 1); else if (e.name === 名 && path.resolve(p) !== path.resolve(a.path)) 正本.push(p); } };
    for (const r of roots) { try { 探す(r); } catch {} }
    const 一番新しい = 正本.sort((x, y) => fs.statSync(y).mtimeMs - fs.statSync(x).mtimeMs)[0];
    const 正本の中身 = 一番新しい && VIO.読む(一番新しい);
    if (正本の中身 !== null && 正本の中身 !== undefined && 正本の中身 !== false && 一番新しい && createHash("sha256").update(正本の中身).digest("hex") !== fileHash(a.path)) throw Error(`審査に出す写しが古い: ${名}。正本 ${一番新しい} と中身が違う。正本から写し直し、sha256 を取り直してから出す`);
  }
}

// 本人の書き込みから直しを拾う。台帳係は書かずに「台帳: 節 | 直し | 初めて|2回目」の行だけ返し、足すのはサーバー（台帳係に Vault の構造を書かせない）
function 台帳に足す(節名, 直し, 回) {
  const s = VIO.読む(LEDGER); if (s === null) { fs.appendFileSync(path.join(STATE_ROOT, "台帳の待ち.jsonl"), JSON.stringify({ 節名, 直し, 回, at: new Date().toISOString() }) + "\n"); return true; }
  const 始 = s.indexOf(`\n### ${節名}\n`); if (始 < 0) return false;
  const 次 = s.slice(始 + 1).search(/\n##+ /); const 終 = 次 < 0 ? s.length : 始 + 1 + 次;
  const 中 = s.slice(始, 終); const 最後 = 中.lastIndexOf("\n|"); if (最後 < 0) return false;
  const 行末 = 始 + 中.indexOf("\n", 最後 + 1); const at = 行末 < 始 ? 終 : 行末;
  const 日 = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
  const 列 = ((中.match(/\n\|[^\n]*\|/) || [""])[0].match(/\|/g) || []).length - 1;
  const 行 = `\n| ${直し.replace(/\|/g, "／")}（${日} 本人・部屋） | ${回 === "2回目" ? "読んで守る（2回目。道具で止める検査にする）" : "読んで守る"} |${" |".repeat(Math.max(0, 列 - 2))}`;
  fs.mkdirSync(path.join(STATE_ROOT, "台帳の控え"), { recursive: true }); fs.writeFileSync(path.join(STATE_ROOT, "台帳の控え", `${Date.now()}.md`), s);
  if (!VIO.書く(LEDGER, s.slice(0, at) + 行 + s.slice(at))) fs.appendFileSync(path.join(STATE_ROOT, "台帳の待ち.jsonl"), JSON.stringify({ 節名, 直し, 回, at: new Date().toISOString() }) + "\n"); return true;
}
function 台帳に拾う(channelId, text, ctx) {
  const 節名 = 台帳の節たち().map(x => x.名);
  const prompt = `[本人が #${チャンネル(channelId).name} に書いた]\n${text}\n\nこの書き込みに、作り方・審査・流れ・道具への直し（これからずっと守ってほしい決まり）が入っているかだけを見る。今回1回だけの頼みや質問は直しではない。\n直しがあれば、1件につき次の1行で返す（節は下の名前をそのまま1つ選ぶ。合う節が無ければ「ハーネスの直し（流れ・役の分け方・道具の決まり。手順書に書き移すまでの置き場）」）:\n台帳: <節の名前> | <直しを1文。本人の言葉を残す> | <初めて か 2回目>\n台帳に同じ直しがもうあれば「2回目」。直しが無ければ「台帳: なし」の1行だけ。ファイルは書かない。\n節の名前: ${節名.join(" / ")}`;
  return 動かす("台帳係", "hq", prompt, ctx, null, { dispatch_id: randomUUID(), max_turns: 4 }).then(r => {
    const 行たち = String(r?.output || "").split("\n").map(l => l.replace(/[*`]/g, "").replace(/｜/g, "|").replace(/^\s*[-・]\s*/, "").replace(/^台帳：/, "台帳:").match(/^台帳:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(初めて|2回目)\s*$/)).filter(Boolean);
    const 足した = 行たち.filter(m => 節名.includes(m[1].trim()) && 台帳に足す(m[1].trim(), m[2].trim(), m[3]));
    console.log(`台帳係: 本人の書き込み1件 → 直し${行たち.length}件 → 台帳に${足した.length}件`);
    fs.appendFileSync(path.join(STATE_ROOT, "台帳の記録.jsonl"), JSON.stringify({ at: new Date().toISOString(), channel: channelId, context: ctx, 本人: text.slice(0, 500), 拾った: 行たち.map(m => ({ 節: m[1], 直し: m[2], 回: m[3] })), 足した: 足した.length }) + "\n");
    const 落ちた = 行たち.filter(m => !足した.includes(m));
    if (落ちた.length) 書く("hq", "台帳係", "error", `台帳に足せなかった（節の名前が合わない）: ${落ちた.map(m => m[1] + " | " + m[2]).join(" / ")}`, null, ctx);
    if (足した.length) 書く("hq", "台帳係", "text", `台帳に足した（次に動く役から効く）:\n${足した.map(m => `・${m[1].trim().split("（")[0]}: ${m[2].trim()}${m[3] === "2回目" ? "（2回目）" : ""}`).join("\n")}`, null, ctx);
    if (足した.some(m => m[3] === "2回目")) 通知(`🔁 同じ直しを2回もらった｜${足した.filter(m => m[3] === "2回目").map(m => m[2].trim()).join(" / ")}\n読んで守るが効いていないので、道具で止める検査にする`);
  }).catch(e => console.error("台帳係:", e.message));
}
const PORT = Number(process.env.TEAM_ROOM_PORT || (VERIFICATION ? 3201 : 3200));
const SOURCE_REVISION = fileHash(fileURLToPath(import.meta.url));
const CSRF_TOKEN = randomUUID();
const { 収束させる } = await import(pathToFileURL(path.join(ROOT, "review-converge.mjs")).href);
const JEV = await import(pathToFileURL(path.join(HOME, "Claude Code/ec-harness/agent_team/jev-openrouter.mjs")).href);
// 判断の層（JEV）。1回の審査で0.01ドルまで・10回まで。鍵が無ければ null で、編集長の判定のまま
// 判断の層の自信が線より低いずれだけ、Opus に3択から1つを聞き直す（道具なし・1手）
async function Opusに聞き直す(ずれ, 種類) {
  const 選べる = Object.keys(種類).filter(k => k !== "other");
  const prompt = `審査のずれを1つ分ける。答えは次の言葉のどれか1つだけを書く: ${選べる.join(" / ")}\n${選べる.map(k => `- ${k}: ${種類[k]}`).join("\n")}\nずれ: 「${ずれ}」`;
  let text = "";
  for await (const m of query({ prompt, options: { model: "claude-opus-5-5", maxTurns: 1, tools: [], allowedTools: [], settingSources: [], permissionMode: "dontAsk", strictMcpConfig: true, mcpServers: {} } })) if (m.type === "result") text = m.result || "";
  return 選べる.find(k => text.includes(k)) || "other";
}
const 判断の層 = () => { try { return JEV.openRouterJev({ apiKey: JEV.existingJevKey(path.join(HOME, ".config/jev/.env")), budgetUsd: 0.01, maxCalls: 10 }); } catch (e) { console.error("判断の層が使えない:", e.message); return null; } };
const { contract, issueApproval, recordReview } = await import(pathToFileURL(path.join(HOME,"Claude Code/ec-harness/lib/contract_bridge.mjs")).href);
const BRAND_CONFIG_PATH = process.env.EC_BRAND_CONFIG || path.join(HOME, "Claude Code/ec-harness/config/brands.json");
const {createHash} = await import("node:crypto");
const {readMeta} = await import(pathToFileURL(path.join(HOME,"Claude Code/ec-harness/lib/meta_readonly.mjs")).href);
function ブランド設定() {
  const cfg = JSON.parse(fs.readFileSync(BRAND_CONFIG_PATH, "utf8"));
  return cfg.brands;
}
function 読取範囲(c, review) {
  const b = ブランド設定()[c.brand];
  const assets = [...書込範囲(c), ...(b.read_roots || []), b.angle_ledger_path, b.metrics_path].filter(Boolean);
  if (!assets.length) throw Error("ブランドの読取範囲設定が無い");
  if (review) {
    for (const a of review.artifacts || []) if (!inside(a.path, 書込範囲(c))) throw Error("別ブランドのレビュー成果物");
    // 編集長は作り手の会話は読まないが、引用が原文どおりかを照らすため原文（案件フォルダ）と決まり（図・手順書）は読む
    return [...review.artifacts.map(a => a.path), ...(b.vault_write_roots || []), ...共有の読取];
  }
  return [...assets, ORG, ROLE_DIR, ...共有の読取];
}
// 全役が読む物: 図・手順書・役（ec/構造）、手順書が呼ぶスキルと道具（2026-10-05 以前は読めず手順書どおりに動けなかった）
// 1回の仕事の上限（2026-10-05 以前は20手・15分・無反応2分で、リサーチの途中で必ず切れていた）。
// 楽天・知恵袋の取得は1コマンド数分かかり、工程2は2a〜2fで100手を超える
// 2026-10-05 本人「上限なしで、終わり次第次へ。接続が切れた時に効くように」。時間・手数では打ち切らない。
// total_ms は setTimeout の上限（24.8日）より下の7日を「無し」の代わりに置く。30分まったく反応が無ければ切れたとみなし、続きから再開する
const 既定 = { max_turns: 100000, total_ms: 7 * 24 * 3600 * 1000, stall_ms: 30 * 60 * 1000 };
const 印の長さ = 20 * 60 * 1000, 印の更新 = 5 * 60 * 1000;
const 共有の読取 = [path.join(HOME, ".claude/projects"), "/private/tmp", "/tmp", path.join(VAULT, "ec/構造"), path.join(HOME, ".claude/skills"), path.join(HOME, "Claude Code/ec-harness")];
function 書込範囲(c) {
  const b = ブランド設定()[c.brand];
  // 作業フォルダ（版つき）に加えて、手順書が成果物の置き場に指定している Vault のブランド／案件フォルダ
  return [...(b.asset_roots || []).map(r=>path.join(r,c.job_id,`r${c.revision}`)), ...(b.vault_write_roots || [])];
}
const 設定 = JSON.parse(fs.readFileSync(path.join(ROOT, "roles.json"), "utf8"));
VIO.控えを置く(path.join(STATE_ROOT, "vault控え"));
const { autopilotStore, decide: 自動の判断 } = await import(pathToFileURL(path.join(ROOT, "autopilot.mjs")).href);
const 自動 = autopilotStore(path.join(STATE_ROOT, "autopilot.json"));
const { treeOf: 木の形, jobsOf, buildTree: 木を作る } = await import(pathToFileURL(path.join(ROOT, "tree.mjs")).href);
const { refImage: 参考の絵, refInfo: 参考の中身 } = await import(pathToFileURL(path.join(ROOT, "ref.mjs")).href);
const { makeDeps: 材料 } = await import(pathToFileURL(path.join(ROOT, "tree-deps.mjs")).href);
const { linesOf: ラインの一覧, lineOf: ラインは } = await import(pathToFileURL(path.join(ROOT, "lines.mjs")).href);
const { teamOf: チームの形 } = await import(pathToFileURL(path.join(ROOT, "team.mjs")).href);

// ── 記録（SQLite） ──
fs.mkdirSync(STATE_ROOT, { recursive: true });
const db = new DatabaseSync(path.join(STATE_ROOT, "room.db"));
db.exec(`
  CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, author TEXT, kind TEXT, text TEXT, meta TEXT, ts INTEGER);
  CREATE TABLE IF NOT EXISTS scoped_sessions (scope TEXT PRIMARY KEY, session_id TEXT);
  CREATE TABLE IF NOT EXISTS scoped_approvals (id INTEGER PRIMARY KEY, manifest_hash TEXT, manifest TEXT, approval TEXT);
`);
const runtime = runtimeStore(db);
const 行に = (r) => r && ({ ...r, meta: r.meta ? JSON.parse(r.meta) : null });
// 流れの木の案件一覧（記録が増えた時だけ数え直す）
const 木 = { 版: -1, 中身: [], jobs() { const n = db.prepare("SELECT max(id) n FROM messages").get().n; if (n !== this.版) { this.中身 = jobsOf(db.prepare("SELECT ts, kind, author, text, json_extract(meta,'$.context.brand') brand, json_extract(meta,'$.context.job_id') job_id, json_extract(meta,'$.context.revision') revision, json_extract(meta,'$.to') \"to\" FROM messages").all()); this.版 = n; } return this.中身; } };

// ── 画面への生配信（SSE） ──
const 聞き手 = new Set();
const 流す = (ev) => { for (const item of 聞き手) { if (ev.msg && !sameContext(ev.msg.meta?.context,item.ctx)) continue; const scoped = ev.type === "status" ? {...ev, status:Object.fromEntries(Object.entries(ev.status).filter(([_,v])=>sameContext(v.context,item.ctx)).map(([k,v])=>[JSON.parse(k)[0],v]))} : ev;
    item.res.write(`data: ${JSON.stringify(scoped)}\n\n`); } };

function 書く(channel, author, kind, text, meta = null, ctx = null) {
  meta = { ...(meta || {}), context: ctx };
  const r = db.prepare("INSERT INTO messages (channel, author, kind, text, meta, ts) VALUES (?,?,?,?,?,?)")
    .run(channel, author, kind, text, meta ? JSON.stringify(meta) : null, Date.now());
  const msg = 行に(db.prepare("SELECT * FROM messages WHERE id = ?").get(r.lastInsertRowid));
  流す({ type: "message", msg });
  return msg;
}
function 直す(id, meta) {
  db.prepare("UPDATE messages SET meta = ? WHERE id = ?").run(JSON.stringify(meta), id);
  流す({ type: "update", msg: 行に(db.prepare("SELECT * FROM messages WHERE id = ?").get(id)) });
}

// ── 役の状態 ──
const 状態 = new Map(); // role -> { busy, channel, abort, chain }
const 役の状態 = (role, ctx) => { const key = ctx ? sessionKey(role, "", ctx) : role; if (!状態.has(key)) 状態.set(key, { busy: false, channel: null, abort: null, chain: Promise.resolve(), 今: null, 最後: null }); return 状態.get(key); };
const 状態を流す = () => 流す({ type: "status", status: Object.fromEntries([...状態].map(([k, v]) => [k, { busy: v.busy, channel: v.channel, context:v.context, 今: v.今, 最後: v.最後 }])) });

// ── 組織図から役の行を引く（写さず毎回読む） ──
function 組織図の行(role) {
  try {
    const 行 = (VIO.読む(ORG) ?? "").split("\n").find((l) => l.startsWith(`| ${role} |`));
    return 行 || "";
  } catch { return ""; }
}
function 手順書(role) {
  const p = path.join(ROLE_DIR, `${role}.md`);
  const t = VIO.読む(p); return t === null ? null : { path: p, text: t };
}
// 1対1（dm:<役>）は、その役だけのチャンネル。メンバーはいないので、誰にも振らずに自分で答える
const チャンネル = (id) => {
  if (String(id).startsWith("dm:")) { const r = id.slice(3); return 設定.roles[r] ? { id, name: r, lead: r, members: [], dm: true } : null; }
  return 設定.channels.find((c) => c.id === id);
};

function 指示(role, ch) {
  const 書 = 手順書(role);
  const lead = ch.lead === role;
  return [
    `あなたは「${role}」。共有のEC部門で、指定されたブランドと案件だけを担当する。`,
    `組織の決まりの正本: ${ORG}（必要な時だけ読む）。`,
    `組織図のあなたの行: ${組織図の行(role) || "（まだ無い）"}`,
    書 ? `あなたの手順書: ${書.path}\n---\n${書.text}\n---` : "あなた専用の手順書はまだ無い。組織図の行の仕事だけをする。分からない所は推測で埋めず、チャンネルに質問を1行書いて止まる。",
    ch.dm ? "今いる場所: 本人（オーナー）との1対1の会話。" : `今いる場所: チャンネル「#${ch.name}」。リーダー: ${ch.lead}。メンバー: ${ch.members.join("・")}。本人（オーナー）も見ている。`,
    ch.dm ? "本人に聞かれた事に、自分の役の範囲で答える。他の役の仕事が要る時は、どの役に頼むべきかを1行で言う。" : lead
      ? "あなたはこのチャンネルのリーダー。自分では作業しない。仕事は `delegate` ツール（頼む）でメンバーに1つずつ振り、返ってきた物を編集長に確かめさせてから、本人にまとめて返す。"
      : "リーダーかメンバーから頼まれた自分の部分だけをやる。他の役の仕事はしない。終わったら、渡す物のパスと1行の結果を返す。",
    台帳の節(role),
    戻しの節(role),
    速い道の節(role),
    "確かめのコマは、並べた1枚（何コマかを1枚に並べた画像）を作って見る。1枚ずつ読むのは並べた1枚で気になった所だけ（2026-10-07 本人）。1回の仕事で画像を読めるのは12枚まで。",
    "本人に向けた返事は『課長の報告』の形にする: 1行目 結論 / 2〜4行目 何が・どうなった（数字は1つまで）/ 最後の行 あなたが決めること（無ければ「無し」）。日本語。コードや内部の言葉は出さない。",
    "戻せない行動（配信・予算の変更・本番公開・送信・削除・支払い・発注）は、道具が止めて本人の承認カードを出す。却下されたら別の道を探さず、そこで止まって報告する。",
    "時間のかかる処理（書き出し・生成）を待つ時は、前で待つ（until ループを前で回す）。背景に回して手番を終えない。部屋の中では手番を終えたあとに起こされることは無い（2026-10-07 キッズの動画で止まった）。",
    "ブラウザ（裏用 Dia）で開いたタブは、読み終えたらその場で `dia close <タブ>` で閉じる。開きっぱなしにしない（2026-10-06 本人「開くごとに消して」）。",
  ].join("\n\n");
}
// ブランド担当（2026-10-07 本人「ブランドが増えても同じ作業でぶつからないように。ここちドライなら、ここちドライ用のストラテジストが立つ」）。
// 同じ役でも、ブランド×案件×版ごとに別の会話・別の作業フォルダ・別のブラウザのタブで動く。ここではその名乗りと、ブランドの入口だけを渡す（中身は写さない）
function ブランド担当(role, ctx) {
  // ラインがあればラインの入口（例 ec/ここちドライ/男性用/_入口.md）。無ければブランドの入口
  const ライン = ラインは(ctx.brand, ctx.job_id);
  const ラインの入口 = ライン && path.join(VAULT, "ec", ctx.brand, ライン.name, "_入口.md");
  const 入口 = ラインの入口 && fs.existsSync(ラインの入口) ? ラインの入口 : path.join(VAULT, "ec", ctx.brand, "_入口.md");
  return [
    `\n\nあなたは「${ctx.brand}${ラインは(ctx.brand, ctx.job_id) ? `（${ラインは(ctx.brand, ctx.job_id).name}）` : ""}」担当の${role}。持つのは案件 ${ctx.job_id}（${ctx.revision}回目）だけ。ほかのブランド・ほかのライン・ほかの案件の物は読まない・書かない・触らない。`,
    ラインは(ctx.brand, ctx.job_id) ? `${ctx.brand} の中でも ${ラインは(ctx.brand, ctx.job_id).name} は客も仕事も別。もう一方のラインの台帳・広告・声を自分のラインの物として使わない。` : "",
    fs.existsSync(入口) ? `${ctx.brand} の決まりと置き場は ${入口} から引く（要る行だけ。ほかのブランドの入口は開かない）。` : "",
    "ブラウザは自分で dia open したタブだけを使う（タブ指定なしの dia は自分が最後に開いたタブに当たる）。",
    "Obsidian が情報源。調べた物・決めた物・作った物の文字は、終わる前に必ず Vault の ec/<ブランド>/<ライン>/<番号>/ に置く（動画・画像・HTML はデスクトップの ~/Desktop/ec/<ブランド>/<ライン>/<番号>/）。HANDOFF の渡す物はその置き場のパスで書く。作業フォルダだけに置いた物は、自動の振り分けが次へ渡さずに戻す。",
    "同じブランドの別の案件が書いているファイルは、書こうとすると止められる。止められたら作業フォルダ側を先に進め、あとで書く。",
  ].filter(Boolean).join("\n");
}

// 同じブランドの別の案件が、同じファイルを同時に書かない（Vault の台帳など、ブランドで1つの物）。最後に書いてから10分は持ち主のもの
const 書き手 = new Map(); // 絶対パス -> { key, label, at }
function 書いてよいか(file, ctx, role) {
  if (!file) return null;
  const key = contextKey(ctx), now = Date.now(), h = 書き手.get(file);
  if (h && h.key !== key && now - h.at < 10 * 60 * 1000) return `同じファイルを別の案件（${h.label}）が書いている途中。${Math.ceil((10 * 60 * 1000 - (now - h.at)) / 60000)}分以内に空く。作業フォルダ側を先に進め、あとで書く`;
  書き手.set(file, { key, label: `${ctx.job_id} の${role}`, at: now });
  return null;
}

// 自動で進めている案件の部長にだけ足す（autopilot.mjs が HANDOFF 行を読んで次の部へ渡す）
function 自動の指示(role, ch, ctx) {
  const job = ctx && 自動.get(ctx);
  if (!job?.on || ch.lead !== role || ch.dm) return "";
  return `\n\n【自動で進めている案件】本人は寝ている。本人に途中の判断を聞かず、手順書と客の声の数で決めて理由を残し、ゴールまで進める。\nゴール: ${job.goal}\nこの部の仕事が編集長を通ったら、返事の最後の行に HANDOFF を書く: 次の工程の部長（戦略責任者／クリエイティブディレクター／ファネル責任者／グロース責任者）宛て。「本人」宛てにするのは、本番公開・配信・予算・お金のかかる発注しか残っていない時か、ゴールの物が全部揃った時だけ。`;
}

// Application boundary: opaque commands and unknown tools never acquire approval.
const 待ち = new Map();
async function 承認を待つ(role, channel, policy, ctx, signal) {
  const manifest = structuredClone(policy.manifest);
  const msg = 書く(channel, role, "approval", `${ctx.brand} / ${ctx.job_id} / ${ctx.revision}: ${manifest.operation}`, {
    status: "待ち", manifest_hash: policy.manifest_hash, input: JSON.stringify(manifest, null, 2), manifest
  }, ctx);
  db.prepare("INSERT INTO scoped_approvals (id, manifest_hash, manifest) VALUES (?,?,?)")
    .run(msg.id, policy.manifest_hash, JSON.stringify(manifest));
  const answer = await new Promise(resolve => {
    const timer=setTimeout(()=>resolve(null),5*60*1000); timer.unref();
    待ち.set(msg.id, {resolve:(v)=>{clearTimeout(timer);resolve(v);}, ctx, manifest, manifest_hash:policy.manifest_hash});
    signal?.addEventListener("abort", () => resolve(null), {once:true});
  });
  待ち.delete(msg.id);
  const bc = ブランド設定()[ctx.brand];
  const ok = approvalMatches(answer, manifest, Date.now(), bc.owners, Math.min(300,bc.approval_max_seconds || 300));
  直す(msg.id, {...msg.meta, status:ok ? "承認":"却下", approval:answer});
  db.prepare("UPDATE scoped_approvals SET approval = ? WHERE id = ?").run(JSON.stringify(answer), msg.id);
  return ok;
}

// ── Telegram（本人への通知はここだけ） ──
const 公開URL = `http://localhost:${PORT}`;
function 通知(text) {
  if (VERIFICATION) return;
  try {
    const { token, chat_id } = JSON.parse(fs.readFileSync(path.join(HOME, ".telegram-arukoto.json"), "utf8"));
    fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id, text }), signal: AbortSignal.timeout(15000),
    }).catch(() => {});
  } catch { /* 設定が無ければ画面だけ */ }
}

// ── 裏用 Dia（9333）のタブの片付け: どの役も動いていない時だけ、残ったタブを全部閉じる（本人の Dia 9222 は触らない） ──
// 2026-10-06 本人「タブが開きすぎてるから開くごとに消して」。走っている役のタブを閉じないよう、全員が空いた時だけ
async function 裏のタブを片付ける() {
  try {
    if ([...状態.values()].some(v => v.busy)) return;
    const tabs = (await (await fetch("http://127.0.0.1:9333/json/list", { signal: AbortSignal.timeout(5000) })).json()).filter(t => t.type === "page");
    for (const t of tabs.slice(1)) await fetch(`http://127.0.0.1:9333/json/close/${t.id}`, { signal: AbortSignal.timeout(5000) }).catch(() => {});
    if (tabs.length > 1) console.log(`裏の Dia のタブを ${tabs.length - 1} 枚閉じた`);
  } catch { /* 裏の Dia が動いていなければ何もしない */ }
}

// ── 役を1回動かす（同じ役は順番待ち） ──
// 接続が切れた・反応が無くなった・サーバーが落ちて中断された時は、打ち切らず同じ会話の続きから再開する（2026-10-05）
const 切れた = (r) => r && r.status !== "success" && r.status !== "cancelled" && !長すぎ(r) && (["stalled","timeout","interrupted","lease_lost"].includes(r.code) || ネットの切れ(r));
// 2026-10-05 15:41 Mac のネットが切れて ENOTFOUND で4本とも止まった。前の判定にこの語が無く再開しなかった
// 見るのは error だけ。output（編集長の判定の JSON など）には16進のハッシュが入り「503」等に当たって、ふつうの結果を切れと読み違えて無限に再開していた（2026-10-06 キッズの編集長）
const ネットの切れ = (r) => /exited with code|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ENETUNREACH|EHOSTUNREACH|EPIPE|socket hang up|network|fetch failed|Can't reach|internet|DNS|overloaded|rate.?limit|\b(529|502|503|504)\b/i.test(String(r?.error || ""));
async function つながるまで待つ() {
  // 回数で諦めない。ネットが戻るまで1分ごとに確かめる（戻った時点で次へ進む）
  for (;;) {
    try { await import("node:dns/promises").then(d => d.lookup("api.anthropic.com")); return; } catch {}
    await new Promise(r => setTimeout(r, 60000));
  }
}
// 会話が長くなりすぎた時（Prompt is too long）は、同じ会話を続けても毎回落ちる。保存した会話を捨てて新しく始め、成果物から続きを拾わせる（2026-10-06 リサーチャーが無限に再開しかけた）
const 長すぎ = (r) => /Prompt is too long|prompt is too long|context.{0,20}(length|window)/i.test(String(r?.error || "") + " " + String(r?.output || ""));
async function 切れても続ける(role, channelId, prompt, ctx, review, runOptions) {
  let result = await 一回(role, channelId, prompt, ctx, review, runOptions);
  if (長すぎ(result) && !runOptions.parent_signal?.aborted) {
    db.prepare("DELETE FROM scoped_sessions WHERE scope = ?").run(sessionKey(role, channelId, ctx));
    書く(channelId, "system", "error", `${role} の会話が長くなりすぎたので、新しい会話で続きから始める（作業フォルダの成果物から拾う）`, null, ctx);
    result = await 一回(role, channelId, `${prompt}\n\n（前の会話が長くなりすぎて切れた。作業フォルダにある成果物と、チャンネルの最近の記録を見て、終わっている所は作り直さず続きからやる）`, ctx, review, { ...runOptions, resume: false, dispatch_id: (runOptions.dispatch_id || "") + "/新しい会話" });
  }
  // ネットの切れは戻るまで何度でも続きから。それ以外の切れ（反応なし等）は5回まで
  for (let n = 1, other = 0; 切れた(result) && (ネットの切れ(result) || ++other <= 5); n++) {
    if (runOptions.parent_signal?.aborted) break;
    書く(channelId, "system", "error", `${role} の接続が切れた／反応が無くなった。つながるのを待って続きから再開する（${n}回目）`, null, ctx);
    await new Promise(r => setTimeout(r, Math.min(30000 * n, 300000)));
    await つながるまで待つ();
    result = await 一回(role, channelId, prompt, ctx, review, { ...runOptions, resume: true });
  }
  return result;
}
// 同時に動く役は部屋全体で4人まで（2026-10-07 本人。10/6 夜は8人が同時に動いて利用枠に当たり30分全員止まった）
// 頼んだ返事を待っている間は枠を返す（4人の部長が待ち合って誰も動けなくなるのを防ぐ）
const 同時の上限 = 4;
const 枠 = { 使用: 0, 列: [], 取る() { if (this.使用 < 同時の上限) { this.使用++; return Promise.resolve(); } return new Promise(r => this.列.push(r)); }, 返す() { const n = this.列.shift(); if (n) n(); else this.使用--; } };
function 動かす(role, channelId, prompt, ctx, review = null, runOptions = {}) {
  const s = 役の状態(role, ctx);
  // 準備で落ちた時も黙らずチャンネルに出す（2026-10-05 権限の上限で落ちて2時間だれも気付かなかった）
  const run = s.chain.then(async () => { await 枠.取る(); try { return await 切れても続ける(role, channelId, prompt, ctx, review, runOptions); } finally { 枠.返す(); } }).catch(e=>{try{書く(channelId,"system","error",`${role} が動き出せなかった: ${String(e.message||e)}`,{},ctx);}catch{} return runtimeResult({...ctx,role,channel:channelId},"error","",{code:e.code||"setup_error",error:String(e.message||e)});});
  s.chain = run.catch(() => {});
  return run;
}

function 道具の一言(name, input) {
  const 短 = (v) => String(v ?? "").replace(/\s+/g, " ").slice(0, 90);
  if (name === "Bash") return `コマンド: ${短(input.description || input.command)}`;
  if (name === "Read") return `読む: ${短(input.file_path)}`;
  if (name === "Write" || name === "Edit") return `書く: ${短(input.file_path)}`;
  if (name === "Grep" || name === "Glob") return `探す: ${短(input.pattern)}`;
  if (name === "WebSearch") return `調べる: ${短(input.query)}`;
  if (name === "WebFetch") return `開く: ${短(input.url)}`;
  if (name === "Skill") return `スキル: ${短(input.skill)}`;
  if (name === "mcp__team__delegate") return null; // 頼んだ事は別の行で出す
  return `${name.replace(/^mcp__/, "").replace(/__/g, " ")}`;
}

async function 一回(role, channelId, prompt, ctx, review, runOptions = {}) {
  const identity={...ctx,role,channel:channelId,dispatch_id:runOptions.dispatch_id||null};
  if(runOptions.parent_signal?.aborted)return runtimeResult(identity,"cancelled","",{code:"cancelled"});
  const requestId=requestKey(role,channelId,ctx,prompt,review,runOptions.dispatch_id);
  const lease=runtime.begin(requestId,identity,{resume:runOptions.resume===true,leaseMs:印の長さ,request:{prompt,review,options:Object.fromEntries(["dispatch_id","max_turns","total_ms","stall_ms","force_lead","source"].filter(k=>runOptions[k]!==undefined).map(k=>[k,runOptions[k]]))}});
  if(lease.cached)return lease.cached;
  // 裏用 Dia は役が手順どおり作業の終わりに止めることがある。動き出す前に毎回立て直す（動いていれば何もしない）
  await new Promise(r => execFile("python3", [path.join(HOME, ".claude/skills/browser/scripts/dia_agent.py"), "start"], { timeout: 60000 }, () => r()));
  const 心拍=setInterval(()=>{try{runtime.renew(requestId,lease.owner,印の長さ);}catch{}
    // 遅れの見張り（2026-10-07 本人「いつもしっかり見れる仕組み」）: 頼んだ返事や承認を待っていないのに20分を超えたら、1回だけ知らせる
    try{const w=役の状態(role,ctx);if(w.busy&&w.始&&!w.遅れを言った&&!w.waitingApproval&&!(w.awaitingDelegates>0)&&Date.now()-w.始>20*60*1000){w.遅れを言った=true;const 分=Math.round((Date.now()-w.始)/60000);書く("hq","system","error",`遅れ: ${ctx.job_id} の${role}が${分}分たっても終わっていない（今: ${w.今||""}）。画像${w.画像}枚・操作${w.道?.length||0}回`,null,ctx);通知(`🐢 遅れ｜${ctx.job_id} の${role}が${分}分\n今: ${w.今||""}`);fs.appendFileSync(path.join(STATE_ROOT,"遅れ.jsonl"),JSON.stringify({at:new Date().toISOString(),role,context:ctx,分,今:w.今,画像:w.画像,道:(w.道||[]).slice(-40)})+"\n");}}catch{}
  },印の更新);
  try {
  const ch = チャンネル(channelId);
  const s = 役の状態(role, ctx);
  const readRoots = 読取範囲(ctx, role === "編集長" ? review : null);
  const rc = runContext(role, channelId, ctx, review);
  if (rc.reviewer && review.max_turns !== undefined && (!Number.isSafeInteger(review.max_turns) || review.max_turns<1 || review.max_turns>60)) throw Error("レビューの最大turn数は1〜60で明示する");
  const writeRoots = 書込範囲(ctx);
  if (!writeRoots.length) throw Error("案件の成果物保存先が無い");
  for (const root of writeRoots) {
    const b=ブランド設定()[ctx.brand];
    if (!inside(root,[...(b.asset_roots || []),...(b.vault_write_roots || [])])) throw Error("成果物保存先がブランド範囲外");
    fs.mkdirSync(root,{recursive:true});
  }
  s.context = ctx;
  s.busy = true; s.channel = channelId; s.abort = new AbortController(); s.今 = "考えています"; 状態を流す();
  s.始 = Date.now(); s.画像 = 0; s.遅れを言った = false; s.道 = []; s.依頼 = String(prompt).slice(0, 400);
  const controller=s.abort;
  const parentAbort=()=>controller.abort();
  if(runOptions.parent_signal?.aborted)controller.abort();else runOptions.parent_signal?.addEventListener("abort",parentAbort,{once:true});
  const sid = rc.resume ? (lease.resumeSid || db.prepare("SELECT session_id FROM scoped_sessions WHERE scope = ?").get(rc.key)?.session_id) : undefined;
  if (rc.reviewer) prompt = rc.prompt;
  const cap=createRoleCapabilities({role,ctx,brandConfig:ブランド設定()[ctx.brand],runId:rc.run_id,signal:s.abort.signal,reviewArtifacts:review?.artifacts,leaseExpiresAt:Date.now()+(runOptions.total_ms||既定.total_ms)});
  const toolErrors=[],childResults=(lease.priorResult?.children||[]).map(child=>{const current=child.request_id&&runtime.get(child.request_id);return current&&completedResultIntact(current,ctx)?current:child;}),createdArtifacts=[...(lease.priorResult?.artifacts||[])];
  const checkpoint=()=>{if(!runtime.progress(requestId,lease.owner,runtimeResult({...identity,run_id:rc.run_id,request_id:requestId},"partial","",{code:"running_checkpoint",artifacts:createdArtifacts,children:childResults})))throw Error("runtime checkpoint lease lost");};
  const childOutcome=result=>{const i=childResults.findIndex(r=>r.request_id&&r.request_id===result.request_id);if(i>=0)childResults[i]=result;else childResults.push(result);checkpoint();};
  const capCall=(name)=>async(input)=>{try{const value=await cap[name](input);if(value.artifact&&inside(value.artifact.path,writeRoots)&&!createdArtifacts.some(a=>a.path===value.artifact.path&&a.sha256===value.artifact.sha256))createdArtifacts.push(value.artifact);if(value.artifact)checkpoint();return{content:[{type:"text",text:JSON.stringify(value)}],isError:false};}catch(e){toolErrors.push({operation:name,error:String(e.message||e)});return{content:[{type:"text",text:JSON.stringify({status:"error",error:String(e.message||e)})}],isError:true};}};
  const mcpServers = {local:createSdkMcpServer({name:"local",version:"1.0.0",tools:[
    ...(cap.operations.includes("local_artifact_create")?[tool("local_artifact_create","この役・ブランド・案件・版のローカル成果物だけを作る",{relative_path:z.string(),mime_type:z.string(),content_utf8:z.string().optional(),content_base64:z.string().optional()},capCall("create"))]:[]),
    ...(cap.operations.includes("local_artifact_inspect")?[tool("local_artifact_inspect","許可された案件・ブランドの素材を読む",{path:z.string(),expected_sha256:z.string().optional(),max_bytes:z.number().optional()},capCall("inspect"))]:[]),
    ...(cap.operations.includes("local_artifact_list")?[tool("local_artifact_list","この案件の成果物一覧",{relative_dir:z.string().optional()},capCall("list"))]:[])
  ]})};
  if (ch.lead === role && ch.members.length) {
    mcpServers.team = createSdkMcpServer({
      name: "team", version: "1.0.0",
      tools: [tool("delegate", "チャンネルのメンバー1人に仕事を1つ頼み、終わるまで待って返事を受け取る（頼む）。", {
        role: z.string().describe(`頼む相手。次のどれか: ${ch.members.join("、")}`),
        request: z.string().describe("相手にやってほしい事。入る物のパスと、終わりの形を書く"),
        review: z.object({artifacts:z.array(z.object({path:z.string(),revision:z.number().int().positive(),sha256:z.string()})),rules:z.string()}).optional(),
      }, async ({ role: 役, request: 依頼, review: 査読 }) => {
        try {
        if (!ch.members.includes(役)) throw Error(`「${役}」はこのチャンネルにいない`);
        if (役 === "編集長") { 読取範囲(ctx, 査読); runContext(役, channelId, ctx, 査読); 写しが古くないか(査読, ctx); }
        const targetChannel = delegationChannel(設定, channelId, 役);
        書く(channelId, role, "handoff", `@${役} ${依頼}`, { to: 役, targetChannel }, ctx);
        if (役 !== "編集長") 最後の作り手.set(contextKey(ctx) + targetChannel, 役);
        s.awaitingDelegates=(s.awaitingDelegates||0)+1;
        枠.返す();
        try {
          const result=await 動かす(役,targetChannel,`[${role}から頼まれた] ${依頼}`,ctx,査読,{...runOptions,parent_signal:controller.signal,dispatch_id:(runOptions.dispatch_id||requestId)+"/"+役+"/"+digest(依頼)});
          childOutcome(result);書く(channelId,role,"handoff_result",`${役}: ${result.status}`,{to:役,result},ctx);
          return handoffResponse(result);
        }finally{s.awaitingDelegates--; await 枠.取る(); }
        }catch(e){const result=runtimeResult({...ctx,role:役,channel:channelId},"error","",{code:"delegate_error",error:String(e.message||e)});toolErrors.push({operation:"mcp__team__delegate",error:result.error});childOutcome(result);return handoffResponse(result);}
      })],
    });
  }
  let 最後 = "";
  let sdkRunId = null;
  let resultSuccess = false;
  let failure=null;
  try {
    const stream=query({
      prompt,
      options: {
        cwd: writeRoots[0] || ROOT,
        resume: sid,
        model: 設定.roles[role]?.model, // 2026-10-07 本人「作業の役は Sonnet、判断の役は Opus」（roles.json の model）
        maxTurns:rc.reviewer ? (review.max_turns ?? 60) : (runOptions.max_turns ?? 既定.max_turns),
        abortController: s.abort,
        systemPrompt: { type: "preset", preset: "claude_code", append: 指示(role, ch) + 自動の指示(role, ch, ctx) + ブランド担当(role, ctx) + "\n案件境界: " + JSON.stringify(ctx) },
        settingSources: rc.reviewer ? [] : ["user", "project"],
        // 役のブラウザは画面外の裏用 Dia（9333）。本人の Dia（9222）は触らない。2026-10-05 本人の Dia の受け口が閉じていて Alibaba で止まった
        // DIA_OWNER: この担当（ブランド/案件/版/役）が開いたタブだけを触る。別ブランドの担当のタブを掴まない（2026-10-07）
        env: { ...process.env, DIA_CDP_PORT: "9333", DIA_SOCK: "/tmp/dia-cdp-9333.sock", DIA_OWNER: `${ctx.brand}/${ctx.job_id}/r${ctx.revision}/${role}` },
        permissionMode: "bypassPermissions",
        allowDangerouslySkipPermissions: true,
        mcpServers,
        hooks: {
          PreToolUse: [{
            timeout: 86400,
            hooks: [async (input, _id, { signal }) => {
              let policy = input.tool_name.startsWith("mcp__local__") ? cap.policy(input.tool_name,input.tool_input||{}) : toolPolicy(input.tool_name, input.tool_input || {}, ctx, readRoots, rc.reviewer, writeRoots);
              if (policy.decision === "allow" && ["Write","Edit","NotebookEdit"].includes(input.tool_name)) { const 待て = 書いてよいか(input.tool_input?.file_path || input.tool_input?.notebook_path, ctx, role); if (待て) policy = { decision: "deny", reason: 待て }; }
              if (policy.decision === "allow" && input.tool_name === "Read" && /\.(png|jpe?g|webp|gif)$/i.test(input.tool_input?.file_path || "") && ++s.画像 > 12) policy = { decision: "deny", reason: "画像は1回の仕事で12枚まで（2026-10-07 本人「確かめは並べた1枚で」）。何コマかを1枚に並べた画像を作って、それを読む" };
              if (policy.decision === "allow" && s.道) { const ti = input.tool_input || {}; const 行 = input.tool_name === "Bash" ? `$ ${String(ti.command || "").slice(0, 300)}` : ["Write", "Edit"].includes(input.tool_name) ? `${input.tool_name} ${ti.file_path || ""}` : input.tool_name.startsWith("mcp__") ? `${input.tool_name} ${JSON.stringify(ti).slice(0, 150)}` : null; if (行) { s.道.push(行); if (s.道.length > 400) s.道.shift(); } }
              let ok = policy.decision === "allow";
              if (policy.decision === "approval") {
                const frozenInput = structuredClone(input.tool_input);
                s.waitingApproval=true;
                try { ok = await 承認を待つ(role, channelId, policy, ctx, signal); } finally {s.waitingApproval=false;}
                // Any input mutation during the wait invalidates the authorization.
                ok = ok && JSON.stringify(input.tool_input) === JSON.stringify(frozenInput) && inside(frozenInput.file_path,writeRoots) && fileHash(frozenInput.file_path) === policy.manifest.before_sha256;
              }
              if(!ok)toolErrors.push({operation:input.tool_name,error:policy.reason||"approval denied"});
              return { hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: ok ? "allow" : "deny", permissionDecisionReason: ok ? "案件境界と承認を確認" : (policy.reason || "本人の固定版承認が無い") } };
            }],
          }],
          PostToolUse: [{hooks:[async (input)=> {
            if (["Write","Edit"].includes(input.tool_name) && inside(input.tool_input?.file_path,writeRoots)) {
              書く(channelId,role,"artifact", "成果物版を保存",{path:input.tool_input.file_path,sha256:fileHash(input.tool_input.file_path),revision:ctx.revision},ctx);
            }
            return {};
          }]}],
        },
      },
    });
    await consumeSDK(stream,{signal:s.abort.signal,abort:()=>s.abort.abort(),totalMs:runOptions.total_ms||既定.total_ms,stallMs:runOptions.stall_ms||既定.stall_ms,waiting:()=>s.waitingApproval||s.awaitingDelegates>0,onEvent:async(m)=>{
      if (m.type === "system" && m.subtype === "init") {
        sdkRunId=m.session_id;
        runtime.session(requestId,lease.owner,m.session_id);
      } else if (m.type === "assistant") {
        for (const c of m.message.content || []) {
          if (c.type === "tool_use") { const t = 道具の一言(c.name, c.input || {}); s.今 = c.name === "mcp__team__delegate" ? `${c.input?.role}に頼んで返事を待っています` : (t || "作業しています"); 状態を流す(); if (t) 書く(channelId, role, "activity", t, null, ctx); }
          else if (c.type === "text" && c.text?.trim()) { s.今 = "書いています"; 状態を流す(); }
        }
      } else if (m.type === "result") {
        最後 = m.result || "";
        resultSuccess = m.subtype === "success";
        if (m.subtype !== "success") 書く(channelId, "system", "error", `${role} が途中で止まった（${m.subtype}）`, null, ctx);
      }
    }});
    if (rc.reviewer && resultSuccess && sdkRunId && !toolErrors.length && !childResults.some(r=>r.status!=="success")) {
      const 編集長の記録=verifiedReviewResult(最後,ctx,review,`${rc.run_id}-${sdkRunId}`);
      // 審査の収束: ずれ1つずつを判断の層がラベル付けし、コードが PASS/FAIL を決める（2026-10-07 本人）
      const { 収束, ...record } = await 収束させる(編集長の記録, { jev: 判断の層() || undefined, 聞き直す: Opusに聞き直す });
      console.log(`審査の収束: ${編集長の記録.decision}→${record.decision} ${JSON.stringify(収束?.内訳 || null)} ${収束?.使った || ""}`);
      if (record.decision === "PASS") 速い道を学ぶ(最後の道.get(contextKey(ctx) + channelId), ctx).catch(e => console.error("速い道:", e.message));
      if (record.decision === "FAIL" && record.reasons.length) 戻しを学ぶ(作り手を引く(ctx, channelId), record.reasons.map(r => r.replace(/^\[書き方・1回直したら再審査なしで次へ\] /, "")), ctx).catch(e => console.error("戻しを学ぶ:", e.message));
      if (収束) fs.appendFileSync(path.join(STATE_ROOT, "審査の収束.jsonl"), JSON.stringify({ at: new Date().toISOString(), context: ctx, 編集長: { decision: 編集長の記録.decision, reasons: 編集長の記録.reasons }, 収束後: { decision: record.decision, reasons: record.reasons }, 収束 }) + "\n");
      for(const a of review.artifacts) if(!inside(a.path,writeRoots)) throw Error("レビュー後に成果物の範囲が変わった");
      const receipt=recordReview(record);
      if(!receipt.review_id) throw Error("独立レビュー記録を保存できない");
      const reviewer={status:record.decision.toLowerCase(),context:record.scope.context,artifact_hashes:record.artifact_hashes,rules_hash:record.rules_hash,review_id:receipt.review_id,reasons:record.reasons};
      書く(channelId,role,"review", `独立レビュー: ${record.decision.toUpperCase()}${収束?.内訳 ? `（編集長は ${収束.編集長の判定}。ずれ ${record.reasons.length + 収束.内訳.捨てた} 件のうち、決定を変える ${収束.内訳.決定を変える}・書き方 ${収束.内訳.書き方}・捨てた ${収束.内訳.捨てた}）` : 収束?.使った === "編集長の判定のまま" ? "（判断の層が使えず、編集長の判定のまま）" : ""}${record.reasons.length?"\n- "+record.reasons.join("\n- "):""}`,{reviewer},ctx);
      最後=JSON.stringify(reviewer);
    }
    if(resultSuccess&&!toolErrors.length&&!childResults.some(r=>r.status!=="success")&&rc.resume)db.prepare("INSERT OR REPLACE INTO scoped_sessions(scope,session_id) VALUES(?,?)").run(rc.key,sdkRunId);
    if (最後) 書く(channelId, role, "text", 最後, null, ctx);
  } catch (e) {
    failure=e;
    書く(channelId, "system", "error", `${role}: ${s.abort.signal.aborted ? "本人が止めた" : String(e.message || e).slice(0, 300)}`, null, ctx);
  } finally {
    cap.close();
    clearInterval(心拍);
    runOptions.parent_signal?.removeEventListener("abort",parentAbort);
    try { const 分 = Math.round((Date.now() - (s.始 || Date.now())) / 60000); fs.appendFileSync(path.join(STATE_ROOT, "かかった時間.jsonl"), JSON.stringify({ at: new Date().toISOString(), role, channel: channelId, context: ctx, 小工程: 小工程を読む(s.依頼), 分, 画像: s.画像, 操作: s.道?.length || 0 }) + "\n"); if (role !== "編集長" && s.道?.length) 最後の道.set(contextKey(ctx) + channelId, { role, 道: s.道.slice(), 依頼: s.依頼, 分 }); } catch {}
    s.busy = false; s.channel = null; s.abort = null; s.今 = null; s.最後 = Date.now(); 状態を流す();
    裏のタブを片付ける();
  }
  const status=failure ? (failure.code==="cancelled" ? "cancelled" : ["timeout","stalled"].includes(failure.code)?"partial":"error") : (!resultSuccess||toolErrors.length||childResults.some(r=>r.status!=="success")) ? "partial" : "success";
  const result=runtimeResult({...identity,run_id:rc.run_id,request_id:requestId},status,最後,{code:failure?.code||(!resultSuccess?"sdk_incomplete":undefined),error:failure?String(failure.message||failure):undefined,artifacts:createdArtifacts,children:childResults,tool_errors:toolErrors});
  書く(channelId,role,"runtime_result",`${role}: ${status}`,{result},ctx);
  return runtime.finish(requestId,lease.owner,result);
  }catch(e){clearInterval(心拍);const failedState=役の状態(role,ctx);failedState.abort?.abort();failedState.busy=false;failedState.abort=null;failedState.channel=null;return runtime.finish(requestId,lease.owner,runtimeResult({...identity,request_id:requestId},"error","",{code:e.code||"setup_error",error:String(e.message||e)}));}
}

// ── 自動の振り分け（autopilot.mjs）: 部長が終わったら HANDOFF を読み、編集長 PASS なら次の部へ書く。止まる時は Telegram 1通 ──
function 自動の次(ctx, results) {
  try {
    const job = 自動.get(ctx);
    const d = 自動の判断({ job, results, channels: 設定.channels });
    if (d.action === "dispatch") {
      自動.hop(ctx, { to: d.handoff.to, ask: d.handoff.ask, channel: d.channel, artifact: d.handoff.artifact, vault_return: !!d.handoff.vault_return });
      本人が書いた(d.channel, d.text, ctx, null, { source: "autopilot" }).catch(e => console.error("自動の振り分け:", e.message));
    } else if (d.action === "later") {
      自動.hop(ctx, { to: "続き", ask: "書き出し待ちの続き", channel: d.channel });
      書く("hq", "自動の振り分け", "text", `${ctx.job_id}: 書き出し待ちで止まったので、${Math.round(d.delayMs / 60000)}分後に続きを頼む`, null, ctx);
      setTimeout(() => 本人が書いた(d.channel, d.text, ctx, null, { source: "autopilot" }).catch(e => console.error("自動の振り分け:", e.message)), d.delayMs);
    } else if (d.action === "stop") {
      自動.stop(ctx, d.reason);
      書く("hq", "自動の振り分け", "text", `${ctx.job_id}: 止めた。${d.reason}`, { autopilot: d }, ctx);
      通知(`${d.done ? "✅ 揃った" : "⏸ 止まった"}｜${ctx.job_id}\n${d.reason}${d.handoff?.artifact ? "\n" + d.handoff.artifact : ""}\n${公開URL}`);
    }
  } catch (e) { console.error("自動の振り分け:", e.message); }
}

// ── 本人の書き込み: @で呼ばれた役、無ければリーダーが受ける ──
function 本人が書いた(channelId, text, ctx, review, runOptions = {}) {
  runOptions={...runOptions,dispatch_id:runOptions.dispatch_id||randomUUID()};
  const ch = チャンネル(channelId);
  const called = runOptions.force_lead ? [ch.lead] : [ch.lead, ...ch.members].filter(r=>text.includes(`@${r}`));
  if ((called.length ? called : [ch.lead]).includes("編集長")) { 読取範囲(ctx,review); runContext("編集長",channelId,ctx,review); }
  書く(channelId,runOptions.source==="next_brief"?"計測からの次発注":runOptions.source==="autopilot"?"自動の振り分け":"本人","text",text,{dispatch_id:runOptions.dispatch_id||null,execution_authorized:false},ctx);
  if (!runOptions.source && !runOptions.no_ledger) 台帳に拾う(channelId, text, ctx);
  const 全員 = [ch.lead, ...ch.members];
  const 呼ばれた = 全員.filter((r) => text.includes(`@${r}`));
  const runs=[];
  for (const r of (runOptions.force_lead ? [ch.lead] : 呼ばれた.length ? 呼ばれた : [ch.lead])) {
    if (r === "編集長") { 読取範囲(ctx, review); runContext(r, channelId, ctx, review); }
    const 最近 = db.prepare("SELECT author, text FROM messages WHERE channel = ? AND json_extract(meta, '$.context.brand') = ? AND json_extract(meta, '$.context.job_id') = ? AND json_extract(meta, '$.context.revision') = ? AND kind IN ('text','handoff') ORDER BY id DESC LIMIT 12").all(channelId, ctx.brand, ctx.job_id, ctx.revision).reverse()
      .map((x) => `${x.author}: ${x.text.slice(0, 300)}`).join("\n");
    runs.push(動かす(r, channelId, `[本人から #${ch.name}] ${text}\n\n（最近のチャンネル）\n${最近}`, ctx, review,runOptions));
  }
  return Promise.all(runs).then((results)=>{自動の次(ctx,results);return results;});
}

async function 実行を再開(requestId,ctx) {
  const saved=runtime.request(requestId,ctx);
  const options={...saved.options,resume:true};
  if(saved.options.source==="next_brief"){
    const limits=nextIntake.canResume(saved.identity.dispatch_id,ctx);
    options.max_turns=Math.min(options.max_turns||20,limits.max_turns);
    options.total_ms=Math.min(options.total_ms||900000,limits.total_ms);
    options.stall_ms=Math.min(options.stall_ms||120000,limits.stall_ms,options.total_ms);
  }
  const result=await 動かす(saved.identity.role,saved.identity.channel,saved.prompt,ctx,saved.review,options);
  if(result.status==="success"&&saved.identity.dispatch_id)await nextIntake.resumeCompleted(saved.identity.dispatch_id,ctx,result);
  if(!String(saved.identity.dispatch_id||"").includes("/"))自動の次(ctx,[result]);
  return result;
}

function 実行承認カード(channel,ctx,job,approvalExpires=null,handoffId=null) {
  if(handoffId){const existing=行に(db.prepare("SELECT * FROM messages WHERE kind='approval' AND json_extract(meta,'$.handoff_id')=?").get(handoffId));if(existing)return existing;}
  const expires=approvalWindow(job,ブランド設定()[ctx.brand],approvalExpires);
  const checked=contract("validate",{job});
  if(checked.errors?.length||checked.status!=="insufficient_evidence"||checked.missing?.length!==1||checked.missing[0]!=="trusted exact owner approval required")throw Error(JSON.stringify(checked));
  const manifest=structuredClone(job);
  return 書く(channel,"本人","approval",`${ctx.brand} / ${ctx.job_id} / ${ctx.revision}: 実行内容の固定版承認`,{status:"待ち",approval_kind:"execution",handoff_id:handoffId,approval_expires_at:expires,manifest_hash:checked.manifest_hash,manifest,input:JSON.stringify({job:manifest,approval_expires_at:expires},null,2)},ctx);
}
db.exec("CREATE UNIQUE INDEX IF NOT EXISTS one_handoff_owner_card ON messages(json_extract(meta,'$.handoff_id')) WHERE kind='approval' AND json_extract(meta,'$.handoff_id') IS NOT NULL");
const intake=reviewIntake({contract,
  reviewJob:(ctx,review)=>動かす("編集長","creative","自動制作からの独立レビュー",ctx,review),
  findReview:(ctx,review)=> {
    const rows=db.prepare("SELECT meta FROM messages WHERE kind='review' AND json_extract(meta,'$.context.brand')=? AND json_extract(meta,'$.context.job_id')=? AND json_extract(meta,'$.context.revision')=? ORDER BY id DESC").all(ctx.brand,ctx.job_id,ctx.revision);
    const expected=review.artifacts.map(a=>a.sha256).sort();
    for(const row of rows){const r=JSON.parse(row.meta).reviewer;if(r.rules_hash===digest(review.rules)&&JSON.stringify([...r.artifact_hashes].sort())===JSON.stringify(expected))return r;}
    return null;
  },
  ownerCard:(id,ctx,job)=>実行承認カード("creative",ctx,job,null,id)
});
// Disabled/missing automation.json is a no-op. No process is restarted by this code.
if (!VERIFICATION && intake.enabled()) {
  const intakeTimer=setInterval(()=>intake().catch(e=>console.error("review intake:",e.message)),30000);intakeTimer.unref();
  intake().catch(e=>console.error("review intake:",e.message));
}

const nextIntake=nextBriefIntake({contract,
 verifyBrief:record=>{
   const target=path.join(HOME,"Claude Code/ec-harness/next_brief_check.py");
   const r=spawnSync("python3",["-B",target],{input:JSON.stringify({record}),encoding:"utf8",maxBuffer:8*1024*1024});
   if(r.error||!r.stdout)throw r.error||Error("next brief verifier unavailable");return JSON.parse(r.stdout);
 },
 lookupResult:(id,ctx)=>{
   const rows=db.prepare("SELECT result FROM runtime_requests WHERE json_extract(identity,'$.dispatch_id')=? AND json_extract(identity,'$.brand')=? AND json_extract(identity,'$.job_id')=? AND json_extract(identity,'$.revision')=? AND result IS NOT NULL").all(id,ctx.brand,ctx.job_id,ctx.revision);
   return rows.length?rows.map(r=>JSON.parse(r.result)):null;
 },
 dispatch:(ctx,brief,opts)=>本人が書いた("hq",`計測に基づく次の発注（ローカル準備のみ。実行承認は無い）\n${JSON.stringify(brief)}`,ctx,null,opts)
});
if(!VERIFICATION && nextIntake.enabled()){
 const t=setInterval(()=>nextIntake().catch(e=>console.error("next brief intake:",e.message)),30000);t.unref();
 nextIntake().catch(e=>console.error("next brief intake:",e.message));
}

// ── HTTP ──
const 型 = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8" };
const 本文 = (req) => new Promise((ok) => { let b = ""; req.on("data", (d) => (b += d)); req.on("end", () => { try { ok(JSON.parse(b || "{}")); } catch { ok({}); } }); });
const 検証本文 = (req) => new Promise((ok,no) => {let size=0,b="";req.on("data",d=>{size+=d.length;if(size>4096)no(Error("bounded verification input required"));else b+=d;});req.on("end",()=>{try{ok(JSON.parse(b));}catch{no(Error("typed verification JSON required"));}});req.on("error",()=>no(Error("verification request interrupted")));});
let metaVerificationBusy = false;
const approvedLocalVsl=localVslDispatcher();
const approvedNativeVslReview=fixedNativeVslReview({runtime,writeMessage:(kind,text,meta,ctx)=>書く("quality","編集長",kind,text,meta,ctx)});
function 検証状態() {
  let operations=null;
  if(VERIFICATION){try{operations=JSON.parse(fs.readFileSync(path.join(STATE_ROOT,"operations/status.json"),"utf8"));if(Date.now()-Date.parse(operations.checked_at)>90000)operations={mode:"readonly_local",status:"heartbeat_stale",production_dispatch:false};}catch{operations={status:"not_managed",production_dispatch:false};}}
  return {mode:VERIFICATION ? "verification":"normal",operations,source_revision:SOURCE_REVISION,meta_read_busy:metaVerificationBusy,scoped_local_vsl:{brand:"アルコット",job_id:"alcott_nonai_vsl_20261002_01",revision:3,operations:["status","run","resume","review"],global_sdk_unlocked:false,publication_allowed:false},model_dispatch_enabled:!VERIFICATION,recurring_automation_enabled:!VERIFICATION&&intake.enabled(),provider_mutations_enabled:false,verification_state_isolated:VERIFICATION};
}

http.createServer(async (req, res) => {
  const u = new URL(req.url, 公開URL);
  const json = (v, code = 200) => { res.writeHead(code, { "content-type": "application/json; charset=utf-8" }); res.end(JSON.stringify(v)); };
  if (req.method === "POST" && (req.headers["x-team-token"] !== CSRF_TOKEN || (req.headers.origin && ![公開URL, `http://127.0.0.1:${PORT}`].includes(req.headers.origin)))) return json({error:"本人画面からの操作が必要"},403);
  if (VERIFICATION && req.method === "POST" && !["/api/verification/meta","/api/verification/local","/api/verification/vsl"].includes(u.pathname)) return json({error:"検証モードでは接続確認とローカル保存検査だけを実行できます",code:"verification_only"},403);
  if (u.pathname === "/api/verification/status") return json(検証状態());
  if(u.pathname==="/api/verification/vsl" && req.method==="POST"){
    if(!VERIFICATION)return json({error:"scoped verification service required"},403);
    try{
      if(Number(req.headers["content-length"]||0)>4096)throw Error("bounded local input required");
      const body=await 検証本文(req),controller=new AbortController();res.once("close",()=>{if(!res.writableEnded)controller.abort();});
      const result=await (body.operation==="review" ? approvedNativeVslReview : approvedLocalVsl)(body,{signal:controller.signal});
      return json(result);
    }catch(e){return json({error:String(e.message||e),provider_calls:0,publication_allowed:false},400);}
  }

  if (["/api/verification/meta","/api/verification/local"].includes(u.pathname) && req.method === "POST") {
    if (!VERIFICATION) return json({error:"検証モードで起動してください"},403);
    let ownsMetaRead=false;
    try {
      if(Number(req.headers["content-length"]||0)>4096)throw Error("bounded verification input required");
      const body=await 検証本文(req);
      const allowed=u.pathname.endsWith("/meta") ? ["brand","since","until"] : ["brand"];
      if(!body||typeof body.brand!=="string"||Object.keys(body).some(k=>!allowed.includes(k))||!Object.hasOwn(ブランド設定(),body.brand))throw Error("registered brand and typed verification fields required");
      if(u.pathname.endsWith("/local")) {
        const ctx=context({brand:body.brand,job_id:"verify_"+randomUUID().replace(/-/g,""),revision:1},ブランド設定()),cfg=ブランド設定()[ctx.brand];
        for(const root of 書込範囲(ctx))fs.mkdirSync(root,{recursive:true});
        const localController=new AbortController();
        const cap=createRoleCapabilities({role:"仕組み係",ctx,brandConfig:cfg,runId:randomUUID(),signal:localController.signal,leaseExpiresAt:Date.now()+10000});
        try {
          const receipt=cap.create({relative_path:"connection-check.json",mime_type:"application/json",content_utf8:JSON.stringify({kind:"local_verification",brand:ctx.brand,job_id:ctx.job_id,revision:1,execution_authorized:false})});
          const inspected=cap.inspect({path:receipt.artifact.path,expected_sha256:receipt.artifact.sha256});
          const message=書く("quality","仕組み係","verification","ローカルの作業記録を保存・照合できました",{receipt,source_revision:SOURCE_REVISION},ctx);
          return json({status:"verified",context:ctx,receipt,inspected_sha256:inspected.artifact.sha256,message_id:message.id,execution_authorized:false});
        } finally {cap.close();}
      }
      if(metaVerificationBusy)return json({error:"Metaの読み取り確認を実行中です"},409);
      metaVerificationBusy=true;ownsMetaRead=true;
      const controller=new AbortController();res.once("close",()=>{if(!res.writableEnded)controller.abort();});
      const report=await readMeta({registryPath:BRAND_CONFIG_PATH,brand:body.brand,since:body.since,until:body.until,cwd:ROOT,signal:controller.signal});
      const dir=path.join(STATE_ROOT,"meta",encodeURIComponent(body.brand));fs.mkdirSync(dir,{recursive:true});
      const evidence=path.join(dir,Date.now()+"-"+randomUUID()+".json");fs.writeFileSync(evidence,JSON.stringify(report,null,2),{flag:"wx"});
      fs.writeFileSync(evidence.replace(/\.json$/,".seal.json"),JSON.stringify({sha256:createHash("sha256").update(fs.readFileSync(evidence)).digest("hex")}),{flag:"wx"});
      return json({...report,evidence_path:evidence});
    } catch(e) {return json({error:String(e.message||e),execution_authorized:false},400);}
    finally {if(ownsMetaRead)metaVerificationBusy=false;}
  }
  if (u.pathname === "/api/events") {
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
    let ctx; try { ctx=context(Object.fromEntries(["brand","job_id","revision"].map(k=>[k,(k === "revision" ? Number(u.searchParams.get(k)) : u.searchParams.get(k))])),ブランド設定()); } catch(e) { res.end(); return; }
    const listener={res,ctx}; 聞き手.add(listener); req.on("close", () => 聞き手.delete(listener));
    res.write(`data: ${JSON.stringify({ type: "hello" })}\n\n`); 状態を流す(); return;
  }
  if (u.pathname === "/api/state") {
    const roles = Object.fromEntries(Object.entries(設定.roles).map(([k, v]) => [k, { ...v, 手順書: !!手順書(k) }]));
    return json({ channels: 設定.channels, roles, csrf_token:CSRF_TOKEN, brands:Object.keys(ブランド設定()), verification:検証状態() });
  }
  if (u.pathname === "/api/messages") {
    const c = u.searchParams.get("channel");
    let ctx;
    try { ctx = context(Object.fromEntries(["brand","job_id","revision"].map(k => [k,(k === "revision" ? Number(u.searchParams.get(k)) : u.searchParams.get(k))])), ブランド設定()); }
    catch (e) { return json({error:e.message}, 400); }
    if (!チャンネル(c)) return json({error:"チャンネルが無い"},400);
    const rows = db.prepare("SELECT * FROM messages WHERE json_extract(meta, '$.context.brand') = ? AND json_extract(meta, '$.context.job_id') = ? AND json_extract(meta, '$.context.revision') = ? ORDER BY id DESC LIMIT 400").all(ctx.brand,ctx.job_id,ctx.revision).reverse().map(行に);
    return json(rows.filter(m => c.startsWith("dm:") ? m.channel === c || m.author === c.slice(3) || m.meta?.to === c.slice(3) : m.channel === c));
  }
  if (u.pathname === "/api/post" && req.method === "POST") {
    const { channel, text, context: supplied, review, autopilot, 作り手 } = await 本文(req);
    let ctx;
    try { ctx = context(supplied, ブランド設定()); 読取範囲(ctx); } catch(e) { return json({error:e.message},400); }
    if (!チャンネル(channel) || !String(text || "").trim()) return json({ error: "チャンネルか本文が無い" }, 400);
    // autopilot: {goal} を付けた発注は、部長が終わるたびに次の部へ自動で渡す（止まるまで）
    if (autopilot?.goal) 自動.start(ctx, { goal: String(autopilot.goal), order: String(text).trim() });
    // 部屋の外（Claude Code の会話）で作った物を審査に出す時、作った役を名乗る。戻された理由はその役の決まりに溜まる（2026-10-07 本人）
    if (review && typeof 作り手 === "string" && 設定.roles[作り手]) 最後の作り手.set(contextKey(ctx) + channel, 作り手);
    try { 本人が書いた(channel, String(text).trim(), ctx, review, autopilot?.goal ? { no_ledger: true } : {}).catch(e=>console.error("dispatcher:",e.message)); return json({ ok: true, autopilot: 自動.get(ctx) }); } catch(e) { return json({error:e.message},400); }
  }
  // 広告（ads-fetch.py が3時間ごとに取る写し）と、その絵。読むだけ
  if (u.pathname === "/api/ads") { const f = path.join(ROOT, "data/ads", path.basename(String(u.searchParams.get("brand") || "")) + ".json"); res.writeHead(200, { "content-type": "application/json; charset=utf-8" }); return res.end(fs.existsSync(f) ? fs.readFileSync(f) : '{"campaigns":[]}'); }
  if (u.pathname.startsWith("/ads-img/")) { const m = u.pathname.match(/^\/ads-img\/(img|pages)\/([A-Za-z0-9_.-]+\.jpg)$/); const f = m && path.join(ROOT, "data/ads", m[1], m[2]); if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); } res.writeHead(200, { "content-type": "image/jpeg", "cache-control": "max-age=86400" }); return fs.createReadStream(f).pipe(res); }
  if (u.pathname === "/api/ref-info") return json(参考の中身(String(u.searchParams.get("brand")), String(u.searchParams.get("job_id")), String(u.searchParams.get("ids") || "").split(",").slice(0, 20)));
  if (u.pathname === "/api/ref-img") { const f = 参考の絵(String(u.searchParams.get("brand")), String(u.searchParams.get("job_id")), String(u.searchParams.get("id"))); if (!f) { res.writeHead(404); return res.end(); } res.writeHead(200, { "content-type": "image/jpeg", "cache-control": "max-age=86400" }); return fs.createReadStream(f).pipe(res); }
  // 流れの木（読むだけ）: brand だけ → その案件の一覧、brand・job_id・revision → 木（tree.mjs）
  // チームの一覧（読むだけ）: 役ごとの今と最近の仕事。作業中かどうかは部屋が持っている今の状態を優先する
  if (u.pathname === "/api/team") {
    const 読む = (brand, job_id, rev) => db.prepare("SELECT * FROM messages WHERE json_extract(meta, '$.context.brand') = ? AND json_extract(meta, '$.context.job_id') = ? AND json_extract(meta, '$.context.revision') = ? ORDER BY id").all(brand, job_id, rev).map(行に);
    const t = チームの形({ jobs: 木.jobs(), read: 読む, channels: 設定.channels, roles: 設定.roles });
    for (const [k, v] of 状態) { if (!v.busy) continue; const role = (() => { try { return JSON.parse(k)[0]; } catch { return k; } })(); const p = t.people[role]; if (p) { p.busy = true; p.stale = false; p.now = v.今 || p.now; if (v.context) p.job = { ...v.context, name: 木.jobs().find((j) => j.job_id === v.context.job_id && j.brand === v.context.brand)?.name }; } }
    return json(t);
  }
  if (u.pathname === "/api/tree") {
    const brand = u.searchParams.get("brand");
    if (!brand) { const all = 木.jobs(); return json({ brands: [...new Set([...Object.keys(ブランド設定()), ...all.map((j) => j.brand)])].map((b) => ({ brand: b, jobs: all.filter((j) => j.brand === b).length, last: Math.max(0, ...all.filter((j) => j.brand === b).map((j) => j.last)), lines: ラインの一覧(b).map((l) => ({ ...l, jobs: all.filter((j) => j.brand === b && j.line?.id === l.id).length })) })) }); }
    const job_id = u.searchParams.get("job_id");
    if (!job_id) return json({ brand, jobs: 木.jobs().filter((j) => j.brand === brand).sort((a, b) => b.last - a.last).map((j) => ({ ...j, autopilot: 自動.get(j) ? { on: !!自動.get(j).on } : null })) });
    const ctx = { brand, job_id, revision: Number(u.searchParams.get("revision")) };
    const 読む = (brand, job_id, rev) => db.prepare("SELECT * FROM messages WHERE json_extract(meta, '$.context.brand') = ? AND json_extract(meta, '$.context.job_id') = ? AND json_extract(meta, '$.context.revision') = ? ORDER BY id").all(brand, job_id, rev).map(行に);
    return json({ ...ctx, ...木を作る(ctx, 材料({ read: 読む, channels: 設定.channels, auto: (c) => 自動.get(c), jobs: () => 木.jobs() })) });
  }
  if (u.pathname === "/api/autopilot") {
    if (req.method === "POST") { try { const b = await 本文(req); const ctx = context(b.context, ブランド設定()); return json(b.stop ? 自動.stop(ctx, "本人が止めた") : 自動.get(ctx)); } catch(e) { return json({error:e.message},400); } }
    return json(自動.all());
  }
  if (u.pathname === "/api/resume" && req.method === "POST") {
    try {const body=await 本文(req);if(Object.keys(body).some(k=>!["request_id","context"].includes(k))||typeof body.request_id!=="string")throw Error("known request_id and context only");const ctx=context(body.context,ブランド設定());return json(await 実行を再開(body.request_id,ctx));}catch(e){return json({error:e.message},409);}
  }
  if (u.pathname === "/api/action-proposal" && req.method === "POST") {
    const {channel,context:supplied,job,approval_expires_at}=await 本文(req);
    try {
      const ctx=context(supplied,ブランド設定());
      if(!チャンネル(channel) || !sameContext(ctx,job) || job.mode !== "live") throw Error("案件・版・ライブ操作が一致しない");
      const msg=実行承認カード(channel,ctx,job,approval_expires_at);
      return json({ok:true,id:msg.id,manifest_hash:msg.meta.manifest_hash});
    } catch(e) { return json({error:e.message},400); }
  }
  if (u.pathname === "/api/approve" && req.method === "POST") {
    const { id, decision, manifest_hash, context:supplied } = await 本文(req);
    let pending = 待ち.get(Number(id));
    const card=行に(db.prepare("SELECT * FROM messages WHERE id = ? AND kind = 'approval'").get(Number(id)));
    if(!pending && card?.meta?.approval_kind === "execution" && card.meta.status === "待ち") pending={ctx:card.meta.context,manifest:card.meta.manifest,manifest_hash:card.meta.manifest_hash,approval_expires_at:card.meta.approval_expires_at,execution:true};
    if (!pending) return json({error:"もう答えが出ている"},409);
    let ctx;
    try { ctx=context(supplied,ブランド設定()); } catch(e) { return json({error:e.message},400); }
    if (!sameContext(ctx,pending.ctx) || manifest_hash !== pending.manifest_hash || !["approve","reject"].includes(decision)) return json({error:"承認対象の版が一致しない"},409);
    const owner=ブランド設定()[ctx.brand].owners?.[0];
    if(!owner) return json({error:"承認者設定が無い"},400);
    if(pending.execution) {
      try {
        let receipt=null;
        if(decision === "approve") {
          const check=contract("validate",{job:pending.manifest});
          if(check.manifest_hash !== manifest_hash || check.errors?.length || check.missing?.length !== 1 || check.missing[0] !== "trusted exact owner approval required") throw Error("承認待ちの間に材料・版が変わった");
          const expires=approvalWindow(pending.manifest,ブランド設定()[ctx.brand],pending.approval_expires_at);
          receipt=issueApproval({job:pending.manifest,owner,expires_at:expires});
          if(receipt.manifest_hash !== manifest_hash || !receipt.approval_id) throw Error("承認記録を保存できない");
        }
        直す(card.id,{...card.meta,status:decision === "approve" ? "承認":"却下",receipt});
        return json({ok:true,receipt});
      } catch(e) { return json({error:e.message},409); }
    }
    pending.resolve({ ...ctx, decision, manifest_hash, owner, approved_at:new Date().toISOString(), expires_at:new Date(Date.now()+5*60*1000).toISOString() });
    return json({ok:true});
  }
  // ── ec-graph（4 広告を作る）を9段の画面から見る・動かす（2026-10-08 本人「ビジュアルで見れるやつで操作したい」） ──
  if (u.pathname === "/api/video") {
    const p = path.resolve(String(u.searchParams.get("p") || ""));
    if (!p.startsWith(path.join(HOME, "Desktop", "ec") + path.sep) || !p.endsWith(".mp4") || !fs.existsSync(p)) { res.writeHead(404); return res.end(); }
    const size = fs.statSync(p).size, m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
    if (m) { const a = m[1] ? +m[1] : 0, b = m[2] ? +m[2] : size - 1; res.writeHead(206, { "content-type": "video/mp4", "accept-ranges": "bytes", "content-range": `bytes ${a}-${b}/${size}`, "content-length": b - a + 1 }); return fs.createReadStream(p, { start: a, end: b }).pipe(res); }
    res.writeHead(200, { "content-type": "video/mp4", "accept-ranges": "bytes", "content-length": size }); return fs.createReadStream(p).pipe(res);
  }
  if (u.pathname === "/api/graph") { const { 地図の1本ずつ } = await import("./tree.mjs"); return json(地図の1本ずつ(String(u.searchParams.get("for") || ""))); }
  if (u.pathname === "/api/graph/run" && req.method === "POST") {
    const { ext, why } = await 本文(req);
    if (!/^\d{6,}$/.test(String(ext || ""))) return json({ error: "参考のIDが無い" }, 400);
    const G = path.join(HOME, "Claude Code", "ec-graph"), lock = path.join(G, "40-runs", `走っている_${ext}`);
    if (fs.existsSync(lock)) return json({ error: "この参考は今走っている" }, 409);
    fs.mkdirSync(path.join(G, "40-runs"), { recursive: true }); fs.writeFileSync(lock, new Date().toISOString());
    const log = path.join(G, "40-runs", `claude_${ext}_${Date.now()}.log`);
    const prompt = `ec-graph の1本を作る。本人が9段の画面の「4 広告を作る」から頼んだ。本人は見ていない。役には渡さず、この会話の Claude 1つで最後までやる。\n` +
      `1. ~/Claude Code/ec-graph/CONSTRAINTS.md（本人の決めたこと）・SKILL.md・SCHEMA.md を全部読む。\n` +
      `2. 対象は ref:${ext}。cd ~/Claude\\ Code/ec-graph && python3 graph.py route ref:${ext} の道どおりに、SKILL.md の手順で作る（new なら最初から、落ちた物は前の作業フォルダを使い直し理由の所だけ直す）。2回落ちたら SKILL.md の「落ちた物を直すループ」まで回す。\n` +
      (why ? `本人からのひとこと: ${String(why).slice(0, 300)}\n` : "") +
      `3. お金のかかる生成（AI動画・画像）はしない。終わったら ${lock} を消す。`;
    const { spawn } = await import("node:child_process");
    const out = fs.openSync(log, "a");
    const ch = spawn(path.join(HOME, ".local", "bin", "claude"), ["-p", prompt, "--dangerously-skip-permissions", "--model", "claude-opus-5-5"], { cwd: G, detached: true, stdio: ["ignore", out, out], env: { ...process.env, CLAUDE_CODE_ENTRYPOINT: "cli" } });
    ch.on("exit", () => { try { fs.unlinkSync(lock); } catch {} });
    ch.unref();
    return json({ ok: true, log });
  }
  if (u.pathname === "/api/stop" && req.method === "POST") {
    const { role, context:supplied } = await 本文(req);
    let ctx; try { ctx=context(supplied,ブランド設定()); } catch(e) { return json({error:e.message},400); }
    役の状態(role,ctx).abort?.abort(); return json({ ok: true });
  }
  const f = path.join(ROOT, "public", u.pathname === "/" ? "index.html" : u.pathname);
  if (f.startsWith(path.join(ROOT, "public")) && fs.existsSync(f) && fs.statSync(f).isFile()) {
    res.writeHead(200, { "content-type": 型[path.extname(f)] || "application/octet-stream" }); return fs.createReadStream(f).pipe(res);
  }
  res.writeHead(404); res.end("無い");
}).listen(PORT, "127.0.0.1", () => {
  console.log(`チームの部屋: ${公開URL}`);
  // サーバーが落ちて入れ直された時、途中だった仕事を続きから拾い直す（2026-10-05）。
  // 拾うのは本人・計測からの発注（上の役）だけ。頼まれた側は、上の役が頼み直した時に「切れても続ける」が続きから再開する
  // 裏用 Dia を立てておく（既に動いていれば使い直す）
  try { execFile("python3", [path.join(HOME, ".claude/skills/browser/scripts/dia_agent.py"), "start"], { timeout: 60000 }, () => {}); } catch {}
  setTimeout(() => {
    for (const o of runtime.orphans()) {
      if (String(o.identity.dispatch_id || "").includes("/")) continue;
      const ctx = { brand: o.identity.brand, job_id: o.identity.job_id, revision: o.identity.revision };
      try { 書く(o.identity.channel, "system", "error", `${o.identity.role} の仕事はサーバーの入れ直しで止まっていたので、続きから再開する`, null, ctx); } catch {}
      実行を再開(o.id, ctx).catch(e => console.error("再開できなかった:", e.message));
    }
  }, 5000);
});
