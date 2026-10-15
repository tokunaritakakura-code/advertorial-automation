// GetHookd の勝ちVSLを、ログイン済みの Dia のタブから内部APIで取る（MCPもクレジットも使わない）。
// `hookd.sh` から「投げる → 待つ → 読む」の3回に割って走る。画像は1枚も返らない。
//
// **ここで待ってはいけない**（2026-09-22 実測）。取得は 8〜15秒かかり、`dia do` の中で await すると
// CDP の評価が時間切れになって **undefined が黙って返る**（件数0と区別が付かず、朝のGetHookdが2回飛んだ）。
// だから取得は投げっぱなしにして `window.__hookd` に置き、hookd.sh が別の `dia do` で拾う。
//
// 2つの枠を別々に取る（本人 2026-09-22「もっとAIネイティブのVSLを見つけて欲しい」）。
//   AI      … AIで作った動画。作り替えの元になる（2026-09-22 実測 126本／1社1本で17社）
//   VSL着地 … 着地がVSLページか記事の長尺。構造を借りる元（同 558件）
//
// 欄の名前は 2026-09-22 に実測で確かめた物だけ使う。**間違った名前は黙って無視されて件数が減らない**:
//   効く:     page_type / ad_format / video_lengths / performance_scores / ads_per_brand_limit
//             is_ai_generated（full / partial）/ language
//   効かない: page_types / ad_formats / landing_page_types / ai_generated / cls_is_ai_generated
// `is_ai_generated` と `page_type` を同時に付けると0件（AIの行に着地が記録されていない）ので分ける。
// 言語は絞らない（en だけにすると17社→6社に落ちる。構造を借りるので言語は問わない）。
window.__hookd = null;
window.__hookdErr = null;

(async () => {
  function ck(n) {
    return (document.cookie.match(new RegExp("(^| )" + n + "=([^;]+)")) || [])[2];
  }
  const x = ck("XSRF-TOKEN");
  const h = { "content-type": "application/json", accept: "application/json" };
  if (x) h["X-XSRF-TOKEN"] = decodeURIComponent(x);

  const 共通 = {
    performance_scores: ["winning", "optimized"],                    // 81点以上
    ad_format: ["video"],
    video_lengths: ["1_to_3_min", "3_to_5_min", "more_than_5_min"],  // 60秒未満を外す
    ads_per_brand_limit: 2,                                          // 1社が埋め尽くさないように（2026-09-30 1→2。夜に毎晩6本借りると1社1本の17社では2晩で尽きる）
    page: 1,
  };
  const 枠 = [
    ["AI", { ...共通, is_ai_generated: ["full", "partial"] }],
    ["VSL着地", { ...共通, page_type: ["vsl_page", "advertorial"] }],
  ];

  async function 探す(cond) {
    const r = await fetch("/api/get-ads", { method: "POST", headers: h, body: JSON.stringify(cond) });
    if (r.status === 401 || r.status === 419 || r.redirected) throw new Error("ログイン切れ（" + r.status + "）");
    if (r.status !== 200) throw new Error("get-ads が " + r.status);
    try { return await r.json(); }
    catch (e) { throw new Error("JSONが返らない（ログイン切れの画面の可能性）"); }
  }

  const N = Number("__N__");
  const 全体 = {};
  const 見た = new Set();
  const out = [];
  try {
    for (const [名, cond] of 枠) {
      const j = await 探す(cond);
      全体[名] = j.filtered_ads_count;
      let n = 0;
      for (const a of (j.data || [])) {
        if (n >= N) break;
        if (見た.has(a.id)) continue;    // AI枠を先に見るので、重なった物はAI扱いで残る
        見た.add(a.id); n++;
        out.push({
          枠: 名, id: a.id, external_id: String(a.external_id || ""),
          brand: (a.brand && a.brand.name) || "", title: a.title || "",
          landing_page: a.landing_page || "", language: a.language || "",
          performance_score: a.performance_score || 0, days_active: a.days_active || 0,
          share_url: a.share_url || "", video_length_seconds: 0, download_url: "", page_type: "",
        });
      }
    }
    if (!out.length) { window.__hookdErr = "0件（全体 " + JSON.stringify(全体) + "）"; return; }

    // 1本ずつの中身（尺と動画の落とし先）。これが無いと60秒の線が引けない
    for (const o of out) {
      try {
        const d = await (await fetch("/api/get-ad/" + o.id, { headers: h })).json();
        const ad = d.ad || d.data || d;
        const m = (ad.medias || ad.media || [])[0] || {};
        o.video_length_seconds = m.video_length || 0;
        o.download_url = m.download_url || "";
        // get-ad は page_type を返さない事が多い。条件で絞っているので枠の名前で埋める
        o.page_type = ad.page_type || (o.枠 === "VSL着地" ? "vsl_page/advertorial" : "");
      } catch (e) { /* 1本落ちても他は出す。秒0のまま出して後段の線で落とす */ }
    }
    window.__hookd = JSON.stringify({ 全体, 広告: out });
  } catch (e) {
    window.__hookdErr = String(e.message || e);
  }
})();
return "投げた";
