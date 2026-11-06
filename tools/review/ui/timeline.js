// Filmstrip (pre-rendered sprite) + waveform (pre-computed peaks) with teal note ranges and a playhead.
const TEAL = "#00b4b4";

export class Timeline {
  constructor(host, { spriteUrl, spriteMeta, peaksUrl, total, onSeek }) {
    this.total = total;
    this.ranges = [];
    this.mark = null;
    this.frame = 0;
    this.peaks = [];
    this.canvas = document.createElement("canvas");
    host.appendChild(this.canvas);
    this.meta = spriteMeta;
    this.img = new Image();
    this.img.onload = () => this.draw();
    this.img.src = spriteUrl;
    fetch(peaksUrl).then((r) => r.json()).then((p) => { this.peaks = p; this.draw(); });
    const seekAt = (e) => {
      const r = this.canvas.getBoundingClientRect();
      onSeek(Math.round(((e.clientX - r.left) / r.width) * (this.total - 1)));
    };
    let dragging = false;
    this.canvas.addEventListener("mousedown", (e) => { dragging = true; seekAt(e); });
    window.addEventListener("mousemove", (e) => dragging && seekAt(e));
    window.addEventListener("mouseup", () => { dragging = false; });
    new ResizeObserver(() => this.draw()).observe(host);
  }

  set({ ranges, mark, frame }) {
    if (ranges) this.ranges = ranges;
    if (mark !== undefined) this.mark = mark;
    if (frame !== undefined) this.frame = frame;
    this.draw();
  }

  draw() {
    const c = this.canvas;
    const w = c.clientWidth || c.parentElement.clientWidth;
    const stripH = 56, waveH = 40, h = stripH + waveH + 4;
    const dpr = window.devicePixelRatio || 1;
    c.width = w * dpr; c.height = h * dpr; c.style.height = h + "px";
    const g = c.getContext("2d");
    g.scale(dpr, dpr);
    g.fillStyle = "#171a1d"; g.fillRect(0, 0, w, h);

    // Filmstrip: as many thumbs as fit, each picked from the sprite by time.
    const m = this.meta;
    if (this.img.complete && this.img.naturalWidth && m && m.count) {
      const tw = stripH * (m.thumb_w / m.thumb_h);
      const n = Math.max(1, Math.ceil(w / tw));
      for (let i = 0; i < n; i++) {
        const idx = Math.min(m.count - 1, Math.floor((i / n) * m.count));
        const sx = (idx % m.cols) * m.thumb_w, sy = Math.floor(idx / m.cols) * m.thumb_h;
        g.drawImage(this.img, sx, sy, m.thumb_w, m.thumb_h, i * tw, 0, tw, stripH);
      }
    }
    // Waveform.
    const y0 = stripH + 4, mid = y0 + waveH / 2;
    g.fillStyle = "#5b636b";
    const p = this.peaks;
    if (p.length) {
      for (let x = 0; x < w; x++) {
        const a = Math.floor((x / w) * p.length), b = Math.max(a + 1, Math.floor(((x + 1) / w) * p.length));
        let peak = 0;
        for (let i = a; i < b; i++) peak = Math.max(peak, p[i] || 0);
        const hh = Math.max(1, peak * (waveH / 2));
        g.fillRect(x, mid - hh, 1, hh * 2);
      }
    } else {
      g.fillRect(0, mid, w, 1);
    }
    const fx = (f) => (f / Math.max(1, this.total - 1)) * w;
    // Saved notes, then the range being marked.
    for (const r of this.ranges) {
      g.fillStyle = "rgba(0,180,180,0.25)";
      g.fillRect(fx(r[0]), 0, Math.max(2, fx(r[1] + 1) - fx(r[0])), h);
    }
    if (this.mark) {
      g.fillStyle = "rgba(0,180,180,0.45)";
      g.fillRect(fx(this.mark[0]), 0, Math.max(2, fx(this.mark[1] + 1) - fx(this.mark[0])), h);
      g.strokeStyle = TEAL; g.lineWidth = 1;
      g.strokeRect(fx(this.mark[0]) + 0.5, 0.5, Math.max(2, fx(this.mark[1] + 1) - fx(this.mark[0])) - 1, h - 1);
    }
    g.fillStyle = "#ffffff";
    g.fillRect(Math.round(fx(this.frame)) - 1, 0, 2, h);
  }
}
