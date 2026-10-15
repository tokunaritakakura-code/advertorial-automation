# 知識の置き場ルール

seiyo-skills の `system/knowledge-routing.md` を、この環境（ads-brain + /study + /brain）に合わせたもの。
「取り込んだものをどこに、どの形で置くか」の正。**ノートの中身の規格は [note-standard.md](note-standard.md) が正。**

## インプットの振り分け

| 何を | どこへ |
|---|---|
| 教材の本体（動画・講座・PDF・記事の中身） | `Obsidian Vault/ec/wiki/ads-brain/sources/` に1本＝1枚（`/study` が書く） |
| 文字起こしの生データ | 同 `raw/`。人もClaudeも読まない。`slice.py` と grep だけが触る |
| 制作で読む形に統合したもの | 同 `playbooks/`。**制作スキル（`/ads`）が読むのはここだけ** |
| 教材どうしの食い違いと裁定 | 同 `_conflicts.md` |
| 作業に紐づくが教材ではない知識（手順・規格） | 該当skillの `references/` 直下 |
| どの作業にも紐づかない一般知識 | memoryのトピックファイル |
| 毎回守らせたい鉄則 | 該当SKILL.mdに数行追記（memoryに置かない） |

**skillの `references/` 直下は仕組み（手順・規格）専用。** 個人の知識ノートと混ぜない。

**memoryには「要点＋ありか＋注意点」の付箋数行だけ。** 中身の丸写し禁止。
付箋の1行は「将来の自分が何という言葉で探すか」で書く（要約ではなく検索キーを優先）。

## ノート化の規格（経路を問わず共通）

surasura経由でも、URLを貼られても、PDFを渡されても、ノート化は必ず [note-standard.md](note-standard.md) の規格で行う。

- **claim単位**。1claim = 1主張。前後の文脈なしで単体で読めること
- 必須タグ: `[出所 | 承認状態 | 位置(URL/タイムスタンプ) | 発信日 | 取得日]` ＋ 種類タグ
- 残すのは **[事実] / [手法] / [逆張り] / [失敗] / [接続]** の5種だけ。感想と一般論は捨てる
- 矛盾は消さずに `⇄反証:` で両論併記
- 陳腐化する領域（API・モデル序列・広告相場）は主張文に「時点情報(YYYY-MM)」を入れる

## ソースの承認

`sources.md` の台帳が正。回答は**承認済みソースの知識をベース**にし、未承認ソースは
ユーザーが明示的に求めた時だけ「未承認」と明示して使う。**承認・降格はユーザーだけが決める。**
取り込み時、台帳に無い新ソースは「未承認」として台帳に自動追記する。

## 新規ファイルを作る前に

既存をGlob/Grepで検索し、追記で済むなら追記を優先する。
`/brain` の `brain.py check` が地図落ち・重複・出典切れを検出するので、迷ったら先に走らせる。

## 昇格ルール（memory → CLAUDE.md / skill）

1. **禁止・鉄則**（怒られ系・再発防止） → 即、該当リポのCLAUDE.mdかskillに昇格して「入れた」と一言報告する。CLAUDE.mdは100行目安、効かなくなった行は削除
2. **事実・ポインタ・進行状態** → memoryのまま。昇格させない
3. **迷うもの** → memoryに置き、3回効いたら昇格候補として提案

## 設計の根拠

- エージェント側（Claudeが賢くなる仕組み）: [agent-learning-rationale.md](agent-learning-rationale.md) と [learning-science.md](learning-science.md)
- 人間側（ユーザー自身が学ぶ時のモード）: [human-learning-science.md](human-learning-science.md)
