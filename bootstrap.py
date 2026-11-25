"""One-shot installer for ClipForge.

Downloads portable ffmpeg + whisper.cpp binaries, a local Whisper model and
installs Python dependencies into .venv. Safe to re-run (skips what exists).

    python bootstrap.py                 # CPU whisper (fast to install)
    python bootstrap.py --cuda          # GPU build for NVIDIA cards (~700MB)
    python bootstrap.py --model base.en # smaller/faster model
"""
from __future__ import annotations

import argparse
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / ".venv"
BIN = BASE / "bin"
MODELS = BASE / "models"
CONFIG = BASE / "config.json"

WHISPER_TAG = "b5907"
WHISPER_CUDA = f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_TAG}/whisper-bin-win-cuda-12.4.0-x64.zip"
WHISPER_CPU = f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_TAG}/whisper-bin-x64.zip"
FFMPEG_ZIP = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{name}"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def say(message: str) -> None:
    print(message, flush=True)


def ssl_context() -> ssl.SSLContext:
    for getter in ("certifi",):
        try:
            module = __import__(getter)
            return ssl.create_default_context(cafile=module.where())
        except Exception:
            pass
    try:
        from pip._vendor import certifi as vendored  # type: ignore

        return ssl.create_default_context(cafile=vendored.where())
    except Exception:
        return ssl.create_default_context()


def download(url: str, dest: Path, label: str) -> Path:
    if dest.exists() and dest.stat().st_size > 1024:
        say(f"  [skip] {label} already present ({dest.stat().st_size / 1048576:.0f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    say(f"  [get ] {label}")
    request = urllib.request.Request(url, headers={"User-Agent": "clipforge-setup"})
    start = time.time()
    last = 0.0
    with urllib.request.urlopen(request, context=ssl_context(), timeout=60) as response:
        total = int(response.headers.get("content-length") or 0)
        done = 0
        with open(part, "wb") as fh:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last > 0.8:
                    last = now
                    if total:
                        pct = done / total * 100
                        speed = done / max(0.1, now - start) / 1048576
                        say(f"        {pct:5.1f}%  {done / 1048576:6.0f}/{total / 1048576:.0f} MB  {speed:4.1f} MB/s")
                    else:
                        say(f"        {done / 1048576:6.0f} MB")
    part.replace(dest)
    say(f"  [done] {label} ({dest.stat().st_size / 1048576:.0f} MB)")
    return dest


def extract_zip(zip_path: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    return dest


def find_file(root: Path, name: str) -> Path | None:
    for path in root.rglob(name):
        return path
    return None


# ------------------------------------------------------------------ python env
def ensure_venv() -> Path:
    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        say("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    return python


def pip_install(python: Path) -> None:
    say("Installing Python dependencies...")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=False)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(BASE / "requirements.txt")],
        check=True,
    )
    say("  [done] dependencies")


# ------------------------------------------------------------------ binaries
def install_ffmpeg() -> tuple[str, str]:
    existing = BIN / "ffmpeg.exe"
    if existing.exists() and (BIN / "ffprobe.exe").exists():
        say("  [skip] ffmpeg already present")
        return str(existing), str(BIN / "ffprobe.exe")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = download(FFMPEG_ZIP, tmp_path / "ffmpeg.zip", "ffmpeg build (196 MB)")
        unpacked = extract_zip(archive, tmp_path / "ffmpeg")
        ffmpeg = find_file(unpacked, "ffmpeg.exe")
        ffprobe = find_file(unpacked, "ffprobe.exe")
        if not ffmpeg or not ffprobe:
            raise SystemExit("could not locate ffmpeg.exe in the archive")
        BIN.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ffmpeg, BIN / "ffmpeg.exe")
        shutil.copy2(ffprobe, BIN / "ffprobe.exe")
    say("  [done] ffmpeg + ffprobe")
    return str(BIN / "ffmpeg.exe"), str(BIN / "ffprobe.exe")


def _whisper_works(exe: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(exe), "-h"],
            capture_output=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "replace")
        return proc.returncode == 0 and "whisper" in text.lower()
    except Exception:
        return False


def install_whisper(prefer_cuda: bool) -> tuple[str, bool]:
    win_dir = BIN / "whisper"
    exe = win_dir / "whisper-cli.exe"
    marker_ok = (BIN / ".cuda-ok")
    if exe.exists() and _whisper_works(exe):
        is_cuda = marker_ok.exists()
        if prefer_cuda and not is_cuda:
            say("  [info] CPU whisper found, upgrading to CUDA build")
        else:
            say(f"  [skip] whisper.cpp already present ({'cuda' if is_cuda else 'cpu'})")
            return str(exe), is_cuda

    attempts = [("cuda", WHISPER_CUDA, 701)] if prefer_cuda else []
    attempts.append(("cpu", WHISPER_CPU, 9))

    for kind, url, size in attempts:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                archive = download(url, tmp_path / "whisper.zip", f"whisper.cpp {kind} ({size} MB)")
                unpacked = extract_zip(archive, tmp_path / "whisper")
                found = find_file(unpacked, "whisper-cli.exe") or find_file(unpacked, "main.exe")
                if not found:
                    raise SystemExit("whisper-cli.exe missing from archive")
                if win_dir.exists():
                    shutil.rmtree(win_dir)
                win_dir.mkdir(parents=True, exist_ok=True)
                for item in found.parent.iterdir():
                    target = win_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target)
                shutil.copy2(found, win_dir / "whisper-cli.exe")
            if _whisper_works(win_dir / "whisper-cli.exe"):
                if kind == "cuda":
                    marker_ok.write_text("ok", encoding="utf-8")
                else:
                    marker_ok.unlink(missing_ok=True)
                say(f"  [done] whisper.cpp ({kind})")
                return str(win_dir / "whisper-cli.exe"), kind == "cuda"
            say(f"  [warn] {kind} build did not run, trying fallback")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            say(f"  [warn] {kind} build failed: {exc}")
    raise SystemExit("could not install a working whisper.cpp binary")


def install_fonts() -> None:
    """Copy caption fonts from the OS. They are not redistributed with the repo."""
    fonts_dir = BASE / "assets" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    system = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in ("arialbd.ttf", "impact.ttf"):
        dest = fonts_dir / name
        if dest.exists() and dest.stat().st_size > 1024:
            continue
        src = system / name
        if src.exists():
            shutil.copy2(src, dest)
            say(f"  [done] caption font {name}")
        else:
            say(f"  [warn] {name} not found - libass will use a system fallback")


def install_model(name: str) -> Path:
    if not name.startswith("ggml-"):
        name = f"ggml-{name}"
    if not name.endswith(".bin"):
        name += ".bin"
    dest = MODELS / name
    if dest.exists():
        say(f"  [skip] model {name} already present")
        return dest
    download(MODEL_URL.format(name=name), dest, f"whisper model {name}")
    return dest


def write_config(ffmpeg: str, ffprobe: str, whisper: str, cuda: bool, model: str) -> None:
    import json

    cfg = {}
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.update(
        {
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
            "whisper_bin": whisper,
            "whisper_model": model,
            "whisper_device": "cuda" if cuda else "cpu",
        }
    )
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cuda", action="store_true", help="install the CUDA whisper build")
    parser.add_argument("--model", default="small.en", help="whisper model: base.en, small.en, small, medium")
    parser.add_argument("--skip-python", action="store_true")
    args = parser.parse_args()

    if os.name != "nt":
        say("This installer targets Windows; on other systems install ffmpeg/whisper.cpp manually.")
    say("\nClipForge setup\n---------------")

    python = ensure_venv()
    if not args.skip_python:
        pip_install(python)

    BIN.mkdir(exist_ok=True)
    MODELS.mkdir(exist_ok=True)
    install_fonts()
    ffmpeg, ffprobe = install_ffmpeg()
    whisper, cuda = install_whisper(args.cuda)
    model_path = install_model(args.model)
    write_config(ffmpeg, ffprobe, whisper, cuda, model_path.name)

    say("\nSetup complete.")
    say(f"  ffmpeg  : {ffmpeg}")
    say(f"  whisper : {whisper} ({'cuda' if cuda else 'cpu'})")
    say(f"  model   : {model_path.name}")
    say("\nStart the app:  .\\run.ps1   (or: .venv\\Scripts\\python.exe server.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
