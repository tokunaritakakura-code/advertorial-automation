(function(){
  // 今日の日付（参考と同じく、開いた日に替わる）
  var d=new Date(),t=(d.getMonth()+1)+"月"+d.getDate()+"日";
  document.querySelectorAll(".today").forEach(function(e){e.textContent=t});
  // 右下の札: 少し下へ送ると出る。× で消える
  var fp=document.getElementById("fixpop"),closed=false;
  if(fp)window.addEventListener("scroll",function(){if(!closed)fp.classList.toggle("on",window.scrollY>600)},{passive:true});
  if(fp)document.getElementById("fixx").addEventListener("click",function(){closed=true;fp.classList.remove("on")});
  // 横に流すカード（3秒ごと・左右の矢印）
  var sl=document.getElementById("slider");
  if(sl){var tr=sl.querySelector(".track"),n=tr.children.length,i=0;
  function go(k){i=(k+n)%n;tr.style.transform="translateX("+(-100*i)+"%)"}
  sl.querySelector(".sa.l").onclick=function(){go(i-1)};sl.querySelector(".sa.r").onclick=function(){go(i+1)};
  setInterval(function(){go(i+1)},3000);}
  // アンケート: 押すとピンクになり、次の問いの真ん中まで滑らかに送る（答えで中身は変わらない）
  function center(el){if(!el)return;var y=el.getBoundingClientRect().top+window.pageYOffset+el.clientHeight/2-window.innerHeight/2;window.scrollTo({top:y,behavior:"smooth"})}
  document.querySelectorAll(".qa").forEach(function(qa){
    qa.querySelectorAll(".ans").forEach(function(b){
      b.addEventListener("click",function(){
        if(qa.dataset.done)return;qa.dataset.done="1";
        b.classList.add("on");
        qa.querySelectorAll("[data-answer]").forEach(function(x){x.removeAttribute("data-answer")});
        var no=+qa.getAttribute("data-q"),nx=document.getElementById("q"+(no+1))||document.getElementById("sendwrap");
        setTimeout(function(){center(nx)},150);
      });
    });
  });
  // 回答を完了する: 隠れていた値段の画像を出す
  var sd=document.getElementById("send");if(sd)sd.addEventListener("click",function(){var r=document.getElementById("reveal");if(!r)return;r.classList.remove("hide");setTimeout(function(){center(r)},100)});
})();
