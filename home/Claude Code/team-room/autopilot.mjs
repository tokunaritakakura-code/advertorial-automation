// 自動の振り分け（本部長の「次へ渡す」だけを機械でやる。自分では作業しない）
// 2026-10-06 本人「ニッチで新しい商品に行くと言ったら、起きた頃には出せる広告・記事・商品ページがある」。
// 以前は部長の HANDOFF 行を Claude（ターミナル）が読んで手で次の部へ書いていた（10/5〜6 で22回）。
// 部長の最後の返事の HANDOFF 行を読み、その発注の中で編集長が PASS を出していれば、次の部長に発注を書く。
// 止まる時（本人宛て・PASS無し・同じ発注の繰り返し・回数の上限・止める印）は、本人に Telegram で1通だけ送る。
import fs from 'node:fs';
import path from 'node:path';

export const 上限 = 40; // 1案件で自動に渡す回数。超えたら本人に聞く（ぐるぐる回るのを止める）

export function autopilotStore(file) {
  const 読む = () => { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return { jobs: {} }; } };
  const 書く = (d) => { fs.mkdirSync(path.dirname(file), { recursive: true }); const t = file + '.tmp'; fs.writeFileSync(t, JSON.stringify(d, null, 2)); fs.renameSync(t, file); };
  const key = (c) => `${c.brand}/${c.job_id}/${c.revision}`;
  return {
    get: (c) => 読む().jobs[key(c)] || null,
    all: () => 読む().jobs,
    start(c, { goal, order }) { const d = 読む(); d.jobs[key(c)] = { on: true, goal, order, hops: 0, history: [], started_at: new Date().toISOString() }; 書く(d); return d.jobs[key(c)]; },
    stop(c, reason) { const d = 読む(); const j = d.jobs[key(c)]; if (j) { j.on = false; j.stopped = { at: new Date().toISOString(), reason }; 書く(d); } return j; },
    hop(c, entry) { const d = 読む(); const j = d.jobs[key(c)]; if (!j) return null; j.hops++; j.history.push({ at: new Date().toISOString(), ...entry }); 書く(d); return j; },
  };
}

// 部長の返事の最後の HANDOFF 行（00 組織図.md の形: 渡す先の役 / 渡す物のパス / やってほしい事1文）
export function handoffOf(text) {
  const 行 = String(text || '').split('\n').map((l) => l.trim().replace(/^[`*>\s]+|[`*\s]+$/g, '')).filter((l) => /^HANDOFF\s*[:：]/i.test(l));
  if (!行.length) return null;
  const 中身 = 行[行.length - 1].replace(/^HANDOFF\s*[:：]\s*/i, '');
  // 区切りは「 / 」。前の空白が無い「）/ 」も区切りとして読む（2026-10-06 男性ボクサーの HANDOFF が読めず止まった）。パスの中の「/」は後ろに空白が無いので割らない
  const [to, artifact, ...rest] = 中身.split(/\s*\/\s+/);
  if (!to || !rest.length) return null;
  return { to: to.trim(), artifact: (artifact || '').trim(), ask: rest.join(' / ').trim() };
}

// この発注の中で最後に出た編集長の判定。子の結果を深さ順にたどる
export function editorVerdict(results) {
  let last = null;
  const walk = (r) => {
    if (!r) return;
    if (r.role === '編集長' && r.status === 'success') { try { const v = JSON.parse(r.output); if (v?.status) last = String(v.status).toLowerCase(); } catch {} }
    for (const c of r.children || []) walk(c);
  };
  for (const r of [].concat(results || [])) walk(r);
  return last; // 'pass' | 'fail' | null
}

// 役 → 発注を書くチャンネル。部長ならそのチャンネル、作る役ならその役がいる部のチャンネル（部長が振る）
export function channelFor(role, channels) {
  const lead = channels.find((c) => c.lead === role && c.id !== 'hq');
  if (lead) return lead;
  return channels.find((c) => c.id !== 'hq' && c.members.includes(role) && role !== '編集長') || null;
}

// 渡す物の置き場: Vault の ec/ か、デスクトップの ec/（動画・画像・HTML）。作業フォルダ（ec-harness/data/brands/…）だけにある物は通さない
export const 置き場どおり = (a) => {
  const p = String(a).replace(/[`'"]/g, '').trim();
  return /(^|\/)Obsidian Vault\/ec\//.test(p) || /^(Vault\s+)?ec\/(?!.*ec-harness)/.test(p) || /(^~|\/Users\/[^/]+)\/Desktop\/ec\//.test(p);
};


// Obsidian が情報源（2026-10-07 本人「毎回 Obsidian に入れる。絶対にぶれないように」）。
// 次の部へ渡す時と、ゴールが揃って本人へ渡す時、渡す物が Vault（文字）でもデスクトップ（動画・画像・HTML）でもなければ、同じ部に「置いてから渡し直す」を頼む。同じ戻しが2回続いたら止める
function 置き場の関門(h, job, lead, channels) {
  if (!h.artifact || 置き場どおり(h.artifact)) return null;
  const own = channels.find((c) => c.lead === lead.role && c.id !== 'hq');
  const 前 = job.history?.[job.history.length - 1];
  if (!own || (前?.vault_return && 前.artifact === h.artifact) || job.hops >= 上限) return { action: 'stop', reason: `渡す物が Obsidian に置かれていない（${h.artifact}）`, handoff: h };
  return { action: 'dispatch', channel: own.id, handoff: { ...h, vault_return: true }, text: [
    `[自動の振り分け・${job.hops + 1}回目] 渡す物「${h.artifact}」が Obsidian の外（作業フォルダ）にある。Obsidian が情報源なので、このままでは次へ渡さない。`,
    '文字の成果物（調べた物・台帳・台本・移植表・判断）は Vault の ec/<ブランド>/<ライン>/<番号>/ に、動画・画像・HTML はデスクトップの ~/Desktop/ec/<ブランド>/<ライン>/<番号>/ に置き（並びは各ブランドの _入口.md）、その置き場のパスで HANDOFF を書き直す。中身は作り直さない。',
    `元の HANDOFF: ${h.to} / ${h.artifact} / ${h.ask}`, `ゴール（本人の元の発注）: ${job.goal}`,
  ].join('\n') };
}

// 次に何をするか。dispatch か stop だけを返す（作業はしない）
export function decide({ job, results, channels }) {
  if (!job?.on) return { action: 'none' };
  const lead = [].concat(results || []).find((r) => r && channels.some((c) => c.lead === r.role));
  if (!lead) return { action: 'none' };
  // partial でも、部長が最後まで書き終え（code 無し）途中の道具の失敗を自分で取り返した時は進める。編集長の PASS は下で必ず見る（2026-10-06 クリエイティブ部で審査の依頼1回が版違いで落ち、出し直して PASS）
  const 取り返した = lead.status === 'partial' && !lead.code && String(lead.output || '').trim();
  if (lead.status !== 'success' && !取り返した) return { action: 'stop', reason: `${lead.role} が最後まで終わらなかった（${lead.status}${lead.code ? '・' + lead.code : ''}）` };
  let h = handoffOf(lead.output);
  // HANDOFF が無く「あなたが決めること」で本人に聞いてきた時も、本部長宛てと同じく部に戻して決めさせる（2026-10-06 男性ボクサー 3b）
  const 聞いた = String(lead.output || '').match(/あなたが決めること\s*[:：]\s*(.+)/);
  if (!h && 聞いた && !/^無し/.test(聞いた[1].trim())) h = { to: '本部長', artifact: '', ask: 聞いた[1].trim().slice(0, 300) };
  // 書き出し・生成の終わりを『知らせが来たら続ける』と言って手番を終えた時は、止めずに少し後で同じ部に続きを頼む（部屋の中では知らせで起こされない。2026-10-07 夜の動画で2回）
  if (!h && /知らせ|待って|待ちます|書き出し|生成.{0,6}終わ|background|notified/i.test(String(lead.output || ''))) {
    const own = channels.find((c) => c.lead === lead.role && c.id !== 'hq');
    if (own && job.hops < 上限) return { action: 'later', channel: own.id, delayMs: 10 * 60 * 1000, text: `[自動の振り分け・${job.hops + 1}回目] さっき『終わったら知らせが来る』と言って止まったが、部屋の中では知らせで起こされない。書き出し・生成の物ができているか自分で確かめ、まだなら前で待ち（until ループを前で回す）、できていたら続きをやる。返事の最後に必ず HANDOFF を書く。ゴール: ${job.goal}` };
  }
  if (!h) return { action: 'stop', reason: `${lead.role} の返事に HANDOFF 行が無い` };

  if (/^(本人|オーナー)$/.test(h.to)) { if (/完了|揃った|出せる/.test(h.ask)) { const g = 置き場の関門(h, job, lead, channels); if (g) return g; } return { action: 'stop', reason: `本人の判断待ち: ${h.ask}`, done: /完了|揃った|出せる/.test(h.ask), handoff: h }; }
  if (h.to === '完了') return { action: 'stop', reason: `ゴールに届いた: ${h.ask}`, done: true, handoff: h };
  // 部長が「本部長」宛てに本人の判断を回してきた時は、本人に聞かず同じ部に戻して、部長が推した案で決めさせる
  // （2026-10-06 補正タンクの部長が 3b のアングルを本部長に回し、振り分けが止まった）
  if (h.to === '本部長') {
    const own = channels.find((c) => c.lead === lead.role && c.id !== 'hq');
    const 前2 = job.history?.[job.history.length - 1];
    if (!own) return { action: 'stop', reason: `${lead.role} の部が無い`, handoff: h };
    if (前2 && 前2.to === '本部長' && 前2.ask === h.ask) return { action: 'stop', reason: `同じ判断を2回本部長に回してきた（${h.ask}）`, handoff: h };
    if (job.hops >= 上限) return { action: 'stop', reason: `自動で${上限}回渡したので一度止めた`, handoff: h };
    return { action: 'dispatch', channel: own.id, handoff: h, text: [
      `[自動の振り分け・${job.hops + 1}回目] 自動で進めている案件なので本人には聞かない。あなたが推した案で決め、理由（客の声の数など）と次点を台帳に残して、この部の残りの小工程を進める。回してきた事: ${h.ask}`,
      h.artifact ? `渡す物: ${h.artifact}` : '', `ゴール（本人の元の発注）: ${job.goal}`, `元の発注の全文: ${job.order}`,
      '返事の最後の行に必ず HANDOFF を書く: 次の工程の部長宛て。「本人」宛ては本番公開・配信・予算・お金のかかる発注しか残っていない時か、ゴールが揃った時だけ。「本部長」宛てにしない。',
    ].filter(Boolean).join('\n') };
  }
  // 前の工程の部長へ「足りない入力を埋めて」と戻す時は、審査する成果物がまだ無いので編集長の判定なしで渡す（2026-10-07 ファネル部長が割り付けの不足を戦略責任者へ戻して止まった）
  const 工程の順 = ['research', 'creative', 'funnel', 'growth'];
  const 戻す先 = channelFor(h.to, channels), 自部 = channels.find((c) => c.lead === lead.role && c.id !== 'hq');
  if (戻す先 && 自部 && 戻す先.lead === h.to && 工程の順.indexOf(戻す先.id) >= 0 && 工程の順.indexOf(自部.id) > 工程の順.indexOf(戻す先.id)) {
    if (job.hops >= 上限) return { action: 'stop', reason: `自動で${上限}回渡したので一度止めた`, handoff: h };
    const 前3 = job.history?.[job.history.length - 1];
    if (前3 && 前3.to === h.to && 前3.ask === h.ask) return { action: 'stop', reason: `同じ戻しが2回続いた（${h.to}: ${h.ask}）`, handoff: h };
    return { action: 'dispatch', channel: 戻す先.id, handoff: h, text: [
      `[自動の振り分け・${job.hops + 1}回目・戻し] ${lead.role} が足りない入力を返してきた。${h.ask}`,
      h.artifact ? `直す点の記録: ${h.artifact}` : '', `ゴール（本人の元の発注）: ${job.goal}`, `元の発注の全文: ${job.order}`,
      '足りない所だけ埋めて検査と編集長を通し、返事の最後の行に HANDOFF を書く: 戻してきた部長宛て（' + lead.role + '）。作り直さない。',
    ].filter(Boolean).join('\n') };
  }
  const verdict = editorVerdict(results);
  if (verdict !== 'pass') return { action: 'stop', reason: verdict ? `編集長が通していない（${verdict}）` : 'この発注で編集長の判定が無い', handoff: h };
  // 本人が「ここまで」と決めた案件は、その部長に渡す手前で止める（2026-10-06 本人「男版だけPDPまで、それ以外は広告を作る前まで」）
  if ((job.stop_before || []).includes(h.to)) return { action: 'stop', reason: `決めた所まで来た（${h.to} の手前で止める）: ${h.ask}`, done: true, handoff: h };
  const ch = channelFor(h.to, channels);
  if (!ch) return { action: 'stop', reason: `渡す先「${h.to}」がどの部にもいない`, handoff: h };
  if (job.hops >= 上限) return { action: 'stop', reason: `自動で${上限}回渡したので一度止めた`, handoff: h };
  const 前 = job.history?.[job.history.length - 1];
  if (前 && 前.to === h.to && 前.ask === h.ask) return { action: 'stop', reason: `同じ発注が2回続いた（${h.to}: ${h.ask}）`, handoff: h };
  const 関門 = 置き場の関門(h, job, lead, channels); if (関門) return 関門;
  const text = [
    `[自動の振り分け・${job.hops + 1}回目] ${ch.lead === h.to ? '' : `@${h.to} の仕事。部長が振る。`}${h.ask}`,
    h.artifact ? `渡す物: ${h.artifact}` : '',
    `ゴール（本人の元の発注）: ${job.goal}`,
    `元の発注の全文: ${job.order}`,
    '正本の図 ec/構造/ハーネス/_参考再現フロー_工程と関門_2026-10-03.canvas で今の小工程を決め、その工程の手順書と既存の道具だけで作る。編集長を通してから返す。',
    '自動で進めている案件。返事の最後の行に必ず HANDOFF を書く: 次の工程の部長（戦略責任者／クリエイティブディレクター／ファネル責任者／グロース責任者）宛て。本人にしか決められない物（本番公開・配信・予算・お金のかかる発注）が残った時、またはゴールの物が全部揃った時だけ「本人」宛て。',
  ].filter(Boolean).join('\n');
  return { action: 'dispatch', channel: ch.id, text, handoff: h };
}
