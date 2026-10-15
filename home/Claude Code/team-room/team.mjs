// チームの一覧（画面の「チーム」で見る物）。部屋の記録を読み直すだけで、何も書かない。
// 2026-10-07 本人「どのチームメンバーがいて、全員を管理できる場所」。
// 役ごとに: 今やっているか・今の作業・どの案件か・今日の仕事数と編集長の判定・最近の仕事。
// 「作業中」は、最後の発注の中で返事がまだ無く、15分以内に作業の記録がある時だけ（落ちた仕事を作業中に見せない）
import { treeOf } from "./tree.mjs";

const 今日 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
const 一行目 = (s) => String(s || "").split("\n").map((l) => l.replace(/^\s*\[[^\]]*\]\s*/, "").replace(/^[#>*\-\s【]+|】/g, " ").trim()).find((l) => l.length > 2) || "";

// jobs: jobsOf の結果、read(brand, job_id, rev): その案件の messages（id 順・meta 解いた物）
export function teamOf({ jobs, read, channels, roles, now = Date.now(), days = 7 }) {
  const 人 = new Map(Object.keys(roles).map((r) => [r, { role: r, 部: roles[r].部, 色: roles[r].色, busy: false, now: "", job: null, last: 0, today: { works: 0, pass: 0, fix: 0 }, recent: [], byBrand: {} }]));
  const 足す = (role) => 人.get(role) || (人.set(role, { role, 部: "", 色: "#8f8f8f", busy: false, now: "", job: null, last: 0, today: { works: 0, pass: 0, fix: 0 }, recent: [], byBrand: {} }), 人.get(role));
  const 境 = 今日();
  // ブランドごとの箱（係はブランドごとに動いたか動いていないかが決まる。2026-10-07 本人）
  const 箱 = (p, brand) => (p.byBrand[brand] ||= { orders: 0, works: 0, pass: 0, fix: 0, today: 0, last: 0, busy: false, now: "", recent: [] });
  const 記す = (p, brand, item, v, isWork) => {
    const b = 箱(p, brand); b.recent.push(item); b.last = Math.max(b.last, item.end || item.ts);
    if (!isWork) b.orders++;
    if (isWork) { b.works++; if (item.ts >= 境) b.today++; if (v === "PASS") b.pass++; if (v === "FIX") b.fix++; }
    if (item.status === "作業中") { b.busy = true; b.now = item.now || b.now; }
  };
  for (const j of jobs.filter((x) => x.last >= now - days * 86400000)) {
    const t = treeOf(read(j.brand, j.job_id, j.revision), channels, null);
    const job = { brand: j.brand, job_id: j.job_id, revision: j.revision, name: j.name || j.job_id };
    const 見た = new Set();
    for (const s of t.stages) for (const o of s.orders) {
      // 部長の仕事（発注を受けて振る）
      const L = 足す(o.lead), oEnd = o.end || o.ts;
      L.last = Math.max(L.last, oEnd);
      if (!見た.has(o.id) && 見た.add(o.id)) { const it = { ts: o.ts, end: o.end, job, stage: s.n, node: `s${s.n}-${o.id}`, what: 一行目(o.ask), status: o.status, verdict: null, lead: true, works: o.works.length }; L.recent.push(it); 記す(L, j.brand, it, null, false); }
      if (o.status === "作業中" && o.acts.length) { L.busy = true; L.now = L.now || "メンバーに振って返事を待っている"; L.job = L.job || job; }
      for (const w of o.works) {
        const P = 足す(w.role), v = w.verdicts.at(-1)?.v || w.reviewed || null;
        P.last = Math.max(P.last, w.end || w.ts);
        const it = { ts: w.ts, end: w.end, job, stage: s.n, node: `s${s.n}-${w.id}`, what: 一行目(w.ask), status: w.status, verdict: v, acts: w.acts.length, artifacts: w.artifacts.length, now: w.status === "作業中" ? (w.acts.at(-1) || "").replace(/^コマンド:\s*/, "") : "" };
        P.recent.push(it); 記す(P, j.brand, it, v, true);
        if (w.ts >= 境) { P.today.works++; if (v === "PASS") P.today.pass++; if (v === "FIX") P.today.fix++; }
        if (w.status === "作業中") { P.busy = true; P.now = w.acts.at(-1)?.replace(/^コマンド:\s*/, "") || "取りかかったところ"; P.job = job; }
      }
    }
  }
  // 作業中でも15分以上なにも記録が無い物は「止まっているかも」
  for (const p of 人.values()) {
    p.recent.sort((a, b) => b.ts - a.ts);
    const 最新 = p.recent[0];
    if (p.busy && 最新 && now - Math.max(最新.ts, p.last) > 15 * 60000 && !p.recent.some((r) => r.status === "作業中" && now - r.ts < 15 * 60000)) p.stale = true;
    p.recent = p.recent.slice(0, 12);
    for (const b of Object.values(p.byBrand)) { b.recent.sort((a, c) => c.ts - a.ts); b.recent = b.recent.slice(0, 15); }
  }
  const 部 = channels.filter((c) => c.id !== "hq").map((c) => ({ id: c.id, name: c.name, lead: c.lead, members: c.members.filter((m) => m !== "編集長") }));
  const hq = channels.find((c) => c.id === "hq");
  const brands = [...new Set(jobs.filter((x) => x.last >= now - days * 86400000).map((x) => x.brand))];
  return { at: now, days, brands, hq: hq ? { name: hq.name, lead: hq.lead, members: hq.members.filter((m) => !部.some((d) => d.lead === m) && m !== "編集長") } : null, 部, 横断: ["編集長"], people: Object.fromEntries(人) };
}
