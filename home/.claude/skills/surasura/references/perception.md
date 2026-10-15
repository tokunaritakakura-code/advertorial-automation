# 画面をどう認識するか（2026-09-04 実測）

## 1. 他社はどう見て、どう触っているか

出どころは公式ドキュメント2本（下に URL）。両方とも **スクリーンショットだけ**を見る。DOM もアクセシビリティツリーも渡していない。

| | Anthropic computer use | OpenAI computer-use-preview |
|---|---|---|
| 入力 | 画面のPNG/JPEG 1枚 | 画面のスクショ1枚 |
| DOM / a11yツリー | 渡さない（公式に「pure visual-only perception」） | 渡さない |
| 出力 | 座標つきの行動（left_click / type / key / scroll / drag / zoom など17種） | click / double_click / drag / move / scroll / keypress / type / wait / screenshot |
| 座標系 | スクショのピクセル空間。実画面へは自分でスケールし直す | 同じ |
| 1手ごと | 行動のあと再びスクショを送り返して結果を確認する | 「短い行動のまとまりのあと、もう一度スクショを返す」 |
| 推奨解像度 | 1280×720 基準。1920×1080 超は避ける | 記載なし |
| スクショ1枚の代金 | **1,000〜1,800トークン**。1リクエストに20枚を超えると制限が厳しくなる | 記載なし |

Anthropic 側だけにある工夫が2つ。**zoom**（見たい矩形だけ原寸で取り直す。小さい文字とみっしり詰まったUI用）と、**行動のまとめ出し**（1返信に click→type→screenshot を並べて1往復にする）。

出どころ:
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- https://developers.openai.com/api/docs/guides/tools-computer-use

## 2. うちが同じ道を行かない理由（実測）

| | スクショ方式 | いまの dia look |
|---|---|---|
| 1回の代金 | 1,000〜1,800トークン | **237〜717トークン** |
| 取得時間 | 683ms（2026-08-27 実測） | **8〜105ms** |
| 掴み方 | 座標。外すと押す物がずれる | 番号かラベル。DOMが入れ替わっても特徴で掴み直す |

速さの正体は ms ではなく**外れ回数**。1回外すと「look → 手書きJSを書く → 試す」で 10〜30秒 溶ける。だから上げるべきは fps ではなく命中率。

## 3. 2026-09-04 に直したもの

Shopify のチェックアウトエディタ（`admin.shopify.com/.../settings/checkout/editor`）で `dia look --all` が **19要素**しか返さず、`dia click 画像を追加` と `dia click 中央` が両方 `ERR: 要素が見つからない` で落ちた。手書きの shadow DOM 探索を2回書く羽目になった。

原因は `dia-core.mjs` の道具一式が `document.querySelectorAll()` しか叩いていなかったこと。Polaris/Web Components の管理画面は中身が全部 shadow root の下にあるので、**画面に見えている物が1つも見えていなかった**。

直したこと（`dia-core.mjs`）:

- `D.roots()` / `D.qsa()` を追加。document → 全 shadowRoot → 同一オリジンの iframe まで潜る。250ms だけ結果を持ち回る
- `D.scan`（look）、`D.byLabel`（clickのラベル指名）、`D.resolve`（番号の掴み直し）、`D.snapshot`（押した後の変化判定）、`upload` の file入力さがしを全部 `D.qsa` に差し替え
- `pickTab` が `dia open` の返す**タブidでも掴める**ようにした。同じURLのタブが2枚あると URL 一部指定では別のタブを触ってしまっていた

同じページの実測（前 → 後）:

| | 前 | 後 |
|---|---|---|
| `dia look --all` の要素数 | 19 | **38** |
| 「中央」「右」「ロゴ」「幅」入力 | 見えない | 見える |
| `dia click 中央` | ERR | **OK** |
| 取得時間 | 108ms | 105ms |
| トークン | 160 | 287 |

普通のページ（arukoto.shop/pages/ar-insole）で 8〜42ms / 237〜352トークン、Meta広告マネージャ（要素5,024個）で shadow root 0個・walk は数ms。重くなっていない。

バックアップは `dia-core.mjs.bak-shadow`。

## 3b. 別オリジンの iframe も見えるようにした（同日）

`Target.setAutoAttach`（flatten）で子セッションを掴み、そこでも同じ道具を動かして番号を続きに混ぜる。iframe 由来の行は `⧉ホスト名` が付く。番号は「どのフレームの何番か」を覚えていて、`dia click <番号>` はそのフレームで動く。ラベル指名は本体で掴めなかった時だけ子枠を探す（今までの挙動は変えない）。

実測（Shopifyチェックアウトエディタ、中に本物の決済画面が入っている）:

| | 前 | 後 |
|---|---|---|
| 見える要素 | 38（本体だけ） | **81**（本体38＋決済画面43） |
| 決済画面の入力欄・支払ボタン | 見えない | 見える・押せる |
| 取得時間（2回目以降） | 105ms | 204ms |

普通のページは2回目以降 9ms。道具が既に入っている枠には入れ直さないので往復が増えない。

## 4. まだ直していない（重い順）

1. **look を2回叩くと同じ表を丸ごともう1回払う。** 差分だけ返す `--diff` があれば 287トークン → 50トークン程度になる。未実装
2. **行動のまとめ出しが弱い。** 今は `dia do` に手書きJSを書くしかない。`click → type → click` を1往復で書ける形が無い
3. **canvas / WebGL の中身は原理的に読めない。** ここだけはスクショ方式に落とすしかない
