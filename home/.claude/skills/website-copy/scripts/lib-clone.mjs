// lib-clone.mjs — 完コピ共通ロジック（transform.mjs / bake.mjs から利用）
// 静的完コピの原則: 描画後DOMを凍結したら、ページ自身の実行スクリプトを剥がして
// 「二度と自己再描画しない」状態にする。これをやらないと、別ドメイン/別Shopifyストアに
// 移植した時に残存アプリJSが再実行され、移植先の実データで枠を描き直す（＝汚染）。

// ---- ① トラッキング/解析スクリプトの部分一致リスト ----
export const STRIP_SRC = ['intelligems', 'klaviyo', 'perf-kit', 'load_feature', 'init-shop-cart-sync',
  'storefront-bf', 'google-analytics', 'googletagmanager', '/gtag/', 'hotjar', 'clarity.ms',
  'facebook.net/', 'connect.facebook', 'tiktok.com/i18n', 'snap.licdn', 'bat.bing', 'doubleclick'];
export const INLINE_MARKERS = ['wpmLoader', 'trekkie', 'monorail', 'webPixelsManager', '_learnq',
  'boomerang', 'gtag(', 'dataLayer', 'fbq(', 'ttq.', 'hj(', 'customDocumentWrite'];

export function stripTracking(html) {
  const removed = [];
  html = html.replace(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*<\/script>/gi, (m, src) => {
    if (STRIP_SRC.some(s => src.includes(s))) { removed.push(src.slice(0, 60)); return ''; }
    return m;
  });
  html = html.replace(/<link\b[^>]*\bhref="[^"]*(klaviyo|intelligems)[^"]*"[^>]*>/gi, () => { removed.push('link'); return ''; });
  html = html.replace(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi, (m, body) => {
    if (body.trim() && INLINE_MARKERS.some(k => body.includes(k))) { removed.push('inline'); return ''; }
    return m;
  });
  return { html, removed };
}

// ---- ② アセットURLの絶対化（ホットリンク＝バイト単位同一＝ピクセル一致） ----
export function absolutize(html, origin) {
  html = html.replace(/(["'(,\s])\/\/([a-z0-9.-]+\.[a-z]{2,})/gi, '$1https://$2');            // //cdn -> https://cdn
  html = html.replace(/(["'(,\s])(\/(?:cdn|assets|files|static|build|images|img|theme|media|uploads)\/)/g,
    `$1${origin}$2`);                                                                            // /build/... -> origin/build/...
  return html;
}

// ---- ③ 実行スクリプトの全剥がし（静的フリーズの肝） ----
// 保持: text/template・application/ld+json・application/json・text/html（いずれも実行されない）
export function stripScripts(html) {
  let count = 0;
  html = html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi, (m, attrs) => {
    const t = /type="([^"]*)"/i.exec(attrs);
    const ty = t ? t[1].toLowerCase() : '';
    if (['text/template', 'application/ld+json', 'application/json', 'text/html'].includes(ty)) return m;
    count++; return '';
  });
  // JSのpreload/modulepreloadも落とす（実行トリガになり得る）
  html = html.replace(/<link\b[^>]*\brel="modulepreload"[^>]*>/gi, '');
  html = html.replace(/<link\b[^>]*\brel="preload"[^>]*\bas="script"[^>]*>/gi, '');
  return { html, count };
}

// ---- ④ 遅延読み込み画像を即表示化（data-src -> src / data-srcset -> srcset） ----
export function promoteLazyImages(html) {
  let count = 0;
  html = html.replace(/<img\b[^>]*>/gi, (tag) => {
    const ds = /\bdata-src="([^"]+)"/i.exec(tag);
    if (!ds) return tag; count++;
    if (/\bsrc="/i.test(tag)) return tag.replace(/\bsrc="[^"]*"/i, `src="${ds[1]}"`);
    return tag.replace(/<img/i, `<img src="${ds[1]}"`);
  });
  html = html.replace(/\bdata-srcset="/gi, 'srcset="');
  return { html, count };
}

// ---- ⑤ 決済ウィジェットの静的化 ----
// スクリプトを剥がすと hosted-field iframe / Apple Pay / PayPal は死ぬので、見た目だけ再現する。
const APPLE_PAY_BTN =
  '<div style="width:100%;height:45px;background:#000;border-radius:4px;display:flex;align-items:center;justify-content:center;gap:5px;cursor:pointer">' +
  '<svg width="17" height="20" viewBox="0 0 24 24" fill="#fff" xmlns="http://www.w3.org/2000/svg"><path d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.037 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701"/></svg>' +
  '<span style="color:#fff;font:600 19px -apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif">Pay</span></div>';
const PAYPAL_BTN =
  '<div style="width:100%;height:45px;background:#ffc439;border-radius:4px;display:flex;align-items:center;justify-content:center;cursor:pointer;font:italic 800 20px Arial,Helvetica,sans-serif;letter-spacing:-.3px">' +
  '<span style="color:#003087">Pay</span><span style="color:#009cde">Pal</span></div>';

// hosted-field（クレカ番号/CVV）用コンテナの枠を打ち消すCSF。
// 移植先ストアのアプリ(PageFly/MoonBundle等)が全ページに注入するグローバルCSSが、
// div型のホストフィールド枠に box-shadow/border を重ねて「枠が二重」になるのを消す。
export const PAYMENT_FIX_CSS =
  '[id*="ixo-pay-"],[id*="hosted-field"],[id*="card-frame"],[class*="hosted-field"]' +
  '{border:0!important;box-shadow:none!important;background:transparent!important;padding:0!important;outline:0!important}';

export function neutralizePayments(html) {
  const notes = [];
  const CARD_HOSTS = /ixopay|adyen|stripe|braintree|spreedly|\bsecure\.|checkout\.|hosted|\/iframes?\//i;
  const inputFor = (isCvv, cls) =>
    `<input type="tel" inputmode="numeric" ${cls} placeholder="${isCvv ? 'XXX' : 'XXXX XXXX XXXX XXXX'}" style="width:100%">`;

  // (a) hosted-field の「div枠＋中のiframe/input」を、通常inputと同じ“単一input”に丸ごと置換する。
  //     div枠を残すと移植先アプリのグローバルCSSと枠が二重になるので、構造ごと素のinputへ。
  //     id直アンカー（開始タグ内にcard/cvv系idを要求）＝外側divに飲み込まれず、対象divだけ確実に捕捉。
  //     中身は単一の iframe か input のみ（=空のerror用divは弾く）。site由来のclassは引き継ぐ。
  html = html.replace(
    /<div\b([^>]*\bid="[^"]*(?:card[-_]?number|cardnum|pan|cvv|cvc)[^"]*"[^>]*)>\s*(?:<iframe\b[^>]*><\/iframe>|<input\b[^>]*\/?>)\s*<\/div>/gi,
    (m, attrs) => {
      if (/error|message|label/i.test(attrs)) return m;
      const cls = (/\bclass="[^"]*"/i.exec(attrs) || ['class="cart-input"'])[0];
      const isCvv = /cvv|cvc/i.test(attrs);
      notes.push('container:' + (isCvv ? 'cvv' : 'pan'));
      return inputFor(isCvv, cls);
    });
  // (b) 残った単発の hosted-field iframe -> 枠なしinput（親の styled box が枠を担当）
  html = html.replace(/<iframe\b[^>]*\bsrc="([^"]*)"[^>]*><\/iframe>/gi, (m, src) => {
    if (!CARD_HOSTS.test(src)) return m;
    const isCvv = /cvv|cvc|security|slave/i.test(src);
    notes.push('iframe:' + (isCvv ? 'cvv' : 'pan'));
    return `<input type="tel" inputmode="numeric" placeholder="${isCvv ? 'XXX' : 'XXXX XXXX XXXX XXXX'}" style="width:100%;height:100%;min-height:22px;border:0;background:transparent;outline:0;font:inherit;padding:0;color:#757575">`;
  });
  // (c) Apple Pay カスタム要素 -> 静的ボタン
  html = html.replace(/<apple-pay-button\b[^>]*><\/apple-pay-button>/gi, () => { notes.push('applepay'); return APPLE_PAY_BTN; });
  // (d) PayPal zoid iframe -> 静的ボタン、detect-close等のzoid断片は除去
  html = html.replace(/<iframe\b[^>]*\bname="__zoid__paypal_buttons__[^"]*"[^>]*><\/iframe>/gi, () => { notes.push('paypal'); return PAYPAL_BTN; });
  html = html.replace(/<iframe\b[^>]*\bname="__(?:zoid|detect_close)[^"]*"[^>]*><\/iframe>/gi, '');
  // (e) JSで表示されるはずだったApple Pay枠の display:none を剥がして見せる
  html = html.replace(/(id="payment-method-express-apple-pay-button-container"[^>]*?style="[^"]*?)display:\s*none;?/gi, '$1');
  return { html, notes };
}

// ---- ⑥ 移植先ストアのアプリ注入ウィジェットを隠す ----
// 完コピを別のShopifyストアに載せると、そのストアのアプリ（バンドル/アップセル/レビュー等）が
// theme app extension として全商品ページに勝手に注入され、クローンに混ざる（例: MoonBundleの
// 「複数個購入でお買い得」ブロックに移植先の実商品が並ぶ）。ベンダー固有プレフィクスのCSSで隠す。
// {% layout none %} でもアプリ埋め込みは注入されるので、静的CSSで確実に display:none する。
const APP_HIDE_CSS =
  '[class*="moonbundle-"],[id*="moonbundle"],' +      // MoonBundle（バンドル/アップセル）
  '[class*="rebuy-"],[id*="rebuy"],' +                 // Rebuy
  '[class*="zipify"],[id*="zipify"],[class*="ocu-"],' + // Zipify OCU
  '[class*="candyrack"],[class*="upsellplus"],' +       // Candy Rack / UpsellPlus
  '[class*="bundler-"],[id*="bundler"],' +             // Bundler
  '[class*="honeycomb-upsell"],[class*="_koala_"],' +   // Honeycomb / Koala
  '[class*="loox-"],[id*="looxReviews"],[class*="okeReviews"],' + // Loox / Okendo（移植先レビュー）
  '[class*="judgeme"],[class*="yotpo"],[class*="stamped-"]' +      // Judge.me / Yotpo / Stamped
  '{display:none!important;visibility:hidden!important}';

export function hideInjectedApps(html) {
  const style = `<style id="clone-hide-store-apps">${APP_HIDE_CSS}${PAYMENT_FIX_CSS}</style>`;
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, style + '</body>');
  return html + style;
}

// ---- ⑦ スクロール連動の出現演出を全表示にする（REVEAL=1 のとき）----
// モダンなブランドLPは下部セクションを opacity:0 で隠し、スクロールでJS表示する。ヘッドレスでは
// スクロールが起きず opacity:0 のまま＝空白。opacity/visibility を全要素で強制表示して内容を出す。
// transform/overflow は触らない（上部の反射・ステッカー・スクロール枠を壊さないため）。
const REVEAL_CSS =
  'html,body{opacity:1!important;visibility:visible!important}' +
  '*{opacity:1!important;visibility:visible!important;animation:none!important;transition:none!important}';

export function revealHidden(html) {
  const style = `<style id="clone-reveal-hidden">${REVEAL_CSS}</style>`;
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, style + '</body>');
  return html + style;
}

// ---- まとめ: 凍結DOMから静的完コピを作る ----
export function freezeStatic(html, origin) {
  const log = {};
  ({ html } = stripTracking(html));
  html = absolutize(html, origin);
  let r;
  r = stripScripts(html); html = r.html; log.scriptsStripped = r.count;
  r = promoteLazyImages(html); html = r.html; log.lazyPromoted = r.count;
  r = neutralizePayments(html); html = r.html; log.payments = r.notes;
  html = hideInjectedApps(html); log.appHideCss = true;
  return { html, log };
}
