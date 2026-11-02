"""Clean background noise from source audio once, before any cut.

A phone take carries a steady hiss ~27 dB under the voice. Loudness
normalization lifts it with the voice, and the 30ms fades at every cut dip it
to zero and back, so each cut audibly "breathes". Denoising the whole source
once (not per segment, where the filter would restart at every cut) gives every
segment the same quiet bed.

Default: RNNoise (speech model sh.rnnn, models/) blended with 25% of the
original signal so the voice keeps its natural texture. Chosen by ear on
Milan's first real take (2026-10-09) over FFT/NLM denoisers, which made the
voice sound processed at full strength.

The cleaned copy is cached in <edit>/clean/<stem>.<method>-d<dry%>.mkv:
video stream copied, audio as PCM so nothing is encoded twice.

EDL switch: "audio_clean": false turns it off; {"method": "anlmdn", "dry": 0.25}
overrides the defaults. Methods: rnnoise, anlmdn, none.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MODEL = Path(__file__).resolve().parents[1] / "models" / "sh.rnnn"
MODEL_URL = ("https://raw.githubusercontent.com/GregorR/rnnoise-models/master/"
             "somnolent-hogwash-2018-09-01/sh.rnnn")
DEFAULT = {"method": "rnnoise", "dry": 0.25}
DENOISERS = {
    "rnnoise": "arnndn=m=sh.rnnn",   # relative: ffmpeg runs from the model's folder (no Windows path escaping)
    "anlmdn": "anlmdn=s=7:p=0.002:r=0.006",
}


def settings_for(edl: dict) -> dict | None:
    raw = edl.get("audio_clean", True)
    if raw is False or raw == "none":
        return None
    settings = {**DEFAULT, **(raw if isinstance(raw, dict) else {})}
    if settings["method"] == "none":
        return None
    if settings["method"] not in DENOISERS:
        raise ValueError(f"audio_clean method {settings['method']!r}: use one of "
                         f"{', '.join(DENOISERS)} or none")
    return settings


def clean_filter(method: str, dry: float) -> str:
    head = "[0:a]highpass=f=80,aresample=48000"
    den = DENOISERS[method]
    if dry <= 0:
        return f"{head},{den}[a]"
    return (f"{head},asplit=2[dry][wet];[wet]{den}[den];[dry]volume={dry:g}[keep];"
            f"[den][keep]amix=inputs=2:weights=1 1:normalize=0[a]")


def clean_path(edit_dir: Path, src: Path, settings: dict) -> Path:
    tag = f"{settings['method']}-d{round(settings['dry'] * 100):02d}"
    return edit_dir / "clean" / f"{src.stem}.{tag}.mkv"


def clean_source(src: Path, edit_dir: Path, settings: dict) -> Path:
    if settings["method"] == "rnnoise" and not MODEL.exists():
        raise RuntimeError(f"RNNoise model missing at {MODEL}. Download sh.rnnn from {MODEL_URL}")
    out = clean_path(edit_dir, src, settings)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mkv")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(Path(src).resolve()),
         "-filter_complex", clean_filter(settings["method"], settings["dry"]),
         "-map", "0:v", "-c:v", "copy", "-map", "[a]", "-c:a", "pcm_s16le",
         str(tmp.resolve())],
        check=True, cwd=MODEL.parent if MODEL.parent.exists() else None,
    )
    tmp.replace(out)  # only a finished file ever lands under the cached name
    return out


def with_clean_sources(edl: dict, edit_dir: Path) -> dict:
    settings = settings_for(edl)
    if settings is None:
        return edl
    sources = {}
    for name, path in edl["sources"].items():
        p = Path(path)
        src = p if p.is_absolute() else edit_dir / p
        print(f"  clean audio ({settings['method']}, {settings['dry']:.0%} original): {src.name}")
        sources[name] = str(clean_source(src, edit_dir, settings))
    return {**edl, "sources": sources}
