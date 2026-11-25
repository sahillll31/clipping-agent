"""YouTube (and generic) video download via yt-dlp."""
from __future__ import annotations

import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from config import ffmpeg_path
from tools import ToolError, probe, run


class DownloadError(ToolError):
    pass


_YOUTUBE_RE = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/", re.I)


def is_supported(url: str) -> bool:
    return bool(re.match(r"^https?://", url.strip(), re.I))


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())[:160]


def download(
    url: str,
    workdir: Path,
    on_progress: Callable[[float, str], None] | None = None,
    cancel: Any = None,
) -> dict[str, Any]:
    """Download best mp4 up to 1080p, or import a local file."""
    local_path: Path | None = None
    if url.startswith("file://"):
        local_path = Path(urllib.parse.unquote(url[7:]))
    elif "://" not in url and Path(url).exists():
        local_path = Path(url)
    if local_path and local_path.is_file():
        return _import_local(local_path, workdir, on_progress)

    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise DownloadError("yt-dlp is not installed - run setup") from exc

    workdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(workdir / "source.%(ext)s")
    ff = ffmpeg_path()

    def hook(data: dict[str, Any]) -> None:
        if cancel is not None and cancel.is_set():
            raise DownloadError("cancelled")
        status = data.get("status")
        if not on_progress:
            return
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = (done / total * 100.0) if total else 0.0
            speed = data.get("speed") or 0
            speed_mb = f"{speed / 1048576:.1f} MB/s" if speed else ""
            on_progress(min(pct, 100.0), f"Downloading {pct:4.0f}% {speed_mb}".strip())
        elif status == "finished":
            on_progress(100.0, "Download complete, merging streams")

    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "format": (
            "bestvideo[height<=1080][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=1080][ext=mp4]/best[height<=1080]/best"
        ),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": False,
        "writeinfojson": False,
        "retries": 3,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
        "noprogress": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "overwrites": True,
        "cachedir": str(workdir / ".ytcache"),
    }
    if ff:
        opts["ffmpeg_location"] = ff

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(_friendly(str(exc))) from exc

    if not info:
        raise DownloadError("yt-dlp returned no metadata")
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise DownloadError("playlist contained no videos")
        info = entries[0]

    files = sorted(workdir.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    files = [f for f in files if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv")]
    if not files:
        raise DownloadError("download finished but no video file was produced")
    video_path = files[0]

    # Normalise odd containers to mp4 so downstream filters are predictable.
    if video_path.suffix.lower() != ".mp4":
        target = workdir / "source.mp4"
        from tools import run

        run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path), "-c", "copy", str(target)])
        video_path.unlink(missing_ok=True)
        video_path = target

    return {
        "path": str(video_path),
        "id": info.get("id") or "",
        "title": _clean_title(info.get("title") or video_path.stem),
        "channel": info.get("uploader") or info.get("channel") or "",
        "duration": float(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or "",
        "view_count": info.get("view_count") or 0,
        "upload_date": info.get("upload_date") or "",
        "webpage_url": info.get("webpage_url") or url,
    }


def _import_local(
    source: Path,
    workdir: Path,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Use a local video file as the source (useful for offline testing)."""
    workdir.mkdir(parents=True, exist_ok=True)
    if on_progress:
        on_progress(10.0, f"Importing {source.name}")
    target = workdir / ("source" + source.suffix.lower())
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    if target.suffix.lower() != ".mp4":
        ff = ffmpeg_path()
        mp4 = workdir / "source.mp4"
        run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(target),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "160k", str(mp4)])
        target.unlink(missing_ok=True)
        target = mp4
    info = probe(target)
    if on_progress:
        on_progress(100.0, "Local file ready")
    return {
        "path": str(target),
        "id": "local",
        "title": source.stem,
        "channel": "Local file",
        "duration": float(info.get("duration") or 0),
        "thumbnail": "",
        "view_count": 0,
        "upload_date": "",
        "webpage_url": source.as_uri(),
    }


def _friendly(message: str) -> str:
    low = message.lower()
    if "sign in to confirm" in low or "bot" in low and "cookies" in low:
        return (
            "YouTube asked for verification (bot check). Try again, or export browser cookies "
            "to data/cookies.txt and set YTDLP_COOKIES in the environment."
        )
    if "private video" in low:
        return "That video is private."
    if "video unavailable" in low or "not available" in low:
        return "That video is unavailable in this region or was removed."
    if "unsupported url" in low:
        return "Unsupported URL - paste a direct video link."
    if "age" in low and "confirm" in low:
        return "Age-restricted video - sign-in cookies are required."
    return message.splitlines()[0][:300] if message else "Download failed"


def cleanup_workdir(workdir: Path, keep_video: bool = False) -> None:
    """Remove bulky intermediates after rendering."""
    for pattern in ("*.wav", "*.ass", ".ytcache"):
        for path in workdir.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    if not keep_video:
        for path in workdir.glob("source.*"):
            path.unlink(missing_ok=True)
