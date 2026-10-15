# この脳の設計根拠（何を、どの研究から取ったか）

2026-08-14 作成。引用は Crossref / OpenAlex で実在と書誌を確認済み（推測で書いていない）。

**前提として一番大事なこと**
学習研究の大半は「人間の記憶」を対象にしている。この脳を読むのはLLMで、LLMは忘れないし、
書いた本人と読む本人が別セッションになる。だから **Kiewra の言う2つの機能のうち、
encoding（書く行為そのものの効果）はこちらには乗らない。乗るのは external storage
（成果物としてのノートの質）だけ**（Kobayashi 2005, Contemporary Educational Psychology,
"What limits the encoding effect of note-taking? A meta-analytic examination"）。

したがって設計方針は1つに絞れる。
**「書く過程」で得をしようとしない。「後で読む人がゼロ文脈で使えるか」だけを最適化する。**

---

## 層1. 取り込み（教材 → 生テキスト → digest）

| 使った研究 | 何を言っているか | この脳での実装 |
|---|---|---|
| Mayer & Moreno 2003, *Educational Psychologist*「Nine Ways to Reduce Cognitive Load in Multimedia Learning」 | 分割（segmenting）・目印（signaling）・不要物の除去（weeding）で理解が上がる | digest.py が章に割り、指示や数字や禁止を機械で目印付けし、雑談を落とす |
| Sweller, van Merriënboer & Paas 1998, *Educational Psychology Review*「Cognitive Architecture and Instructional Design」 | 冗長性効果。同じ内容を2形式で同時に見せると負荷が増えて学習が下がる | 生テキストとdigestを両方読ませない。digestを読んだら生には戻らず、章単位でだけ取りに行く |
| Kalyuga, Ayres, Chandler & Sweller 2003, *Educational Psychologist*「The Expertise Reversal Effect」 | 詳しい説明は初心者には効くが、慣れた読み手には邪魔になる | playbookは8000字上限。制作時は地図から必要な1本だけ開く |

**採らなかったもの**: 全文を要約させる方式。要約は Dunlosky et al. 2013 で低有用度に分類されている（後述）。

---

## 層2. ノートの取り方（教材 → source ページ）

| 使った研究 | 何を言っているか | この脳での実装 |
|---|---|---|
| Chi, Bassok, Lewis, Reimann & Glaser 1989, *Cognitive Science*「Self-explanations: How students study and use examples in learning to solve problems」 | 成績の良い学習者は例を読みながら「なぜそうなるのか」を自分に説明している。説明の量が転移を分ける | 主張ごとに **「なぜそうなるのか」欄を必須**にした。教材が理由を言っていない場合は「理由の記載なし」と書かせる（空欄にしない） |
| Woloshyn, Willoughby, Wood & Pressley 1990, *Journal of Educational Psychology*「Elaborative interrogation facilitates adult learning of factual paragraphs」 | 事実に対して「なぜそれが本当か」を問わせると定着が上がる | 上と同じ欄。加えて「これが正しいなら何が起きるはずか」を書かせる |
| Mueller & Oppenheimer 2014 *Psychological Science*（+ 2018 Corrigendum）と、Morehead, Dunlosky & Rawson 2019 *Educational Psychology Review*「How Much Mightier Is the Pen than the Keyboard for Note-Taking?」 | 元論文は手書きがPCより良いとしたが、**2019年の追試で主効果は再現されなかった**。頑健に残っているのは「逐語率が高いノートほど理解が悪い」という相関の方 | **媒体の話は採らない。「逐語コピー禁止・自分の言葉で言い換える」だけを採る。** 確認用の逐語は主張1つにつき1文まで |
| Kiewra の note-taking 2機能論（Kobayashi 2005 のメタ分析で整理） | ノートには encoding（書く効果）と external storage（保管物としての価値）がある。後者の効果の方が安定して大きい | 後で読む側だけを最適化する。書式を固定し、機械が検査できる形にする |

**採らなかったもの**: Cornellノート方式。学術的な裏付けが薄い（検索して出てくるのは
2023年の看護教育の実践報告程度で、効果量を示した研究が見当たらない）。
形が有名なだけの方式をコピーしない。

---

## 層3. 統合（source → playbook）

ここが一番大事な層。**知識を別の商品・別のニッチに使い回せるかどうかは、ここの書き方で決まる。**

| 使った研究 | 何を言っているか | この脳での実装 |
|---|---|---|
| Gick & Holyoak 1983, *Cognitive Psychology*「Schema induction and analogical transfer」（および 1980「Analogical problem solving」） | **例が1つだと転移しない。2つ以上の例を比べて、共通する抽象的な型を言葉にした時に初めて転移する** | playbookに **「共通の型（スキーマ）」欄を必須**にした。さらに、ルールの状態を 仮説（出典1本） / 定説（独立した出典2本以上） に分け、**1本しか根拠が無いルールは「仮説」と表示する** |
| Catrambone 1998, *Journal of Experimental Psychology: General*「The subgoal learning model」 | 手順にサブゴールの見出しを付けると、初見の問題を解ける率が上がる。フラットな手順書は転移しない | playbookの手順を **サブゴール見出しで束ねる**。番号を並べるだけにしない |
| Renkl, Stark, Gruber & Mandl 1998, *Contemporary Educational Psychology*「Learning from Worked-Out Examples」 | 解答例（worked example）が有効。ただし例のばらつきと自己説明が伴う時に転移が上がる | playbookに **「お手本」欄を必須**。抽象ルールだけを置かない |
| Kirschner, Sweller & Clark 2006, *Educational Psychologist*「Why Minimal Guidance During Instruction Does Not Work」 | 手探りさせる指導は、完全な手順を与える指導に負ける | playbookは「〜を検討する」と書かない。命令形で、数字で書く |
| Hattie & Donoghue 2016, *npj Science of Learning*「Learning strategies: a synthesis and conceptual model」 | 有効な戦略は 表層（事実）→ 深層（関係）→ 転移 の段階ごとに違う。段階を取り違えると効かない | 脳の中を段階で分けた。sources=表層、playbook=深層と転移。制作で読むのは転移層だけ |

---

## 層4. 検証（書いたものが使えるかを確かめる）

| 使った研究 | 何を言っているか | この脳での実装 |
|---|---|---|
| Dunlosky, Rawson, Marsh, Nathan & Willingham 2013, *Psychological Science in the Public Interest*「Improving Students' Learning With Effective Learning Techniques」 | 10手法を有用度で格付けした。**高：練習テスト（practice testing）と分散学習。低：要約、ハイライト、再読** | **要約で終わらせない。** playbookを書いたら閉本テストを必ず1回通す（`selftest.py`）。ハイライト相当の作業（原文の抜き書き）は成果物に残さない |
| Roediger & Karpicke 2006, *Psychological Science*「Test-Enhanced Learning」 | テストは記憶の測定ではなく、記憶そのものを強くする | 同上。テストは統合の後ではなく、統合の一部として組み込む |
| Karpicke & Blunt 2011, *Science*「Retrieval Practice Produces More Learning than Elaborative Studying with Concept Mapping」 | 概念マップを作るより、思い出す練習の方が学習効果が高い | 綺麗な体系図を作る作業を増やさない。テストで穴を出す方に時間を使う |
| Bjork & Bjork 2011「Making things hard on yourself, but in a good way」 | 楽に感じる勉強法は効いていない。適度な困難が定着を生む | テストは選択式にしない。**playbookだけを見て、実際に広告を1本書けるか**で判定する |

**この層でやっていること**: source から質問を作り、**playbook だけを見て答える**。
答えられなければ playbook に穴がある。要約が上手くできたかではなく、
**外部保管物として機能するか**を測っている。

---

## 層5. 再利用（制作時に読む）

| 使った研究 | 何を言っているか | この脳での実装 |
|---|---|---|
| Sweller et al. 1998（分割注意効果） | 1つの判断に要る情報が複数箇所に散っていると負荷が上がる | 1つの判断に要るものは1つのplaybookに閉じる。またぐなら地図に「2本読む」と書く |
| Kalyuga et al. 2003（熟達の逆転効果） | 説明が増えるほど良いわけではない | 8000字を超えたら割る。地図は100行を超えさせない |
| Cepeda, Pashler, Vul, Wixted & Rohrer 2006, *Psychological Bulletin*「Distributed practice in verbal recall tasks」 | 間隔を空けた反復が定着を生む | **これは人間の記憶の話なので、そのままは採らない。** 採ったのは「時間を空けて見直す枠を作る」という運用だけ。playbookに `updated` を持たせ、古いものを check が拾えるようにしている |

---

## どこまでが研究で、どこからが類推か（ここを混ぜない）

**引いた論文はどれも、広告制作について何かを示したものではない。**
実験の対象は、学生の文章理解、数学の手続き学習、単語の再生、放射線問題の類推転移などで、
「LLMが読む手順書」を扱った研究は1本も無い。だから正直に線を引いておく。

| 研究がそのまま言っていること | この脳での使い方 | どちらか |
|---|---|---|
| 逐語率の高いノートは理解が低い（人間の学習者） | 逐語コピーを禁止する | **類推**。ただし保管物の質としても筋が通る |
| 2例以上の比較でスキーマができ、転移する（Gick & Holyoak 1983、放射線問題） | 出典1本のルールを「仮説」に留める | **類推**。ただし「1例からの一般化は危険」は統計的にも正しい |
| サブゴール見出しが初見問題の正答率を上げる（Catrambone 1998、数学と統計の手続き） | 手順をサブゴールで束ねる | **類推**。広告制作の手順で検証したわけではない |
| 練習テストは要約より学習効果が高い（Dunlosky et al. 2013） | 書いた playbook を閉本テストする | **半分は直接**。ここで測っているのは記憶ではなく「playbookだけで復元できるか」なので、テストの目的が違う |
| 分割・目印・不要物除去が理解を助ける（Mayer & Moreno 2003） | digestの章割りと目印付け | **類推**。人間の注意資源の話をトークン予算の話に置き換えている |
| 間隔を空けた反復が定着させる（Cepeda et al. 2006） | **使っていない** | LLMは忘れないので、そのままでは意味が無い |

**この表の意味**: 上のどれかが後で外れても、脳の構造は壊れない。
外れた時に直すのは「なぜその欄があるか」の説明であって、欄そのものではない。
逆に言うと、**この設計は「研究がそう言っているから正しい」ではなく、
「この形にしておくと、後で間違いを見つけられる」から採っている。**

## この設計で意図的に切ったもの

| 切ったもの | 理由 |
|---|---|
| Cornellノート / SQ3R などの形式 | 効果量を示した研究が見当たらない。形が有名なだけ |
| 手書き推奨 | 2019年の追試で再現されていない（Morehead et al. 2019） |
| 要約中心のノート | Dunlosky et al. 2013 で低有用度 |
| 概念マップの自動生成 | Karpicke & Blunt 2011 でテストに負けている。作る手間の割に効かない |
| ゲーミフィケーション・学習スタイル適合 | この用途に関係がない |

---

## 参考文献（すべて書誌確認済み）

- Bjork, E. L., & Bjork, R. A. (2011). Making things hard on yourself, but in a good way.
- Catrambone, R. (1998). The subgoal learning model. *J. Exp. Psychol.: General*.
- Cepeda, N. J., Pashler, H., Vul, E., Wixted, J. T., & Rohrer, D. (2006). *Psychological Bulletin*.
- Chi, M. T. H., Bassok, M., Lewis, M. W., Reimann, P., & Glaser, R. (1989). *Cognitive Science*.
- Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham, D. T. (2013). *PSPI*.
- Fiorella, L., & Mayer, R. E. (2015). Eight Ways to Promote Generative Learning. *Educ. Psychol. Rev.*
- Gick, M. L., & Holyoak, K. J. (1980; 1983). *Cognitive Psychology*.
- Hattie, J., & Donoghue, G. M. (2016). *npj Science of Learning*.
- Kalyuga, S., Ayres, P., Chandler, P., & Sweller, J. (2003). *Educational Psychologist*.
- Karpicke, J. D., & Blunt, J. R. (2011). *Science*.
- Kirschner, P. A., Sweller, J., & Clark, R. E. (2006). *Educational Psychologist*.
- Kobayashi, K. (2005). *Contemporary Educational Psychology*.
- Mayer, R. E., & Moreno, R. (2003). *Educational Psychologist*.
- Morehead, K., Dunlosky, J., & Rawson, K. A. (2019). *Educational Psychology Review*.
- Mueller, P. A., & Oppenheimer, D. M. (2014; Corrigendum 2018). *Psychological Science*.
- Renkl, A., Stark, R., Gruber, H., & Mandl, H. (1998). *Contemporary Educational Psychology*.
- Roediger, H. L., & Karpicke, J. D. (2006). *Psychological Science*.
- Sweller, J., van Merriënboer, J. J. G., & Paas, F. (1998). *Educational Psychology Review*.
- Woloshyn, V. E., Willoughby, T., Wood, E., & Pressley, M. (1990). *J. Educational Psychology*.
