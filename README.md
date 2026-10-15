# advertorial-automation（VSL を受けて記事を作る仕組み）

読む人: この仕組みを自分の Mac に入れて、記事を作る人（と、その人の Claude Code）。
読む時: 入れる前と、1本目を作る前。
読まなくていい条件: なし。

## 1. これは何か

VSL（売るための動画広告）を1本渡すと、その動画を見終わった人に何が残っているか（どこまで分かったか・まだ残っている疑い・広告が開けた問い）を書き出し、記事の形を「普通（人が語る暴露・物語）」「リスティクル（〇〇な7つの理由）」「ランキング（#1〜#5 の比べ）」の3つから1つ選び、買うまでに要る15の事を全部入れて記事を書き、画像は ChatGPT で作り、機械の検査と別の AI（編集長）の審査を合格するまで回して、記事（`index.html`）を作る仕組み。Claude Code が手順書を読んで全部回す。人がするのは、商品と VSL を渡すことだけ。

## 2. 全体の流れ

正本は `~/Documents/Obsidian Vault/ec/構造/ハーネス/05 記事を作る.md` の「一回で作る道」。

| # | やる事 |
|---|---|
| 1 | VSL を文字起こしする（whisper-cli）。これが正本 |
| 2 | 見終わった人の状態を書き、いちばん大きい問いの種類で、普通・リスティクル・ランキングのどれにするか決める（`_VSLから型を選ぶ.md`） |
| 3 | 移植表を書く。固定した参考を段に分け、段ごとに「画像・文の働き」を左、うちの商品の文を右に置く |
| 4 | 入り（記事を開いて最初の画面）を作る。広告が開けた問いを頭で受け、閉じずに次の問いを開ける |
| 5 | 数字・権威・客の声を埋める（テスト中は決めた値を `テスト用に決めた値.md` に残し、noindex を付ける） |
| 6 | ページを組む。字の形は自分の店の商品ページと同じ。値段の段とコメント欄は道具で作る |
| 7 | 画像を ChatGPT の MCP で作る（参考の同じ場所の画像を添付して、人と商品を自分の物に替える） |
| 8 | 画像の置き方の検査と動きの検査 |
| 9 | 編集長（別の AI）の審査 → 直す → もう一度。合格するまで回す |
| 10 | 仕上がりの検査と、PC（1280）とスマホ（390）の幅での最後の確かめ |

### どのファイルが何をするか

| ファイル | すること |
|---|---|
| `~/Documents/Obsidian Vault/ec/構造/ハーネス/05 記事を作る.md` | 手順の正本（上の1〜10） |
| `~/Documents/Obsidian Vault/ec/構造/型/_VSLから型を選ぶ.md` | 3つの形のどれにするかの決め方 |
| `~/Documents/Obsidian Vault/ec/構造/型/_買うまでの15の事.md` | 15の事・見終わった人の状態・問いのつなぎ方 |
| `~/Documents/Obsidian Vault/ec/構造/型/`（`_仕掛けの棚.md`・`_見た目の手本.md`・`_必ず入れる物.md`・型ごとの `_分解.md`） | 記事の部品と型の棚 |
| `~/Documents/Obsidian Vault/ec/決めたこと.md` | 守る決め（フックが EC の会話の最初に全文入れる） |
| `~/Documents/Obsidian Vault/ec/構造/ハーネス/役/編集長.md`・`記事ライター.md`・`ファネル責任者.md` | 審査の関門と、作る役の決まり |
| `~/Claude Code/ec-harness/記事の検査.py` | 移植表と index.html を機械で落とす |
| `~/Claude Code/ec-harness/記事の仕上がり検査.py` | 仮置き・細長い画像・数字の食い違い・文の長さ・テストの印を落とす |
| `~/Claude Code/ec-harness/画像の置き方.py` | 参考とうちの画像の場所・大きさを突き合わせる（dia を使う） |
| `~/Claude Code/ec-harness/動きの検査.py` | 参考とうちの動く物（動画）を突き合わせる（ffmpeg を使う） |
| `~/Claude Code/ec-harness/審査を回す.py` | 機械の検査 → 部屋の編集長に出す → 判定を待つ → `審査_<回>.md` を書く |
| `~/Claude Code/team-room/`（`server.mjs` ほか） | 審査の部屋。編集長（Opus）が判定する。http://127.0.0.1:3200 |
| `~/Claude Code/adv-kata/新規.sh`・`measure.py` | 記事の殻と移植表のひな形を作る・参考のページを数える |
| `~/.claude/skills/kata-tsukuru/` | 参考を保存する・値段の段とコメント欄を組む・幅の検査 |
| `~/.claude/skills/listicle-copy/`・`ranking-copy/`・`bakuro-copy/` | リスティクル・ランキング・暴露の記事を書くスキル |
| `~/.claude/skills/vsl-sagasu/` | 勝っている VSL を GetHookd から探す |
| `~/.claude/skills/surasura/`・`~/.local/bin/dia` | ブラウザ（Dia）を操作する道具 `dia` |
| `~/.claude/mcp/chatgpt-image/server.mjs` | ChatGPT で画像を作る MCP |
| `~/.claude/hooks/` | `決めたこと.md` を会話に入れる・書いた .md の書式を検査する |
| `example/草むしり椅子/` | 試しで作った3本（下の7） |

## 3. 要る物と入れ方

| 要る物 | 入れ方 | 確かめ方 |
|---|---|---|
| Claude Code | https://claude.com/claude-code | `claude --version` |
| Python 3 と部品 | `brew install python` → `pip3 install playwright pillow opencv-python numpy && python3 -m playwright install chromium` | `python3 -c "import playwright, PIL, cv2; print('ok')"` |
| Node.js（22.5 以上。部屋が `node:sqlite` を使う） | `brew install node` | `node -v` |
| ffmpeg | `brew install ffmpeg` | `ffmpeg -version \| head -1` |
| whisper-cli とモデル | `brew install whisper-cpp` → `mkdir -p ~/.cache/whisper && curl -L -o ~/.cache/whisper/ggml-large-v3-turbo.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin` | `whisper-cli -h \| head -1` と `ls -lh ~/.cache/whisper/ggml-large-v3-turbo.bin` |
| Obsidian の Vault | 置き場は `~/Documents/Obsidian Vault/`（`install.sh` が `ec/` を作る）。Obsidian で開けば図（.canvas）も見られる | `ls ~/Documents/Obsidian\ Vault/ec` |
| Dia ブラウザと dia | https://www.diabrowser.com を入れる。`dia` は `install.sh` が `~/.local/bin` に置く（`~/.local/bin` を PATH に入れる） | `dia-agent tabs` が返事をする |
| ChatGPT の画像の MCP | Codex CLI を入れて ChatGPT でログイン（`brew install codex` → `codex login`）。その後 `claude mcp add chatgpt-image -s user -- node ~/.claude/mcp/chatgpt-image/server.mjs` | `claude mcp list` に chatgpt-image が出る |
| GetHookd のアカウント（VSL を探す時だけ） | https://app.gethookd.ai に Dia でログインしたタブを開いておく。鍵は要らない | `dia tabs \| grep gethookd` |
| OpenRouter のキー（審査の判断の層） | `.env.example` の通り `~/.config/jev/.env` に置く | 部屋の起動時に「判断の層が使えない」が出ない |

OpenRouter のキーが無くても、審査は Opus（Claude Code のログインのまま）だけで回る。

`~/.claude.json` の MCP の行は、上の `claude mcp add` で次の形になる（`<自分のユーザー名>` は自分の物）。

```json
"mcpServers": {
  "chatgpt-image": { "type": "stdio", "command": "node", "args": ["/Users/<自分のユーザー名>/.claude/mcp/chatgpt-image/server.mjs"], "env": {} }
}
```

## 4. 入れ方

1. このフォルダで `./install.sh`（先に何が変わるか見たい時は `./install.sh --見るだけ`）。`home/` の中が `$HOME` の同じ場所に入る。既にある物は `<名前>.bak-<日時>` に避ける
2. `.env.example` を見て鍵を置く（OpenRouter と Telegram。どちらも無くても動く）
3. フックを足す: `~/.claude/settings.hooks.example.json` の `hooks` を、自分の `~/.claude/settings.json` の `hooks` に足す（上書きしない）
4. 部屋（編集長）を立てる: `cd ~/Claude\ Code/team-room && node server.mjs` → http://127.0.0.1:3200 が開けば立っている。審査の間はずっと立てておく
5. ブランドを足す: `~/Claude Code/ec-harness/config/brands.json` の `自分のブランド` を自分のブランド名に替える（コピーして増やしてよい）。試しで作る時は `リサーチ` のままでよい

## 5. 1本作る時の頼み方

Claude Code を `~/Claude Code/team-room` で開き、下を貼る。`<>` を自分の物に替える。見本は `example/草むしり椅子/_試しの指示.md`。

```text
<商品名>の記事を1本、端まで作って。VSL は <VSL の動画ファイルかリンク>。
商品の情報は <商品情報.md のパス>（痛み・客・試した物・商品の形・値段・保証）。
記事のフォルダは ~/Claude Code/team-room/引き継ぎ/VSL記事リサーチ_資料/<商品名>/記事_1_<短い名前>/。

作り方は ~/Documents/Obsidian Vault/ec/構造/ハーネス/05 記事を作る.md の「VSL 動画の飛び先の記事を一回で作る道」の 1〜10 の順。
新しい仕組みは作らない。
- 形の選び方: ~/Documents/Obsidian Vault/ec/構造/型/_VSLから型を選ぶ.md
- 15の事・見終わった人の状態・問いのつなぎ: ~/Documents/Obsidian Vault/ec/構造/型/_買うまでの15の事.md
- 決め: ~/Documents/Obsidian Vault/ec/決めたこと.md
- 見た目の手本: ~/Claude Code/team-room/引き継ぎ/VSL記事リサーチ_資料/針マット/ここちドライの手本/

本人は途中で何もしない。聞くのはお金のかかる生成が要る時だけ。
形は先に決めず、見終わった人の状態を書き、3つの形を並べて比べてから選ぶ。15の事は全部入れる。
数字はテスト用に決めて テスト用に決めた値.md に残し、noindex を付ける。公開しない。
画像は chatgpt-image の MCP で作る。
検査と編集長の審査は合格するまで回す（案件ID は <英数字の短い名前>）。
終わったら 報告.md に、言った事ごとに 通った／通っていない と証拠1行を書く。
```

## 6. 審査の回し方

```bash
python3 ~/Claude\ Code/ec-harness/審査を回す.py <記事のフォルダ> <案件ID>
```

部屋（http://127.0.0.1:3200）が立っている事が前提。記事のフォルダには `index.html`・`移植表*.md`・`画像の置き方の引数.txt`（1行目に参考の URL、2行目から引数）が要る。

| 終了コード | 意味 | 次にやる事 |
|---|---|---|
| 0 | 合格（指摘なし） | 終わり |
| 1 | 不合格。`審査_<回>.md` を書いた | 全部直し、`直し_<回>.md` に「探した語: <語>／見つかった所: <数>／全部そろえた」を1行ずつ書いて、もう一度走らせる |
| 2 | 出せなかった（機械の検査が落ちた・部屋が動いていない・判定が待つ分の間に出なかった） | `検査の結果.md` を見て直す。部屋が立っているか見る |
| 3 | 合格だが書き方の指摘がある | `審査_<回>.md` の指摘を直し、機械の検査だけ回す（再審査には出さない） |

回数の上限は無い。同じ所で2回続けて落ちたら、記事だけでなく手順か道具を直してから続ける。

## 7. 今回の試しの結果（`example/草むしり椅子/`）

草むしり椅子（試しの商品）で、構造の違う他社の VSL 3本を「うちの VSL がこうだったら」として、その飛び先の記事を3本作った。3本とも形は「普通（権威の暴露記事）」になり、3本とも部屋の編集長の審査に合格した。

| 記事 | 元にした VSL の構造 | 合格した回 |
|---|---|---|
| `記事_1_時間で変化/` | 時間で変化を追う（24時間→3日→1週→2週）＋医者が横で話す | 6回目 |
| `記事_2_医者が原因/` | 専門家が本当の原因を明かし、今の対策を切る | 10回目 |
| `記事_3_体の場所が責める/` | 体の場所（腰）が持ち主を責める独り語り | 4回目 |

見方: `example/草むしり椅子/index.html` をブラウザで開くと3本と `まとめ.html` に飛べる。各記事のフォルダの `報告.md` が結果のまとめ、`審査_<回>.md` が編集長の指摘、`直し_<回>.md` がどう直したか、`移植表*.md` が参考とうちの文の対応。`install.sh` は同じ物を `~/Claude Code/team-room/引き継ぎ/VSL記事リサーチ_資料/草むしり椅子/` にも置く（記事1は「普通」の形の固定の参考として手順書が指している）。

画像のうち、記事で使っていない元の PNG（2MB 超）は、幅1600px の JPEG（`<名前>_縮小.jpg`）に縮めて替えた。記事で使っている画像はそのまま。

## 8. 入れていない物と理由

| 入れていない物 | 理由 | 代わりにどうするか |
|---|---|---|
| 鍵・トークン・ログイン情報（`.env`・Codex のログイン・Telegram・OpenRouter・Meta・Shopify） | 人の物 | 自分の物を `.env.example` の置き場に置く |
| 他社のページの写し（各記事の `参考/`・`参考の画像/`・`参考の動く物/`・`作業/`、`形式別/lp/`、`kata-tsukuru/runs/*/refs`・`参考/`、素材庫の中身） | 他社の物 | 各記事の `参考を取り直す.md` の URL とコマンドで、自分の手元で取り直す |
| 他社の VSL の台本の全文（`構造/VSL structure/VSL example/` の1本ずつの台本） | 他社の物 | 索引の `_index.md` だけ入れた |
| 個人の物（メールアドレス・Meta の広告アカウント・ピクセル・Shopify のストアの値） | 人の物 | ファイルの中では `REPLACE_ME` に替えた。自分の値を入れる |
| 自分のブランドの資料（`ec/アルコット/`・`ec/ここちドライ/`） | 人のブランド | 自分のブランドの `ec/<ブランド>/` を作る |
| `vsl-sagasu/scripts/state`・各スキルの `runs`・`.bak*`・`__pycache__`・`node_modules`・部屋の `data/` | 作業の記録で、仕組みではない | `install.sh` が `npm install` を回す。`data/` は部屋が作る |

他社の参考の取り直し方: 記事の参考は `python3 ~/.claude/skills/kata-tsukuru/scripts/参考を保存する.py "<URL>" <記事のフォルダ>/参考/`。3つの形の固定の参考は、普通が `example/草むしり椅子/記事_1_時間で変化/`（参考の URL は同じフォルダの `参考を取り直す.md`）、リスティクルが `~/Claude Code/kata-tsukuru/runs/listicle-native/型.md`、ランキングが `~/Claude Code/kata-tsukuru/runs/ranking-static/型.md`（中の URL を同じコマンドで取り直す）。
