// 流れ: ブランドを選ぶ → 案件ごとの木（案件 → 工程 → 発注 → 役の仕事）。読むだけ。/api/tree を6秒ごとに読み直す
(() => {
const F = { brand: null, job: null, jobs: [], tree: null, raw: "", roles: {}, open: new Set(), shut: new Set(), sel: null, view: { x: 40, y: 80, k: 0.85 }, fitted: false, timer: null };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const t2 = (ts) => { if (!ts) return ""; const d = new Date(ts), now = new Date(); const hm = d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }); return d.toDateString() === now.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`; };
const ago = (ts) => { if (!ts) return ""; const m = Math.round((Date.now() - ts) / 60000); return m < 1 ? "今" : m < 60 ? `${m}分前` : m < 1440 ? `${Math.round(m / 60)}時間前` : `${Math.round(m / 1440)}日前`; };
const col = (r) => F.roles[r]?.色 || "#8f8f8f";
const 一行目 = (s) => String(s || "").split("\n").map((l) => l.replace(/^\s*\[[^\]]*\]\s*/, "").replace(/^[#>*\-\s【]+|】/g, " ").trim()).find((l) => l.length > 2) || "";
const 工程名 = { 1: "商品を決める", 2: "客を知る", 3: "アングルと割り付け", 4: "広告を作る", 5: "記事を作る", 6: "店を作る", 7: "配信する", 8: "測る", 9: "学ぶ" };
const 状態の名 = { success: "済み", partial: "途中", error: "失敗", cancelled: "止めた", 作業中: "作業中", 切れた: "切れた" };
const keyOf = (j) => `${j.job_id}/${j.revision}`;
// 画面に出す名前（本人 2026-10-07「nightly て何か分からない。一目で分かるように」）。案件は日本語の名前、ブランドは中身が分かる名前
const 案件名 = (j) => j?.name || F.jobs.find((x) => keyOf(x) === keyOf(j || {}))?.name || j?.job_id || "";
const ブランド名 = (b) => ({ リサーチ: "新商品リサーチ" })[b] || b;
// 読む先。部屋では /api/tree、リンクのページ（claude.ai）では window.FLOW_SOURCE が差し替える
const SRC = window.FLOW_SOURCE || {
  roles: async () => (await (await fetch("/api/state")).json()).roles,
  team: async () => (await (await fetch("/api/team")).json()),
  ads: async (b) => (await (await fetch(`/api/ads?brand=${encodeURIComponent(b)}`)).json()),
  img: (p) => "/ads-img/" + p,
  refInfo: async (brand, job_id, ids) => (await fetch(`/api/ref-info?${new URLSearchParams({ brand, job_id, ids: ids.join(",") })}`)).json(),
  ref: (brand, job_id, id) => `/api/ref-img?${new URLSearchParams({ brand, job_id, id })}`,
  // 部屋（ローカル）では、そのまま部屋の発注として送る（止まっている自動の振り分けを同じゴールで動かし直す）
  answer: async (ctx, text, goal, channel) => { const st = await (await fetch("/api/state")).json(); const r = await fetch("/api/post", { method: "POST", headers: { "x-team-token": st.csrf_token }, body: JSON.stringify({ channel, text, context: ctx, autopilot: goal ? { goal } : undefined }) }); return r.json(); },
  brands: async () => (await (await fetch("/api/tree")).json()).brands || [],
  jobs: async (brand) => (await (await fetch(`/api/tree?brand=${encodeURIComponent(brand)}`)).json()).jobs || [],
  tree: async (brand, job_id, revision) => (await fetch(`/api/tree?${new URLSearchParams({ brand, job_id, revision })}`)).text(),
};

document.body.insertAdjacentHTML("beforeend", `
<section id="flow" hidden aria-label="流れ">
  <aside class="fl-side"><div class="fl-hello"><span class="fl-orb" aria-hidden="true"><svg viewBox="0 0 80 80"><defs><clipPath id="oc"><circle cx="40" cy="40" r="39"/></clipPath><radialGradient id="osky" cx=".5" cy=".15" r=".95"><stop offset="0" stop-color="#a9c6ff"/><stop offset=".45" stop-color="#c7b7ee"/><stop offset=".8" stop-color="#efc3d6"/><stop offset="1" stop-color="#f6d5cf"/></radialGradient><radialGradient id="ogl" cx=".32" cy=".2" r=".55"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset=".6" stop-color="#fff" stop-opacity=".08"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient><radialGradient id="opuff" cx=".45" cy=".35" r=".65"><stop offset="0" stop-color="#fff"/><stop offset=".7" stop-color="#fbeef3"/><stop offset="1" stop-color="#e9d6e8" stop-opacity=".85"/></radialGradient><filter id="ob1"><feGaussianBlur stdDeviation="1.6"/></filter><filter id="ob2"><feGaussianBlur stdDeviation=".7"/></filter></defs><g clip-path="url(#oc)"><rect width="80" height="80" fill="url(#osky)"/><g class="orb-clouds" filter="url(#ob1)" opacity=".75"><ellipse cx="18" cy="26" rx="16" ry="6" fill="#fff"/><ellipse cx="62" cy="20" rx="13" ry="5" fill="#fff"/></g><g class="orb-cloud-front" filter="url(#ob2)"><circle cx="22" cy="58" r="13" fill="url(#opuff)"/><circle cx="38" cy="50" r="16" fill="url(#opuff)"/><circle cx="56" cy="56" r="14" fill="url(#opuff)"/><circle cx="68" cy="66" r="12" fill="url(#opuff)"/><circle cx="10" cy="70" r="12" fill="url(#opuff)"/><rect x="0" y="62" width="80" height="20" fill="#fbeef3"/></g><rect width="80" height="80" fill="url(#ogl)"/></g><circle cx="40" cy="40" r="39" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.5"/></svg></span><b id="fl-greet"></b></div><div class="fl-mode glass" role="tablist"><button role="tab" data-mode="flow" aria-selected="true"><svg viewBox="0 0 24 24"><rect x="3" y="9.5" width="6" height="5" rx="1.6"/><rect x="15" y="3.5" width="6" height="5" rx="1.6"/><rect x="15" y="15.5" width="6" height="5" rx="1.6"/><path d="M9 12h2.5a2 2 0 0 0 2-2V8a2 2 0 0 1 1.5-2M11.5 12a2 2 0 0 1 2 2v2a2 2 0 0 0 1.5 2"/></svg>流れ</button><button role="tab" data-mode="team" aria-selected="false" hidden><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9" r="2.4"/><path d="M15.5 14.2A4.5 4.5 0 0 1 21 18.5"/></svg>チーム</button></div><div id="fl-side-flow"><div class="cap">ブランド</div><div id="fl-brands"></div></div><div id="fl-side-team" hidden><div class="cap">ブランド</div><div id="fl-tbrands"></div><div class="cap">部</div><div id="fl-depts"></div></div></aside>
  <div class="fl-main">
    <div class="fl-team" id="fl-team" hidden></div>
    <div class="fl-vp" id="fl-vp"><div class="fl-world" id="fl-world"><svg class="fl-edges" id="fl-edges"></svg><div id="fl-nodes"></div></div></div>
    <div class="fl-top" id="fl-top"></div>
    <div class="fl-tools glass"><button id="fl-fit" title="全体を見る"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button><button id="fl-out" title="小さく"><svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg></button><span id="fl-pct">85%</span><button id="fl-in" title="大きく"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></button><button id="fl-reset" title="動かした節を元の並びに戻す"><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4"/></svg></button></div>
    <div class="fl-empty" id="fl-empty" hidden></div>
    <aside class="fl-pane" id="fl-pane" hidden></aside>
  </div>
</section>`);

// ── 開く・閉じる ──
const あいさつ = () => { const h = new Date().getHours(); return `${h < 5 ? "こんばんは" : h < 11 ? "おはよう" : h < 18 ? "こんにちは" : "こんばんは"}、Tokunari`; };
async function openFlow(hash) {
  $("fl-greet").textContent = あいさつ();
  $("flow").hidden = false; document.body.classList.add("flow-on");
  $("r-flow")?.setAttribute("aria-current", "true"); $("r-home")?.setAttribute("aria-current", "false");
  if (!Object.keys(F.roles).length) { try { F.roles = await SRC.roles(); } catch {} }
  const [, b, j, r, sel] = String(hash || "").split("/").map(decodeURIComponent);
  F.pendingSel = sel || null;
  await loadBrands(b);
  if (j) F.job = { job_id: j, revision: Number(r) };
  await pickBrand(F.brand, !!j);
  clearInterval(F.timer); F.timer = setInterval(() => !document.hidden && !$("flow").hidden && (F.mode === "team" ? loadTeam() : refresh()), 6000);
}
function closeFlow() {
  $("flow").hidden = true; document.body.classList.remove("flow-on"); clearInterval(F.timer);
  $("r-flow")?.setAttribute("aria-current", "false"); $("r-home")?.setAttribute("aria-current", "true");
  if (location.hash.startsWith("#flow")) history.replaceState(null, "", location.pathname);
}
const setHash = () => SRC.noHash ? null : history.replaceState(null, "", "#flow/" + [F.brand, F.job?.job_id, F.job?.revision, F.sel].filter((x) => x != null).map(encodeURIComponent).join("/"));

// ── ブランドと案件 ──
async function loadBrands(want) {
  const list = (await SRC.brands()).filter((b) => b.jobs).sort((a, b) => b.last - a.last);
  F.brand = want && list.some((b) => b.brand === want) ? want : F.brand || list[0]?.brand || null;
  F.brands = list; drawSide();
}
async function pickBrand(brand, keepJob) {
  F.brand = brand; if (!keepJob) F.job = null;
  if (!brand) return empty("まだ記録のある案件がありません");
  F.jobs = await SRC.jobs(brand);
  if (ラインあり() && !F.lineSel[brand]) { const want = F.job && F.jobs.find((j) => keyOf(j) === keyOf(F.job)); F.lineSel[brand] = (want || F.jobs[0])?.line?.id || (F.brands.find((b) => b.brand === brand).lines[0].id); }
  const 見せる = 見える案件();
  if (!F.job || !見せる.some((j) => keyOf(j) === keyOf(F.job))) F.job = 見せる[0] || null;
  await pickJob(F.job);
}
async function pickJob(job) {
  F.screen = "flow";
  F.job = job; F.tree = null; F.raw = ""; F.open.clear(); F.shut.clear(); F.sel = null; F.fitted = false; $("fl-pane").hidden = true;
  drawTop(); setHash();
  if (!job) return empty("このブランドにはまだ案件がありません");
  await refresh();
}
async function refresh() {
  if (!F.job || F.screen === "ads") return;
  let raw; try { raw = await SRC.tree(F.brand, F.job.job_id, F.job.revision); } catch { return; }
  if (!raw || F.screen === "ads") return; // 読んでいる間に広告に切り替わったら描かない
  if (raw === F.raw) return;
  F.raw = raw; F.tree = JSON.parse(raw);
  if (F.tree.error) return empty(F.tree.error);
  $("fl-empty").hidden = true;
  draw();
  if (F.pendingSel) { const id = F.pendingSel; F.pendingSel = null; const st = id.split("-")[0]; if (st !== id) { F.open.clear(); F.open.add(st); } F.sel = id; draw(); }
  if (!F.fitted) { fit(); F.fitted = true; if (F.sel) { focusOn(F.sel); showPane(F.sel); } }
  if (F.sel) showPane(F.sel, true);
  const j = F.jobs.find((x) => keyOf(x) === keyOf(F.job)); if (j && F.tree.current) j.stage = F.tree.current;
  drawTop();
}
function empty(msg) { $("fl-nodes").innerHTML = ""; $("fl-edges").innerHTML = ""; const e = $("fl-empty"); e.hidden = false; e.textContent = msg; }

function drawSide() {
  $("fl-brands").innerHTML = (F.brands || []).map((b) => {
    const cur = b.brand === F.brand;
    const ls = b.lines || [], sel = F.lineSel[b.brand];
    const 切替 = cur && ls.length ? `<div class="fl-lines glass" role="tablist">${ls.map((l) => `<button role="tab" data-fl="${esc(l.id)}" aria-selected="${sel === l.id}">${esc(l.name)}<small>${l.jobs}</small></button>`).join("")}</div>` : "";
    const 見せる = 見える案件();
    const 広告 = cur ? `<button class="fl-job fl-adsentry" data-ads aria-current="${F.screen === "ads"}"><span class="nm"><svg viewBox="0 0 24 24"><path d="M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z"/><path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/></svg>広告</span><small>${F.adsBrand === b.brand && F.ads ? `${見える広告().length} キャンペーン ・ ${見える広告().reduce((a, c) => a + c.adsets.reduce((x, s) => x + s.ads.length, 0), 0)} 本` : "キャンペーン・広告セット・記事"}</small></button>` : "";
    const jobs = cur ? 切替 + `<div class="fl-jobs">${広告}<div class="fl-cap">案件</div>${見せる.length ? "" : `<div class="fl-empty-line">まだ案件がない</div>`}${見せる.map((j) => `<button class="fl-job" data-fj="${esc(keyOf(j))}" aria-current="${F.screen !== "ads" && !!F.job && keyOf(j) === keyOf(F.job)}"><span class="nm">${esc(案件名(j))}</span><small>${j.autopilot?.on ? '<i class="on" title="自動で進行中"></i>' : ""}${j.revision > 1 ? `${j.revision}回目 ・ ` : ""}${j.stage ? `${esc(工程名[j.stage] || "")}まで ・ ` : ""}${ago(j.last)}</small></button>`).join("")}</div>` : "";
    return `<button class="glass fl-brand" data-fb="${esc(b.brand)}" aria-current="${cur}">${esc(ブランド名(b.brand))}<small>案件 ${b.jobs} ・ ${ago(b.last)}</small></button>${jobs}`;
  }).join("");
}
// 選んでいるライン（女性用／男性用 など）の案件だけ。ラインの無いブランドは全部
F.lineSel = {};
const ラインあり = () => (F.brands || []).find((b) => b.brand === F.brand)?.lines?.length > 0;
const 見える案件 = () => ラインあり() ? F.jobs.filter((j) => j.line?.id === F.lineSel[F.brand]) : F.jobs;
function drawTop() {
  drawSide();
  const t = F.tree, s = t?.stages?.find((x) => x.n === t.current);
  const 更新 = SRC.stamp?.();
  // 上はブランド名だけ（本人 2026-10-07「ここちドライだけとかに」。案件名・版・工程は左と木で分かる）
  $("fl-top").innerHTML = F.brand ? `<span class="glass fl-title">${esc(ブランド名(F.brand))}</span>` : "";
}

// 使い直しの元を一言で（前の回／移した元の案件／Obsidian に前からある物）
const 元の一言 = (f) => !f ? "" : f.kind === "vault" ? "前からある物を使う" : f.kind === "job" ? `「${f.name || f.job_id}」で済んだ物を使う` : `${f.revision}回目で済んだ物を使う`;
// 正本の図（EC全体 1〜9）の担当と作る物
const 工程の説明 = {
  1: ["リサーチャー／責任者 戦略責任者", "商品候補と選定根拠"], 2: ["リサーチャー／責任者 戦略責任者", "確定客像・客の言葉・反論台帳"],
  3: ["戦略担当／責任者 戦略責任者", "アングルと、広告・記事・店の割り付け"], 4: ["制作の5役／責任者 クリエイティブディレクター", "審査合格の広告と編集できる原本"],
  5: ["記事ライター／責任者 ファネル責任者", "広告の続きを受ける記事・クイズ"], 6: ["ストア担当／責任者 ファネル責任者", "商品ページ・カート等の検査済み変更"],
  7: ["メディアバイヤー／責任者 グロース責任者", "入稿準備と配信変更"], 8: ["アナリスト／責任者 グロース責任者", "取得時刻付きの判断材料"], 9: ["戦略担当／責任者 戦略責任者", "次の発注と共通ルールの更新案"],
};
const 長さ = (ms) => { const m = Math.round(ms / 60000); return m < 60 ? `${m}分` : m < 1440 ? `${Math.floor(m / 60)}時間${m % 60 ? m % 60 + "分" : ""}` : `${Math.floor(m / 1440)}日${Math.round((m % 1440) / 60)}時間`; };
const 頭の数行 = (s, n = 3) => String(s || "").split("\n").map((l) => l.replace(/^[#>*\-\s]+/, "").replace(/\*\*/g, "").trim()).filter((l) => l && !/^HANDOFF/i.test(l)).slice(0, n).join("\n");

// ── 広告（キャンペーン → 広告セット → 広告 → 記事）。2026-10-07 本人「動画の最初の場面と記事の最初の画像で、どの広告がどの記事か一瞬で分かるように」
F.screen = "flow"; F.ads = null; F.adsBrand = null; F.adOpen = new Set();
const 見える広告 = () => (F.ads?.campaigns || []).filter((c) => !ラインあり() || !c.line || c.line.id === F.lineSel[F.brand]);
const 状態札 = (st) => st === "ACTIVE" ? '<span class="tag 通った">配信中</span>' : st === "PAUSED" || st === "CAMPAIGN_PAUSED" || st === "ADSET_PAUSED" ? '<span class="tag 済み">止めている</span>' : `<span class="tag 済み">${esc(st || "")}</span>`;
const 円 = (v) => "¥" + Math.round(v || 0).toLocaleString("ja-JP");
async function openAds() {
  F.screen = "ads"; F.sel = null; $("fl-pane").hidden = true; F.fitted = false;
  if (F.adsBrand !== F.brand) { F.ads = null; try { F.ads = await SRC.ads(F.brand); F.adsBrand = F.brand; } catch { F.ads = { campaigns: [] }; } F.adOpen.clear(); }
  // 作っている広告: このラインの案件で、広告の工程（4）まで来ている物。木を読んで、あなたの番かどうかも見る
  // 作っている広告は、ec-graph で作っている動画1本ずつ（2026-10-08 本人「押しても役の木に戻るだけで意味が無い」）。部屋の役の案件は出さない
  F.making = [];
  const 線 = (F.brands || []).find((b) => b.brand === F.brand)?.lines?.find((l) => l.id === F.lineSel[F.brand]);
  try { const g = await (await fetch(`/api/graph?for=${encodeURIComponent(F.brand + (線 ? "/" + 線.name : ""))}`)).json(); F.making = [...g.refs.map((r) => ({ r, 候補: false })), ...g.next.map((r) => ({ r, 候補: true }))]; } catch {}
  if (F.screen !== "ads") return;
  drawTop();
  if (!見える広告().length && !F.making.length) { F.nodes = new Map(); return empty("このブランド（ライン）の広告はまだ無い"); }
  $("fl-empty").hidden = true; draw(); fit(); F.fitted = true;
}
const 広告の大きさ = { art: [250, 84], cp: [360, 84], mk: [360, 84], as: [320, 72], jb: [340, 92], ad: [330, 104], ask: [330, 104], pg: [330, 104] };
const 広告の列 = { art: 0, cp: 320, mk: 320, as: 740, jb: 740, ad: 1120, ask: 1120, pg: 1510 };
const 広告の間 = { cp: 18, mk: 18, as: 12, jb: 12, ad: 10, ask: 10, pg: 0 };
const 待ち = (m) => m.st?.state === "本人待ち";
// 質問の文（クリエイティブディレクターの最後の返事）と、そこに出てくる参考の広告ID
// 参考の広告IDが書いてある一番新しい文（返事か、本人の発注の文）。前は一番新しい返事だけを見ていたので、
// 作業の報告が後から来るとIDが無くなり、候補が空になった（2026-10-08 本人「昨日まで入ってたのに今は入ってない」）
const IDあり = (t) => /\b\d{15,17}\b/.test(t || "");
const 質問の文 = (m) => [...(m.st?.orders || [])].reverse().flatMap((o) => [o.output, o.ask]).filter(IDあり).join("\n") || [...(m.st?.orders || [])].reverse().find((o) => o.output)?.output || "";  // 工程4の全部の文から、新しい順に
const 候補 = (m) => { const t = 質問の文(m), ids = [...new Set(t.match(/\b\d{15,17}\b/g) || [])]; return ids.map((id) => ({ id, 説明: (t.split("\n").find((l) => l.includes(id)) || "").replace(/^[\s\-*・①-⑨0-9.]+/, "").replace(id, "").replace(/^[：:、\s]+/, "").replace(/\*\*/g, "").trim() })); };
function buildAds() {
  const cs = 見える広告();
  const 開く = (id, i) => F.adOpen.size ? F.adOpen.has(id) : i === 0;
  const mk = [{ id: "mk", type: "mk", kids: (F.making || []).map((m) => ({ id: (m.候補 ? "n" : "r") + m.r.ext, type: "jb", m, kids: [] })) }];
  const root = { id: "root", type: "art", kids: mk.concat(cs.map((c, i) => ({ id: "c" + c.id, type: "cp", c, open: 開く("c" + c.id, i),
    kids: 開く("c" + c.id, i) ? c.adsets.map((a) => ({ id: "s" + a.id, type: "as", a, kids: a.ads.map((d) => ({ id: "a" + d.id, type: "ad", d, kids: d.page ? [{ id: "p" + d.id, type: "pg", p: d.page, kids: [] }] : [] })) })) : [] }))) };
  const measure = (n) => { const [w, h] = 広告の大きさ[n.type]; n.w = w; n.h = h; if (!n.kids.length) return (n.sh = h); const g = 広告の間[n.kids[0].type]; n.kh = n.kids.reduce((a, k) => a + measure(k), 0) + g * (n.kids.length - 1); return (n.sh = Math.max(h, n.kh)); };
  const all = [];
  const place = (n, top) => { n.x = 広告の列[n.type]; n.y = top + (n.sh - n.h) / 2; all.push(n); if (!n.kids.length) return; const g = 広告の間[n.kids[0].type]; let y = top + (n.sh - n.kh) / 2; for (const k of n.kids) { place(k, y); y += k.sh + g; } };
  measure(root); place(root, 0);
  const off = 位置();
  const shift = (n, ax, ay) => { const o = off[n.id], dx = ax + (o?.dx || 0), dy = ay + (o?.dy || 0); n.x += dx; n.y += dy; for (const k of n.kids) shift(k, dx, dy); };
  shift(root, 0, 0);
  return all;
}
function adNodeHTML(n) {
  const st = `left:${n.x}px;top:${n.y}px;width:${n.w}px;height:${n.h}px`, sel = F.sel === n.id ? " sel" : "";
  if (n.type === "art") { const l = ラインあり() ? (F.brands.find((b) => b.brand === F.brand)?.lines || []).find((x) => x.id === F.lineSel[F.brand])?.name : ""; return `<div class="fn rt${sel}" data-n="root" style="${st}"><div class="tx"><small>${esc(ブランド名(F.brand))}${l ? " ・ " + esc(l) : ""}</small><b>広告</b><small>${F.ads?.since ? `${F.ads.since.slice(5).replace("-", "/")}〜${F.ads.until.slice(5).replace("-", "/")} の数字 ・ ${t2(F.ads.at)} に取った` : ""}</small></div></div>`; }
  if (n.type === "cp") { const c = n.c, ads = c.adsets.reduce((a, s) => a + s.ads.length, 0); return `<div class="fn cp${n.open ? " open" : ""}${sel}" data-n="${n.id}" style="${st}"><span class="ic">C</span><div class="tx"><b>${esc(c.name)}</b><small>広告セット ${c.adsets.length} ・ 広告 ${ads} ・ 7日 ${円(c.spend)}</small></div>${状態札(c.status)}<span class="tog">›</span></div>`; }
  if (n.type === "mk") { const 作 = F.making.filter((m) => !m.候補); return `<div class="fn cp mkg${sel}" data-n="mk" style="${st}"><span class="ic mk">＋</span><div class="tx"><b>作っている広告</b><small>${作.length ? `${作.length}本 ・ 済み ${作.filter((m) => m.r.status === "delivered").length} ・ 作業中 ${作.filter((m) => m.r.status === "running").length} ・ 本人待ち ${作.filter((m) => m.r.status === "needs_human").length}` : "まだ無い（このラインの勝ち広告の棚がまだ地図に無い）"}</small></div></div>`; }
  if (n.type === "jb") { const r = n.m.r, 状 = n.m.候補 ? "候補" : ({ running: "作業中", needs_human: "本人待ち", fail_1: "やり直し", passed: "通った", delivered: "済み" }[r.status] || r.status);
    const dots = (r.steps || []).map((x) => `<i class="gs ${x.ok ? "ok" : x.ok === null ? "na" : "no"}"></i>`).join("");
    return `<div class="fn rp${n.m.候補 ? " nx" : ""}${sel}" data-n="${n.id}" style="${st}"><div class="tx"><small>${esc(r.ext)} ・ 星${(r.score || 0) >= 91 ? 5 : 4} ・ ${esc(r.days)}日勝ち</small><b>${esc(String(r.label || "").replace(/^"|"$/g, ""))}</b>${dots ? `<span class="gsteps">${dots}</span>` : ""}</div><span class="tag ${esc(状)}">${esc(状)}</span></div>`; }
  if (n.type === "jb") { const m = n.m; return `<div class="fn as${sel}" data-n="${n.id}" style="${st}"><span class="ic s">案</span><div class="tx"><b>${esc(案件名(m.job))}</b><small>広告を作る ・ ${esc(m.st?.state || "")}</small></div>${待ち(m) ? '<span class="tag 本人待ち">本人待ち</span>' : `<span class="tag ${esc(m.st?.state || "")}">${esc(m.st?.state || "")}</span>`}</div>`; }
  if (n.type === "ask") { const c = 候補(n.m).slice(0, 4); return `<div class="fn cr ask${sel}" data-n="${n.id}" style="${st}"><div class="mini">${c.map((x) => `<img src="${esc(SRC.ref(F.brand, n.m.job.job_id, x.id))}" alt="" loading="lazy" draggable="false" onerror="this.style.visibility='hidden'">`).join("")}</div><div class="tx"><b>${待ち(n.m) ? "あなたの番" : "参考の候補"}</b><small>${待ち(n.m) ? "作り方・形・本数・参考を選んで送る" : "押すと、どの広告か見て選べる"}</small><small>参考の候補 ${候補(n.m).length} 本</small></div><span class="tag 本人待ち">答える</span></div>`; }
  if (n.type === "as") { const a = n.a; return `<div class="fn as${sel}" data-n="${n.id}" style="${st}"><span class="ic s">S</span><div class="tx"><b>${esc(a.name)}</b><small>広告 ${a.ads.length} ・ 7日 ${円(a.spend)}</small></div>${状態札(a.status)}</div>`; }
  if (n.type === "ad") { const d = n.d; return `<div class="fn cr${sel}" data-n="${n.id}" style="${st}">${d.img ? `<img class="th" src="${esc(SRC.img("img/" + d.img))}" alt="" loading="lazy" draggable="false">` : `<span class="th none">${d.kind === "video" ? "動画" : "画像"}</span>`}<div class="tx"><b>${esc(d.name)}</b><small>7日 ${円(d.spend)} ・ クリック ${Math.round(d.clicks)} ・ 購入 ${Math.round(d.purchases)}</small><small>${d.page ? "→ " + esc(d.page.path) : "着地の記録なし（30日）"}</small></div>${状態札(d.status)}</div>`; }
  const p = n.p; return `<div class="fn pg${sel}" data-n="${n.id}" style="${st}">${p.img ? `<img class="th wide" src="${esc(SRC.img("pages/" + p.img))}" alt="" loading="lazy" draggable="false">` : `<span class="th wide none">記事</span>`}<div class="tx"><small>${/products\//.test(p.path) ? "商品ページ" : /quiz/.test(p.path) ? "クイズ" : "記事"}</small><b>${esc(p.title)}</b><small>${esc(p.path)}</small></div></div>`;
}
// 大きい画面（広告の画面）。押した物を全画面で開き、戻るで1つ前に戻る（2026-10-07 本人「横から出すんじゃなくて大画面で。戻るボタンも」）
F.stack = [];
function 全画面(head, body, push = true) {
  const pane = $("fl-pane");
  if (push) F.stack.push({ head, body });
  pane.classList.add("full");
  pane.innerHTML = `<header><button class="glass back" data-back>${F.stack.length > 1 ? "← 戻る" : "← 閉じる"}</button>${head}</header><div class="body">${body}</div>`;
  pane.hidden = false; pane.querySelector(".body").scrollTop = 0;
}
function 戻る() { F.stack.pop(); const p = F.stack.at(-1); if (p) return 全画面(p.head, p.body, false); $("fl-pane").hidden = true; $("fl-pane").classList.remove("full"); F.sel = null; F.asking = null; draw(); }
const 広告の札 = (d) => `<button class="glass kk-tile" data-adtile="${esc(d.id)}">${d.img ? `<img src="${esc(SRC.img("img/" + d.img))}" alt="" loading="lazy">` : `<span class="noimg">${d.kind === "video" ? "動画" : "画像"}</span>`}<span class="tt"><b>${esc(d.name)}</b><small>7日 ${円(d.spend)} ・ 購入 ${Math.round(d.purchases)}</small>${状態札(d.status)}</span>${d.page ? `<span class="to"><i>→</i>${d.page.img ? `<img src="${esc(SRC.img("pages/" + d.page.img))}" alt="" loading="lazy">` : ""}<small>${esc(d.page.title.slice(0, 28))}</small></span>` : `<span class="to none"><small>飛び先の記録なし</small></span>`}</button>`;
const セットの段 = (a) => `<section class="kk-sec"><h4>${esc(a.name)} <small>${a.ads.length}本 ・ 7日 ${円(a.spend)}</small></h4><div class="kk-grid">${a.ads.map(広告の札).join("")}</div></section>`;
function 一覧を開く(kind, x) {
  if (kind === "root") return 全画面(`<div class="tx"><b>${esc(ブランド名(F.brand))}の広告</b><small>キャンペーン ${見える広告().length} ・ ${F.ads.since.slice(5).replace("-", "/")}〜${F.ads.until.slice(5).replace("-", "/")}</small></div>`, 見える広告().map((c) => `<h3 class="kk-camp">${esc(c.name)} ${状態札(c.status)}</h3>` + c.adsets.map(セットの段).join("")).join(""));
  if (kind === "cp") return 全画面(`<div class="tx"><b>${esc(x.name)}</b><small>キャンペーン ・ 広告セット ${x.adsets.length} ・ 7日 ${円(x.spend)}</small></div>${状態札(x.status)}`, x.adsets.map(セットの段).join(""));
  if (kind === "as") return 全画面(`<div class="tx"><b>${esc(x.name)}</b><small>広告セット ・ 広告 ${x.ads.length} ・ 7日 ${円(x.spend)}</small></div>${状態札(x.status)}`, `<div class="kk-grid">${x.ads.map(広告の札).join("")}</div>`);
  if (kind === "mk") return 全画面(`<div class="tx"><b>作っている広告</b><small>案件 ${F.making.length}</small></div>`, F.making.map((m) => `<button class="glass mk-row" data-mkjob="${esc(keyOf(m.job))}"><b>${esc(案件名(m.job))}</b><small>広告を作る ・ ${esc(m.st?.state || "")}</small>${待ち(m) ? '<span class="tag 本人待ち">あなたの番</span>' : ""}</button>`).join(""));
}
const 広告を探す = (id) => { for (const c of F.ads?.campaigns || []) for (const a of c.adsets) for (const d of a.ads) if (d.id === id) return d; return null; };
function adPane(n) {
  const pane = $("fl-pane"); let head = "", body = "";
  if (n.type === "ask") return askPane(n.m);
  if (n.type === "art") return 一覧を開く("root");
  if (n.type === "mk") return;
  if (n.type === "cp") return 一覧を開く("cp", n.c);
  if (n.type === "as") return 一覧を開く("as", n.a);
  if (n.type === "jb") { F.screen = "flow"; return pickJob(F.jobs.find((x) => keyOf(x) === keyOf(n.m.job))); }
  if (n.type === "ad" || n.type === "pg") {
    const d = n.type === "ad" ? n.d : F.nodes.get("a" + n.id.slice(1))?.d; if (!d) return;
    head = `<div class="tx"><b>${esc(d.name)}</b><small>${d.kind === "video" ? "動画" : "画像"}の広告 ・ ${esc(F.ads.since.slice(5).replace("-", "/"))}〜の7日</small></div>${状態札(d.status)}`;
    body = `${d.img ? `<img class="kk-big" src="${esc(SRC.img("img/" + d.img))}" alt="">` : ""}<div class="fs-stats"><div><b>${円(d.spend)}</b><small>消化</small></div><div><b>${Math.round(d.clicks)}</b><small>クリック</small></div><div class="ok"><b>${Math.round(d.purchases)}</b><small>購入</small></div><div><b>${d.purchases ? 円(d.spend / d.purchases) : "—"}</b><small>1件の獲得</small></div></div>`
      + `<h4>飛び先</h4>` + (d.page ? `<a class="glass kk-page" href="${esc(d.page.url)}" target="_blank" rel="noopener">${d.page.img ? `<img src="${esc(SRC.img("pages/" + d.page.img))}" alt="">` : ""}<span><b>${esc(d.page.title)}</b><small>${esc(d.page.path)} ・ 開く ↗</small></span></a>` : `<div class="txt" style="color:var(--sub)">30日の訪問の記録に、この広告からの着地が無い</div>`);
  } else return;
  全画面(head, `<div class="kk-detail"><div>${body.split("<h4>飛び先</h4>")[0]}</div><div><h4>飛び先</h4>${body.split("<h4>飛び先</h4>")[1] || ""}</div></div>`);
}

// あなたの番: 工程4の入口の質問に、ボタンで答えて部屋に送る（2026-10-07 本人「送る場所は部屋の流れで大丈夫」）
function askPane(m) {
  const c = 候補(m), q = 質問の文(m);
  // 工程4の入口（種類・形・本数・リップ）の質問だけボタンの欄。ほかの質問（お金の承認など）は、質問の文と返事の欄
  if (!/入口|フォーマット|リップ/.test(q)) {
    全画面(`<span class="tag 本人待ち">あなたの番</span><div class="tx"><b>${esc(案件名(m.job))}</b><small>${esc((m.tree.waiting?.ask || "").split(" / ").pop().slice(0, 80))}</small></div>`, `<div class="ask-form"><h4>聞かれていること</h4><div class="fs-concl txt">${esc(頭の数行(q, 12))}</div><h4>返事</h4><textarea id="ask-memo" rows="5" placeholder="例: 承認。110クレジットで進めて"></textarea><div class="ask-send"><button class="ask-go" id="ask-go" data-free>部屋に送る</button><span id="ask-msg"></span></div><details class="ask-raw"><summary>質問の全文</summary><div class="txt">${esc(q)}</div></details></div>`);
    F.asking = m; return;
  }
  const 形 = ["VSL", "静止画", "ネイティブ", "UGC", "アニメ"];
  全画面(`<span class="tag 本人待ち">あなたの番</span><div class="tx"><b>${esc(案件名(m.job))}</b><small>広告を作る前に決めること</small></div>`, `<div class="ask-form">
    <h4>① 作り方</h4><div class="ask-row" data-q="作り方">${["競合のリップ", "オリジナルVSL"].map((x, i) => `<button class="glass ask-opt" data-v="${x}" aria-pressed="${i === 0}">${x}</button>`).join("")}</div>
    <h4>② 形（いくつでも）</h4><div class="ask-row multi" data-q="形">${形.map((x, i) => `<button class="glass ask-opt" data-v="${x}" aria-pressed="${i === 0}">${x}</button>`).join("")}</div>
    <h4>③ 本数</h4><div class="ask-row"><button class="glass ask-step" data-step="-1">−</button><b id="ask-n" class="ask-n">3</b><button class="glass ask-step" data-step="1">＋</button><span class="ask-unit">本</span></div>
    <h4>④ 参考にする広告（押して選ぶ）</h4><div class="ask-refs">${c.map((x, i) => `<div class="glass ask-ref" data-id="${x.id}" aria-pressed="${i === c.length - 1}" role="button" tabindex="0"><img src="${esc(SRC.ref(F.brand, m.job.job_id, x.id))}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'noimg',textContent:'絵なし'}))"><span class="rt"><b>${esc(x.id.slice(-6))}</b><small>${esc(x.説明.slice(0, 80))}</small><span class="links" data-links="${x.id}"></span></span></div>`).join("") || '<div class="txt" style="color:var(--sub)">質問の中に参考の候補が無い</div>'}</div>
    <h4>⑤ ひとこと（任意）</h4><textarea id="ask-memo" rows="3" placeholder="例: にじみを冒頭で言う1本を先に"></textarea>
    <div class="ask-send"><button class="ask-go" id="ask-go">部屋に送る</button><span id="ask-msg"></span></div>
    <details class="ask-raw"><summary>クリエイティブディレクターの質問（原文）</summary><div class="txt">${esc(q)}</div></details>
  </div>`);
  F.asking = m;
  // 候補の下に GetHookd で見るリンク（2026-10-07 本人「GetHookd で見れるリンクを下に」）
  SRC.refInfo?.(F.brand, m.job.job_id, c.map((x) => x.id)).then((info) => { for (const [id, v] of Object.entries(info || {})) { const el = document.querySelector(`[data-links="${id}"]`); if (el && v) el.innerHTML = `${v.share ? `<a href="${esc(v.share)}" target="_blank" rel="noopener">GetHookd で見る ↗</a>` : ""}${v.lp ? `<a href="${esc(v.lp)}" target="_blank" rel="noopener">飛び先 ↗</a>` : ""}`; } }).catch(() => {});
}
async function askSend() {
  const m = F.asking; if (!m) return;
  const pane = $("fl-pane"), 選 = (q) => [...pane.querySelectorAll(`[data-q="${q}"] [aria-pressed="true"]`)].map((b) => b.dataset.v);
  const refs = [...pane.querySelectorAll('.ask-ref[aria-pressed="true"]')].map((b) => b.dataset.id);
  const memo = $("ask-memo").value.trim();
  if (pane.querySelector("[data-free]")) { if (!memo) { $("ask-msg").textContent = "返事を書いてから送る"; return; } }
  const n = Number($("ask-n")?.textContent || 0);
  const text = pane.querySelector("[data-free]") ? `本人の返事（${new Date().toLocaleString("ja-JP")}）\n${memo}` : [`本人の答え（工程4の入口・${new Date().toLocaleString("ja-JP")}）`, `- 作り方: ${選("作り方").join("・")}`, `- 形: ${選("形").join("・") || "おまかせ"}`, `- 本数: ${n}本`, `- 参考: ${refs.join("・") || "おまかせ"}`, memo ? `- ひとこと: ${memo}` : "", "この答えで工程4を進める（関門0-1・0-2は済み）。"].filter(Boolean).join("\n");
  const last = [...(m.st?.orders || [])].pop(), msg = $("ask-msg"), go = $("ask-go");
  go.disabled = true; msg.textContent = "送っています…";
  try { const r = await SRC.answer({ brand: m.job.brand, job_id: m.job.job_id, revision: m.job.revision }, text, m.tree.autopilot?.goal, last?.channel || "creative"); if (!r.ok) throw new Error(r.error || "送れなかった"); msg.textContent = "送った。部屋で広告づくりが動き出す"; }
  catch (e) { msg.textContent = e.message; go.disabled = false; }
}

// ── 手で動かした位置（この端末だけに残す） ──
const 位置の鍵 = () => F.screen === "ads" ? `flow-pos:ads:${F.brand}/${F.lineSel[F.brand] || ""}` : `flow-pos:${F.brand}/${F.job?.job_id}/${F.job?.revision}`;
function 位置() { if (F.posKey !== 位置の鍵()) { F.posKey = 位置の鍵(); try { F.pos = JSON.parse(localStorage.getItem(F.posKey) || "{}"); } catch { F.pos = {}; } } return F.pos; }
function 位置を残す() { try { localStorage.setItem(位置の鍵(), JSON.stringify(F.pos)); } catch {} }

// ── 木の形と置き場所 ──
const 大きさ = { rt: [250, 92], st: [290, 72], od: [320, 84], wk: [290, 60], rp: [340, 92], nx: [340, 64] };
const 列 = { rt: 0, st: 330, od: 700, wk: 1100, rp: 700, nx: 700 };
const 間 = { st: 16, od: 22, wk: 10, rp: 14, nx: 14 };
function build(t) {
  const 案件 = { id: "root", type: "rt", kids: [] };
  for (const s of t.stages) {
    const sid = `s${s.n}`;
    const 枝 = s.orders.length > 0 || !!(s.refs?.length || s.next?.length);
    const open = 枝 && (F.open.size ? F.open.has(sid) : !F.shut.has(sid) && (s.n === t.current || (s.n === 4 && !!s.refs?.length)));
    const sn = { id: sid, type: "st", s, open, kids: [] };
    // 4 広告を作る: ec-graph の1本ずつ（作った・作っている物）と、次の候補（2026-10-08 本人「このステップは何だなって見れる」）
    if (open && s.refs) { for (const r of s.refs) sn.kids.push({ id: `${sid}-r${r.ext}`, type: "rp", r, kids: [] }); for (const r of s.next || []) sn.kids.push({ id: `${sid}-n${r.ext}`, type: "nx", r, kids: [] }); }
    if (open) s.orders.forEach((o, i) => {
      const on = { id: `${sid}-${o.id}`, type: "od", o, kids: [] };
      if (!F.shut.has(on.id)) on.kids = o.works.map((w) => ({ id: `${sid}-${w.id}`, type: "wk", wk: w, o, kids: [] }));
      sn.kids.push(on);
    });
    案件.kids.push(sn);
  }
  const measure = (n) => { const [w, h] = 大きさ[n.type]; n.w = w; n.h = h; if (!n.kids.length) return (n.sh = h); const g = 間[n.kids[0].type]; n.kh = n.kids.reduce((a, k) => a + measure(k), 0) + g * (n.kids.length - 1); return (n.sh = Math.max(h, n.kh)); };
  const place = (n, top, out) => { n.x = 列[n.type]; n.y = top + (n.sh - n.h) / 2; out.push(n); if (!n.kids.length) return; const g = 間[n.kids[0].type]; let y = top + (n.sh - n.kh) / 2; for (const k of n.kids) { place(k, y, out); y += k.sh + g; } };
  // 工程は1〜9を同じ間隔で縦に並べる（背骨）。開いた工程の発注と仕事は、その工程の高さを中心に右へ広げる
  const all = []; const [sw, shh] = 大きさ.st; let y = 0;
  for (const sn of 案件.kids) { sn.w = sw; sn.h = shh; sn.x = 列.st; sn.y = y; y += shh + 間.st; all.push(sn);
    if (sn.kids.length) { measure(sn);
      // 4 広告を作る: 1本ずつの節（rp・nx）を工程4の高さを中心に置き、部屋の発注はその下へ続ける（発注が多いと1本ずつの節が画面の外に出たため）
      const ad = sn.kids.filter((k) => k.type === "rp" || k.type === "nx");
      const ah = ad.reduce((a, k) => a + k.sh, 0) + 間.od * Math.max(0, ad.length - 1);
      let top = sn.y + shh / 2 - (ad.length ? ah : sn.kh) / 2;
      for (const k of sn.kids) { place(k, top, all); top += k.sh + 間.od; } } }
  const [rw, rh] = 大きさ.rt; Object.assign(案件, { w: rw, h: rh, x: 列.rt, y: (y - 間.st) / 2 - rh / 2 }); all.unshift(案件);
  const minY = Math.min(...all.map((n) => n.y)); if (minY < 0) for (const n of all) n.y -= minY;
  // 手で動かした分（節ごとのずれ）。動かした節の下の枝も一緒に動く
  const off = 位置();
  const shift = (n, ax, ay) => { const o = off[n.id], dx = ax + (o?.dx || 0), dy = ay + (o?.dy || 0); n.x += dx; n.y += dy; for (const k of n.kids) shift(k, dx, dy); };
  shift(案件, 0, 0);
  return all;
}
const live = (n) => n.type === "rt" ? !!F.tree.autopilot?.on : n.type === "st" ? n.s.state === "作業中" : n.type === "od" ? n.o.status === "作業中" : (n.type === "rp" || n.type === "nx") ? n.r.status === "running" : n.wk.status === "作業中";

function nodeHTML(n) {
  const st = `left:${n.x}px;top:${n.y}px;width:${n.w}px;height:${n.h}px`;
  const sel = F.sel === n.id ? " sel" : "";
  if (n.type === "rt") {
    const a = F.tree.autopilot;
    const sub = F.tree.waiting ? "あなたの判断待ち" : a ? (a.on ? `自動で進行中 ・ ${a.hops}回渡した` : "止まっている") : "手で発注";
    return `<div class="fn rt${sel}" data-n="root" style="${st}"><div class="tx"><small>${esc(ブランド名(F.tree.brand))}${F.tree.revision > 1 ? ` ・ ${F.tree.revision}回目` : ""}</small><b>${esc(案件名(F.job))}</b><small>${esc(sub)}</small></div></div>`;
  }
  if (n.type === "st") {
    const s = n.s, c = s.counts;
    const sub = s.state === "まだ" ? "まだ" : s.state === "使い直し" ? 元の一言(s.from) : `発注 ${c.orders} ・ 仕事 ${c.works}${c.pass || c.fix ? ` ・ 審査 ${c.pass + c.fix}` : ""}`;
    return `<div class="fn st ${esc(s.state)}${n.open ? " open" : ""}${sel}" data-n="${n.id}" style="${st}"><span class="num">${s.n}</span><div class="tx"><b>${esc(s.name)}</b><small>${esc(sub)}</small></div>${s.state !== "まだ" ? `<span class="tag ${esc(s.state)}">${esc(s.state === "使い直し" ? "済み" : s.state)}</span>${s.orders.length || s.refs?.length ? '<span class="tog">›</span>' : ""}` : ""}</div>`;
  }
  if (n.type === "rp" || n.type === "nx") {
    const r = n.r, 状 = { running: "作業中", needs_human: "本人待ち", fail_1: "やり直し", passed: "通った", delivered: "済み", new: "候補" }[r.status] || r.status;
    const dots = (r.steps || []).map((x) => `<i class="gs ${x.ok ? "ok" : x.ok === null ? "na" : "no"}" title="${esc(x.name)}${x.ok ? "：済み" : x.ok === null ? "：まだ見ていない" : "：まだ"}"></i>`).join("");
    return `<div class="fn rp${n.type === "nx" ? " nx" : ""}${sel}" data-n="${n.id}" style="${st}"><div class="tx"><small>${esc(r.ext)} ・ 星${(r.score || 0) >= 91 ? 5 : 4} ・ ${esc(r.days)}日勝ち</small><b>${esc(String(r.label || "").replace(/^"|"$/g, ""))}</b>${dots ? `<span class="gsteps">${dots}</span>` : ""}</div><span class="tag ${esc(状)}">${esc(状)}</span></div>`;
  }
  if (n.type === "od") {
    const o = n.o;
    return `<div class="fn od${sel}" data-n="${n.id}" style="${st}"><div class="tx"><small>${esc(o.by)} → ${esc(o.lead)} ・ ${t2(o.ts)}</small><b>${esc(一行目(o.ask))}</b></div><span class="tag ${esc(o.status)}">${esc(状態の名[o.status] || o.status)}</span></div>`;
  }
  const w = n.wk, ed = w.role === "編集長";
  const v = w.verdicts.at(-1)?.v;
  const tag = v ? `<span class="tag ${v}">${v}</span>` : w.status !== "success" ? `<span class="tag ${esc(w.status)}">${esc(状態の名[w.status] || w.status)}</span>` : w.reviewed ? `<span class="tag ${w.reviewed}" title="編集長の判定">${w.reviewed}</span>` : "";
  const sub = [w.acts.length ? `作業 ${w.acts.length}` : "", w.artifacts.length ? `成果物 ${w.artifacts.length}` : "", t2(w.ts)].filter(Boolean).join(" ・ ");
  return `<div class="fn wk${ed ? " ed" : ""}${sel}" data-n="${n.id}" style="${st}"><span class="dia" style="--c:${esc(col(w.role))}"></span><div class="tx"><b>${esc(ed ? "編集長の審査" : w.role)}</b><small>${esc(sub)}</small></div>${tag}</div>`;
}
function draw() {
  const 広告 = F.screen === "ads";
  const all = 広告 ? buildAds() : build(F.tree); F.nodes = new Map(all.map((n) => [n.id, n]));
  $("fl-nodes").innerHTML = all.map(広告 ? adNodeHTML : nodeHTML).join("");
  const paths = [];
  for (const p of all) for (const k of p.kids) {
    const x1 = p.x + p.w, y1 = p.y + p.h / 2, x2 = k.x, y2 = k.y + k.h / 2, dx = (x2 - x1) * 0.5;
    paths.push(`<path class="${!広告 && live(k) ? "live" : ""}" d="M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}"/>`);
  }
  const H = Math.max(...all.map((n) => n.y + n.h)) + 40, W = Math.max(...all.map((n) => n.x + n.w)) + 20;
  const svg = $("fl-edges"); svg.setAttribute("width", W); svg.setAttribute("height", H); svg.innerHTML = paths.join("");
  F.bounds = { w: W, h: H };
  apply();
}

// ── 動かす（ドラッグ・ホイール・つまむ） ──
function apply() { const v = F.view; $("fl-world").style.transform = `translate(${v.x}px,${v.y}px) scale(${v.k})`; $("fl-vp").style.backgroundPosition = `${v.x}px ${v.y}px`; $("fl-vp").style.backgroundSize = `${24 * v.k}px ${24 * v.k}px`; $("fl-pct").textContent = Math.round(v.k * 100) + "%"; }
function zoomAt(k, cx, cy) { const v = F.view; k = Math.min(2, Math.max(0.2, k)); v.x = cx - (cx - v.x) * (k / v.k); v.y = cy - (cy - v.y) * (k / v.k); v.k = k; apply(); }
// 全体の幅が入る大きさ（読める大きさより小さくしない）で、開いている工程を画面の真ん中に
function fit() {
  const vp = $("fl-vp").getBoundingClientRect(); if (!F.bounds || !vp.width) return;
  const pad = 40, k = Math.min(1, Math.max(0.62, (vp.width - pad * 2) / F.bounds.w));
  const open = [...F.nodes.values()].find((n) => (n.type === "st" || n.type === "cp") && n.open);
  const cy = open ? open.y + open.h / 2 : F.bounds.h / 2;
  F.view = { k, x: Math.max(pad, (vp.width - F.bounds.w * k) / 2), y: F.bounds.h * k < vp.height - 110 ? 70 + (vp.height - 110 - F.bounds.h * k) / 2 : vp.height / 2 + 20 - cy * k }; apply();
}
function focusOn(id) { const n = F.nodes.get(id), r = $("fl-vp").getBoundingClientRect(); if (!n) return; F.view.y = r.height / 2 + 20 - (n.y + n.h / 2) * F.view.k; apply(); }
const vp = $("fl-vp"); let drag = null;
let nd = null, 次の絵 = 0;
vp.addEventListener("pointerdown", (e) => {
  const el = e.target.closest(".fn");
  if (el) { const id = el.dataset.n, o = 位置()[id] || { dx: 0, dy: 0 }; nd = { id, x: e.clientX, y: e.clientY, dx: o.dx, dy: o.dy, moved: false, pid: e.pointerId }; return; } // つかむのは動き出してから（先につかむと押した節にクリックが届かない）
  drag = { x: e.clientX, y: e.clientY, vx: F.view.x, vy: F.view.y }; vp.setPointerCapture(e.pointerId); vp.classList.add("drag"); });
vp.addEventListener("pointermove", (e) => {
  if (nd) {
    const mx = e.clientX - nd.x, my = e.clientY - nd.y;
    if (!nd.moved && Math.hypot(mx, my) < 4) return;
    if (!nd.moved) { try { vp.setPointerCapture(nd.pid); } catch {} }
    nd.moved = true; vp.classList.add("moving");
    位置()[nd.id] = { dx: nd.dx + mx / F.view.k, dy: nd.dy + my / F.view.k };
    if (!次の絵) 次の絵 = requestAnimationFrame(() => { 次の絵 = 0; draw(); });
    return;
  }
  if (!drag) return; F.view.x = drag.vx + e.clientX - drag.x; F.view.y = drag.vy + e.clientY - drag.y; apply(); });
vp.addEventListener("pointerup", () => { if (nd?.moved) { 位置を残す(); F.dragged = true; setTimeout(() => (F.dragged = false), 0); } nd = null; drag = null; vp.classList.remove("drag", "moving"); });
vp.addEventListener("wheel", (e) => { e.preventDefault(); const r = vp.getBoundingClientRect(); if (e.ctrlKey || e.metaKey) zoomAt(F.view.k * Math.exp(-e.deltaY * 0.01), e.clientX - r.left, e.clientY - r.top); else { F.view.x -= e.deltaX; F.view.y -= e.deltaY; apply(); } }, { passive: false });
const center = () => { const r = vp.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };

// ── 中身（どう作ったか） ──
function list(items) { return items.length ? `<ol>${items.map((a) => `<li>${esc(a.replace(/^コマンド:\s*/, ""))}</li>`).join("")}</ol>` : `<div class="txt" style="color:var(--sub)">記録なし</div>`; }
function long(title, s) { if (!s) return ""; const big = s.length > 360; return `<h4>${title}</h4><div class="txt${big ? " clamp" : ""}">${esc(s)}</div>${big ? `<button class="more" data-more>全部見る</button>` : ""}`; }
function files(paths) { return paths.length ? `<h4>作った物（${paths.length}）</h4>` + paths.map((p) => { const i = p.lastIndexOf("/"); return `<button class="glass fl-file" data-copy="${esc(p)}" title="押すとパスを写す">${esc(p.slice(i + 1))}<small>${esc(p.slice(0, i).replace(/^\/Users\/[^/]+/, "~"))}</small></button>`; }).join("") : ""; }
function showPane(id, quiet) {
  $("fl-pane").classList.remove("full"); F.stack = [];
  const n = F.nodes?.get(id); const pane = $("fl-pane");
  if (!n) { pane.hidden = true; return; }
  if (n.type === "rt") return paneRoot();
  if (n.type === "st") return paneStage(n.s, quiet);
  if (n.type === "rp" || n.type === "nx") return paneRef(n.r, n.type === "nx");
  let head, body;
  if (n.type === "od") {
    const o = n.o;
    head = `<span class="dia" style="--c:${esc(col(o.lead))};width:14px;height:14px;border-radius:3px;transform:rotate(45deg);background:var(--c)"></span><div class="tx"><b>${esc(o.lead)}への発注</b><small>${esc(o.by)}から ・ ${t2(o.ts)}${o.end ? ` 〜 ${t2(o.end)}` : ""}</small></div><span class="tag ${esc(o.status)}">${esc(状態の名[o.status] || o.status)}</span>`;
    body = long("頼まれた事", o.ask)
      + `<h4>振った順（${o.works.length}）</h4>${o.works.length ? `<ol>${o.works.map((w) => `<li>${esc(w.role)}${w.verdicts.at(-1) ? ` ・ ${w.verdicts.at(-1).v}` : ""}</li>`).join("")}</ol>` : list([])}`
      + (o.acts.length ? `<h4>${esc(o.lead)}がやった事（${o.acts.length}）</h4>${list(o.acts)}` : "")
      + files(o.artifacts) + long("返事", o.output) + (o.handoff ? `<h4>次に渡した先</h4><div class="txt">${esc(o.handoff)}</div>` : "") + (o.stopped ? long("自動の振り分け", o.stopped) : "");
  } else {
    const w = n.wk;
    head = `<span class="dia" style="--c:${esc(col(w.role))};width:14px;height:14px;border-radius:3px;transform:rotate(45deg);background:var(--c)"></span><div class="tx"><b>${esc(w.role)}</b><small>${esc(w.from)}から ・ ${t2(w.ts)}${w.end ? ` 〜 ${t2(w.end)}` : ""}</small></div><span class="tag ${esc(w.status)}">${esc(状態の名[w.status] || w.status)}</span>`;
    body = long("頼まれた事", w.ask)
      + `<h4>やった事（${w.acts.length}）</h4>${list(w.acts)}`
      + files(w.artifacts)
      + (w.verdicts.length ? `<h4>編集長の判定</h4>` + w.verdicts.map((v) => `<div class="fl-verdict"><span class="tag ${v.v}">${v.v}</span>${esc(v.text)}</div>`).join("") : "")
      + long("返事", w.output);
  }
  pane.innerHTML = `<header>${head}<button class="glass x" data-close title="閉じる"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></header><div class="body">${body}</div>`;
  if (!quiet) pane.querySelector(".body").scrollTop = 0;
  pane.hidden = false;
  if (!quiet) { const r = $("fl-vp").getBoundingClientRect(), room = r.width - pane.offsetWidth - 36, right = F.view.x + (n.x + n.w) * F.view.k; if (room > 300 && right > room) { F.view.x -= right - room; apply(); } }
}
// 4 広告を作るの1本: 工程のどこまで進んだか・動画・作る/やり直すボタン
function paneRef(r, 候補) {
  // 左に参考・右にうちの動画、その下に台本を左（原文）・右（日本語）で秒ごとに並べる（2026-10-08 本人「参考動画を左に。左右でスクリプト」）
  const 声の版 = r.out ? String(r.out).replace(/_日本語字幕\.mp4$/, "_日本語.mp4") : null;
  const v = (p, id) => p ? `<video id="${id}" class="gvid" controls preload="metadata" src="/api/video?p=${encodeURIComponent(p)}"></video>` : `<div class="gnone">${id === "g-ours" ? "まだ作っていない" : "原本が無い"}</div>`;
  const 秒 = (x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
  const 台本 = (r.script || []).map((x) => `<tr data-seek="${x.s}"><td class="gt">${秒(x.s)}</td><td>${esc(x.en)}</td><td>${esc(x.ja)}</td></tr>`).join("");
  const steps = (r.steps || []).map((x) => `<li class="${x.ok ? "ok" : x.ok === null ? "na" : "no"}">${esc(x.name)}<small>${x.ok ? "済み" : x.ok === null ? "まだ見ていない" : "まだ"}</small></li>`).join("");
  const head = `<div class="tx"><b>${esc(String(r.label || "").replace(/^"|"$/g, ""))}</b><small>参考 ${esc(r.ext)} ・ 星${(r.score || 0) >= 91 ? 5 : 4} ・ ${esc(r.days)}日勝ち${r.job ? ` ・ ${esc(r.job)}` : ""}</small></div>`;
  const body = `<div class="glr"><div><h4>参考（英語）</h4>${v(r.ref, "g-ref")}</div><div><h4>うち（日本語の声）</h4>${v(声の版, "g-ours")}</div></div>`
    + (台本 ? `<h4>台本（行を押すと両方の動画がその秒へ飛ぶ）</h4><table class="gscript"><thead><tr><th></th><th>参考の原文</th><th>うちの日本語</th></tr></thead><tbody>${台本}</tbody></table>` : "")
    + (候補 ? "" : `<h4>工程</h4><ol class="gflow">${steps}</ol>`)
    + (r.last_reason && r.status !== "delivered" ? `<h4>落ちた理由</h4><div class="txt">${esc(r.last_reason)}</div>` : "")
    + (r.ret ? `<h4>門の結果</h4><div class="txt">機械: ${esc(r.ret.gate?.machine || "")} ・ 別の目: ${esc(r.ret.gate?.fresh || "")}${r.ret.gate?.reason ? `<br>${esc(r.ret.gate.reason)}` : ""}${r.ret.total_secs ? `<br>かかった時間: ${Math.round(r.ret.total_secs / 60)}分` : ""}</div>` : "")
    + `<h4>${候補 ? "作る" : "やり直す"}</h4><textarea id="g-why" rows="2" placeholder="ひとこと（なくてもいい）。例: 32秒の字幕をもっと短く"></textarea><button class="glass fs-go" data-grun="${esc(r.ext)}">${候補 ? "この参考で作る" : "この1本をやり直す"}</button><div id="g-msg" class="txt"></div>`;
  F.stack = []; 全画面(head, body);
}
// 工程の1枚: 何を作る工程か → 結論 → 数字 → やった流れ（誰が・編集長の判定）→ 作った物
function paneStage(s, quiet) {
  const pane = $("fl-pane"), [担当, 作る物] = 工程の説明[s.n] || ["", ""];
  const works = s.orders.flatMap((o) => o.works), 始 = Math.min(...s.orders.map((o) => o.ts)), 終 = Math.max(...s.orders.map((o) => o.end || o.ts), ...works.map((w) => w.end || w.ts));
  const 最後 = [...s.orders].reverse().find((o) => o.output);
  const files = [...new Set([...s.orders.flatMap((o) => o.artifacts), ...works.flatMap((w) => w.artifacts)])];
  const 判定の札 = (v) => `<span class="fs-v ${v}">${v === "PASS" ? "通した" : "差し戻し"}</span>`;
  const 人の札 = (w, o) => w.role === "編集長"
    ? `<button class="fs-step ed" data-pick="s${s.n}-${w.id}" title="${esc(一行目(w.ask))}"><span class="fs-dot" style="--c:${esc(col("編集長"))}"></span>審査${w.verdicts.at(-1) ? 判定の札(w.verdicts.at(-1).v) : ""}</button>`
    : `<button class="fs-step" data-pick="s${s.n}-${w.id}" title="${esc(一行目(w.ask))}"><span class="fs-dot" style="--c:${esc(col(w.role))}"></span>${esc(w.role)}<small>${w.acts.length ? `作業${w.acts.length}` : ""}${w.artifacts.length ? ` ・ 成果物${w.artifacts.length}` : ""}</small></button>`;
  const 流れ = s.orders.map((o) => `<li class="fs-order"><button class="fs-head" data-pick="s${s.n}-${o.id}"><span class="fs-who">${esc(o.by)} → ${esc(o.lead)}</span><span class="fs-when"><span class="tag ${esc(o.status)}">${esc(状態の名[o.status] || o.status)}</span>${t2(o.ts)}</span><b>${esc(一行目(o.ask))}</b></button>`
    + (o.works.length ? `<div class="fs-chain">${o.works.map((w) => 人の札(w, o)).join('<span class="fs-arrow" aria-hidden="true">→</span>')}</div>` : `<div class="fs-chain"><span class="fs-none">${o.status === "作業中" ? "部長が振る前" : "メンバーに振らずに返した"}</span></div>`)
    + `</li>`).join("");
  const 元へ = s.from && s.from.kind !== "vault" ? `<button class="glass fs-go" data-go-node='${esc(JSON.stringify({ brand: s.from.brand, job_id: s.from.job_id, revision: s.from.revision, node: "s" + s.n }))}'>元を見る</button>` : "";
  const 使い直し = s.state === "使い直し" ? `<div class="fs-reuse">この案件では作り直さず、${s.from?.kind === "vault" ? `Obsidian に前からある物（<code>${esc(s.from.path)}</code>）を使う。` : `${esc(元の一言(s.from))}。`}${元へ}</div>` : "";
  pane.innerHTML = `<header><span class="num fs-num">${s.n}</span><div class="tx"><b>${esc(s.name)}</b><small>${s.orders.length ? `${t2(始)} 〜 ${t2(終)} ・ ${長さ(終 - 始)}` : s.state === "使い直し" ? 元の一言(s.from) : "まだ"}</small></div><span class="tag ${esc(s.state)}">${esc(s.state === "使い直し" ? "済み" : s.state)}</span><button class="glass x" data-close title="閉じる"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></header><div class="body">`
    + `<div class="fs-what"><div><small>作る物</small><b>${esc(作る物)}</b></div><div><small>担当</small><span>${esc(担当)}</span></div></div>`
    + 使い直し
    + (s.state === "本人待ち" && F.tree.waiting ? `<div class="fs-ask"><small>あなたに聞いていること</small>${esc(F.tree.waiting.ask.split(" / ").pop())}</div>` : "")
    + (最後 ? `<h4>結論（${esc(最後.lead)}の最後の返事）</h4><div class="fs-concl txt${頭の数行(最後.output).length > 160 ? " clamp" : ""}">${esc(頭の数行(最後.output))}</div>${頭の数行(最後.output).length > 160 ? `<button class="more" data-more>全部見る</button>` : ""}` : "")
    + (s.orders.length ? `<div class="fs-stats"><div><b>${s.counts.orders}</b><small>発注</small></div><div><b>${works.filter((w) => w.role !== "編集長").length}</b><small>仕事</small></div><div class="ok"><b>${s.counts.pass}</b><small>通した</small></div><div class="fix"><b>${s.counts.fix}</b><small>差し戻し</small></div></div>` : "")
    + (s.orders.length ? `<h4>やった流れ</h4><ol class="fs-flow">${流れ}</ol>` : "")
    + (files.length ? files.length && `<h4>作った物（${files.length}）</h4>` + files.map((p) => { const i = p.lastIndexOf("/"); return `<button class="glass fl-file" data-copy="${esc(p)}" title="押すとパスを写す">${esc(p.slice(i + 1))}<small>${esc(p.slice(0, i).replace(/^\/Users\/[^/]+/, "~"))}</small></button>`; }).join("") : "")
    + `</div>`;
  if (!quiet) pane.querySelector(".body").scrollTop = 0;
  pane.hidden = false;
}
function paneRoot() {
  const t = F.tree, a = t.autopilot, pane = $("fl-pane");
  pane.innerHTML = `<header><div class="tx"><b>${esc(案件名(F.job))}</b><small>${esc(ブランド名(t.brand))}${t.revision > 1 ? ` ・ ${t.revision}回目` : ""}</small></div><button class="glass x" data-close title="閉じる"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></header><div class="body">`
    + (t.waiting ? long("あなたの判断待ち", t.waiting.ask) : "")
    + (a ? long("ゴール", a.goal) + `<h4>自動の振り分け</h4><div class="txt">${a.on ? "進行中" : "止まっている"} ・ ${a.hops}回渡した${a.stopped?.reason ? `\n${esc(a.stopped.reason)}` : ""}</div>` : `<h4>自動の振り分け</h4><div class="txt">使っていない（手で発注）</div>`)
    + `<h4>工程</h4><ol>${t.stages.filter((s) => s.state !== "まだ").map((s) => `<li>${s.n} ${esc(s.name)} ・ ${esc(s.state)}</li>`).join("")}</ol></div>`;
  pane.hidden = false;
}

// ── チーム（全員の今） ──
F.mode = "flow"; F.team = null; F.teamRaw = ""; F.person = null;
async function setMode(m) {
  F.mode = m; $("fl-pane").hidden = true; F.sel = null; F.person = null;
  if (m === "team") history.replaceState(null, "", "#team"); else setHash();
  document.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-selected", x.dataset.mode === m));
  const team = m === "team";
  $("fl-side-flow").hidden = team; $("fl-side-team").hidden = !team; $("fl-team").hidden = !team;
  for (const id of ["fl-vp", "fl-top"]) $(id).hidden = team; document.querySelector(".fl-tools").hidden = team;
  if (team) { F.teamRaw = ""; await loadTeam(); } else { await refresh(); }
}
async function loadTeam() {
  if (!SRC.team) return;
  let t; try { t = await SRC.team(); } catch { return; }
  const raw = JSON.stringify({ ...t, at: 0 }); if (raw === F.teamRaw) return;
  F.teamRaw = raw; F.team = t; drawTeam(); if (F.person) showPerson(F.person, true);
}
// 選んでいるブランドだけの数字（全ブランドなら合計）
function 数字(p) {
  if (!F.teamBrand) return { busy: p.busy, stale: p.stale, now: p.now, job: p.job, last: p.last, today: p.today.works, pass: p.today.pass, fix: p.today.fix, recent: p.recent, 期間: false };
  const b = p.byBrand?.[F.teamBrand];
  if (!b) return { busy: false, now: "", last: 0, today: 0, pass: 0, fix: 0, recent: [], none: true };
  return { busy: b.busy && p.busy, stale: p.stale, now: b.now || p.now, job: b.recent.find((r) => r.status === "作業中")?.job || null, last: b.last, today: b.today, pass: b.pass, fix: b.fix, works: b.works, orders: b.orders, recent: b.recent, 期間: true };
}
const 色の顔 = (r, s = 34) => `<span class="fl-ava" style="--c:${esc(col(r))};--s:${s}px" aria-hidden="true"><i></i></span>`;
function 人の札(r, lead) {
  const p0 = F.team.people[r]; if (!p0) return "";
  const p = 数字(p0);
  const st = p.none ? "動いていない" : p.busy ? (p.stale ? "止まっているかも" : "作業中") : "待機中";
  const sub = p.none ? `このブランドでは${F.team.days}日動いていない` : p.busy ? `${p.job ? esc(p.job.name || p.job.job_id) + " ・ " : ""}${esc(p.now || "")}` : p.last ? `${t2(p.last)} に終わった` : "まだ仕事なし";
  const 数 = p.期間 && p.orders && !p.works ? `${F.team.days}日で 発注 ${p.orders}件を受けて振った` : p.期間 ? `${F.team.days}日で ${p.works}件${p.pass || p.fix ? ` ・ PASS ${p.pass} ・ FIX ${p.fix}` : ""}${p.today ? ` ・ 今日 ${p.today}` : ""}` : p.today ? `今日 ${p.today}件${p.pass || p.fix ? ` ・ PASS ${p.pass} ・ FIX ${p.fix}` : ""}` : "今日はまだ";
  return `<button class="glass fl-person${lead ? " lead" : ""}${p.busy ? " busy" : ""}${p.busy && p.stale ? " stale" : ""}${p.none ? " none" : ""}" data-person="${esc(r)}" aria-current="${F.person === r}">${色の顔(r, lead ? 40 : 32)}<span class="tx"><b>${esc(r)}</b><small class="now">${sub}</small><small>${数}</small></span><span class="tag ${p.busy ? (p.stale ? "差し戻し" : "作業中") : "済み"}">${st}</span></button>`;
}
function drawTeam() {
  const t = F.team; if (!t) return;
  if (F.teamBrand === undefined) F.teamBrand = F.brand || null;
  if (F.teamBrand && !t.brands.includes(F.teamBrand)) F.teamBrand = null;
  const ps = Object.values(t.people).map(数字), busy = ps.filter((p) => p.busy && !p.stale).length, today = ps.reduce((a, p) => a + p.today, 0), 動いた = ps.filter((p) => !p.none).length;
  $("fl-tbrands").innerHTML = [null, ...t.brands].map((b) => `<button class="glass fl-brand" data-tb="${esc(b || "")}" aria-current="${(F.teamBrand || null) === b}">${esc(b ? ブランド名(b) : "全ブランド")}<small>${b ? `${Object.values(t.people).filter((p) => p.byBrand?.[b]).length}人が動いた` : "合計"}</small></button>`).join("");
  const 部 = [...(t.hq ? [{ id: "hq", name: t.hq.name, lead: t.hq.lead, members: t.hq.members }] : []), ...t.部];
  $("fl-depts").innerHTML = 部.map((d) => `<button class="fl-job" data-dept="${esc(d.id)}"><span class="nm">${esc(d.name)}</span><small>${[d.lead, ...d.members].filter((r) => t.people[r]?.busy).length ? '<i class="on"></i>作業中あり' : "待機"} ・ ${d.members.length + 1}人</small></button>`).join("") + `<button class="fl-job" data-dept="qa"><span class="nm">品質（全部の部の審査）</span><small>${t.people["編集長"]?.busy ? '<i class="on"></i>作業中' : "待機"} ・ 1人</small></button>`;
  $("fl-team").innerHTML = `<header class="fl-team-head"><h2>${esc(F.teamBrand ? ブランド名(F.teamBrand) : "チーム")}</h2><p>${F.teamBrand ? `${t.days}日で <b>${動いた}</b>人が動いた ・ ` : ""}<b>${busy}</b>人が作業中 ・ 今日の仕事 <b>${today}</b>件 ・ ${t2(t.at)} 時点</p></header>
    <div class="fl-org">${部.map((d) => `<section class="fl-dept" id="dept-${esc(d.id)}"><h3>${esc(d.name)}</h3>${人の札(d.lead, true)}<div class="fl-members">${d.members.map((r) => 人の札(r)).join("")}</div></section>`).join("")}
    <section class="fl-dept qa" id="dept-qa"><h3>品質と仕組み</h3><p class="fl-note">全部の部の成果物を、次へ渡す前に審査する</p>${人の札("編集長", true)}</section></div>`;
}
function showPerson(r, quiet) {
  const p0 = F.team?.people[r], pane = $("fl-pane"); if (!p0) return;
  const p = 数字(p0);
  const 札 = (w) => `<button class="glass fl-file fl-work" data-go-node='${esc(JSON.stringify({ brand: w.job.brand, job_id: w.job.job_id, revision: w.job.revision, node: w.node }))}'><span class="row"><b>${esc(w.what || "（文なし）")}</b>${w.verdict ? `<span class="tag ${w.verdict}">${w.verdict}</span>` : w.status !== "success" ? `<span class="tag ${esc(w.status)}">${esc(状態の名[w.status] || w.status)}</span>` : ""}</span><small>工程${w.stage} ・ ${t2(w.ts)}${w.acts ? ` ・ 作業 ${w.acts}` : ""}${w.artifacts ? ` ・ 成果物 ${w.artifacts}` : ""}${w.lead ? ` ・ ${w.works}人に振った` : ""}</small></button>`;
  // 全ブランドならブランドごと、ブランドを選んでいれば案件ごとにまとめる
  const 束 = new Map();
  for (const w of p.recent) { const k = F.teamBrand ? `${w.job.name || w.job.job_id}${w.job.revision > 1 ? `（${w.job.revision}回目）` : ""}` : ブランド名(w.job.brand); if (!束.has(k)) 束.set(k, []); 束.get(k).push(w); }
  const 状態 = p.none ? "動いていない" : p.busy ? (p.stale ? "止まっているかも" : "作業中") : "待機中";
  pane.innerHTML = `<header>${色の顔(r, 30)}<div class="tx"><b>${esc(r)}</b><small>${esc(p0.部 || "")} ・ ${esc(F.teamBrand || "全ブランド")}${p.last ? ` ・ 最後の動き ${t2(p.last)}` : ""}</small></div><span class="tag ${p.none ? "済み" : p.busy ? (p.stale ? "差し戻し" : "作業中") : "済み"}">${状態}</span><button class="glass x" data-close title="閉じる"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></header><div class="body">`
    + (p.busy ? `<h4>今やっていること</h4><div class="txt">${p.job ? `${esc(ブランド名(p.job.brand))} / ${esc(p.job.name || p.job.job_id)}\n` : ""}${esc(p.now || "")}</div>` : "")
    + (!F.teamBrand && Object.keys(p0.byBrand || {}).length ? `<h4>ブランドごと（${F.team.days}日）</h4><div class="fl-split">${Object.entries(p0.byBrand).map(([b, x]) => `<button class="glass fl-brand" data-tb="${esc(b)}">${esc(b)}<small>${x.works}件${x.pass || x.fix ? ` ・ PASS ${x.pass} ・ FIX ${x.fix}` : ""}${x.busy ? " ・ 作業中" : ""}</small></button>`).join("")}</div>` : "")
    + (p.recent.length ? [...束].map(([k, ws]) => `<h4>${esc(k)}（${ws.length}）</h4>` + ws.map(札).join("")).join("") : `<h4>やった事</h4><div class="txt" style="color:var(--sub)">${F.teamBrand ? `${esc(F.teamBrand)}では${F.team.days}日動いていない` : `${F.team.days}日の仕事なし`}</div>`)
    + `</div>`;
  if (!quiet) pane.querySelector(".body").scrollTop = 0;
  pane.hidden = false;
}
async function jumpTo(x) {
  await setMode("flow");
  F.pendingSel = x.node; F.brand = x.brand; F.job = { job_id: x.job_id, revision: x.revision };
  await loadBrands(x.brand); await pickBrand(x.brand, true);
}

// ── 押した時 ──
document.addEventListener("click", async (e) => {
  const rf = e.target.closest("#r-flow"); if (rf) { e.stopPropagation(); return $("flow").hidden ? openFlow(location.hash.slice(1)) : closeFlow(); }
  if (e.target.closest("#r-home") && !$("flow").hidden) return closeFlow();
  if ($("flow").hidden || !e.target.closest("#flow")) return;
  const b = e.target.closest("[data-fb],[data-fj],[data-close],[data-copy],[data-more],#fl-fit,#fl-in,#fl-out,#fl-reset");
  if (b?.dataset.fb) return pickBrand(b.dataset.fb);
  const fl = e.target.closest("[data-fl]"); if (fl && F.screen === "ads") { F.lineSel[F.brand] = fl.dataset.fl; F.adOpen.clear(); return openAds(); }
  if (fl) { F.lineSel[F.brand] = fl.dataset.fl; const 見せる = 見える案件(); drawSide(); if (見せる.length) return pickJob(見せる[0]); F.job = null; F.tree = null; drawTop(); setHash(); $("fl-pane").hidden = true; return empty("このラインにはまだ案件がない。案件ができると、ここに出る"); }
  if (b?.dataset.fj) return pickJob(F.jobs.find((j) => keyOf(j) === b.dataset.fj));
  if (b?.dataset.close !== undefined && b?.hasAttribute("data-close")) { F.sel = null; F.person = null; $("fl-pane").hidden = true; return F.mode === "team" ? drawTeam() : draw(); }
  if (b?.dataset.copy) { try { await navigator.clipboard.writeText(b.dataset.copy); b.querySelector("small").textContent = "パスを写した"; } catch {} return; }
  if (b?.hasAttribute("data-more")) { b.previousElementSibling.classList.remove("clamp"); b.remove(); return; }
  if (b?.id === "fl-fit") return fit();
  if (b?.id === "fl-in" || b?.id === "fl-out") return zoomAt(F.view.k * (b.id === "fl-in" ? 1.2 : 1 / 1.2), ...center());
  if (b?.id === "fl-reset") { F.pos = {}; 位置を残す(); draw(); return fit(); }
  const md = e.target.closest("[data-mode]"); if (md) return setMode(md.dataset.mode);
  const tb = e.target.closest("[data-tb]"); if (tb) { F.teamBrand = tb.dataset.tb || null; if (F.teamBrand) F.brand = F.teamBrand; drawTeam(); return F.person && showPerson(F.person); }
  const pm = e.target.closest("[data-person]"); if (pm) { F.person = pm.dataset.person; drawTeam(); return showPerson(F.person); }
  const pk = e.target.closest("[data-pick]"); if (pk) { F.sel = pk.dataset.pick; draw(); showPane(F.sel); setHash(); return focusOn(F.sel); }
  const go = e.target.closest("[data-go-node]"); if (go) return jumpTo(JSON.parse(go.dataset.goNode));
  const dp = e.target.closest("[data-dept]"); if (dp) { document.getElementById("dept-" + dp.dataset.dept)?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  if (e.target.closest("a[href]")) return; // カードの中のリンクはそのまま開く
  if (e.target.closest("[data-back]")) return 戻る();
  const sk = e.target.closest("[data-seek]"); if (sk) { const t = +sk.dataset.seek; for (const id of ["g-ref", "g-ours"]) { const el = $(id); if (el) { el.currentTime = t; el.play?.().catch(() => {}); } } return; }
  const gr = e.target.closest("[data-grun]"); if (gr) { gr.disabled = true; const st = await (await fetch("/api/state")).json(); const r = await (await fetch("/api/graph/run", { method: "POST", headers: { "x-team-token": st.csrf_token }, body: JSON.stringify({ ext: gr.dataset.grun, why: $("g-why")?.value || "" }) })).json(); $("g-msg").textContent = r.ok ? "始めた。終わると工程の印が進む（6秒ごとに読み直す）" : (r.error || "始められなかった"); return; }
  const tile = e.target.closest("[data-adtile]"); if (tile) { const d = 広告を探す(tile.dataset.adtile); if (d) return adPane({ type: "ad", d, id: "a" + d.id }); }
  const mr = e.target.closest("[data-mkjob]"); if (mr) { const m = F.making.find((x) => keyOf(x.job) === mr.dataset.mkjob); if (m) return 待ち(m) ? askPane(m) : (F.stack = [], $("fl-pane").hidden = true, pickJob(F.jobs.find((x) => keyOf(x) === mr.dataset.mkjob))); }
  if (e.target.closest("[data-ads]")) return openAds();
  const op = e.target.closest(".ask-opt"); if (op) { const row = op.closest(".ask-row"); if (!row.classList.contains("multi")) row.querySelectorAll(".ask-opt").forEach((x) => x.setAttribute("aria-pressed", "false")); op.setAttribute("aria-pressed", op.getAttribute("aria-pressed") === "true" && row.classList.contains("multi") ? "false" : "true"); return; }
  const stp = e.target.closest(".ask-step"); if (stp) { const el = $("ask-n"); el.textContent = Math.max(1, Math.min(20, Number(el.textContent) + Number(stp.dataset.step))); return; }
  const ar = e.target.closest(".ask-ref"); if (ar) { ar.setAttribute("aria-pressed", ar.getAttribute("aria-pressed") === "true" ? "false" : "true"); return; }
  if (e.target.closest("#ask-go")) return askSend();
  const n = e.target.closest(".fn"); if (!n || F.dragged) return;
  const id = n.dataset.n, node = F.nodes.get(id);
  if (F.screen === "ads") {
    const 右端 = (() => { const r = n.getBoundingClientRect(); return e.clientX > r.right - Math.max(48, 44 * (r.width / n.offsetWidth)); })();
    if (node?.type === "cp" && !e.target.closest(".tog") && !右端) { F.sel = id; F.stack = []; draw(); return adPane(node); }
    if (["art", "mk", "as"].includes(node?.type)) { F.sel = id; F.stack = []; draw(); return adPane(node); }
    if (node?.type === "cp") { const 開 = new Set([...F.nodes.values()].filter((x) => x.type === "cp" && x.open).map((x) => x.id)); 開.has(id) ? 開.delete(id) : 開.add(id); F.adOpen = 開.size ? 開 : new Set(["__none__"]); draw(); return focusOn(id); }
    if (node?.type === "jb") { F.sel = id; F.stack = []; draw(); return paneRef(node.m.r, node.m.候補); }
    if (["ad", "pg", "ask"].includes(node?.type)) { F.sel = id; F.stack = []; draw(); return adPane(node); }
    return;
  }
  if (node?.type === "st") {
    const 畳む = !!e.target.closest(".tog") || (() => { const r = n.getBoundingClientRect(); return e.clientX > r.right - Math.max(48, 44 * (r.width / n.offsetWidth)); })();
    if ((node.s.orders.length || node.s.refs?.length) && (畳む || !node.open)) { if (node.open) { F.open.clear(); F.shut.add(id); } else { F.open.clear(); F.shut.delete(id); F.open.add(id); } }
    F.sel = 畳む ? F.sel : id; draw(); if (!畳む) { showPane(id); setHash(); } return focusOn(id);
  }
  F.sel = id; draw(); showPane(id); setHash();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && F.stack.length && !$("fl-pane").hidden) return 戻る(); if (e.key === "Escape" && !$("flow").hidden && !$("fl-pane").hidden) { F.sel = null; $("fl-pane").hidden = true; draw(); } });
window.addEventListener("resize", () => { if (!$("flow").hidden && !F.sel) fit(); });
const 最初 = location.hash;
if (SRC.autoOpen) openFlow(最初.startsWith("#flow") ? 最初.slice(1) : "").then(() => 最初 === "#team" && setMode("team")); else if (location.hash.startsWith("#flow")) openFlow(location.hash.slice(1));
window.FLOW_REFRESH = async () => {
  if ($("flow").hidden) return;
  if (!F.brand || !F.job) { await loadBrands(F.brand); return pickBrand(F.brand, !!F.job); }
  await loadBrands(F.brand); F.jobs = await SRC.jobs(F.brand); drawTop(); await refresh();
};
})();
