# 学習科学の根拠 — kamikudakiの各セクションが「なぜその形か」

kamikudakiの出力構成は、認知科学の実証研究に基づく。各手法の効果量と出典、
そしてこのスキルでの実装方法。**要約を渡すこと自体には学習効果がほぼ無い**という
研究事実が出発点（下記 Dunlosky et al. 2013）。

## 効果の序列（総説）

**Dunlosky, Rawson, Marsh, Nathan & Willingham (2013).** Improving students'
learning with effective learning techniques. *Psychological Science in the
Public Interest, 14*(1), 4–58.
10種の学習テクニックを効果検証した決定版レビュー。

- **高効果**: ①検索練習（practice testing）②分散学習（distributed practice）
- **中効果**: 精緻化質問・自己説明・交互練習（interleaving）
- **低効果**: 再読・ハイライト・**要約**・キーワード記憶術

→ スキルへの含意: クイズ（§6）と復習スケジュール（Phase 4）は飾りではなく本体。
「要約だけ読んで分かった気になる」のを防ぐ設計にする。

## 1. 検索練習・テスト効果 → 🧪想起クイズ

- **Roediger & Karpicke (2006).** Test-enhanced learning: Taking memory tests
  improves long-term retention. *Psychological Science, 17*(3), 249–255.
  再読より想起テストの方が1週間後の保持が大幅に高い。
- **Karpicke & Blunt (2011).** Retrieval practice produces more learning than
  elaborative studying with concept mapping. *Science, 331*, 772–775.
  想起練習は概念マップ作成（精緻化学習）すら上回った。

実装: ダイジェスト末尾に5〜7問。事実確認だけでなく「なぜ」「もし〜なら」型の
推論問題を混ぜる。答えはすぐ見えない位置に置く（想起の努力を発生させるため）。

## 2. 分散学習・間隔反復 → Phase 4 復習スケジュール

- **Cepeda, Pashler, Vul, Wixted & Rohrer (2006).** Distributed practice in
  verbal recall tasks. *Psychological Bulletin, 132*(3), 354–380.
- **Cepeda et al. (2008).** Spacing effects in learning: A temporal ridgeline
  of optimal retention. *Psychological Science, 19*(11), 1095–1102.
  最適な復習間隔は「保持したい期間」に比例して伸びる。

実装: 1日後→1週間後→1ヶ月後の拡張間隔で「クイズを解き直す」復習を提案
（再読ではなく再テスト。§1との合わせ技）。

## 3. 事前テスト効果 → --quiz-first モード

- **Richland, Kornell & Kao (2009).** The pretesting effect: Do unsuccessful
  retrieval attempts enhance learning? *Journal of Experimental Psychology:
  Applied, 15*(3), 243–257.
  本文を読む前に質問に答えさせると、**間違えても**その後の学習が向上する。
- **Kornell, Hays & Bjork (2009).** Unsuccessful retrieval attempts enhance
  subsequent learning. *JEP: Learning, Memory, and Cognition, 35*(4), 989–998.

実装: --quiz-first では解説前に予想クイズを出し、ユーザーの回答を待ってから
本文解説に入る。「外れても効果がある」と一言添えて心理的ハードルを下げる。

## 4. 精緻化質問・自己説明 → 📌コアポイントの「Why」欄

- **Pressley, McDaniel, Turnure, Wood & Ahmad (1987).** Generation and
  precision of elaboration. *JEP: Learning, Memory, and Cognition, 13*(2), 291–300.
  「なぜそれが真なのか？」と問う精緻化質問が記憶を強化。
- **Chi, de Leeuw, Chiu & LaVancher (1994).** Eliciting self-explanations
  improves understanding. *Cognitive Science, 18*(3), 439–477.
  自分の言葉で説明し直すことが理解を深める。

実装: 各コアポイントに「なぜそう言えるか」を必ず付ける。ティーチバックモードは
自己説明をユーザー側に発生させる装置。

## 5. ICAP枠組み → ティーチバック提案

- **Chi & Wylie (2014).** The ICAP framework: Linking cognitive engagement to
  active learning outcomes. *Educational Psychologist, 49*(4), 219–243.
  学習効果は Interactive > Constructive > Active > Passive の順。
  受動的に読む(P) < メモを取る(A) < 自分の言葉で生成する(C) < 対話で修正し合う(I)。

実装: ダイジェストを読むだけだとPassive止まり。クイズでActive/Constructiveへ、
ティーチバック（ユーザーが説明→Claudeが添削）でInteractiveまで引き上げる。

- **Fiorella & Mayer (2013).** The relative benefits of learning by teaching
  and teaching expectancy. *Contemporary Educational Psychology, 38*, 281–288.
  「教えるつもり」で学ぶだけで効果あり（d=.59）、実際に教えるとさらに定着。
  → 「Feynmanテクニック」は俗称で直接の実証論文は無いが、この
  learning-by-teaching研究と自己説明研究（§4）が実質的な学術的裏付け。

## 6. 二重符号化・マルチメディア学習 → 📊図解

- **Paivio (1986).** *Mental representations: A dual coding approach.* Oxford
  University Press. 言語＋視覚の2経路で符号化すると記憶が強化。
- **Mayer (2009).** *Multimedia Learning* (2nd ed.). Cambridge University Press.
  言葉と対応する図を近接して提示すると理解が向上（マルチメディア原理）。
  ただし無関係な装飾は逆効果（一貫性原理）。

実装: mermaid図は「概念間の関係」が複雑なときだけ。飾りの図は出さない。

## 7. 先行オーガナイザ → 🗺30秒でつかむ全体像

- **Ausubel (1960).** The use of advance organizers in the learning and
  retention of meaningful verbal material. *Journal of Educational
  Psychology, 51*(5), 267–272.
  学習前に上位の枠組みを与えると、新情報が既有知識に接続されやすくなる。

実装: 冒頭に「中心主張＋これから何をどの順で説明するか」の地図を置く。

## 8. 望ましい困難 → 設計全体の思想

- **Bjork & Bjork (2011).** Making things hard on yourself, but in a good way:
  Creating desirable difficulties to enhance learning. In *Psychology and the
  Real World* (pp. 56–64). UCLA Bjork Learning and Forgetting Lab の中核概念。
  スムーズに感じる学習（再読等）は定着せず、適度な認知的負荷が長期記憶を作る。

実装: 「読みやすい要約を渡して終わり」にしない理由そのもの。クイズ・想起・
説明の負荷は意図的に残す。ただし本文理解のハードル（悪い困難）は噛み砕きで除去。

## 9. 生成効果・交互練習（補助）

- **Slamecka & Graf (1978).** The generation effect. *JEP: Human Learning and
  Memory, 4*(6), 592–604. 与えられるより自分で生成した情報は記憶に残る。
- **Rohrer & Taylor (2007).** The shuffling of mathematics problems improves
  learning. *Instructional Science, 35*, 481–498. 混ぜて練習する方が定着。

実装: 「🔗あなたへの接続」はユーザー自身の文脈で例を生成させる足場。
複数ソースを学んでいる場合、クイズに過去ダイジェストの問いを1問混ぜてよい。
