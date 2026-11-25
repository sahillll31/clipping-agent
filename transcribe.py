"""Local speech-to-text through a whisper.cpp binary."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from config import load_config, model_path, resolve_device, whisper_path
from tools import ToolError, run_streaming

_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)\s*%", re.I)
_STAMP_RE = re.compile(r"\[(\d+):(\d+):(\d+)[.,](\d+)\s*-->\s*(\d+):(\d+):(\d+)[.,](\d+)\]")
_NOISE_RE = re.compile(
    r"^[\s\.\,\!\?\-]*$|^\[?(music|applause|laughter|blank_audio|silence|inaudible)\]?$|^[\(\[]?♪",
    re.I,
)


def _stamp_to_ms(h: str, m: str, s: str, frac: str) -> int:
    h, m, s = int(h), int(m), int(s)
    ms = int((frac + "000")[:3])
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def _load_words(json_path: Path) -> list[dict[str, Any]]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    entries = data.get("transcription") or data.get("segments") or []
    words: list[dict[str, Any]] = []
    for entry in entries:
        offsets = entry.get("offsets") or {}
        start = offsets.get("from")
        end = offsets.get("to")
        text = (entry.get("text") or "").strip()
        if start is None or end is None:
            stamps = entry.get("timestamps") or {}
            try:
                parts = re.findall(r"\d+", stamps.get("from", ""))
                start = _stamp_to_ms(*parts[:4]) if parts else None
                parts2 = re.findall(r"\d+", stamps.get("to", ""))
                end = _stamp_to_ms(*parts2[:4]) if parts2 else None
            except Exception:
                start = end = None
        if start is None or end is None:
            continue
        start_s, end_s = start / 1000.0, end / 1000.0
        if end_s <= start_s:
            end_s = start_s + 0.06
        if not text or _NOISE_RE.match(text) or _NOISE_RE.match(text.strip(".,!? ")):
            continue
        words.append({"start": round(start_s, 3), "end": round(end_s, 3), "text": text})
    return words


def _join_text(a: str, b: str) -> str:
    if not a:
        return b
    if b.startswith(("'", ",", ".", "!", "?", ":", ";", "%", ")", "s", "t", "re", "ve", "ll", "d", "m")):
        # whisper tokens usually carry their own leading space; only glue when punctuation
        if b[0] in "',.!?:;%)":
            return a + b
    if a.endswith((" ", "\n")):
        return a + b
    return a + " " + b


def build_segments(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        text = ""
        for w in current:
            text = _join_text(text, w["text"])
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            segments.append(
                {
                    "start": round(current[0]["start"], 3),
                    "end": round(current[-1]["end"], 3),
                    "text": text,
                    "words": [w.copy() for w in current],
                }
            )
        current.clear()

    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = (nxt["start"] - word["end"]) if nxt else 99.0
        dur = current[-1]["end"] - current[0]["start"]
        chars = sum(len(w["text"]) + 1 for w in current)
        ends_sentence = bool(re.search(r"[.!?][\"')\]]?$", word["text"]))
        ends_break = bool(re.search(r"[,;:][\"')\]]?$", word["text"]))
        long_enough = len(current) >= 4
        if (
            (ends_sentence and long_enough and chars >= 18)
            or chars >= 150
            or dur >= 14
            or (pause >= 0.9 and long_enough)
            or (ends_break and chars >= 90)
        ):
            flush()
    flush()
    return segments


def transcribe(
    wav: str | Path,
    workdir: Path,
    *,
    duration: float = 0.0,
    on_progress: Callable[[float, str], None] | None = None,
    cancel: Any = None,
) -> dict[str, Any]:
    cfg = load_config()
    exe = whisper_path(cfg)
    model = model_path(cfg)
    if not exe:
        raise ToolError("whisper.cpp binary not found - run setup")
    if not model.exists():
        raise ToolError(f"whisper model missing: {model.name} - run setup")

    out_prefix = workdir / "transcript"
    json_path = workdir / "transcript.json"
    json_path.unlink(missing_ok=True)
    device = resolve_device(cfg)
    threads = cfg.get("threads") or 0
    model_is_en = ".en." in model.name

    cmd = [
        exe,
        "-m",
        str(model),
        "-f",
        str(wav),
        "-of",
        str(out_prefix),
        "-oj",
        "-ml",
        "1",
        "-pp",
        "-l",
        "en" if model_is_en else "auto",
        "-t",
        str(threads or 8),
    ]
    if device == "cuda":
        cmd += ["-ngl", "99"]

    last_report = 0.0
    lines: list[str] = []

    def on_line(line: str) -> None:
        nonlocal last_report
        lines.append(line)
        if cancel is not None and cancel.is_set():
            raise ToolError("cancelled")
        match = _PROGRESS_RE.search(line)
        if match and on_progress:
            pct = float(match.group(1))
            now = time.time()
            if now - last_report > 0.4 or pct >= 100:
                last_report = now
                elapsed = duration * pct / 100.0 if duration else 0
                label = f"Transcribing {pct:3.0f}%"
                if duration:
                    label += f" ({elapsed:.0f}/{duration:.0f}s of audio)"
                on_progress(pct, label)
        elif on_progress and _STAMP_RE.search(line):
            stamp = _STAMP_RE.search(line)
            if stamp and duration:
                done = _stamp_to_ms(*stamp.groups()[:4]) / 1000.0
                pct = min(99.0, done / duration * 100.0)
                on_progress(max(pct, 1.0), f"Transcribing {pct:3.0f}%")

    timeout = max(900.0, duration * 4.0 + 300.0)
    code = run_streaming(cmd, on_line, cwd=str(workdir), timeout=timeout)
    if code != 0:
        tail = "\n".join(lines[-8:])
        raise ToolError(f"whisper.cpp exited with code {code}\n{tail}")

    if not json_path.exists():
        # whisper.cpp sometimes writes next to the cwd without the prefix
        candidates = list(workdir.glob("*.json"))
        candidates = [c for c in candidates if c != json_path]
        if not candidates:
            raise ToolError("whisper.cpp produced no transcript JSON")
        json_path = max(candidates, key=lambda p: p.stat().st_size)

    words = _load_words(json_path)
    if not words:
        raise ToolError("No speech detected in this video (empty transcript)")
    segments = build_segments(words)
    text = " ".join(s["text"] for s in segments)
    if on_progress:
        on_progress(100.0, f"Transcribed {len(words)} words")
    return {
        "words": words,
        "segments": segments,
        "text": text,
        "duration": duration or (words[-1]["end"] if words else 0),
        "language": "en" if model_is_en else "auto",
        "word_count": len(words),
    }
