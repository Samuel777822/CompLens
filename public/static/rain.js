// Falling legal-metrology glyphs (the symbols from the pillars): section sign, ticks, rupee, units.
(() => {
  if (window.__complensRain) return; window.__complensRain = true;
  const cv = document.getElementById("rain"); if (!cv) return;
  const ctx = cv.getContext("2d");
  const G = ["§","✓","✕","₹","g","ml","kg","℮","%","®","¶","|||"];
  const CELL = 30, TRAIL = 9;
  const still = matchMedia("(prefers-reduced-motion:reduce)").matches;
  let cols = [], W = 0, H = 0, last = 0;
  const pick = () => G[(Math.random() * G.length) | 0];
  function size(){
    const d = Math.min(devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight; cv.width = W * d; cv.height = H * d; ctx.setTransform(d,0,0,d,0,0);
    const n = Math.ceil(W / CELL);
    cols = Array.from({length: n}, (_, i) => cols[i] || {
      y: still ? Math.random() * H : -Math.random() * H, v: 40 + Math.random() * 70, on: Math.random() < .8,
      g: Array.from({length: TRAIL}, pick)
    });
    cols.length = n;
  }
  function draw(t){
    const dt = Math.min((t - last) / 1000, .1); last = t;
    ctx.clearRect(0, 0, W, H);
    ctx.textAlign = "center"; ctx.font = "18px 'CompLens Pixel', monospace";
    cols.forEach((c, i) => {
      if (!c.on && !still) { if (Math.random() < .004) { c.on = true; c.y = -CELL; } return; }
      if (!still) c.y += c.v * dt;
      const x = i * CELL + CELL / 2, head = Math.floor(c.y / CELL);
      for (let k = 0; k < TRAIL; k++) {
        const y = (head - k) * CELL; if (y < -CELL || y > H + CELL) continue;
        ctx.fillStyle = k === 0 ? "#eaffa6" : `rgba(200,240,50,${(1 - k / TRAIL) * .95})`;
        if (k === 0) { ctx.shadowColor = "#c8f032"; ctx.shadowBlur = 12; } else ctx.shadowBlur = 0;
        ctx.fillText(c.g[(head - k) % TRAIL < 0 ? 0 : (head - k) % TRAIL], x, y);
      }
      ctx.shadowBlur = 0;
      if (Math.random() < .02) c.g[(Math.random() * TRAIL) | 0] = pick();
      if (c.y - TRAIL * CELL > H) { c.y = -CELL; c.v = 40 + Math.random() * 70; c.on = Math.random() < .9; }
    });
    if (!still) requestAnimationFrame(draw);
  }
  if (document.fonts) document.fonts.load("18px 'CompLens Pixel'"); size(); addEventListener("resize", size);
  requestAnimationFrame(draw);
})();
