#!/usr/bin/env node
// dia.mjs — Diaを最短で操作する入り口。常駐プロセス(dia-daemon.mjs)に投げ、無ければ自分で起動する。
//
// 実測(2026-08-27, このマシン):
//   Playwright connectOverCDP 1,763ms → 素のCDP 37ms → 常駐で1桁ms
//   スクショで見る 683ms/約1,300画像トークン → 操作要素だけ蒸留 2ms/793トークン(rakuten.co.jp)
//
// 動詞:
//   dia tabs                                  開いているタブ一覧
//   dia open <url> [--fg] [--win <語>]        裏で開く(本人の画面もカーソルも奪わない)
//                                             --win でその語を含むタブと同じ窓にタブとして足す
//   dia nav <url> [--tab <urlの一部>]          既存タブを飛ばす
//   dia look [--tab x] [--max 300] [--all] [--filter 正規表現]
//                                             操作できる要素に番号を振って出す(既定は画面内だけ)
//   dia click <番号|ラベル> [--tab x] [--force] 押して、何が変わったかまで返す(押せない状態なら押さずに理由を返す)
//   dia type <番号|ラベル> <文字列> [--enter]
//   dia upload <ファイル...> [--sel <CSS>] [--click <ラベル>]
//                                             file入力にファイルを差し込む。--click は押した瞬間に作られる隠しinputを捕まえる
//   dia read [--tab x] [--max 4000]           本文テキストだけ
//   dia do '<JS>' [--save <名前>] [--note ..]  1往復でまとめて実行。--save で手順を記憶
//   dia recipe list|run <名前>|save <名前> --js <ファイル>
//   dia wait --text/--appear/--gone/--url/--idle [--timeout 15000]
//   dia dialog accept|dismiss [--text ..]      ページが出した alert/confirm/prompt に答える
//   dia close [--tab x]
//   dia daemon status|stop
//   dia doctor                                繋がらない時の診断(何をすれば直るかまで出す)
import net from 'node:net';
import fs from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SOCK = process.env.DIA_SOCK || '/tmp/dia-cdp.sock';
const argv = process.argv.slice(2);
const cmd = argv[0];
const BOOL = new Set(['fg', 'enter', 'idle', 'all', 'json', 'force']);
const flag = (n, d = null) => {
  const i = argv.indexOf('--' + n);
  if (i < 0) return d;
  if (BOOL.has(n)) return true;
  return argv[i + 1] !== undefined && !argv[i + 1].startsWith('--') ? argv[i + 1] : true;
};
// フラグとその値を除いた残りが位置引数
const pos = (() => {
  const out = []; 
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) { if (!BOOL.has(a.slice(2))) i++; continue; }
    out.push(a);
  }
  return out;
})();

function connect() {
  return new Promise((res, rej) => {
    const c = net.createConnection(SOCK);
    c.once('connect', () => res(c));
    c.once('error', rej);
  });
}

async function ensureDaemon() {
  try { return await connect(); } catch {}
  try { fs.unlinkSync(SOCK); } catch {}
  const child = spawn(process.execPath, [path.join(HERE, 'dia-daemon.mjs')], {
    detached: true, stdio: 'ignore', env: process.env,
  });
  child.unref();
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 50));
    try { return await connect(); } catch {}
  }
  throw new Error('常駐プロセスを起動できなかった');
}

async function call(cmdName, args = {}) {
  const conn = await ensureDaemon();
  return new Promise((res, rej) => {
    let buf = '';
    conn.on('data', d => {
      buf += d;
      const i = buf.indexOf('\n');
      if (i > -1) {
        conn.end();
        const m = JSON.parse(buf.slice(0, i));
        m.error ? rej(new Error(m.error)) : res(m.out);
      }
    });
    conn.on('error', rej);
    conn.write(JSON.stringify({ cmd: cmdName, args }) + '\n');
  });
}

const t0 = Date.now();
const stamp = new Date().toISOString().slice(0, 10);
const done = (extra = '') => console.error(`  (${Date.now() - t0}ms)${extra ? ' ' + extra : ''}`);
// 担当ごとのタブ（2026-10-07 本人「ブランドが増えても同じ作業でぶつからないように」）。
// DIA_OWNER（部屋が役ごとに渡す。例 ここちドライ/kids-0107/r1/コピーライター）がある時は、自分が開いたタブだけを触る。
// --tab 無しで「先頭のタブ」（別ブランドの担当のタブかもしれない）を掴まない。DIA_OWNER が無ければ今までどおり。
const OWNER = process.env.DIA_OWNER || null;
const 持ち物の場所 = OWNER ? `/tmp/dia-owner/${(await import('node:crypto')).createHash('sha1').update(OWNER).digest('hex').slice(0, 16)}.json` : null;
const fsm = await import('node:fs');
const 持ち物 = () => { try { return JSON.parse(fsm.readFileSync(持ち物の場所, 'utf8')).tabs || []; } catch { return []; } };
const 持ち物を書く = (tabs) => { fsm.mkdirSync('/tmp/dia-owner', { recursive: true }); fsm.writeFileSync(持ち物の場所 + '.tmp', JSON.stringify({ owner: OWNER, tabs })); fsm.renameSync(持ち物の場所 + '.tmp', 持ち物の場所); };
async function 開いているタブ() { const port = process.env.DIA_CDP_PORT || 9222; return (await (await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(3000) })).json()).filter(t => t.type === 'page'); }
async function tab() {
  const m = flag('tab');
  if (!OWNER) return m;
  const mine = 持ち物(), ts = await 開いているタブ(), live = mine.map(id => ts.find(t => t.id === id)).filter(Boolean);
  if (live.length !== mine.length) 持ち物を書く(live.map(t => t.id));
  if (m && m !== true) {
    const hit = live.find(t => t.id === m) || [...live].reverse().find(t => t.url.includes(m) || (t.title || '').includes(m));
    if (!hit) throw new Error(`この担当（${OWNER}）が開いたタブに「${m}」が無い。dia open <url> で自分のタブを開く（ほかの担当のタブは触らない）`);
    return hit.id;
  }
  if (!live.length) throw new Error(`この担当（${OWNER}）はまだタブを開いていない。先に dia open <url> で開く（ほかの担当のタブは触らない）`);
  return live[live.length - 1].id;
}

try {
  if (cmd === 'doctor') {
    const { execSync } = await import('node:child_process');
    const sh = (c) => { try { return execSync(c, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { return ''; } };
    const PORT = process.env.DIA_CDP_PORT || 9222;
    let ng = 0;

    const diaRunning = sh(`pgrep -f "/Applications/Dia.app/Contents/MacOS/Dia" | head -1`);
    console.log(diaRunning ? `✓ Diaが動いている (pid=${diaRunning})` : '✗ Diaが動いていない');
    if (!diaRunning) { console.log('   → Diaを開く: open -a Dia'); ng++; }

    const owner = sh(`lsof -nP -iTCP:${PORT} -sTCP:LISTEN -t | head -1`);
    const ownerName = owner ? sh(`ps -p ${owner} -o comm=`) : '';
    if (!owner) {
      console.log(`✗ ポート${PORT}を誰も開いていない`);
      // エージェントがこの案内を読んで本人の Dia を閉じる事故が起きた（本人 2026-10-07「dia を触ってたら勝手に閉じられる」）
      console.log(`   → 本人の Dia は閉じない（作業中のタブが消える）。エージェントは osascript の quit も kill もしない`);
      console.log(`   → この回は Dia を使わずに止まり、本人に「Dia をデバッグポート付きで開き直してほしい」と1行で伝える`);
      ng++;
    } else if (/Dia/i.test(ownerName)) {
      console.log(`✓ ポート${PORT}はDiaが開いている (pid=${owner})`);
    } else {
      console.log(`✗ ポート${PORT}をDia以外が使っている: ${ownerName} (pid=${owner})`);
      console.log(`   → そのプロセスを止めるか、DIA_CDP_PORT=別番号 で逃がす`);
      ng++;
    }

    let tabCount = null;
    try { tabCount = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`, { signal: AbortSignal.timeout(3000) })).json()).filter(t => t.type === 'page').length; }
    catch {}
    console.log(tabCount === null ? `✗ CDPが応答しない` : `✓ CDPが応答した (${tabCount}タブ)`);
    if (tabCount === null) ng++;

    try { const r = await call('ping'); console.log(`✓ 常駐プロセスが動いている (pid=${r.pid} 稼働${r.up}秒)`); }
    catch { console.log('✗ 常駐プロセスが上がらない → node のバージョンを確認 (node -v は v22以上が必要)'); ng++; }

    console.log(ng === 0 ? '\n全部OK。dia look から始められる' : `\n${ng}件やることがある(上の → を上から順に)`);
    if (ng) process.exit(5);

  } else if (cmd === 'daemon') {
    const sub = pos[0] || 'status';
    if (sub === 'stop') {
      try { const c = await connect(); c.write(JSON.stringify({ cmd: 'stop' }) + '\n'); c.end(); console.log('停止した'); }
      catch { console.log('動いていない'); }
    } else {
      // status は勝手に起動しない(素の接続だけ試す)
      try {
        const c = await connect();
        const r = await new Promise((res, rej) => {
          let b = ''; c.on('data', d => { b += d; const i = b.indexOf('\n'); if (i > -1) { c.end(); res(JSON.parse(b.slice(0, i))); } });
          c.on('error', rej); setTimeout(() => rej(new Error('無応答')), 2000);
          c.write(JSON.stringify({ cmd: 'ping' }) + '\n');
        });
        console.log(`動いている pid=${r.out.pid} 稼働${r.out.up}秒`);
      } catch { console.log('動いていない'); }
    }

  } else if (cmd === 'tabs') {
    const r = await call('tabs');
    r.lines.forEach(l => console.log(l));
    done(`${r.count}タブ`);

  } else if (cmd === 'open') {
    if (!pos[0]) throw new Error('usage: dia open <url> [--fg] [--win <既にその窓にあるタブのurlか題名の一部>]');
    const r = await call('open', { url: pos[0], fg: !!flag('fg'), win: flag('win') || null });
    if (OWNER && r.targetId) 持ち物を書く([...持ち物().filter(id => id !== r.targetId), r.targetId]);
    console.log(r.targetId);
    done(r.url.slice(0, 80));

  } else if (cmd === 'nav') {
    if (!pos[0]) throw new Error('usage: dia nav <url> [--tab <urlの一部>]');
    await call('nav', { tab: await tab(), url: pos[0] });
    console.log('OK ' + pos[0]);
    done();

  } else if (cmd === 'look') {
    const r = await call('look', {
      tab: await tab(), max: flag('max', '300'),
      viewport: !flag('all'), filter: flag('filter'),
    });
    console.log(`# ${r.url}`);
    console.log(r.list);
    done(`${r.count}要素 ≈${Math.round((r.list || '').length / 4)}トークン` +
         (r.folded ? ` / 同型の繰り返し${r.folded}種は3件に畳んだ` : '') +
         (flag('all') ? '' : ' / 画面内のみ(--allで全部)'));

  } else if (cmd === 'click' || cmd === 'type') {
    if (!pos[0]) throw new Error(`usage: dia ${cmd} <番号|ラベル> ${cmd === 'type' ? '<文字列> [--enter]' : ''}`);
    const r = cmd === 'click'
      ? await call('click', { tab: await tab(), target: pos[0], force: !!flag('force') })
      : await call('type', { tab: await tab(), target: pos[0], text: pos.slice(1).join(' '), enter: !!flag('enter') });
    console.log(r.result);
    if (r.ヒント) console.log('→ ' + r.ヒント);
    if (r.候補) { console.log('候補:'); console.log(r.候補); }
    if (r.diff?.length) { console.log('変化:'); r.diff.forEach(d => console.log('  ' + d)); }
    else if (!String(r.result).startsWith('ERR') && (cmd === 'click' || flag('enter')))
      console.log('変化: 見た目に変化なし(押した先が何もしないか、読み込み待ち → dia wait か look)');
    done();

  } else if (cmd === 'dialog') {
    const act = pos[0] === 'accept' ? 'accept' : pos[0] === 'dismiss' ? 'dismiss' : null;
    if (!act) throw new Error('usage: dia dialog accept|dismiss [--text "入れる文字"]');
    const r = await call('dialog', { tab: await tab(), action: act, text: flag('text', '') === true ? '' : (flag('text', '') || '') });
    console.log(r.開いていない ? r.note : `${r.答えた}: ${r.中身}`);
    done();

  } else if (cmd === 'upload') {
    if (!pos.length) throw new Error("usage: dia upload <ファイル...> [--sel <CSSセレクタ>] [--click <ラベル>]");
    // 常駐プロセスのcwdは呼び出し元と違う。相対パスはここ(クライアント側)で絶対にする
    const r = await call('upload', {
      tab: await tab(), target: flag('sel'), click: flag('click'),
      files: pos.map(f => path.resolve(f)),
    });
    console.log('OK upload ' + (r.result || ''));
    if (r.diff?.length) { console.log('変化:'); r.diff.forEach(d => console.log('  ' + d)); }
    else console.log('変化: 見た目に変化なし(サイトがまだ読んでいない可能性 → dia wait で待つ)');
    done();

  } else if (cmd === 'read') {
    const r = await call('read', { tab: await tab(), max: flag('max', '0') });
    console.log(r.text);
    done(`${r.len}文字 ≈${Math.round(r.len / 4)}トークン`);

  } else if (cmd === 'do') {
    const js = flag('js') && flag('js') !== true ? fs.readFileSync(flag('js'), 'utf8') : pos[0];
    if (!js) throw new Error("usage: dia do '<JS>' [--save <名前>] | dia do --js <ファイル>");
    const r = await call('do', { tab: await tab(), js, save: flag('save'), note: flag('note', ''), stamp });
    console.log(typeof r.value === 'string' ? r.value : JSON.stringify(r.value, null, 1));
    (r.warn || []).forEach(w => console.error('NOTE: ' + w));
    done(r.host);

  } else if (cmd === 'recipe') {
    const sub = pos[0];
    if (sub === 'list') {
      const { recipes } = await call('recipe', { action: 'list', host: flag('host') });
      const hosts = Object.keys(recipes);
      if (!hosts.length) console.log('まだ1件も無い。dia do ... --save <名前> で貯まる');
      for (const h of hosts) {
        console.log(`\n## ${h}`);
        for (const [n, r] of Object.entries(recipes[h]))
          console.log(`  ${n.padEnd(22)} 成功${r.ok || 0}/失敗${r.fail || 0}  最終成功:${r.lastOk || '-'}  ${r.note || ''}`);
      }
    } else if (sub === 'run') {
      const r = await call('recipe', {
        action: 'run', tab: await tab(), host: flag('host'), name: pos[1], stamp,
        args: flag('args') ? JSON.parse(flag('args')) : {},
      });
      console.log(typeof r.value === 'string' ? r.value : JSON.stringify(r.value, null, 1));
      done(`${r.host}/${r.name} 成功${r.stats?.ok || 0}/失敗${r.stats?.fail || 0}`);
    } else if (sub === 'save') {
      const js = flag('js') && flag('js') !== true ? fs.readFileSync(flag('js'), 'utf8') : pos[2];
      if (!pos[1] || !js) throw new Error('usage: dia recipe save <名前> --js <ファイル> [--host x] [--note ..]');
      const r = await call('recipe', { action: 'save', tab: await tab(), host: flag('host'), name: pos[1], js, note: flag('note', ''), stamp });
      console.log(`保存: ${r.host}/${pos[1]}`);
    } else throw new Error('usage: dia recipe list|run <名前>|save <名前> --js <ファイル>');

  } else if (cmd === 'wait') {
    const r = await call('wait', {
      tab: await tab(), text: flag('text'), gone: flag('gone'), appear: flag('appear'),
      url: flag('url'), idle: !!flag('idle'), timeout: flag('timeout', '15000'),
    });
    console.log(r.ok ? 'OK' : 'TIMEOUT');
    done(`${r.ms}ms待った`);
    if (!r.ok) process.exit(4);

  } else if (cmd === 'close') {
    const r = await call('close', { tab: await tab() });
    console.log('closed ' + r.closed.slice(0, 70));

  } else {
    console.error('usage: dia tabs|open|nav|look|click|type|upload|read|do|recipe|wait|close|daemon');
    process.exit(1);
  }
} catch (e) {
  console.error('ERR:', e.message);
  if (/fetch failed|ECONNREFUSED|CDP|タブが無い|常駐プロセスを起動できなかった/.test(e.message))
    console.error('→ 原因を調べる: dia doctor');
  process.exit(1);
}
process.exit(0);
