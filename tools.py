"""Small helpers around subprocesses and media probing."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Iterable

from config import IS_WINDOWS, ffmpeg_path, ffprobe_path, load_config

CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


class ToolError(RuntimeError):
    pass


def run(
    cmd: Iterable[str],
    *,
    cwd: str | Path | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if check and proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-1200:]
        raise ToolError(f"command failed ({proc.returncode}): {' '.join(cmd[:4])}...\n{tail}")
    return proc


def run_streaming(
    cmd: Iterable[str],
    on_output: Callable[[str], None] | None = None,
    *,
    cwd: str | Path | None = None,
    timeout: float | None = None,
) -> int:
    """Run a process, streaming stdout+stderr chunk-by-chunk (split on CR/LF)."""
    cmd = [str(c) for c in cmd]
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=0,
        creationflags=CREATE_NO_WINDOW,
    )
    buffer: list[str] = []
    deadline_hit = threading.Event()

    def _timer() -> None:
        if timeout:
            deadline_hit.set()
            try:
                proc.kill()
            except Exception:
                pass

    timer = threading.Timer(timeout, _timer) if timeout else None
    if timer:
        timer.daemon = True
        timer.start()
    try:
        assert proc.stdout is not None
        while True:
            ch = proc.stdout.read(1)
            if ch == "":
                break
            if ch in ("\r", "\n"):
                line = "".join(buffer).strip()
                buffer.clear()
                if line and on_output:
                    on_output(line)
            else:
                buffer.append(ch)
        line = "".join(buffer).strip()
        if line and on_output:
            on_output(line)
        code = proc.wait()
    finally:
        if timer:
            timer.cancel()
    if deadline_hit.is_set():
        raise ToolError("command timed out")
    return code


def probe(path: str | Path) -> dict:
    """Return width, height, duration, has_audio, fps for a media file."""
    exe = ffprobe_path()
    if not exe:
        raise ToolError("ffprobe not found - run setup first")
    proc = run(
        [
            exe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    data = json.loads(proc.stdout or "{}")
    info = {"width": 0, "height": 0, "duration": 0.0, "has_audio": False, "fps": 30.0}
    fmt = data.get("format") or {}
    try:
        info["duration"] = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        pass
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and not info["width"]:
            info["width"] = int(stream.get("width") or 0)
            info["height"] = int(stream.get("height") or 0)
            rate = stream.get("avg_frame_rate") or "30/1"
            try:
                num, _, den = rate.partition("/")
                info["fps"] = float(num) / float(den or 1) if float(den or 1) else 30.0
            except (ValueError, ZeroDivisionError):
                info["fps"] = 30.0
        if stream.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def extract_audio(video: str | Path, out_wav: str | Path, *, sample_rate: int = 16000) -> Path:
    exe = ffmpeg_path()
    if not exe:
        raise ToolError("ffmpeg not found - run setup first")
    out_wav = Path(out_wav)
    run(
        [
            exe,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ]
    )
    return out_wav


def humanize_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def atomic_write(path: str | Path, text: str) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
