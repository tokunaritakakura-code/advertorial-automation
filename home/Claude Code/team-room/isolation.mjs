import { createHash, randomUUID } from 'node:crypto';
import path from 'node:path';
import fs from 'node:fs';
export function context(value, brands) {
  if (!value || typeof value !== 'object') throw Error('ブランド・案件・版が必要');
  const { brand, job_id, revision } = value;
  if (typeof brand !== 'string' || !Object.hasOwn(brands, brand)) throw Error('未登録ブランド');
  if (typeof job_id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(job_id)) throw Error('案件IDが必要');
  if (!Number.isSafeInteger(revision) || revision < 1) throw Error('成果物版が必要');
  return Object.freeze({ brand, job_id, revision });
}
export const contextKey = (c) => JSON.stringify([c.brand, c.job_id, c.revision]);
export const sessionKey = (role, channel, c) => JSON.stringify([role, channel, c.brand, c.job_id, c.revision]);
export const sameContext = (a, b) => !!a && !!b && contextKey(a) === contextKey(b);
export function delegationChannel(config, source, role) {
  const ch = config.channels.find(x => x.id === source);
  if (!ch?.members.includes(role)) throw Error('委譲先が部門に属していない');
  return config.channels.find(x => x.lead === role)?.id || source;
}
function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k)+':'+canonical(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
export const digest = (v) => createHash('sha256').update(canonical(v)).digest('hex');
export function inside(file, roots) {
  if (typeof file !== 'string' || !path.isAbsolute(file)) return false;
  // Existing parents are resolved too, so symlinks cannot escape an allowed root.
  function resolved(p) {
    const suffix = [];
    while (!fs.existsSync(p)) { const up = path.dirname(p); if (up === p) return null; suffix.unshift(path.basename(p)); p = up; }
    return path.join(fs.realpathSync(p), ...suffix);
  }
  const p = resolved(file);
  return !!p && roots.some(root => { const r = resolved(root); return r && (p === r || p.startsWith(r + path.sep)); });
}
export function reviewPrompt(c, review) {
  if (!review || !Array.isArray(review.artifacts) || !review.artifacts.length || !review.rules?.trim()) throw Error('独立レビューには成果物と基準が必要');
  for (const a of review.artifacts) {
    if (a.revision !== c.revision || !path.isAbsolute(a.path || '') || !/^[a-f0-9]{64}$/.test(a.sha256 || '')) throw Error('レビュー成果物の版・ハッシュが不正');
    if (fileHash(a.path) !== a.sha256) throw Error('レビュー成果物が変更された');
  }
  return `独立レビュー。作り手の会話・自己評価・過去のsessionを使わず、次の成果物と基準だけを判定する。\n案件: ${JSON.stringify(c)}\n成果物: ${JSON.stringify(review.artifacts)}\n基準:\n${review.rules}\n最終回答は次の形のJSONだけにする（囲みや前置きを付けない）。decisionはPASSまたはFAIL。artifact_hashesは全成果物のSHA-256。rules_hashは次の固定値。reasonsには、見つけたずれを全部書く（1つ見つけて止めない。2026-10-07 本人）。1件1行で「どこが・何が・どう直すか」。ずれの重さは書かなくてよい（後でコードが振り分ける）。ずれが1つも無ければ空の配列でPASS。\n${JSON.stringify({decision:"PASS",artifact_hashes:review.artifacts.map(a=>a.sha256),rules_hash:digest(review.rules),reasons:[]})}`;
}
// iCloud が詰まると Vault のファイルを開いた所で戻ってこない（2026-10-08 06:02）。開けなければ4秒で諦めて投げる（サーバーを固めない）
import { execFileSync as _ex } from 'node:child_process';
export const 時間つきで読む = (p) => { try { return _ex('perl', ['-e', 'alarm 4; open(F, "<", $ARGV[0]) or exit 2; binmode F; binmode STDOUT; local $/; print <F>;', p], { timeout: 6000, maxBuffer: 512 * 1024 * 1024 }); } catch (e) { if (e.status === 2) return null; throw Error('ファイルが4秒で開けない（iCloud の詰まり）: ' + p); } };
export const fileHash = (p) => { const b = fs.existsSync(p) ? 時間つきで読む(p) : null; return b ? createHash('sha256').update(b).digest('hex') : null; };
// 役が手順書どおりに仕事できる線（2026-10-05 本人「チームを作った意味をなしてほしい」）。
// 以前は 読む・承認つきで書く 以外を全部拒否していて、手順書が呼ぶ道具（voc.py・スキル・Web・GetHookd）が使えなかった。
// 止めるのは戻せない行動だけ（送信・公開・支払い・本番の変更・削除・push）。そこは準備までで止まり、本人の承認で動く（agent-team 関門4）。
const 戻せないコマンド = /\brm\s+-[a-z]*r|\bgit\s+push\b|\bvercel\b|\bnetlify\b|\bdeploy\b|\blaunchctl\b|\bcrontab\b|広告を入れる\.py|meta-yoyaku|shop-api|kids-deploy|\btelegram\.mjs\b|\bsendmail\b|curl\b[^|]*-X\s*(POST|PUT|PATCH|DELETE)|curl\b[^|]*--data|\bsudo\b/i;
const 秘密 = /\.ssh\/|\.env\b|telegram-arukoto\.json|\.codex\/auth\.json|credentials|\.netrc/i;
// chatgpt-image はクレジット0・手元に絵を書くだけなので役が使ってよい（2026-10-06 夜のうちに静止画を作るため）
// GetHookd は毎回ブラウザ（裏用 Dia の画面）で使う。MCP は残高を使い、0で止まるので役には渡さない（2026-10-06 本人「毎回ブラウザ操作しないと」）
const 読むだけのMCP = /^mcp__(chatgpt-image__generate_image$|obsidian-vault__(read_|list_|search_|directory_tree|get_file_info)|meta-ads__ads_(get_|insights_|library_search)|shopify-dev__|shopify__shopify_(shop|products|orders|sales_summary)$|plugin_claude-mem_mcp-search__)/;
const 戻せないMCP = /^mcp__(meta-ads__|shopify__|claude_ai_Shopify__|gethookd__(create_|delete_|update_|save_|remove_|add_|copy_|start_|stop_|cancel_|submit_|share_|unshare_|run_)|claude_ai_Gmail__|claude_ai_Claude_Docs__)/;
export function toolPolicy(name, input, c, roots, reviewer = false, writeRoots = []) {
  if (name === 'mcp__team__delegate' && !reviewer) return { decision: 'allow' };
  const file = input.file_path || input.path || input.notebook_path;
  if (['Read','Glob','Grep'].includes(name)) {
    if (file && 秘密.test(file)) return {decision:'deny', reason:'秘密のファイルは読まない'};
    return !file || inside(file, roots) ? {decision:'allow'} : {decision:'deny', reason:'この案件の読取範囲外'};
  }
  if (['Write','Edit','NotebookEdit'].includes(name)) {
    if (reviewer) return {decision:'deny', reason:'編集長は作らない'};
    return inside(file, writeRoots) ? {decision:'allow'} : {decision:'deny', reason:'この案件の書込範囲外（Vault のブランド／案件フォルダと作業フォルダだけ）'};
  }
  if (name === 'Bash') {
    const cmd = String(input.command || '');
    if (秘密.test(cmd)) return {decision:'deny', reason:'秘密のファイルに触るコマンド'};
    if (戻せないコマンド.test(cmd)) return {decision:'deny', reason:'戻せない行動。準備までで止め、チャンネルに「本人の承認が要る: <何を>」と1行書いて終わる'};
    return {decision:'allow'};
  }
  if (['Skill','WebFetch','WebSearch','TodoWrite','ToolSearch'].includes(name)) return {decision:'allow'};
  if (読むだけのMCP.test(name)) return {decision:'allow'};
  if (戻せないMCP.test(name)) return {decision:'deny', reason:'戻せない・お金のかかる行動。準備までで止め、チャンネルに「本人の承認が要る: <何を>」と1行書いて終わる'};
  return {decision:'deny', reason:'未登録の道具。要るならチャンネルに道具名を1行書いて止まる'};
}
export function approvalMatches(a, manifest, now = Date.now(), owners = ['owner'], maxSeconds = 300) {
  return !!a && a.decision === 'approve' && a.manifest_hash === digest(manifest) && sameContext(a, manifest) && owners.includes(a.owner) && Number.isFinite(Date.parse(a.approved_at)) && Date.parse(a.approved_at) <= now && Date.parse(a.expires_at) > now && Date.parse(a.expires_at)-Date.parse(a.approved_at) <= maxSeconds*1000;
}
export function runContext(role, channel, c, review) {
  return {key:sessionKey(role, channel, c), reviewer:role === '編集長', run_id:randomUUID(), resume:role !== '編集長', prompt:role === '編集長' ? reviewPrompt(c, review) : null};
}

export function verifiedReviewResult(text, c, review, runId) {
  // 編集長が ```json の囲みや前置きを付けても、中の1つの JSON だけを読む（2026-10-05 囲みで落ちて理由が消えた）
  const body=String(text).replace(/```(?:json)?/gi,'');const from=body.indexOf('{'),to=body.lastIndexOf('}');
  const result=JSON.parse(from>=0&&to>from?body.slice(from,to+1):body);
  const keys=Object.keys(result).sort().join(',');
  if(!['artifact_hashes,decision,rules_hash','artifact_hashes,decision,reasons,rules_hash'].includes(keys) || !['PASS','FAIL'].includes(result.decision) || (result.reasons!==undefined && !(Array.isArray(result.reasons)&&result.reasons.every(r=>typeof r==='string')))) throw Error('独立レビューの結果形式が不正');
  const hashes=review.artifacts.map(a=>a.sha256).sort();
  if(!Array.isArray(result.artifact_hashes) || JSON.stringify([...result.artifact_hashes].sort())!==JSON.stringify(hashes) || result.rules_hash!==digest(review.rules)) throw Error('独立レビューの版・基準が違う');
  for(const a of review.artifacts) if(fileHash(a.path)!==a.sha256) throw Error('レビュー中に成果物が変わった');
  return {scope:{...c,context:`${c.brand}/${c.job_id}/${c.revision}/review/${runId}`},run_id:runId,artifact_hashes:hashes,rules_hash:result.rules_hash,decision:result.decision,reasons:result.reasons||[]};
}
export function approvalWindow(job, cfg, supplied = null, now = Date.now()) {
  const jobEnd=Date.parse(job.expires_at), max=cfg.approval_max_seconds;
  if(!Number.isFinite(jobEnd) || jobEnd<=now || !Number.isFinite(max) || max<=0) throw Error('案件の期限・ブランド承認期限が必要');
  const ceiling=Math.min(jobEnd,now+max*1000);
  const expiry=supplied ? Date.parse(supplied) : ceiling;
  if(!Number.isFinite(expiry) || expiry<=now || expiry>ceiling || expiry<jobEnd) throw Error('承認期限は案件全体を含みブランド上限内にする。案件期限を短くするか実行に近い時点で承認する');
  if(job.scheduled_at != null && (!Number.isFinite(Date.parse(job.scheduled_at)) || Date.parse(job.scheduled_at)>=expiry)) throw Error('予約日時が承認期限外。実行に近い時点で承認する');
  // Preserve sub-millisecond ISO precision; Python compares the exact original deadline.
  return supplied || job.expires_at;
}
