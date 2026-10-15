---
name: browser
description: ブラウザを裏で操作して、本人の画面を一切触らずに調べ物・入力・クリック・トークン取得までやり切るスキル。既定はDiaの専用インスタンスを画面外に立てる方式（本人のDiaは触らない・タブを何枚でも並列で使える）。本人のログイン済みセッションが要る時だけ、本人のDiaにCDPで繋ぐ。発動:「ブラウザ触って」「お前が操作して」「ログインしてるやつで見て」「管理画面やっといて」「/browser」。リサーチ（/gethookd /voc-research /rival-census）とストア構築（/store）で使う。
---
> 目標1文で任せたい操作は `jev <url> "<目標>"`（Dia の裏タブで動く）。使い方は `~/.claude/手順/ブラウザ操作.md` の Jev 節。


# browser — ブラウザを裏で操作する

**本人の画面を奪わない。** カーソルもタブもフォーカスも触らない。

2モードある。**既定はA。** Bは本人のログイン済みセッションでしか見えない場所に入る時だけ。

| | A. 専用インスタンス（既定） | B. 本人のDiaに繋ぐ |
|---|---|---|
| 本人のDia | **触らない** | 起動し直す（タブが一瞬消える） |
| 本人への確認 | 要らない | **要る** |
| 並列タブ | **何枚でも**（実測: 10タブ0.42秒） | 1枚だけ（本人のタブに触らないため） |
| ログイン | 専用プロファイルに1回だけ通す | 本人のセッションをそのまま使える |
| 指紋 | 本物のChromeとして通る | 同上 |

**このファイルの並び順は意図的。** 冒頭＝外せない関門、中盤＝参考（引くもの）、末尾＝実行手順。

---

<gates>

# 1. 関門 — ここを通らないものは成果物にしない

## 本人の画面を触らない

- **`bring_to_front()` を呼ばない。** 呼んだ瞬間に本人の画面が変わる
- **合成クリック（CGEvent・cliclick・`System Events` の座標クリック）を使わない。**
  本人のカーソルを奪う。別ウィンドウに当たる。IMEで全角化する。
  どうしても要るなら、その場で本人に明示の許可を取る
- **スクショで画面を確認しない。** 一番手前のウィンドウしか写らないので、結局前に出すことになる。
  確認はDOMを読む（`pg.evaluate`）
- **クッキーの保管庫を複製しない。** v10暗号化で復号できないうえ、
  本人アカウントをスクレイプに使わない決まりに反する

## 立てたら必ず落とす

```bash
python3 ~/.claude/skills/browser/scripts/dia_agent.py stop
```

**作業が終わった時点で落とす。** 放置したブラウザは本人の環境で動き続ける。
モードBの時は、CDPポートを開けたまま常用しない
（9222が開いている間は、同じPCの他のプロセスからブラウザを操作できてしまう）。

## 取れなかったものを0件と書かない

ブロック・タイムアウト・真っ白なページを「該当なし」として下流に流さない。
判定は `~/.claude/skills/voc-research/scripts/netblock.py` を使う（シグネチャで見る。サイズで見ない）。

## スクロールする前に、スクロールが要るか確かめる

**多くのサイトは1ページ分が最初から入っている。** 実測で楽天は
6回スクロール（+5.76秒/ページ）しても 50件→50件・価格50件→50件で完全一致だった。

順番はこう。

1. スクロールなしで数える
2. 足りなければ**そのページが裏で叩いているAPIか埋め込みJSONを探す**（一番速い）
3. それも無ければ最下部へ1回送る
4. 人間らしい小刻みスクロールは**最後の手段**（30回で6.6秒。速度以外の利点は無い）

## 固定待ちを書かない

`wait_for_timeout(3500)` のような固定待ちではなく `wait_for_selector` で待つ。
実測: 楽天の検索ページで **3.50秒 → 0.12秒**、取れる中身は同一。

</gates>

---

<reference>

# 2. 参考 — 実測で分かっていること（引くもの。通読しない）

## 専用インスタンスの指紋（2026-08-22 実測）

Diaの実体を別プロファイルで起動し、CDPでPlaywrightから繋いだ状態。

| 見られるもの | 値 |
|---|---|
| User-Agent | `...Chrome/151.0.0.0 Safari/537.36`（**Headless の文字なし**） |
| `navigator.webdriver` | **false** |
| `navigator.plugins.length` | 5 |
| `window.chrome` | object |
| WebGL renderer | `ANGLE (Apple, ANGLE Metal Renderer: Apple M5, ...)`（実機） |
| `Sec-Ch-Ua` | `"Chromium";v="151", "Not=A?Brand";v="99"` |

**唯一の弱点は `Sec-Ch-Ua` が `Chromium` であること**（本物のChromeなら `Google Chrome`）。
ここを見ている相手には出る。それ以外は本物として通る。

**Playwright同梱のChromiumを使わない理由**: TLSフィンガープリント(JA3)が実在するどのChromeとも
一致せず、JavaScriptが1行も動く前に落とされる。Diaの実体ならその問題が無い。

**headless を使わない理由**: UAに `HeadlessChrome` が出るうえ、CDPの `Runtime.enable` と並んで
CloudflareとDataDomeが名指しで見ているシグナルに近い。画面外に普通のウィンドウを置く方が安全。

## 速さ（2026-08-22 実測）

| 見たこと | 結果 |
|---|---|
| 1タブ開いて遷移 | 0.08秒 |
| 5タブ | 0.23秒 |
| 10タブ | 0.42秒 |
| 楽天検索・固定3500ms待ち | 3.50秒 |
| 楽天検索・`wait_for_selector` | **0.12秒** |
| 楽天検索・スクロール6回 | +5.76秒（取れる中身は変わらない） |

`rakuten_browser.py` を上の2点で直した実測: **45.7秒 → 11.3秒**（1キーワード）。
取れた95件は旧版と**完全一致**（name/price/shop/url すべて）。

**同一ドメインには直列で投げる。** 並列にすると自分でブロックを誘発する。並列はホストをまたぐ時だけ。

## Cookieのコピーは通らない（2026-08-21 実測）

本人のDiaのプロファイルから `Cookies` をコピーしても、別インスタンスでは0件になる。
`v10` 形式でmacOS Keychainの「Dia Safe Storage」の鍵で暗号化されており、
コピー先では復号されずに静かに捨てられる（DBの2,374行はそのまま残るのに0件で返る）。

**だから専用プロファイルに1回ログインする方式にした。** 本人アカウントを使わない決まりとも合う。

## 詰まりどころ（実際に踏んだもの）

### フォームが送信されない

React/Remix が `click()` を握りつぶす。**ネイティブ送信に落とす。**

```python
pg.evaluate("""()=>{
  const f = document.querySelector('#その入力').closest('form');
  HTMLFormElement.prototype.submit.call(f);   // requestSubmit ではなく submit
}""")
```

### 入力しても値が消える

制御コンポーネントは `fill()` を無視する。**ネイティブsetter＋イベント発火。**

```python
pg.evaluate("""(v)=>{
  const el = document.querySelector('#id');
  const proto = el.tagName==='TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
  Object.getOwnPropertyDescriptor(proto.prototype,'value').set.call(el, v);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
}""", value)
```

### ボタンが押せない

`get_by_role("button")` が効かない時は **`<a>` かもしれない**。DOMを先に見る。

```python
pg.evaluate("""()=>[...document.querySelectorAll('button,a,[role=button]')]
  .filter(e=>/探す語/.test(e.innerText||''))
  .map(e=>({tag:e.tagName, t:e.innerText.trim().slice(0,30), href:e.getAttribute('href')||''}))""")
```

### チェックボックスを押しても反映されない

見えている選択UIが**本体ではない**ことがある。隠れた `textarea` / `input` が実体。
`document.querySelectorAll('input,textarea')` を全部出して name を読む。

### ページが真っ白／`chrome-error://`

リダイレクト先が死んでいる。**受け口を先に立ててから**遷移させる。

### モードBで本人のタブを触らない

Dia はタブを遅延読み込みするので `ctx.pages` の中身は毎回変わる。
**URLで探して見つからない前提で書く**
（`next((x for x in ctx.pages if ...), None) or ctx.new_page()`）。

`--enable-applescript-javascript` は Dia では効かない（Developerメニューに許可の項目が無い）。CDPだけが通る。

## 使う場面

| 場面 | モード | 何をする |
|---|---|---|
| 楽天・Amazon・広告ライブラリの取得（`/voc-research` `/gethookd` `/rival-census`） | A | ログイン不要な取得の高速化 |
| Threads・Instagram等 | A（専用プロファイルにログイン） | 検索モードで収集 |
| `/store` の構築 | B | Shopify管理画面の設定・アプリ導入・テーマ・ポリシー作成 |
| トークンが失効した時 | B | 下のOAuthの手順で取り直す |

</reference>

---

<procedure>

# 3. 実行手順

## モードA: 専用インスタンス（既定）

```bash
D=~/.claude/skills/browser/scripts/dia_agent.py
python3 $D start        # 画面外に立てる（既に動いていれば再利用）
python3 $D status       # 状態とタブ一覧
python3 $D stop         # ← 作業が終わったら必ず
```

繋ぐ。

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=40000)
    pg.wait_for_selector(SEL, timeout=20000)     # 固定待ちを書かない
    ...
    pg.close()
    b.close()            # connect_over_cdp の close はブラウザを落とさない
```

ログインが要るサイトは1回だけ通す。画面に出るのはこの時だけ。

```bash
python3 $D login https://www.threads.com/login
# → 画面にDiaが出る。人がログインして Enter。自動で裏用に立て直す
```

プロファイルは `~/.claude/browser-profiles/dia-agent`。作り直すなら `python3 $D reset`。

ネットワークが要るので `dangerouslyDisableSandbox` で実行する。

## モードB: 本人のDiaに繋ぐ

**先に本人に断る。** タブは復元されるが一瞬消える。未保存のものが無いか確認してもらう。

```bash
osascript -e 'tell application "Dia" to quit'
for i in $(seq 1 24); do pgrep -x "Dia" >/dev/null || break; sleep 0.5; done
open -a "Dia" --args --remote-debugging-port=9222 --remote-allow-origins=http://127.0.0.1:9222
sleep 8
curl -s -m 3 http://127.0.0.1:9222/json/version
```

繋ぎ方はモードAと同じ（ポートが9222）。**自分用のタブを1枚だけ作って、そこで完結させる。**
本人のタブに `goto` しない。終わったら自分のタブを閉じ、
Diaを普通に起動し直すことを本人に勧める。

## OAuth でトークンを取る（Shopify等）

Dev Dashboard のアプリは `shpat\_` を画面に出さない。**自分でOAuthを回す。**

1. アプリ設定でスコープを入れて**リリース**（バージョンを作らないと反映されない）
2. リダイレクトURL許可リストに `http://localhost:8765/cb` を入れて**もう一度リリース**
3. 資格情報から client_id と client_secret を取る（「シークレットを表示する」の aria-label のボタンを押す）
4. **先にローカルの受け口を起動する**（飛ばすと `ERR_CONNECTION_REFUSED` で認可コードが消える）
5. ブラウザで `https://{shop}/admin/oauth/authorize?client_id=..&scope=..&redirect_uri=..&state=..`
   - `oauth_error=same_site_cookies` が出たら、先に `https://{shop}/admin` を開いてセッションを張る
6. 受け口に来た `code` を `POST /admin/oauth/access_token` で交換
7. `~/.shopify-mcp.json` に書く

**秘密情報を標準出力に出さない。** ファイルに落として、先頭数文字だけ見せる。

</procedure>
