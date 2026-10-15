// 流れの木（画面の「流れ」で見る物）。部屋の記録（messages）を読み直すだけで、何も書かない。
// 2026-10-07 本人「ブランドを押したら、どの工程まで行って、どうやって作ったかが木で見える」。
// 木: 案件 → 工程（正本の図の EC全体 1〜9）→ 発注（本人・自動の振り分けが部長に書いた1回）→ 役の仕事（部長が頼んだ1回）。
// 役の仕事には、頼まれた文・やった作業（道具の一言）・保存した成果物・編集長の判定・返事を付ける。

import { jobName } from "./job-names.mjs";
import { lineOf } from "./lines.mjs";
export const 工程名 = { 1: "商品を決める", 2: "客を知る", 3: "アングルと割り付け", 4: "広告を作る", 5: "記事を作る", 6: "店を作る", 7: "配信する", 8: "測る", 9: "学ぶ" };
// 役から工程を引く（文に「工程N」が書いてあればそちらが先）
const 役の工程 = { "戦略担当": 3, "クリエイティブ・ストラテジスト": 4, "コピーライター": 4, "吹き替えディレクター": 4, "映像編集者": 4, "生成アーティスト": 4, "クリエイティブディレクター": 4, "記事ライター": 5, "ストア担当": 6, "メディアバイヤー": 7, "アナリスト": 8, "リサーチャー": 2, "戦略責任者": 3, "ファネル責任者": 5, "グロース責任者": 7 };
const 発注者 = new Set(["本人", "自動の振り分け", "計測からの次発注"]);
const 工程を読む = (s) => { const m = String(s || "").match(/工程\s*([1-9])(?![0-9])/); return m ? Number(m[1]) : null; };
const 切る = (s, n) => { s = String(s ?? ""); return s.length > n ? s.slice(0, n) + "…" : s; };
const 判定 = (meta) => { const s = String(meta?.reviewer?.status || "").toLowerCase(); return s === "pass" ? "PASS" : s ? "FIX" : null; };
const 手渡し = (out) => { const l = String(out || "").split("\n").map((x) => x.trim().replace(/^[`*>\s]+|[`*\s]+$/g, "")).filter((x) => /^HANDOFF\s*[:：]/i.test(x)).pop(); return l ? l.replace(/^HANDOFF\s*[:：]\s*/i, "") : null; };

// ブランドごとの案件の一覧（最新の動きが上）
export function jobsOf(rows) {
  const by = new Map();
  for (const r of rows) {
    const k = `${r.brand}\u0000${r.job_id}\u0000${r.revision}`;
    const j = by.get(k) || { brand: r.brand, job_id: r.job_id, revision: Number(r.revision), first: r.ts, last: r.ts, count: 0, stage: null, order: "" };
    if (!j.order && r.kind === "text" && r.author === "本人") j.order = r.text;
    j.first = Math.min(j.first, r.ts); j.last = Math.max(j.last, r.ts); j.count++;
    // 工程: 頼んだ文（handoff）か、本人・自動の振り分けの発注文に書いてある「工程N」。入口で本人に聞いて止まった案件も数える
    const s = r.kind === "handoff" ? 工程を読む(r.text) || 役の工程[r.to] : r.kind === "text" && (r.author === "本人" || r.author === "自動の振り分け") ? 工程を読む(r.text) : null;
    if (s && (!j.stage || s >= j.stage)) j.stage = s;
    by.set(k, j);
  }
  return [...by.values()].filter((j) => j.brand && j.job_id).map(({ order, ...j }) => ({ ...j, name: jobName(j.job_id, order), line: lineOf(j.brand, j.job_id) }));
}

// 1案件の木。rows は id 順の messages（meta は解いた物）
export function treeOf(rows, channels, auto) {
  const 部長 = new Map(channels.map((c) => [c.id, c.lead]));
  const 部長の集合 = new Set(channels.map((c) => c.lead));
  const 発注 = []; // 上の発注
  const 開いた発注 = new Map(); // channel -> 発注
  const 開いた仕事 = new Map(); // role -> 仕事
  let 番 = 0;
  const 新しい仕事 = (role, from, text, ts, channel) => ({ id: `w${++番}`, role, from, ask: text, ts, end: null, channel, status: "作業中", acts: [], artifacts: [], verdicts: [], output: null });

  for (const m of rows) {
    const meta = m.meta || {};
    if (m.kind === "text" && 発注者.has(m.author) && meta.dispatch_id && !String(meta.dispatch_id).includes("/")) {
      const o = { id: `o${++番}`, by: m.author, lead: 部長.get(m.channel) || m.channel, channel: m.channel, ask: m.text, ts: m.ts, end: null, status: "作業中", works: [], acts: [], artifacts: [], output: null, handoff: null };
      発注.push(o); 開いた発注.set(m.channel, o); continue;
    }
    if (m.kind === "text" && m.author === "自動の振り分け") { const o = 発注.at(-1); if (o) o.stopped = m.text; continue; }
    const o = 開いた発注.get(m.channel);
    if (m.kind === "handoff" && o) {
      const w = 新しい仕事(meta.to, m.author, m.text.replace(/^@\S+\s*/, ""), m.ts, m.channel);
      w.stage = 工程を読む(w.ask) || null;
      o.works.push(w); 開いた仕事.set(meta.to, w); continue;
    }
    if (m.kind === "activity") {
      const w = 開いた仕事.get(m.author);
      if (w) w.acts.push(切る(m.text, 240)); else if (o && m.author === o.lead) o.acts.push(切る(m.text, 240));
      continue;
    }
    if (m.kind === "artifact" && meta.path) {
      const w = 開いた仕事.get(m.author);
      const list = w ? w.artifacts : o ? o.artifacts : null;
      if (list && !list.includes(meta.path)) list.push(meta.path);
      continue;
    }
    if (m.kind === "review") {
      const w = 開いた仕事.get("編集長") || 開いた仕事.get(m.author);
      const v = 判定(meta);
      if (w && v) w.verdicts.push({ v, text: 切る(m.text.replace(/^独立レビュー:\s*/, ""), 900), ts: m.ts });
      continue;
    }
    if (m.kind === "handoff_result" && meta.result) {
      const role = meta.result.role || meta.to; const w = 開いた仕事.get(role);
      if (w) { w.end = m.ts; w.status = meta.result.status; w.output = 切る(meta.result.output, 4000); 開いた仕事.delete(role); }
      continue;
    }
    if (m.kind === "runtime_result" && meta.result && o && meta.result.role === o.lead && !String(meta.result.dispatch_id || "").includes("/")) {
      o.end = m.ts; o.status = meta.result.status; o.output = 切る(meta.result.output, 4000); o.handoff = 手渡し(meta.result.output); 開いた発注.delete(m.channel);
    }
  }

  // 途中で切れた物（サーバーの入れ直し等で返事が来なかった）は、最後の発注以外「切れた」にする
  発注.forEach((o, i) => {
    if (o.status === "作業中" && i < 発注.length - 1) o.status = "切れた";
    for (const w of o.works) if (w.status === "作業中" && (o.status !== "作業中" || w !== o.works.at(-1))) w.status = "切れた";
  });

  // 工程を決める: 仕事は文の「工程N」→役。編集長は直前の仕事と同じ工程。発注は中の仕事の工程（無ければ文→部長）
  for (const o of 発注) {
    let 前 = null;
    for (const w of o.works) {
      if (!w.stage) w.stage = w.role === "編集長" ? 前 : 役の工程[w.role] || null;
      if (w.role !== "編集長") 前 = w.stage;
      // 編集長の判定は、審査した仕事にも付ける
      if (w.role === "編集長" && w.verdicts.length) { const t = o.works[o.works.indexOf(w) - 1]; if (t && t.role !== "編集長") t.reviewed = w.verdicts.at(-1).v; }
    }
    const s = o.works.map((w) => w.stage).filter(Boolean);
    // 仕事の無い発注（入口で本人に聞いて止まった等）は、部長の工程。戦略責任者だけは2と3を持つので文から読む
    const 既定 = o.lead === "戦略責任者" ? 工程を読む(o.ask) || 3 : 役の工程[o.lead] || 工程を読む(o.ask) || 0;
    o.stages = [...new Set(s.length ? s : [既定])].sort((a, b) => a - b);
  }

  const 工程 = [];
  for (let n = 1; n <= 9; n++) {
    const os = 発注.filter((o) => o.stages.includes(n)).map((o) => ({ ...o, works: o.works.filter((w) => w.stage === n || (!w.stage && o.stages[0] === n)) }));
    const works = os.flatMap((o) => o.works);
    const 最後の判定 = works.flatMap((w) => w.verdicts).at(-1)?.v || null;
    const 作業中 = os.some((o) => o.status === "作業中") || works.some((w) => w.status === "作業中");
    工程.push({ n, name: 工程名[n], orders: os, state: !os.length ? "まだ" : 作業中 ? "作業中" : 最後の判定 === "PASS" ? "通った" : 最後の判定 === "FIX" ? "差し戻し" : "済み",
      counts: { orders: os.length, works: works.length, pass: works.flatMap((w) => w.verdicts).filter((v) => v.v === "PASS").length, fix: works.flatMap((w) => w.verdicts).filter((v) => v.v === "FIX").length } });
  }
  // 自動の振り分けが本人の判断待ちで止まっていて、最後の発注がその工程なら「本人待ち」
  const 最後 = 発注.at(-1);
  if (auto && !auto.on && /本人の判断待ち/.test(auto.stopped?.reason || "") && 最後 && 最後.status !== "作業中") { const st = 工程.find((x) => x.n === 最後.stages.at(-1)); if (st) st.state = "本人待ち"; }
  const 着手 = 工程.filter((s) => s.state !== "まだ");
  return { stages: 工程, waiting: 工程.find((x) => x.state === "本人待ち") ? { ask: 最後?.handoff || auto?.stopped?.reason || "" } : null, current: 着手.at(-1)?.n || null, autopilot: auto ? { on: !!auto.on, goal: auto.goal, hops: auto.hops, stopped: auto.stopped || null } : null };
}

// 今の案件で手を付けていない手前の工程は、ほかで済ませた物を使っている（2026-10-07 本人「終わってるはずなのに、まだと出る」）。
// 探す順: ① 同じ案件の前の回 ② 移した元の案件（data/job-links.json）③ Vault にある物（部屋ができる前に済ませた工程）
// sources: [{ kind: "rev"|"job", brand, job_id, revision, tree }]、vault: (工程番号) => Vault のパス or null
export function inherit(tree, sources = [], vault = null) {
  const 最初 = Math.min(...tree.stages.filter((s) => s.state !== "まだ").map((s) => s.n));
  for (const s of tree.stages) {
    if (s.state !== "まだ" || !(s.n < 最初)) continue;
    const p = sources.find((t) => t.tree.stages.find((x) => x.n === s.n && x.state !== "まだ"));
    if (p) { s.state = "使い直し"; s.from = { kind: p.kind, brand: p.brand, job_id: p.job_id, revision: p.revision, name: p.name || null }; continue; }
    const v = vault?.(s.n);
    if (v) { s.state = "使い直し"; s.from = { kind: "vault", path: v }; }
  }
  return tree;
}

// 1案件の木を、使い直しまで含めて作る（部屋と見るだけのサーバーの両方が使う）
// deps: { read(brand, job_id, rev), channels, auto(ctx), links, vault(ctx) => (n) => path, name(ctx) }
export function buildTree(ctx, deps, depth = 0) {
  const t = treeOf(deps.read(ctx.brand, ctx.job_id, ctx.revision), deps.channels, depth ? null : deps.auto?.(ctx));
  const sources = [];
  if (depth < 3) {
    for (let r = ctx.revision - 1; r >= 1; r--) sources.push({ kind: "rev", brand: ctx.brand, job_id: ctx.job_id, revision: r, tree: buildTree({ ...ctx, revision: r }, deps, depth + 1) });
    const link = deps.links?.[`${ctx.brand}/${ctx.job_id}/${ctx.revision}`];
    if (link) sources.push({ kind: "job", ...link, name: deps.name?.(link) || link.job_id, tree: buildTree(link, deps, depth + 1) });
  }
  return 地図を重ねる(inherit(t, sources, deps.vault?.(ctx)), ctx);
}

// 4 広告を作るは、ec-graph（記事 @polydao の14段で作った地図）の状態を出す（2026-10-08 本人「この9段の画面に従って」）
// 作っている物があれば作業中、2回落ちて本人待ちがあれば本人待ち、納品があれば済み
import fs_ from "node:fs";
import os_ from "node:os";
// 1本ずつ（作った・作っている物）と次の候補。prefix は「ここちドライ」か「ここちドライ/男性用」（2026-10-08 本人「作っている広告を押して意味があるように」）
export function 地図の1本ずつ(prefix) {
  const t = { stages: [{ n: 4, state: "まだ" }] };
  地図を重ねる(t, { brand: prefix });
  const s = t.stages[0];
  return { refs: s.refs || [], next: s.next || [], graph: s.graph || null };
}
export function 地図を重ねる(tree, ctx) {
  let rows = [];
  try { rows = fs_.readFileSync(`${os_.homedir()}/Claude Code/ec-graph/20-graph/nodes.jsonl`, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)); } catch { return tree; }
  const mine = rows.filter((n) => n.type === "ref" && String(n.for || "").startsWith(ctx.brand));
  if (!mine.length) return tree;
  const c = (st) => mine.filter((n) => n.status === st).length;
  const g = { delivered: c("delivered"), needs_human: c("needs_human"), running: c("running"), fail_1: c("fail_1"), new: c("new") };
  const s4 = tree.stages.find((s) => s.n === 4);
  if (s4) {
    s4.graph = g;
    // 1本ずつの工程（作業フォルダの印から読む）。本人が画面でどこまで進んだかを見る（2026-10-08 本人「このステップは何だなって見れる」）
    const J = `${os_.homedir()}/Claude Code/vsl-jp/jobs`, G = `${os_.homedir()}/Claude Code/ec-graph`;
    const ある = (p) => { try { fs_.accessSync(p); return true; } catch { return false; } };
    const 読む = (p) => { try { return JSON.parse(fs_.readFileSync(p, "utf8")); } catch { return null; } };
    // 参考の原本（棚の原本フォルダ）。左に置いて比べる（2026-10-08 本人「参考動画を左に」）
    const 参考の動画 = (ext) => { const p = `${os_.homedir()}/Desktop/ec/ここちドライ/男性用/01 商品/完コピの材料/原本/gethookd/${ext}_0.mp4`; return ある(p) ? p : null; };
    const 工程 = (n) => {
      const j = n.job ? `${J}/${n.job}` : null, ret = 読む(`${G}/10-returns/${n.ext}.json`), chk = j && 読む(`${j}/raw/check.json`);
      const 落ち = chk ? Object.keys(chk.落ちた || chk.fails || {}).length : null;
      return [
        ["測る", !!j && ある(`${j}/raw/cards.json`)], ["訳", !!j && ある(`${j}/ja_src.json`)], ["声", !!j && ある(`${j}/.done_voice`)],
        ["英字を消す", !!j && ある(`${j}/.done_patch`)], ["字幕", !!j && ある(`${j}/.done_burn`)], ["検査", 落ち === 0 && !!j && ある(`${j}/.done_export`)],
        ["別の目", ret?.gate?.fresh ? String(ret.gate.fresh).startsWith("PASS") : null], ["納品", n.status === "delivered"],
      ].map(([name, ok]) => ({ name, ok }));
    };
    s4.refs = mine.filter((n) => n.status !== "new").sort((a, b) => ["running", "needs_human", "fail_1", "passed", "delivered"].indexOf(a.status) - ["running", "needs_human", "fail_1", "passed", "delivered"].indexOf(b.status))
      .map((n) => ({ id: n.id, ext: n.ext, label: n.label, status: n.status, score: n.score, days: n.days, job: n.job, out: n.out, last_reason: n.last_reason, steps: 工程(n), ret: 読む(`${G}/10-returns/${n.ext}.json`), ref: 参考の動画(n.ext),
        script: ((n.job && 読む(`${J}/${n.job}/ja_src.json`)) || []).map((x) => ({ s: x.start, e: x.end, en: x.src, ja: x.ja })) }));
    s4.next = mine.filter((n) => n.status === "new" && n.fmt === "video" && (n.score || 0) >= 81).sort((a, b) => (b.score - a.score) || (b.days - a.days)).slice(0, 3)
      .map((n) => ({ id: n.id, ext: n.ext, label: n.label, status: n.status, score: n.score, days: n.days, ref: 参考の動画(n.ext) }));
    if (g.running) s4.state = "作業中";
    else if (g.needs_human) s4.state = "本人待ち";
    else if (g.delivered) s4.state = "済み";
  }
  return tree;
}
