# EC contract v1

共通エンジンは `config/brands.json` を読む。ブランド名は完全一致の明示入力で、未指定・未知・別口座は拒否する。設定・承認DB・エンジンは制作エージェントの書き込み対象にしない。

## Manifest

```json
{
  "schema_version": 1,
  "brand": "ブランド名",
  "job_id": "job-001",
  "mode": "live",
  "revision": 1,
  "account_id": "登録済み口座",
  "expires_at": "2026-10-03T00:00:00+09:00",
  "artifacts": [{"id": "video", "revision": 1, "path": "ブランド素材ルート内の絶対パス", "sha256": "64桁のSHA-256"}],
  "actions": [{"id": "start", "operation": "activate", "target": "対象ID", "account_id": "登録済み口座", "depends_on": [], "payload": {"step": {"する": "動かす", "id": "対象ID"}}}],
  "evidence": {
    "brand": "ブランド名", "revision": 1, "status": "executable",
    "checks": [{"name": "preflight", "status": "pass"}],
    "reviewer": {"status": "pass", "review_id": "保存済み独立レビューreceipt", "rules_hash": "基準のSHA-256", "context": "ブランド名/job-001/1/review/毎回新しいID", "artifact_hashes": ["全素材のSHA-256"]}
  }
}
```

操作は create_ad / activate / pause / set_budget / publish / generate_local / validate_local / verify_artifact。任意shellは契約操作にしない。create_ad は artifact_id、set_budget は金額 amount、ローカル操作の target はブランド素材ルート内を必須とする。depends_on は前の操作IDだけ参照できる。実行側は契約の payload と実際の送信注文・手順の完全一致を確認する。

status は rejected / insufficient_evidence / valid_structure / executable。dry-run は executable にならない。検査対象0や欠測は適切に insufficient_evidence とし、実行可能という意味にしない。検査レコードの真実性は実行側の記録担当が保証する。ライブのレビューは固定DBに保存されたreceiptを必須とする。任意のPASS文字列・context・ハッシュ一覧だけでは本人承認も実行も通らない。

## 独立レビュー

新規SDK sessionの完了callbackだけが `trusted-review-record` を呼ぶ。公開API・delegate tool・制作toolには登録しない。SDKの最終結果は厳密なJSON `decision: PASS/FAIL` と、渡した全artifact_hashesおよびrules_hashの完全一致を確認する。実際のrun_id、brand/job/revision、fresh context、判定を固定DBへ記録し、返されたreview_idをmanifestへ入れる。run_idは一度しか記録できない。レビューreceiptがない、別ブランド／案件／版、異なる素材や基準、FAILなら本人承認を発行しない。

```text
python3 -B lib/ec_contract.py trusted-review-record
stdin: {"brand":"登録ブランド", "job_id":"job-001", "revision":1, "context":"brand/job/revision/review/新規ID", "artifact_hashes":["素材SHA-256"], "run_id":"実際のSDK run", "rules_hash":"基準SHA-256", "decision":"PASS"}
stdout: {"schema_version":1,"review_id":"固定DB receipt",...}
```

Python内部では `StateStore.record_review(scope, artifact_hashes, run_id, rules_hash, decision)`、`read_review(review_id, job)` を使う。`validate_job(..., trusted_review=保存済みreview)` は信頼済みアプリ内部と隔離テスト用で、ライブCLIはinline reviewを信用せず固定DBから読む。

## 承認

canonical JSON 全体のSHA-256で、操作・金額・時刻・素材版・検査・レビューを固定する。ハッシュは認証署名ではない。認証した本人UIだけが `trusted-owner-approve` を呼び、保存されたランダム approval_id を実行側へ渡す。制作・delegateツールにはissuer、Bash、設定／DBの書き込みを渡さない。ローカルOSユーザーを攻撃者から隔離する新しいシステム権限設定は、この修正では行わない。

```text
python3 -B lib/ec_contract.py trusted-owner-approve
stdin: {"job": manifest, "owner": "登録済み本人識別子", "expires_at": "期限付き日時"}
stdout: {"schema_version":1,"approval_id":"receipt ID",...}

python3 -B lib/ec_contract.py validate
stdin: {"job": manifest, "approval_id": "receipt ID"}
stdout: {"schema_version":1,"status":"executable",...}
```

ライブCLIは固定の `config/brands.json` と `data/control.sqlite3` を使う。inline承認、任意DB、ライブ設定上書き、環境変数による承認設定は使わない。保存済みreceiptのブランド・案件・mode・revision・manifestハッシュ・期限を照合する。scheduled_atはtimezone付きで案件期限より前、承認期限より前でなければならない。案件expires_atも承認期限以内でなければならず、validateはauthorization_expires_atを返す。予約投入前と各mutation直前に再検証する。過去のscheduled_atは再試行のため許容するが、案件と承認の期限切れは許容しない。承認の最大期間は設定値を超えず、遠い未来の予約は本人が適切な時点で再承認する。期限を自動延長しない。本人UIはsame-originとCSRFを確認し、本人が見たmanifestハッシュとクリック時のハッシュが一致する場合だけ発行する。既存の文章「OK」はライブ承認へ変換しない。

## 状態・再開・学習

`StateStore(path)` は隔離テスト／信頼済みアプリ内部で利用する。register(job,config)、acquire(brand,job,mode,holder)、checkpoint(job,holder,stage,status,evidence,dependencies)、resumable(job,stage)、append_lineage(job,holder,kind,payload)、release(...)。SQLiteトランザクションで段の保存と履歴を一緒に確定する。リースがない別ワーカーは記録できない。

checkpointのevidenceにはbrand/revisionが必要。outputsを記録する場合、ブランド素材ルート内の実ファイルpath/sha256が必要。完了記録は変更不可。同じmode/revision/入力manifestだけを再開でき、入力・出力が改変／消失／symlink逸脱した場合は再開できない。delivery完了はliveのみでreceipt_idが必要。制作完了と配信設定完了とeffective deliveryと実納品は別の状態として呼び出し側が記録する。

metrics履歴はbrand/revision/period_start/period_end/ad_ids/sourceを必須とし、登録されたブランドの計測元と一致させる。独立した週の証拠は期間が重複しないことを independent_periods() で確認する。各履歴でartifact ID/version、approval_id、配信先ID、次の判断IDを保存する。関数の存在だけで実案件の記録が完成するものではない。

レビューのcontextは reviewer_context(brand,job_id,revision) で毎回新しく作る。別案件sessionのresumeは禁止し、渡すのは対象版の成果物と基準のみとする。

## 検証

```sh
python3 -B -m unittest discover -s tests -p test_contract.py -v
node --check lib/contract_bridge.mjs
```

テストは一時フォルダ・模擬ブランド・ローカルSQLiteのみ。CLIテストはコアと設定を一時フォルダへ複製して固定相対パスを維持し、本番DB・APIへ接続しない。ここちドライの未確定テスト合格線等はnullのままにし、呼び出し側は判断を停止する。
