"""Job orchestration: download -> transcribe -> analyze -> render."""
from __future__ import annotations

import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Any

import downloader
import moments
import render
import transcribe
import tools
from config import JOBS_DIR, load_config
from store import JobStore


def build_options(cfg: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    defaults = cfg.get("defaults") or {}

    def clamp(value: Any, low: float, high: float, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = fallback
        return max(low, min(high, number))

    target = clamp(raw.get("target_length", defaults.get("target_length", 40)), 15, 90, 40)
    count = int(clamp(raw.get("clip_count", defaults.get("clip_count", 5)), 1, 12, 5))
    return {
        "clip_count": count,
        "target_length": int(target),
        "min_length": max(10, int(target) - 12),
        "max_length": min(90, int(target) + 20),
        "captions": bool(raw.get("captions", defaults.get("captions", True))),
        "hook_header": bool(raw.get("hook_header", defaults.get("hook_header", True))),
        "niche": str(raw.get("niche") or defaults.get("niche") or "auto"),
        "llm": str(raw.get("llm") or defaults.get("llm") or "auto"),
    }


class Reporter:
    """Throttled progress writer so the JSON store is not hammered."""

    def __init__(self, store: JobStore, job_id: str, interval: float = 0.6) -> None:
        self.store = store
        self.job_id = job_id
        self.interval = interval
        self._last = 0.0

    def __call__(self, progress: float, message: str, *, stage: str | None = None, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last < self.interval:
            return
        self._last = now
        fields: dict[str, Any] = {
            "progress": round(max(0.0, min(100.0, progress)), 1),
            "message": message[:220],
        }
        if stage:
            fields["stage"] = stage
            fields["status"] = stage
        self.store.update(self.job_id, **fields)


def _span(value: float, lo: float, hi: float) -> float:
    return lo + (hi - lo) * max(0.0, min(1.0, value / 100.0))


def process_job(store: JobStore, job_id: str) -> None:
    cfg = load_config()
    job = store.get(job_id)
    if not job:
        return
    cancel = store.cancel_event(job_id)
    opts = job["options"]
    workdir = JOBS_DIR / job_id
    clips_dir = workdir / "clips"
    report = Reporter(store, job_id)

    def log(line: str) -> None:
        store.append_log(job_id, line)

    def cancelled() -> bool:
        return cancel.is_set()

    started = time.time()
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        store.update(
            job_id,
            status="downloading",
            stage="downloading",
            started_at=started,
            message="Resolving video",
            progress=1.0,
            error="",
        )

        # ---------------------------------------------------------- download
        video = downloader.download(
            job["url"],
            workdir,
            on_progress=lambda pct, msg: report(_span(pct, 2, 28), msg, stage="downloading"),
            cancel=cancel,
        )
        if cancelled():
            raise RuntimeError("cancelled")
        log(f"Downloaded: {video['title']} ({video['duration']:.0f}s)")
        store.update(
            job_id,
            video={
                "title": video["title"],
                "channel": video["channel"],
                "duration": video["duration"],
                "thumbnail": video["thumbnail"],
                "view_count": video["view_count"],
                "upload_date": video["upload_date"],
                "webpage_url": video["webpage_url"],
            },
            progress=28.0,
            message=f"Downloaded {video['title'][:70]}",
        )

        info = tools.probe(video["path"])
        if not info["duration"]:
            info["duration"] = video["duration"]
        if not info["has_audio"]:
            raise RuntimeError("This video has no audio track to transcribe")
        log(f"Media: {info['width']}x{info['height']}, {info['duration']:.0f}s")

        # ---------------------------------------------------------- transcribe
        store.update(job_id, status="transcribing", stage="transcribing", progress=30.0,
                     message="Extracting audio")
        wav = tools.extract_audio(video["path"], workdir / "audio.wav")
        report(32.0, "Loading whisper model", stage="transcribing", force=True)
        transcript = transcribe.transcribe(
            wav,
            workdir,
            duration=info["duration"],
            on_progress=lambda pct, msg: report(_span(pct, 32, 58), msg, stage="transcribing"),
            cancel=cancel,
        )
        if cancelled():
            raise RuntimeError("cancelled")
        log(f"Transcript: {transcript['word_count']} words, {len(transcript['segments'])} segments")
        store.update(
            job_id,
            transcript={
                "segments": [
                    {"start": s["start"], "end": s["end"], "text": s["text"]}
                    for s in transcript["segments"]
                ],
                "text": transcript["text"][:20000],
                "word_count": transcript["word_count"],
                "language": transcript["language"],
            },
            progress=58.0,
            message=f"Transcribed {transcript['word_count']} words",
        )

        # ---------------------------------------------------------- analyze
        store.update(job_id, status="analyzing", stage="analyzing", progress=60.0,
                     message="Scoring moments against trend patterns")
        clips, engine = moments.analyze(
            transcript,
            opts,
            wav=wav,
            duration=info["duration"],
            log=log,
            progress=lambda pct, msg: report(_span(pct, 60, 72), msg, stage="analyzing"),
            cancel=cancel,
        )
        if cancelled():
            raise RuntimeError("cancelled")
        store.update(job_id, llm=engine, progress=72.0,
                     message=f"{len(clips)} moments selected ({engine})")

        # ---------------------------------------------------------- render
        store.update(job_id, status="rendering", stage="rendering", progress=73.0,
                     message="Rendering vertical clips")
        public_clips: list[dict[str, Any]] = []
        total = max(1, len(clips))
        for idx, clip in enumerate(clips):
            if cancelled():
                raise RuntimeError("cancelled")
            base = idx + 1
            out_path = clips_dir / f"clip_{base:02d}.mp4"
            report(
                73.0 + 26.0 * (idx / total),
                f"Rendering clip {base}/{total}",
                stage="rendering",
                force=True,
            )
            try:
                rendered = render.render_clip(
                    video["path"],
                    clip,
                    workdir,
                    out_path,
                    info,
                    captions=opts["captions"],
                    hook_header=opts["hook_header"],
                    on_progress=lambda pct, msg, b=base: report(
                        73.0 + 26.0 * ((b - 1 + pct / 100.0) / total), f"Clip {b}/{total}: {msg}",
                        stage="rendering",
                    ),
                    cancel=cancel,
                )
            except Exception as exc:
                log(f"Clip {base} failed: {exc}")
                continue

            public_clip = {
                "id": f"c{base}",
                "index": len(public_clips),
                "start": clip["start"],
                "end": clip["end"],
                "duration": clip["duration"],
                "title": clip.get("title", ""),
                "hook": clip.get("hook", ""),
                "caption": clip.get("caption", ""),
                "hashtags": clip.get("hashtags", []),
                "score": clip.get("score", 0),
                "reason": clip.get("reason", ""),
                "niche": clip.get("niche", ""),
                "file": f"clips/{rendered['file']}",
                "thumb": f"clips/{rendered['thumb']}",
                "bytes": rendered["bytes"],
            }
            public_clips.append(public_clip)

        if not public_clips:
            raise RuntimeError("every clip failed to render - check the server log")

        (workdir / "clips.json").write_text(
            json.dumps(public_clips, indent=2), encoding="utf-8"
        )
        store.finish(
            job_id,
            public_clips,
            job.get("video") or {},
            job.get("transcript") or {},
            engine,
        )
        log(f"Done in {time.time() - started:.0f}s")

    except Exception as exc:  # noqa: BLE001
        if cancelled():
            store.update(
                job_id,
                status="cancelled",
                stage="cancelled",
                message="Cancelled",
                finished_at=time.time(),
            )
            log("Cancelled by user")
        else:
            message = str(exc) or exc.__class__.__name__
            log(f"ERROR: {message}")
            log(traceback.format_exc()[-1500:])
            store.fail(job_id, message)
    finally:
        if not cfg.get("keep_source"):
            downloader.cleanup_workdir(workdir)
            for leftover in ("audio.wav", "captions.ass"):
                (workdir / leftover).unlink(missing_ok=True)
            shutil.rmtree(workdir / "fonts", ignore_errors=True)
            (workdir / "transcript.json").unlink(missing_ok=True)
