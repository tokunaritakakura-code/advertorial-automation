// 審査の収束（2026-10-07 本人の承認。_変更待ち_頭の分け方と審査の収束_2026-10-07.md の3）
// 編集長が書き出したずれを、判断の層（JEV）が1つずつ3択に分け、コードが PASS / FAIL を決める。
// JEV が使えない・自信が低い・決められない時は「決定を変える」に倒す（戻すのが安全な側）。
import path from "node:path";
import os from "node:os";
import { pathToFileURL } from "node:url";

export const 種類 = Object.freeze({
  決定を変える: "直さないと成果物の結論・約束・順位・事実が変わる。作り話のまま、他社のロゴや商品名が残る（トライアルの店のレビューの表示は競合のコピーでよい）、件数で順位が変わる、約束と中身がずれる、本人の直しの台帳の行に反する、参考との差の検査が0でない、のどれか",
  書き方: "直しても結論は変わらない表記のずれ。印、版の番号、言い回し、ファイル同士の写し違い、体裁",
  本人の決まりに反する: "本人が指摘しないと決めた指摘。薬機法や景表法の指摘、店の評価や名前つきの声を疑う指摘、うちのブランドの物語への置き換えを作り話とする指摘、トライアルの店で競合のレビューの表示をコピーした事への指摘",
  other: "上のどれか決められない",
});
export const 自信の線 = 0.85;
const 本体の上限 = 12000;

// 純粋な部分: ラベルからの振り分け
export function 振り分ける(reasons, labels) {
  const 決定 = [], 書き方 = [], 捨てた = [];
  reasons.forEach((r, i) => {
    const l = labels[i];
    const 種 = l && l.confidence >= 自信の線 ? l.choice : "決定を変える";
    if (種 === "書き方") 書き方.push(r);
    else if (種 === "本人の決まりに反する") 捨てた.push(r);
    else 決定.push(r);
  });
  const decision = 決定.length ? "FAIL" : "PASS";
  const 理由 = [...決定, ...書き方.map(r => `[書き方・1回直したら再審査なしで次へ] ${r}`)];
  return { decision, reasons: 理由, 内訳: { 決定を変える: 決定.length, 書き方: 書き方.length, 捨てた: 捨てた.length } };
}

function 問い(i, r) {
  return [`d${i}`, { type: "choice", instructions: `審査で見つかったずれ ${i + 1}: 「${r}」。このずれがどれに当たるかを1つ選ぶ。`, criteria: 種類 }];
}

// ずれを本体の上限に収まる束に分ける
export function 束にする(reasons, state) {
  const 束 = []; let 今 = [];
  const 大きさ = qs => Buffer.byteLength(JSON.stringify({ model: "typesafe/jev-1.13", state, questions: Object.fromEntries(qs.map(([i, r]) => 問い(i, r))) }));
  reasons.forEach((r, i) => {
    if (今.length && 大きさ([...今, [i, r]]) > 本体の上限) { 束.push(今); 今 = []; }
    今.push([i, r]);
  });
  if (今.length) 束.push(今);
  return 束;
}

let 既定の判断 = null;
async function JEVを用意() {
  if (既定の判断) return 既定の判断;
  const m = await import(pathToFileURL(path.join(os.homedir(), "Claude Code/ec-harness/agent_team/jev-openrouter.mjs")).href);
  const key = m.existingJevKey(path.join(os.homedir(), ".config/jev/.env"));
  既定の判断 = () => m.openRouterJev({ apiKey: key, budgetUsd: 0.01, maxCalls: 10 });
  return 既定の判断;
}

// 編集長の結果（record）を収束させる。jev を渡せばそれを使う（テスト用）
export async function 収束させる(record, { jev = null, 種類の説明 = "", 聞き直す = null } = {}) {
  const reasons = record.reasons || [];
  if (!reasons.length) return { ...record, 収束: { 内訳: null, 使った: "なし（ずれ0件）" } };
  try {
    const call = jev || (await JEVを用意())();
    const state = { 何の審査か: 種類の説明 || "EC の成果物の独立レビュー", ずれの数: reasons.length };
    const labels = [];
    for (const 束 of 束にする(reasons, state)) {
      const res = await call({ state, questions: Object.fromEntries(束.map(([i, r]) => 問い(i, r))) });
      for (const [i] of 束) {
        const a = res?.answers?.[`d${i}`];
        labels[i] = a && Object.hasOwn(種類, a.choice) && Number.isFinite(a.confidence) ? { choice: a.choice, confidence: a.confidence } : null;
      }
    }
    // 自信が線より低い物・決められない物だけ Opus に聞き直す（決まった3択から1つ）。聞き直せなければ決定を変えるに倒す
    let 聞き直した = 0;
    if (聞き直す) for (const [i, r] of reasons.entries()) {
      const l = labels[i];
      if (l && l.confidence >= 自信の線 && l.choice !== "other") continue;
      try { const c = await 聞き直す(r, 種類); if (Object.hasOwn(種類, c) && c !== "other") { labels[i] = { choice: c, confidence: 1, 聞き直し: true }; 聞き直した++; } } catch {}
    }
    const r = 振り分ける(reasons, labels);
    return { ...record, decision: r.decision, reasons: r.reasons, 収束: { 内訳: r.内訳, 編集長の判定: record.decision, 使った: "JEV", 聞き直した, ラベル: labels } };
  } catch (e) {
    // 判断の層が使えない時は、編集長の判定をそのまま使う（今までと同じ）
    return { ...record, 収束: { 内訳: null, 使った: "編集長の判定のまま", 理由: String(e.message || e).slice(0, 200) } };
  }
}
