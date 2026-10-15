// タブのアイコン: 淡い空の玉の中で、雲がゆっくり流れる（キャラクターなし。左上のあいさつの玉と同じ質感）。
// 2026-10-07 本人「キャラクターなしで、さっき見せたやつの質感・高級感のまま。ここのアイコンも同じに」。
// ファビコンは SVG のアニメが止まるので、canvas で1コマずつ描いて差し替える
(() => {
  const S = 64, cv = document.createElement("canvas"); cv.width = cv.height = S;
  const g = cv.getContext("2d");
  let link = document.querySelector('link[rel="icon"]');
  if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
  const 雲 = (x, y, r) => { const gr = g.createRadialGradient(x - r * 0.2, y - r * 0.3, r * 0.1, x, y, r); gr.addColorStop(0, "#ffffff"); gr.addColorStop(0.7, "#fbeef3"); gr.addColorStop(1, "rgba(233,214,232,.85)"); g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); };
  function 描く(t) {
    const d = Math.sin(t / 2600) * 3; // 雲がゆっくり左右に流れる
    g.clearRect(0, 0, S, S);
    g.save(); g.beginPath(); g.arc(32, 32, 31, 0, Math.PI * 2); g.clip();
    const sky = g.createRadialGradient(32, 6, 2, 32, 22, 60);
    sky.addColorStop(0, "#a9c6ff"); sky.addColorStop(0.45, "#c7b7ee"); sky.addColorStop(0.8, "#efc3d6"); sky.addColorStop(1, "#f6d5cf");
    g.fillStyle = sky; g.fillRect(0, 0, S, S);
    g.globalAlpha = 0.7; g.filter = "blur(1.2px)"; g.fillStyle = "#fff";
    g.beginPath(); g.ellipse(15 + d, 20, 13, 4.5, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(50 - d, 15, 10, 4, 0, 0, Math.PI * 2); g.fill();
    g.globalAlpha = 1; g.filter = "blur(0.5px)";
    雲(17 + d * 0.6, 47, 11); 雲(31 + d * 0.6, 40, 13); 雲(46 + d * 0.6, 45, 11.5); 雲(56 + d * 0.6, 54, 10); 雲(8 + d * 0.6, 56, 10);
    g.fillStyle = "#fbeef3"; g.fillRect(0, 50, S, 14);
    g.filter = "none";
    const gl = g.createRadialGradient(20, 13, 1, 22, 16, 30); gl.addColorStop(0, "rgba(255,255,255,.75)"); gl.addColorStop(0.6, "rgba(255,255,255,.08)"); gl.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gl; g.fillRect(0, 0, S, S);
    g.restore();
    g.strokeStyle = "rgba(255,255,255,.8)"; g.lineWidth = 1.5; g.beginPath(); g.arc(32, 32, 31, 0, Math.PI * 2); g.stroke();
    link.href = cv.toDataURL("image/png");
  }
  const t0 = performance.now();
  描く(0);
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) setInterval(() => 描く(performance.now() - t0), 150);
})();
