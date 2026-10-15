/* 値段の段（ここちドライ型）の動き。ここちドライ advertorial-08 の本番で動いている物だけ（2026-10-11 実測）:
   下の固定帯を、決めた所（data-nedan-from の要素。無ければこの値段の段）を読み手が通り過ぎてから出し、
   本文のボタン（.nd-cta・a.cta・[data-cta]）が画面に見えている間は消す。出し入れは CSS の 0.2秒の透明度。
   本番には 光る・脈打つ・数字が動く・残り時間 は無いので、ここにも入れない。 */
(function(){
  var st=document.querySelectorAll('.nd-stick');
  for(var i=1;i<st.length;i++) st[i].parentNode.removeChild(st[i]); // 1ページに1本だけ
  st=st[0]; if(!st) return;
  var nd=st.closest('.nd');
  var sel=st.getAttribute('data-nedan-from');
  var from=(sel&&document.querySelector(sel))||nd;
  function f(){
    var on=from.getBoundingClientRect().top<innerHeight*0.3;
    var c=document.querySelectorAll('.nd-cta,a.cta,[data-cta]');
    for(var j=0;j<c.length;j++){ if(st.contains(c[j])) continue; var r=c[j].getBoundingClientRect(); if(r.top<innerHeight&&r.bottom>0){on=false;break} }
    st.classList.toggle('off',!on);
  }
  addEventListener('scroll',f,{passive:true}); addEventListener('resize',f); f();
})();
