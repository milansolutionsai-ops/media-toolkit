// Where each platform's buttons and caption text cover a vertical video. Approximate, measured on 1080x1920
// and scaled by width. Horizontal videos get no zones (these overlays are for vertical feeds).
export const PLATFORMS = {
  instagram: { name: "Instagram Reels", top: 220, bottom: 420, right: 140 },
  tiktok: { name: "TikTok", top: 160, bottom: 480, right: 160 },
  shorts: { name: "YouTube Shorts", top: 200, bottom: 400, right: 140 },
  linkedin: { name: "LinkedIn", top: 120, bottom: 300, right: 120 },
};

export function zones(platform, w, h) {
  const p = PLATFORMS[platform];
  if (!p || w >= h) return [];
  const k = w / 1080;
  const top = Math.round(p.top * k), bottom = Math.round(p.bottom * k), right = Math.round(p.right * k);
  return [
    { x: 0, y: 0, w, h: top, label: "top bar" },
    { x: 0, y: h - bottom, w, h: bottom, label: "caption and name" },
    { x: w - right, y: top, w: right, h: h - top - bottom, label: "buttons" },
  ];
}

// Absolutely positioned boxes over a <video>, in percent so they follow the element's size.
export function overlay(platform, w, h) {
  const box = document.createElement("div");
  box.className = "safezones";
  for (const z of zones(platform, w, h)) {
    const el = document.createElement("div");
    el.className = "zone";
    Object.assign(el.style, { left: `${(z.x / w) * 100}%`, top: `${(z.y / h) * 100}%`,
      width: `${(z.w / w) * 100}%`, height: `${(z.h / h) * 100}%` });
    el.textContent = z.label;
    box.append(el);
  }
  return box;
}
