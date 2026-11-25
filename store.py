"""Thread-safe job store persisted to data/jobs.json."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import JOBS_DIR

STAGES = [
    ("queued", "Queued"),
    ("downloading", "Downloading video"),
    ("transcribing", "Transcribing audio"),
    ("analyzing", "Finding viral moments"),
    ("rendering", "Rendering clips"),
    ("done", "Done"),
]


def _new_job(url: str, options: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    return {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "options": options,
        "status": "queued",
        "stage": "queued",
        "progress": 0.0,
        "message": "Waiting in queue",
        "error": "",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "video": {},
        "transcript": {},
        "clips": [],
        "log": [],
        "llm": "",
    }


class JobStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (JOBS_DIR.parent / "jobs.json")
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for job in raw.get("jobs", []):
            if job.get("status") in ("queued", "downloading", "transcribing", "analyzing", "rendering"):
                job["status"] = "error"
                job["stage"] = "error"
                job["error"] = "Interrupted by server restart"
                job["message"] = "Interrupted by server restart"
            self._jobs[job["id"]] = job

    def _save(self) -> None:
        payload = {"jobs": list(self._jobs.values())}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # ---------------------------------------------------------------- api
    def create(self, url: str, options: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            job = _new_job(url, options)
            self._jobs[job["id"]] = job
            self._cancel[job["id"]] = threading.Event()
            self._save()
            return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
            return [dict(j) for j in jobs]

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = time.time()
            self._save()

    def append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            log = job.setdefault("log", [])
            log.append({"t": time.time(), "line": line[:400]})
            del log[:-200]
            job["updated_at"] = time.time()

    def cancel_event(self, job_id: str) -> threading.Event:
        with self._lock:
            if job_id not in self._cancel:
                self._cancel[job_id] = threading.Event()
            return self._cancel[job_id]

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] in ("done", "error", "cancelled"):
                return False
            self.cancel_event(job_id).set()
            return True

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            self._cancel.pop(job_id, None)
            if not job:
                return False
            self._save()
        return True

    def fail(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(
                status="error",
                stage="error",
                error=message,
                message=message,
                finished_at=time.time(),
                updated_at=time.time(),
            )
            self._save()

    def finish(self, job_id: str, clips: list[dict[str, Any]], video: dict, transcript: dict, llm: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(
                status="done",
                stage="done",
                progress=100.0,
                message=f"Ready - {len(clips)} clip{'s' if len(clips) != 1 else ''}",
                clips=clips,
                video=video,
                transcript=transcript,
                llm=llm,
                finished_at=time.time(),
                updated_at=time.time(),
            )
            self._save()
