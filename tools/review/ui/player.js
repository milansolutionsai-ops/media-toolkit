// Frame-exact wrapper around <video>. The current frame comes from the seek we asked for, never from the
// element's own clock; during playback it follows requestVideoFrameCallback for display only.
import { frameToSeek, timeToFrame, clampFrame } from "./frames.js";

export class Player {
  constructor(video, fps, total, onFrame) {
    this.v = video;
    this.fps = fps;
    this.total = total;
    this.frame = 0;
    this.onFrame = onFrame;
    this.reverseTimer = null;
    const tick = (_now, meta) => {
      if (!this.v.paused) {
        this.frame = clampFrame(timeToFrame(meta.mediaTime, this.fps), this.total);
        this.onFrame(this.frame);
      }
      this.v.requestVideoFrameCallback(tick);
    };
    this.v.requestVideoFrameCallback(tick);
    this.v.addEventListener("pause", () => this.seek(timeToFrame(this.v.currentTime, this.fps)));
  }

  seek(n) {
    this.frame = clampFrame(n, this.total);
    this.v.currentTime = frameToSeek(this.frame, this.fps);
    this.onFrame(this.frame);
  }

  stopReverse() {
    clearInterval(this.reverseTimer);
    this.reverseTimer = null;
  }

  pause() {
    this.stopReverse();
    if (!this.v.paused) this.v.pause();
  }

  toggle() {
    if (this.reverseTimer) return this.pause();
    if (this.v.paused) { this.v.playbackRate = 1; this.v.play(); } else this.v.pause();
  }

  // speed > 0 plays forward at 1x/2x/4x, speed < 0 steps backward frame by frame.
  shuttle(speed) {
    this.stopReverse();
    if (speed === 0) return this.pause();
    if (speed > 0) {
      this.v.playbackRate = [1, 1, 2, 4, 8][speed];
      this.v.play();
      return;
    }
    if (!this.v.paused) this.v.pause();
    const rate = this.fps * [1, 1, 2, 4, 8][-speed];
    this.reverseTimer = setInterval(() => {
      if (this.frame <= 0) return this.stopReverse();
      this.seek(this.frame - 1);
    }, 1000 / Math.min(rate, 60));
  }
}
