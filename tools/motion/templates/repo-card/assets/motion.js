// Spring motion for HyperFrames / GSAP compositions. Classic script: defines window.Motion.
// Copy into a project's assets/ and load with <script src="assets/motion.js"></script> after GSAP.
//
// Why: fixed ease curves slide A→B and feel cheap; a damped spring speeds up, overshoots a hair
// and settles. Everything is a pure function of time, so seeking any frame is deterministic.
//
//   Motion.spring(t, k, d)        0→1 damped spring at time t seconds (k stiffness, d damping)
//   Motion.track(t, keys, k, d)   value with several targets: keys [[time, value], ...], one spring per change, stacked
//   Motion.ease(dur, preset)      GSAP ease from a spring, for a tween of `dur` seconds: ease: Motion.ease(0.5, "ui")
//
// Presets: "ui" snappy, tiny overshoot (buttons, boxes, icons) · "type" no overshoot (text) · "heavy" slow, settles (big type, logos)
(function () {
  const P = { ui: [260, 24], type: [170, 26], heavy: [120, 22] };
  function spring(t, k = 170, d = 26) {
    if (t <= 0) return 0;
    const w0 = Math.sqrt(k), z = d / (2 * w0);
    if (z < 1) {
      const wd = w0 * Math.sqrt(1 - z * z);
      return 1 - Math.exp(-z * w0 * t) * (Math.cos(wd * t) + (z * w0 / wd) * Math.sin(wd * t));
    }
    return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
  }
  function track(t, keys, k = 170, d = 26) {
    let v = keys[0][1];
    for (let i = 1; i < keys.length; i++) v += (keys[i][1] - keys[i - 1][1]) * spring(t - keys[i][0], k, d);
    return v;
  }
  function ease(dur, preset = "ui") {
    const [k, d] = Array.isArray(preset) ? preset : P[preset] || P.ui;
    const end = spring(dur, k, d);
    // progress p (0..1) → spring value, nudged so the tween lands exactly on 1 at its end
    return (p) => spring(p * dur, k, d) + (1 - end) * p;
  }
  window.Motion = { spring, track, ease, presets: P };
})();
