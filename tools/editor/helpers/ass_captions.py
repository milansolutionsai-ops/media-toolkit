"""ASS subtitle writer: brand captions with a teal keyword, plus the hook title box.

SRT can't colour a single word or draw a box, so the master subtitle file is ASS.
Styles follow Milan's Visual & Asset Playbook and STYLE_GUIDE.md: IBM Plex Sans
Bold (bundled in fonts/, passed to libass via fontsdir), UPPERCASE, warm
off-white #E9E8E4 with a dark outline, keyword in teal #00B4B4; hook title in a
box at the top for its first seconds.

Sizes scale with the frame: PlayRes = the video's own size, and the caption size
keeps the proven SRT style's proportions (FontSize 18 / MarginV 50 at libass's
default PlayResY 288).
"""

from __future__ import annotations

from pathlib import Path

FONT = "IBM Plex Sans"
# ASS colours are &HAABBGGRR
OFF_WHITE = "&H00E4E8E9"   # #E9E8E4
TEAL = "&H00B4B400"        # #00B4B4
DARK = "&H0014120E"        # #0E1214
FAINT = "&H99E4E8E9"       # off-white at ~40% opacity (watermark)
BOX = "&H3014120E"         # dark slate at ~80% opacity (sentence pill)


def ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    """Strip characters libass reads as override syntax."""
    return text.replace("{", "").replace("}", "").replace("\\", "").strip()


def header(width: int, height: int) -> str:
    u = height / 288  # one unit of the old SRT style
    cap = round(18 * u)
    hook = round(height * 0.042)
    return "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caption,{FONT},{cap},{OFF_WHITE},{OFF_WHITE},{DARK},{DARK},"
        f"-1,0,0,0,100,100,0,0,1,{round(2 * u)},0,2,{round(width * 0.06)},{round(width * 0.06)},{round(50 * u)},1",
        f"Style: Hook,{FONT},{hook},{DARK},{DARK},{OFF_WHITE},{OFF_WHITE},"
        f"-1,0,0,0,100,100,0,0,3,{round(hook * 0.35)},0,8,{round(width * 0.1)},{round(width * 0.1)},{round(height * 0.09)},1",
        # one full sentence per cue in a translucent pill, top third (dialogue / explainer pieces)
        f"Style: Sentence,{FONT},{round(height * 0.029)},{OFF_WHITE},{OFF_WHITE},{BOX},{BOX},"
        f"-1,0,0,0,100,100,0,0,3,{round(height * 0.009)},0,8,{round(width * 0.12)},{round(width * 0.12)},{round(height * 0.16)},1",
        # faint handle mid-frame, discourages reposts
        f"Style: Watermark,{FONT},{round(height * 0.016)},{FAINT},{FAINT},{FAINT},{FAINT},"
        f"-1,0,0,0,100,100,1,0,1,0,0,2,0,0,{round(height * 0.42)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])


def caption_text(words: list[tuple[str, bool]], upper: bool = True) -> str:
    """Caption text (UPPERCASE by default); keyword words in teal, then back to the style colour."""
    out = []
    for word, keyword in words:
        w = _clean(word).upper() if upper else _clean(word)
        if not w:
            continue
        out.append(f"{{\\1c{TEAL}&}}{w}{{\\r}}" if keyword else w)
    return " ".join(out)


def active_text(words: list[str], active: int) -> str:
    """UPPERCASE chunk with the spoken word on a teal box (a thick teal outline behind that word only)."""
    out = []
    for i, word in enumerate(words):
        w = _clean(word).upper()
        if not w:
            continue
        out.append(f"{{\\bord14\\3c{TEAL}&}}{w}{{\\r}}" if i == active else w)
    return " ".join(out)


def dialogue(start: float, end: float, style: str, text: str, layer: int = 0) -> str:
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}"


def hook_event(text: str, seconds: float) -> str:
    return dialogue(0.0, seconds, "Hook", _clean(text), layer=1)


def write_ass(path: Path, width: int, height: int,
              cues: list[tuple[float, float, str]], hook: dict | None = None,
              style: str = "Caption", watermark: str | None = None, total: float | None = None) -> None:
    lines = [header(width, height)]
    if watermark and total:
        lines.append(dialogue(0.0, total, "Watermark", _clean(watermark)))
    if hook and hook.get("text"):
        lines.append(hook_event(hook["text"], float(hook.get("seconds", 3))))
    lines += [dialogue(a, b, style, t) for a, b, t in cues]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
