// Pure frame and keyboard logic, shared by the player and the tests.

export const parseFps = (s) => {
  const [a, b] = String(s).split("/").map(Number);
  return b ? a / b : a;
};

// Seek to the middle of a frame so the decoder can't round to its neighbour.
export const frameToSeek = (n, fps) => (n + 0.5) / fps;
export const timeToFrame = (t, fps) => Math.floor(t * fps + 1e-6);
export const clampFrame = (n, total) => Math.max(0, Math.min(total - 1, n));

export function contextWindow(note, windows, fps, total) {
  const pad = {
    picture: windows.picture_frames,
    sound: Math.round(windows.sound_seconds * fps),
    cut: Math.round(windows.cut_seconds * fps),
  }[note.tag];
  return [clampFrame(note.start - pad, total), clampFrame(note.end + pad, total)];
}

export const initialKeyState = () => ({
  frame: 0, total: 1, markIn: null, markOut: null, tag: "picture", shuttle: 0, action: null,
});

const TAGS = { p: "picture", s: "sound", c: "cut" };

// One keypress in, next state out. `action` tells the view what to do beyond the state change.
export function reduceKey(state, ev) {
  const s = { ...state, action: null };
  const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;
  const step = ev.shiftKey ? 10 : 1;
  switch (k) {
    case "ArrowRight": s.frame = clampFrame(s.frame + step, s.total); s.action = "seek"; s.shuttle = 0; break;
    case "ArrowLeft": s.frame = clampFrame(s.frame - step, s.total); s.action = "seek"; s.shuttle = 0; break;
    case " ": s.action = "toggle-play"; s.shuttle = 0; break;
    case "j": s.shuttle = s.shuttle > 0 ? 0 : Math.max(-4, (s.shuttle || 0) - 1); s.action = "shuttle"; break;
    case "k": s.shuttle = 0; s.action = "pause"; break;
    case "l": s.shuttle = s.shuttle < 0 ? 0 : Math.min(4, (s.shuttle || 0) + 1); s.action = "shuttle"; break;
    case "i": s.markIn = s.frame; if (s.markOut === null || s.markOut < s.frame) s.markOut = s.frame; break;
    case "o":
      if (s.markIn === null) s.markIn = s.frame;
      s.markOut = s.frame;
      if (s.markOut < s.markIn) [s.markIn, s.markOut] = [s.markOut, s.markIn];
      break;
    case "p": case "s": case "c": s.tag = TAGS[k]; s.action = "tag"; break;
    case "Enter": s.action = "save"; break;
    case "Escape": s.markIn = null; s.markOut = null; s.action = "cancel"; break;
    default: return state;
  }
  return s;
}

export const fmtTime = (frame, fps) => {
  const t = frame / fps;
  const m = Math.floor(t / 60);
  const sec = (t - m * 60).toFixed(2).padStart(5, "0");
  return `${m}:${sec}`;
};
