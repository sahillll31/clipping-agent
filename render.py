"""Vertical clip rendering with word-level karaoke captions (ffmpeg + libass)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable

from config import FONTS_DIR, ffmpeg_path
from tools import ToolError, run, run_streaming

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30


# --------------------------------------------------------------------------- ASS
def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    text = text.replace("\\", " ")
    text = text.replace("{", "(").replace("}", ")")
    text = text.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()


_SENTENCE_END = re.compile(r"[.!?][\"')\]]?$")


def _text_of(words: list[dict[str, Any]]) -> str:
    return " ".join(w["text"] for w in words).strip()


def _split_rows(words: list[dict[str, Any]], max_chars: int = 20) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for word in words:
        if row and len(_text_of(row + [word])) > max_chars:
            rows.append(row)
            row = [word]
        else:
            row.append(word)
    if row:
        rows.append(row)
    return rows


def build_cards(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group words into short caption cards (max two rows each)."""
    cards: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for i, word in enumerate(words):
        if not cur:
            cur = [word]
            continue
        gap = word["start"] - cur[-1]["end"]
        text = _text_of(cur + [word])
        span = word["end"] - cur[0]["start"]
        sentence_done = _SENTENCE_END.search(cur[-1]["text"]) and len(_text_of(cur)) >= 12
        if len(text) > 42 or gap > 0.85 or span > 3.6 or sentence_done:
            cards.append(cur)
            cur = [word]
        else:
            cur.append(word)
    if cur:
        cards.append(cur)

    # Guarantee no card needs more than two rows.
    final: list[list[dict[str, Any]]] = []

    def push(card: list[dict[str, Any]]) -> None:
        if len(_split_rows(card)) <= 2:
            final.append(card)
        elif len(card) > 1:
            mid = len(card) // 2
            push(card[:mid])
            push(card[mid:])
        else:
            final.append(card)

    for card in cards:
        push(card)
    return final


def build_ass(clip: dict[str, Any], *, captions: bool = True, hook_header: bool = True) -> str:
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {OUT_W}",
        f"PlayResY: {OUT_H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,Arial,72,&H0000FFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,1,0,1,7,3,2,80,80,430,1",
        "Style: Hook,Impact,62,&H0000FFFF,&H00FFFFFF,&H00000000,&H82000000,-1,0,0,0,100,100,2,0,1,6,4,8,80,80,200,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events: list[str] = []

    if hook_header:
        hook = _clean(clip.get("hook") or clip.get("title") or "")
        if hook:
            hook = hook.upper()
            if len(hook) > 64:
                hook = hook[:61].rsplit(" ", 1)[0] + "..."
            end = min(4.4, float(clip.get("duration") or 4.0))
            events.append(
                f"Dialogue: 1,{_ass_time(0)},{_ass_time(end)},Hook,,0,0,0,,{{\\fad(180,240)}}{hook}"
            )

    if captions:
        words = [w for w in (clip.get("words") or []) if w.get("text")]
        cards = build_cards(words)
        for idx, card in enumerate(cards):
            start = max(0.0, card[0]["start"] - 0.05)
            end = card[-1]["end"] + 0.18
            if idx + 1 < len(cards):
                end = min(end, max(start + 0.25, cards[idx + 1][0]["start"] - 0.02))
            if end - start < 0.18:
                end = start + 0.18
            rows = _split_rows(card)
            pieces: list[str] = []
            for row_i, row in enumerate(rows):
                for w_i, word in enumerate(row):
                    nxt = row[w_i + 1]["start"] if w_i + 1 < len(row) else word["end"]
                    cs = max(4, int(round((nxt - word["start"]) * 100)))
                    pieces.append(f"{{\\kf{cs}}}{_clean(word['text'])}")
                    if w_i + 1 < len(row):
                        pieces.append(" ")
                if row_i + 1 < len(rows):
                    pieces.append("\\N")
            body = "".join(pieces).strip()
            if body:
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{body}")

    return "\n".join(header + events) + "\n"


# --------------------------------------------------------------------------- ffmpeg
def _prepare_fonts(workdir: Path) -> str:
    fonts = workdir / "fonts"
    fonts.mkdir(exist_ok=True)
    for font in ("arialbd.ttf", "impact.ttf"):
        src = FONTS_DIR / font
        dst = fonts / font
        if src.exists() and (not dst.exists() or dst.stat().st_size != src.stat().st_size):
            shutil.copy2(src, dst)
    return "fonts"


def _graph(portrait: bool) -> str:
    if portrait:
        return (
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},setsar=1,fps={OUT_FPS},"
            "ass=captions.ass:fontsdir=fonts[v]"
        )
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},boxblur=22:2,eq=brightness=-0.14:saturation=0.9[bgb];"
        f"[fg]scale={OUT_W}:-2:flags=lanczos,setsar=1[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2:shortest=1,fps={OUT_FPS},"
        "ass=captions.ass:fontsdir=fonts[v]"
    )


def render_clip(
    video: str | Path,
    clip: dict[str, Any],
    workdir: Path,
    out_path: Path,
    info: dict[str, Any],
    *,
    captions: bool = True,
    hook_header: bool = True,
    on_progress: Callable[[float, str], None] | None = None,
    cancel: Any = None,
) -> dict[str, Any]:
    ff = ffmpeg_path()
    if not ff:
        raise ToolError("ffmpeg not found - run setup first")
    workdir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ass_path = workdir / "captions.ass"
    ass_path.write_text(build_ass(clip, captions=captions, hook_header=hook_header), encoding="utf-8")
    _prepare_fonts(workdir)

    start = float(clip["start"])
    duration = max(1.0, float(clip["end"]) - start)
    portrait = (info.get("height") or 0) >= (info.get("width") or 1)

    cmd = [
        ff, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-i", str(video),
        "-t", f"{duration:.3f}",
        "-filter_complex", _graph(portrait),
        "-map", "[v]",
    ]
    if info.get("has_audio", True):
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += [
        "-r", str(OUT_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(out_path),
    ]

    def handle(line: str) -> None:
        if cancel is not None and cancel.is_set():
            raise ToolError("cancelled")
        if on_progress and line.startswith("out_time="):
            match = re.match(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
            if match:
                h, m, s = match.groups()
                done = int(h) * 3600 + int(m) * 60 + float(s)
                pct = min(99.0, done / duration * 100)
                on_progress(pct, f"Rendering {pct:3.0f}%")

    code = run_streaming(cmd, handle, cwd=str(workdir), timeout=max(600.0, duration * 8))
    if code != 0:
        raise ToolError(f"ffmpeg failed while rendering clip (exit {code})")
    if not out_path.exists() or out_path.stat().st_size < 20_000:
        raise ToolError("render produced no usable file")

    thumb = out_path.with_name(out_path.stem + "_thumb.jpg")
    run(
        [ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", "1.0", "-i", str(out_path),
         "-frames:v", "1", "-vf", f"scale={OUT_W // 2}:{OUT_H // 2}", str(thumb)],
        check=False,
    )
    if not thumb.exists():
        thumb = out_path

    return {"file": out_path.name, "thumb": thumb.name, "bytes": out_path.stat().st_size}
