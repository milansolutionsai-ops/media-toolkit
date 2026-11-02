"""SFX stem for b1-06 (v4, 30s pacing): pops, impacts, whooshes, one riser. Music comes from audio/music/."""
import numpy as np, wave, sys
SR = 48000; DUR = 30.0
H, M, C, I, S0, SD, R, E, P = 0.5, 3.0, 4.5, 7.0, 8.5, 2.5, 23.5, 26.0, 28.0  # same as index.html
out = np.zeros(int(SR * DUR))
rng = np.random.default_rng(6)

def place(sig, t, gain):
    i = int(t * SR); j = min(len(out), i + len(sig))
    out[i:j] += gain * sig[: j - i]

def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / attack, 1) * np.exp(-t / decay)

def pop(f0=900):
    n = int(0.09 * SR); t = np.arange(n) / SR
    f = f0 * np.exp(-t * 18)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.025)

def impact():
    n = int(0.9 * SR); t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t * 4) + 38) / SR) * env(n, 0.003, 0.28)
    crack = rng.standard_normal(n) * env(n, 0.001, 0.03)
    return boom + 0.35 * crack

def whoosh(length=0.35):
    n = int(length * SR); x = rng.standard_normal(n)
    # sweep a one-pole lowpass upward for the "air" motion
    a = np.linspace(0.02, 0.35, n); y = np.zeros(n); s = 0.0
    for k in range(n):
        s += a[k] * (x[k] - s); y[k] = s
    shape = np.sin(np.pi * np.arange(n) / n) ** 2
    return y * shape * 2.2

def riser(length=1.0):
    n = int(length * SR); t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * (t / length) ** 2) / SR)
    return (0.5 * tone + 0.5 * rng.standard_normal(n) * 0.4) * (t / length) ** 2

for k in range(6):                      # hook words
    place(pop(800 + 60 * k), k * H, 0.55)
for t in (M, C + 1.0, R + 1.0, P):      # flash, CONTEXT, ONLY THEN, payoff
    place(impact(), t, 0.9)
place(whoosh(), I - 0.15, 0.6)          # into "6 STEPS"
for k in range(6):                      # step cards
    place(whoosh(), S0 + SD * k - 0.15, 0.6)
for k in range(6):                      # recap icons
    place(pop(1100), R + 0.08 * k, 0.4)
place(whoosh(), E + 0.85, 0.5)          # line swap
place(riser(), P - 1.0, 0.35)           # into payoff

out = np.clip(out / max(1e-9, np.abs(out).max()) * 0.9, -1, 1)
pcm = (np.repeat(out[:, None], 2, 1) * 32767).astype("<i2")
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
