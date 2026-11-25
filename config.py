"""Configuration and filesystem layout for ClipForge."""
from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
BIN_DIR = BASE_DIR / "bin"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
STATIC_DIR = BASE_DIR / "static"
WEB_DIST = BASE_DIR / "web" / "dist"
CONFIG_PATH = BASE_DIR / "config.json"
TRENDS_PATH = BASE_DIR / "trends.json"

IS_WINDOWS = platform.system() == "Windows"

DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8765,
    "ffmpeg": "",
    "ffprobe": "",
    "whisper_bin": "",
    "whisper_model": "ggml-small.en.bin",
    # auto: use cuda build when present, otherwise cpu
    "whisper_device": "auto",
    "threads": 0,
    "workers": 1,
    "llm": {
        # auto: use Ollama when reachable, otherwise local heuristics
        "enabled": "auto",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:3b",
        "timeout": 600,
    },
    "defaults": {
        "clip_count": 5,
        "target_length": 40,
        "min_length": 18,
        "max_length": 60,
        "captions": True,
        "hook_header": True,
        "niche": "auto",
        "llm": "auto",
    },
}

for _d in (DATA_DIR, JOBS_DIR, BIN_DIR, MODELS_DIR, FONTS_DIR, STATIC_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg = _deep_merge(cfg, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def _find_exe(*names: str) -> str:
    """Look in the project bin folder first, then on PATH."""
    for name in names:
        candidate = BIN_DIR / name
        if candidate.exists():
            return str(candidate)
        found = shutil.which(name)
        if found:
            return found
    if BIN_DIR.exists():
        lowered = [n.lower() for n in names]
        for path in BIN_DIR.rglob("*.exe"):
            if path.name.lower() in lowered:
                return str(path)
    return ""


def ffmpeg_path(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("ffmpeg") or _find_exe("ffmpeg.exe", "ffmpeg") or ""


def ffprobe_path(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("ffprobe") or _find_exe("ffprobe.exe", "ffprobe") or ""


def whisper_path(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return (
        cfg.get("whisper_bin")
        or _find_exe("whisper-cli.exe", "whisper.exe", "main.exe")
        or ""
    )


def model_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    return MODELS_DIR / cfg.get("whisper_model", "ggml-small.en.bin")


def resolve_device(cfg: dict[str, Any] | None = None) -> str:
    """Return 'cuda' only when a cuda-capable whisper build is configured."""
    cfg = cfg or load_config()
    device = (cfg.get("whisper_device") or "auto").lower()
    if device in ("cpu", "cuda"):
        return device
    marker = BIN_DIR / ".cuda-ok"
    return "cuda" if marker.exists() else "cpu"


def _version_of(exe: str) -> str:
    if not exe:
        return ""
    try:
        proc = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        text = (proc.stderr or "") + (proc.stdout or "")
        return text.strip().splitlines()[0][:80] if text.strip() else ""
    except Exception:
        return ""


def health(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    ff = ffmpeg_path(cfg)
    ffp = ffprobe_path(cfg)
    wh = whisper_path(cfg)
    mp = model_path(cfg)
    gpu = ""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        if proc.returncode == 0:
            gpu = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    except Exception:
        gpu = ""
    return {
        "ffmpeg": bool(ff),
        "ffprobe": bool(ffp),
        "whisper": bool(wh),
        "model": mp.exists(),
        "model_name": cfg.get("whisper_model"),
        "device": resolve_device(cfg),
        "gpu": gpu,
        "ffmpeg_version": _version_of(ff),
        "data_dir": str(DATA_DIR),
        "ready": bool(ff and ffp and wh and mp.exists()),
    }
