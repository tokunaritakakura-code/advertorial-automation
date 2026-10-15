// Offline Python contract bridge. Never parses approval from natural-language text.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const core = fileURLToPath(new URL('./ec_contract.py', import.meta.url));
export function contract(command, payload) {
  const r = spawnSync('python3', ['-B', core, command], { input: JSON.stringify(payload), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  if (r.error || !r.stdout) throw r.error || new Error(r.stderr || 'contract unavailable');
  const result = JSON.parse(r.stdout);
  if (result.schema_version !== 1) throw new Error('unsupported contract response');
  return result;
}
export function requireExecutable(payload) {
  const result = contract('validate', payload);
  if (result.status !== 'executable') throw new Error(`Execution refused: ${JSON.stringify(result)}`);
  return result;
}

// ONLY authenticated same-origin owner UI may call; never register as agent tool.
export function issueApproval({job, owner, expires_at}) {
  const result = contract('trusted-owner-approve', {job, owner, expires_at});
  if (!result.approval_id) throw new Error(JSON.stringify(result));
  return result;
}

// ONLY fresh independent SDK reviewer completion callback may invoke.
export function recordReview(payload) {
  const result = contract('trusted-review-record', payload);
  if (!result.review_id) throw new Error(JSON.stringify(result));
  return result;
}
