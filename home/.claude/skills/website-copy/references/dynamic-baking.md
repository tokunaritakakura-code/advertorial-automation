# 動的コンテンツの焼き込み（bake）— 一番の肝

curlで取った生HTMLには「JSが後から中身を入れる空欄」がある。ヘッドレスChromeで実際に描画させて
`--dump-dom` でJS実行後のDOMを取り、その完成後の中身を静的HTMLに移植する。`bake.mjs` が下の3パターンを
manifest.json のフラグで自動判定して処理する。

## パターン1: 価格換算（通貨アプリ）

- 症状: 生HTMLは `$199` のまま（USD）。実際は通貨換算アプリ（bucksCC等）がJPY等に書き換えている。
- 焼き込み: DOMの `bucks-original`/`bucks-current` 属性から換算表を作り、生HTMLの `<span class=money>$X</span>` を
  換算後スパンに置換。**放置するとドル表示のままになるので必須**。
- 別アプリの場合: DOMで実際に表示されている金額の属性名を確認し、置換ルールを足す。

## パターン2: レビューウィジェット（Loox等のiframe型）

- 症状: 生HTMLは空の `<iframe id="looxReviewsFrame" src="https://loox.io/...">` だけ。中身は別オリジン。
- 焼き込み: そのsrcをfetch → `<script>`除去 → 相対URL絶対化 → **`body{visibility:hidden}` を visible で上書き**
  （Looxは自分をhiddenにしてJSで表示する設計。上書きしないと真っ白）→ `srcdoc` 属性に丸ごと埋め込む。
  さらに親ページに「iframe内の高さを読んで自動フィット」する小スクリプトを足す（同一オリジンなので読める）。
- 別サービス（Judge.me / Yotpo / Stamped）の場合: iframe型なら同じ手が効く。インライン注入型なら
  DOMから該当コンテナのサブツリーを抜いてプレースホルダ差し替え（パターン3と同じ発想）。

## パターン3: メールフォーム（Klaviyo等）

- 症状: 生HTMLは空の `<div class="klaviyo-form-XXXX">` プレースホルダ。JSがフォームを注入する。
- 焼き込み: DOMから同じidのコンテナ（バランスの取れた `<div>` サブツリー）を抜き、生HTML側の
  プレースホルダと差し替える。

## 新しいウィジェットが出てきたら

1. `bash scripts/screenshot.sh` で元と完コピを撮り `diff.py` で差分帯を出す。
2. 差分が大きい帯＝焼き込み漏れ。その領域のDOM（original-dom.html）と生HTML（clone.html）を見比べ、
   「生HTMLで空 / DOMで中身あり」の箇所を特定。
3. iframe型か・インライン注入型かを見て、パターン2か3の手を当てる。`bake.mjs` に新ルールを追記。

## 構造的に一致できないもの（追わない）

- 自動再生動画の**再生フレーム**（撮る瞬間で絵が変わる）
- **カウントダウンの秒数**（常に現在時刻基準）
- スクロール発火の**アニメ途中状態**
これらは残差として許容する。デスクトップ差分1〜2%はほぼこれ。
