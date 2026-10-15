#!/usr/bin/env node
// frame-player.mjs <outdir> [inputFile=clone-baked.html]
// capture.mjs の実測データ(scrollmap/stylemap/reveal)を使って、JSを剥がした静的クローンに
// 「動き」を最小の自前ランタイムで足す。注入するのは以下:
//   A) frame-scrub : 連番フレームのcanvas動画を、スクロール位置に同期して描画(安定セレクタで対象特定)
//   B) carousel    : Swiper等の商品スライダーを、クリップ+矢印/ドット/スワイプで復活(実スライドで再現)
//   C) scroll-style: GSAPがスクロールで変えていた要素の transform/opacity を実測どおり再現(テキスト演出)
//   + 外科的 reveal CSS(スクロールで隠れていた要素だけ表示)
import fs from 'fs';
import path from 'path';

const outdir = process.argv[2];
const input = process.argv[3] || 'clone-baked.html';
if (!outdir) { console.error('usage: frame-player.mjs <outdir> [inputFile]'); process.exit(1); }
const rd = (f, d) => { const p = path.join(outdir, f); return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : d; };
const scrollmap = rd('scrollmap.json', {});
const stylemap = rd('stylemap.json', {});
const reveal = rd('reveal.json', { desktop: [], mobile: [] });

let html = fs.readFileSync(path.join(outdir, input), 'utf8');

// reveal は「スクロールで隠れていた要素の実測クラス」だけを対象にする。
// インラインopacity(=GSAPが出し分けている見出し等)は scroll-style プレーヤーに任せる
// （ここで強制表示すると出し分けを潰して見出しが重なるため、対象にしない）。
const cls = [...new Set([...(reveal.desktop || []), ...(reveal.mobile || [])])].filter(c => /^[A-Za-z0-9_-]+$/.test(c));
const revSel = cls.length ? cls.map(c => '.' + c).join(',') + '{opacity:1!important;visibility:visible!important}' : '';
const revealCss = `<style id="clone-reveal-hidden">${revSel}canvas{opacity:1!important;visibility:visible!important}</style>`;

const runtime = `
<script id="clone-runtime">
(function(){
  var SM=${JSON.stringify(scrollmap)}, ST=${JSON.stringify(stylemap)};
  function q(sel){ try{ return document.querySelector(sel); }catch(e){ return null; } }
  function isMobile(){ return innerWidth<=768; }

  // ---- A) frame-scrub ----
  var fstate={};
  function driverOf(c, sel){ var d=sel&&q(sel); if(!d){ var vh=innerHeight,el=c.parentElement; while(el&&el!==document.body){ if(el.offsetHeight>vh*1.3){d=el;break;} el=el.parentElement; } if(!d) d=c.closest('section')||c.parentElement||c; }
    var t=0,n=d; while(n){t+=n.offsetTop;n=n.offsetParent;} return {top:t,height:d.offsetHeight,vh:innerHeight}; }
  function frameAt(s,p){ if(!s.length)return 0; if(p<=s[0].p)return s[0].f; if(p>=s[s.length-1].p)return s[s.length-1].f;
    for(var i=0;i<s.length-1;i++){ if(p>=s[i].p&&p<=s[i+1].p) return (p-s[i].p)<(s[i+1].p-p)?s[i].f:s[i+1].f; } return s[s.length-1].f; }
  function preload(st,m){ if(st.imgs)return; var lo=Infinity,hi=-Infinity; m.samples.forEach(function(s){lo=Math.min(lo,s.f);hi=Math.max(hi,s.f);}); st.lo=lo;st.hi=hi;st.imgs={};
    for(var f=lo;f<=hi;f++){ var im=new Image(); im.decoding='async'; im.src=m.base+String(f).padStart(m.pad,'0')+m.ext; st.imgs[f]=im; } }
  function frames(){ var mob=isMobile();
    Object.keys(SM).forEach(function(key){ var e=SM[key], m=mob?(e.mobile||e.desktop):(e.desktop||e.mobile); if(!m||!m.samples||!m.samples.length)return;
      var c=q(key); if(!c||c.tagName!=='CANVAS'||c.offsetParent===null)return;
      var st=fstate[key]||(fstate[key]={}); preload(st,m);
      var d=driverOf(c,m.driverSel), p=Math.max(0,Math.min(1,(scrollY-d.top)/((d.height-d.vh)||1))), f=frameAt(m.samples,p), im=st.imgs[f];
      if(!(im&&im.complete&&im.naturalWidth)){ for(var k=f;k>=st.lo;k--){ if(st.imgs[k]&&st.imgs[k].complete&&st.imgs[k].naturalWidth){im=st.imgs[k];break;} } }
      if(im&&im.complete&&im.naturalWidth){ var ctx=st.ctx||(st.ctx=c.getContext('2d')); if(c.width!==im.naturalWidth){c.width=im.naturalWidth;c.height=im.naturalHeight;}
        ctx.clearRect(0,0,c.width,c.height); ctx.drawImage(im,0,0,c.width,c.height); } });
  }

  // ---- C) scroll-style ----
  function styleAt(s,rel){ if(!s.length)return s[0]; if(rel<=s[0].rel)return s[0]; if(rel>=s[s.length-1].rel)return s[s.length-1];
    for(var i=0;i<s.length-1;i++){ if(rel>=s[i].rel&&rel<=s[i+1].rel) return (rel-s[i].rel)<(s[i+1].rel-rel)?s[i]:s[i+1]; } return s[s.length-1]; }
  function styles(){ var mob=isMobile();
    Object.keys(ST).forEach(function(key){ var e=ST[key], m=mob?(e.mobile||e.desktop):(e.desktop||e.mobile); if(!m||!m.samples||m.samples.length<2)return;
      var el=q(key); if(!el||el.offsetParent===null)return; var top=0,n=el; while(n){top+=n.offsetTop;n=n.offsetParent;}
      var v=styleAt(m.samples, scrollY-top); if(v.t) el.style.transform=v.t; if(v.o!=='') el.style.opacity=v.o; });
  }

  // ---- B) carousel (Swiper互換の最小スライダー) ----
  function initCarousels(){
    document.querySelectorAll('.swiper').forEach(function(sw){
      if(sw.__cl)return; sw.__cl=1;
      var wrap=sw.querySelector('.swiper-wrapper'); if(!wrap)return;
      var slides=[].slice.call(wrap.querySelectorAll(':scope > .swiper-slide')); if(slides.length<2)return;
      sw.style.overflow='hidden'; wrap.style.display='flex'; wrap.style.transition='transform .45s cubic-bezier(.25,.1,.25,1)'; wrap.style.willChange='transform';
      slides.forEach(function(s){ s.style.flex='0 0 auto'; });
      var idx=0;
      function slideW(){ return slides[0].getBoundingClientRect().width + (parseFloat(getComputedStyle(wrap).columnGap||getComputedStyle(wrap).gap)||0); }
      function go(i){ idx=Math.max(0,Math.min(slides.length-1,i)); wrap.style.transform='translate3d('+(-idx*slideW())+'px,0,0)';
        slides.forEach(function(s,j){ s.classList.toggle('swiper-slide-active', j===idx); }); updateDots(); }
      var scopes=[sw, sw.parentElement, sw.parentElement&&sw.parentElement.parentElement].filter(Boolean);
      function findBtn(re){ for(var si=0;si<scopes.length;si++){ var c=[].find.call(scopes[si].querySelectorAll('[aria-label],button,.swiper-button-next,.swiper-button-prev,[class*="arrow"],[class*="next"],[class*="prev"]'), function(b){ if(b.closest('.swiper-wrapper')||b.classList.contains('swiper-slide'))return false; var l=(b.getAttribute('aria-label')||'')+' '+b.className; return re.test(l); }); if(c)return c; } return null; }
      var next=findBtn(/next/i), prev=findBtn(/prev|previous/i);
      if(next) next.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); go(idx+1); });
      if(prev) prev.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); go(idx-1); });
      var dots=[]; for(var si=0;si<scopes.length&&!dots.length;si++){ dots=[].filter.call(scopes[si].querySelectorAll('[aria-label]'), function(b){ return !b.closest('.swiper-wrapper') && /go to slide|pagination|bullet/i.test((b.getAttribute('aria-label')||'')+b.className); }); }
      function updateDots(){ dots.forEach(function(d,j){ d.classList.toggle('swiper-pagination-bullet-active', j===idx); }); }
      dots.forEach(function(d,j){ d.addEventListener('click', function(e){ e.preventDefault(); go(j); }); });
      // drag / swipe
      var down=false,x0=0,base=0;
      function px(e){ return (e.touches&&e.touches[0]?e.touches[0].clientX:e.clientX); }
      sw.addEventListener('pointerdown', function(e){ down=true; x0=px(e); base=-idx*slideW(); wrap.style.transition='none'; });
      window.addEventListener('pointermove', function(e){ if(!down)return; wrap.style.transform='translate3d('+(base+(px(e)-x0))+'px,0,0)'; });
      window.addEventListener('pointerup', function(e){ if(!down)return; down=false; wrap.style.transition=''; var dx=px(e)-x0; if(Math.abs(dx)>slideW()*0.2) go(idx+(dx<0?1:-1)); else go(idx); });
      go(0);
    });
  }

  function loop(){ try{frames();}catch(e){} try{styles();}catch(e){} requestAnimationFrame(loop); }
  function start(){ try{initCarousels();}catch(e){} requestAnimationFrame(loop); addEventListener('resize', function(){ document.querySelectorAll('.swiper').forEach(function(s){s.__cl=0;}); initCarousels(); }); }
  if(document.readyState!=='loading') start(); else document.addEventListener('DOMContentLoaded', start);
})();
</script>`;

const inject = revealCss + runtime;
html = /<\/body>/i.test(html) ? html.replace(/<\/body>/i, inject + '</body>') : html + inject;
fs.writeFileSync(path.join(outdir, input), html);
console.log(JSON.stringify({ canvasKeys: Object.keys(scrollmap).length, styleKeys: Object.keys(stylemap).length, revealClasses: cls.length }, null, 1));
