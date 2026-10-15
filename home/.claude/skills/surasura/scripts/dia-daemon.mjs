// dia-daemon.mjs — CDP接続を握ったまま常駐する。1コマンドごとに繋ぎ直さないための常駐プロセス。
// 実測(2026-08-27): 常駐なし 90〜110ms/操作 → 常駐あり 1桁ms。
// unixソケットで改行区切りJSONを受ける。dia.mjs が自動で起動するので直接叩く必要はない。
//   起動: node dia-daemon.mjs &      停止: node dia.mjs daemon stop
import net from 'node:net';
import fs from 'node:fs';
import { ops, dropSockets } from './dia-core.mjs';

const SOCK = process.env.DIA_SOCK || '/tmp/dia-cdp.sock';
const IDLE_EXIT_MS = 30 * 60 * 1000;     // 30分触られなければ自分で終わる

try { fs.unlinkSync(SOCK); } catch {}
let last = Date.now();

const server = net.createServer((conn) => {
  let buf = '';
  conn.on('data', async (chunk) => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\n')) > -1) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (!line.trim()) continue;
      last = Date.now();
      let req;
      try { req = JSON.parse(line); } catch { conn.write(JSON.stringify({ error: 'bad json' }) + '\n'); continue; }
      if (req.cmd === 'ping') { conn.write(JSON.stringify({ ok: true, out: { pid: process.pid, up: Math.round(process.uptime()) } }) + '\n'); continue; }
      if (req.cmd === 'stop') { conn.write(JSON.stringify({ ok: true, stopping: true }) + '\n'); setTimeout(() => process.exit(0), 50); continue; }
      const fn = ops[req.cmd];
      if (!fn) { conn.write(JSON.stringify({ error: '未知のコマンド: ' + req.cmd }) + '\n'); continue; }
      try {
        const out = await fn(req.args || {});
        conn.write(JSON.stringify({ ok: true, out }) + '\n');
      } catch (e) {
        // 接続が腐っている可能性があるので一度捨てて次回張り直す
        if (/timeout|closed|ECONN|WebSocket/i.test(e.message)) dropSockets();
        conn.write(JSON.stringify({ error: e.message }) + '\n');
      }
    }
  });
  conn.on('error', () => {});
});

server.listen(SOCK, () => {
  fs.chmodSync(SOCK, 0o600);
  console.error(`dia-daemon: ${SOCK} pid=${process.pid}`);
});

setInterval(() => { if (Date.now() - last > IDLE_EXIT_MS) process.exit(0); }, 60000).unref?.();
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { try { fs.unlinkSync(SOCK); } catch {} process.exit(0); });
process.on('exit', () => { try { fs.unlinkSync(SOCK); } catch {} });
