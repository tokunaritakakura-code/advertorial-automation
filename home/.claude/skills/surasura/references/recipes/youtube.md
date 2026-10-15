# レシピ: YouTube

## 最速経路
`bash scripts/yt-ingest.sh <url> [outdir]` — ブラウザ不要・再生不要の完全機械経路。
出力の `manifest.md`(文字起こし×キーフレームの時刻同期統合)が学習素材。**字幕単体で学習しない。**

- 手動字幕あり(投稿者が付けたもの=正確): 字幕直取得で数秒
- 手動字幕なし: 音声だけDL→ローカルWhisper large-v3-turbo。**自動生成字幕は精度が悪いので使わない**
- 映像: DL→ `frames.py` が場面転換(scene score)+45秒間隔フロアで最大150枚、768pxに縮小。
  抽出は8並列、画が動いていないコマはdHash(ハミング距離4)で破棄
- **同じ動画は2度取らない**: `~/.claude/skills/surasura/.cache/<動画ID>/` にmanifestがあれば即返す
  (実測 2026-08-27: 初回48.9s → 2回目0.01s)。取り直しは `NO_CACHE=1`
- 出力: manifest.md(人間/Claude用) + beats.json({t,frame,caption}, 下流エージェント用) +
  montage/(時刻+字幕チップ付きcontact sheet 30コマ/枚)
- **2段読み**(2026-08-15導入, 元ネタ=yt-video-ingest-kitのcontact.py): まずモンタージュで全景→
  情報の濃いコマだけ個別768pxを精読。個別20枚読みよりトークン数倍安い
- キーフレームはClaudeが画像として読む。スライド/コードの文字でWhisperの固有名詞ミスを訂正(相互補正)
- 映像DLが全滅したら `yt-grab.mjs`: 統一ブラウザで`<video>`をseek→要素スクショ(等間隔N点、
  プレイヤーUIはCSSで消す、広告はスキップ試行)。DL規制がどれだけ強まっても死なない最終手段。
  共有ブラウザを占有するのでシリアル実行のみ。実測8/8成功(2026-08-15)

## セットアップ(導入済み 2026-08-15)
- `brew install whisper-cpp`(whisper-cli) / モデルの実体は `~/.cache/whisper/ggml-large-v3-turbo.bin`(1.5GB)。
  yt-ingest.sh は `~/.cache/whisper/` → `~/Library/Caches/whisper-cpp/` の順に探す
  (差し替えは env `SURASURA_WHISPER_MODEL`)
- yt-dlp / ffmpeg はHomebrew導入済み

## チャンネル一括(大規模モード)
チャンネルURL→動画一覧の展開は `scripts/yt-channel.mjs --channel <url> --limit N`(旧task-fleetから移植、実測済みで堅い)
(`/videos` タブに正規化してShorts二重展開を防ぐ・android player clientで字幕スロットル回避)。
一覧だけ拝借し、各本は yt-ingest.sh をWorkflowで並列に回す。

## 第3の脚(オプション): Gemini直視聴
GeminiのAPIはYouTube URLを渡すだけで動画を直接視聴できる(公式機能, 1fps+音声, 公開動画のみ,
無料枠8時間/日)。DLもASRも不要の最短経路だがGoogle依存。急ぎ・大量の下見に使い、本学習はyt-ingestで。

## 実測の速度表(2026-08-27, 18分40秒の動画・M系Mac 10コア)

| 工程 | 実測 | 備考 |
|---|---|---|
| メタ+手動字幕 | 数秒 | 字幕があればWhisper不要 |
| 映像DL(360p 35MB) | 4〜8s | |
| 場面転換検出 | 2.5s | 全解像度デコード |
| フレーム抽出60枚 | 1.71s → **0.46s** | 8並列化(2026-08-27) |
| yt-grab 撮り直し43枚 | 約35s | シリアル・プレイヤー実解像度 |
| **Whisper large-v3-turbo** | **59s / 18.6分音声** | 約19倍速。ここが最大のコスト |
| 全部込み(手動字幕あり) | **48.9s** | 2回目はキャッシュで0.01s |

**却下した高速化案(実測して効かなかった。もう試さない)**
- Whisperを貪欲デコードに(`-bs 1 -bo 1`): 59s→52s(12%)しか縮まないのに単語一致率93.5%まで崩れる。精度負け
- Whisperを4分割して並列(`-P 4`): 59s→**63s**。Metalが既に飽和していて逆に遅い
- 場面転換検出の前に320pxへ縮小: 2.5s→**3.5s**。scaleの方が高くつく

## 映像の解像度(2026-08-27 実測・重要)

**動画によっては720pが403になり、その時yt-dlpは360p(format 18)を"成功"として返す。**
実測(aircAruvnKk, 3Blue1Brown): 720p(format 398 av01)は default でも 統一Chromeのcookie付きでも
**403 Forbidden**。android/mweb は 360p しか持っておらず、web_safari/ios は「format not available」、
tv は「page needs to be reloaded」。一方 BBJa32lCaaY では 398 が普通に落ちた。
→ 403に当たった動画は**黙って360pのコマで学習していた**(スライド・コード画面の文字が潰れる)。
403の出方は動画ごとに違うので、解像度は毎回ffprobeで確認する。

対策(yt-ingest.shに実装済み): 降ってきた映像の高さが `MIN_HEIGHT`(既定720)未満なら、
`frames.py --times-only` に**時刻だけ**選ばせ、`yt-grab.mjs --times-file` が
ブラウザのプレイヤーから撮り直す(実測1920x1080 → 768pxに縮小して保存)。
場面転換の選び方はそのまま・画は本来の解像度、という組み合わせ。撮り直しを止めるなら `NO_HIRES=1`。

## 落とし穴
- **映像DLの403 Forbidden**(2026-08-15実測): 既定クライアントが選ぶフォーマットが403になることがある。
  `--extractor-args "youtube:player_client=android"` で通った(yt-ingest.shにフォールバック実装済み)。
  iosクライアントはstoryboardしか返さない・tvは要PO token。全滅したらyt-dlpの更新を最初に疑う
- YouTubeはクラウド/データセンターIPをほぼブロック(`Sign in to confirm you're not a bot`)。
  ローカルMac(住宅IP)なら無縁。**このパイプラインをクラウドに移植しない**
- Whisperは動画の尻を超えて幻覚することがある → yt-ingestがduration超の行を捨てて対策済み
- Whisperの固有名詞ミス対策: タイトル+章題を `--prompt` に渡している(2026-08-27導入・速度は不変)
- 手動字幕の優先順は ja-orig > ja > en-orig > en。**原語が英語でも和訳字幕があればそちらを採る**ので、
  話者の原語表現をそのまま引用したい時は en を指定して取り直す
- 自動字幕VTTは行が2-3回重複する(進行表示) → to_segments.py がdedupe(そもそも自動字幕は不使用)
