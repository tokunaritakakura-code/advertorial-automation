---
name: website-copy
description: >
  公開WebページのURLを渡すと、ピクセル一致の静的完コピを作り、必要なら
  Shopifyの非公開テーマに商品ページとして移植するスキル。
  生HTML取得→トラッキング除去＋アセットのホットリンク化→ヘッドレスChromeで
  動的要素（価格換算・レビュー・フォーム）を焼き込み→スクショ差分で答え合わせ。
  トリガー: /website-copy <URL>、「このページ完コピして」「このLPをShopifyに移植して」。
  画面収録からのUI再現は kankopi、ゼロからのサイト構築は higgsfield-websites。
---

# website-copy — 公開ページの完コピ → Shopify移植

スクリプトは `~/.claude/skills/website-copy/scripts/`（各ファイル冒頭に詳細コメントあり）。
Shopify移植の手順・制約は `references/shopify-integration.md`（移植時は必読）。

**このファイルの並び順は意図的。** 冒頭＝外せない関門、中盤＝参考、末尾＝実行手順。

---

<gates>

# 1. 関門 — ここを通らないものは成果物にしない

## 大原則

1. **ライブ(MAIN)テーマには絶対に書かない。** 完コピは非公開テーマへ（MCPもブロックする仕様）
2. **スクショ差分で確認するまで「完成」と言わない。** 答え合わせループが本体
3. **権利・許可のあるページに使う**（自社LP・許諾済みファネルの移植が想定用途）

## 差分の読み方

差分が大きい500px帯を特定→原因（**大半はbakeの焼き込み漏れ**）を直して再実行。
動画の再生フレーム・カウントダウン秒など**構造的に一致不能なランタイム要素の残差は無視してよい**。

## Shopifyに上げる時

- 商品は **DRAFT**、テーマは**非公開**
- themeFilesUpsert は body type: URL で送る（**ファイル内容をコンテキストに通さない**）
- 256KB制限があるので `chunk.mjs` で200KBスニペットに分割してから上げる

</gates>

---

<reference>

# 2. 参考

- `references/shopify-integration.md` — Shopify移植の手順・制約（移植時は必読）
- transform はトラッキング除去＋アセットを元ドメイン絶対URLに書き換える
  （**ホットリンク＝バイト単位で同一＝ピクセル一致の理由**）
- **bake が一番の肝。** curlでは空欄になる動的な穴（価格換算・レビュー・メールフォーム）を
  JS実行後のDOMで埋める。`manifest.json` の動的ウィジェット検出結果を必ず確認する
- `diff.py` は PIL が要るので `/opt/homebrew/bin/python3`（brew python）で叩く
- ページビルダー製（gempages / shogun / replo）は生HTMLが白飛びする。
  `bake.mjs` が副産物で吐く `original-dom.html`（JS実行後のDOM）を土台にする

</reference>

---

<procedure>

# 3. 実行手順

## Phase 1 — 完コピ生成

作業ディレクトリを作り（`mktemp -d`）、順に実行。

```bash
bash scripts/fetch.sh "<URL>" <outdir>              # → original.html（サーバーの生HTML）
node scripts/transform.mjs <outdir> "<origin>"      # → clone.html + manifest.json
node scripts/bake.mjs <outdir> "<URL>"              # → clone-baked.html（動的要素を焼き込み）
```

## Phase 2 — ローカル答え合わせ

```bash
bash scripts/screenshot.sh "<元URL>" <outdir>/orig.png
bash scripts/screenshot.sh "file://<outdir>/clone-baked.html" <outdir>/clone.png
/opt/homebrew/bin/python3 scripts/diff.py <outdir>/orig.png <outdir>/clone.png
```

## Phase 3 — Shopify移植（頼まれた時のみ）

`references/shopify-integration.md` を読んでから。

1. `node scripts/chunk.mjs <outdir> <suffix>` — 256KB制限回避のため200KBスニペットに分割 → `theme/`
2. Shopify MCP接続確認（`get-shop-info`、別ストアなら `switch-shop`）
3. stagedUploadsCreate（MCP）→ `node scripts/upload-gcs.mjs <targets.json> <outdir>/theme`
   → themeFilesUpsert
4. 商品作成（DRAFT）→ templateSuffix 割り当て → `onlineStorePreviewUrl` か
   `?preview_theme_id=` でプレビュー

## Phase 4 — 本番答え合わせ

プレビューURLと元URLをスクショ差分（Phase 2と同じループ）。
一致するまで bake→chunk→再アップロード。

</procedure>
