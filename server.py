"""ClipForge web server (FastAPI + background workers)."""
from __future__ import annotations

import json
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import moments
import pipeline
from config import (
    JOBS_DIR,
    MODELS_DIR,
    STATIC_DIR,
    TRENDS_PATH,
    WEB_DIST,
    health,
    load_config,
    save_config,
)
from store import STAGES, JobStore

store = JobStore()
queue_: "queue.Queue[str]" = queue.Queue()
_workers: list[threading.Thread] = []


def _worker_loop(name: str) -> None:
    while True:
        job_id = queue_.get()
        try:
            pipeline.process_job(store, job_id)
        except Exception as exc:  # noqa: BLE001
            store.fail(job_id, f"worker error: {exc}")
        finally:
            queue_.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    count = max(1, min(4, int(cfg.get("workers") or 1)))
    for i in range(count):
        thread = threading.Thread(target=_worker_loop, args=(f"clipforge-{i}",), daemon=True)
        thread.start()
        _workers.append(thread)
    # Re-queue jobs that were waiting when the server stopped.
    for job in store.list():
        if job.get("status") == "queued":
            queue_.put(job["id"])
    yield
    for thread in _workers:
        thread.join(timeout=0.2)


app = FastAPI(title="ClipForge", version="1.0.0", lifespan=lifespan)


class JobRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    clip_count: int | None = None
    target_length: int | None = None
    niche: str | None = None
    captions: bool | None = None
    hook_header: bool | None = None
    llm: str | None = None


class ConfigRequest(BaseModel):
    whisper_model: str | None = None
    whisper_device: str | None = None
    workers: int | None = None
    keep_source: bool | None = None
    llm_model: str | None = None
    llm_enabled: str | None = None


def _public(job: dict[str, Any]) -> dict[str, Any]:
    data = dict(job)
    data.pop("log", None)
    data["log_tail"] = [entry["line"] for entry in (job.get("log") or [])[-8:]]
    data["stages"] = [{"key": key, "label": label} for key, label in STAGES]
    return data


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    cfg = load_config()
    status = health(cfg)
    status["llm"] = moments.llm_status(cfg)
    status["stages"] = [{"key": k, "label": v} for k, v in STAGES]
    status["defaults"] = cfg.get("defaults")
    status["queue"] = queue_.qsize()
    return status


@app.get("/api/jobs")
def api_jobs() -> dict[str, Any]:
    return {"jobs": [_public(job) for job in store.list()]}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict[str, Any]:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return _public(job)


@app.post("/api/jobs")
def api_create(request: JobRequest) -> dict[str, Any]:
    url = request.url.strip()
    is_remote = url.lower().startswith(("http://", "https://"))
    is_local = url.lower().startswith("file://") or (url and Path(url).is_file())
    if not (is_remote or is_local):
        raise HTTPException(400, "Paste a full http(s) video URL")
    cfg = load_config()
    if not health(cfg)["ready"]:
        raise HTTPException(503, "ClipForge is not set up yet - run setup first")
    options = pipeline.build_options(
        cfg, request.model_dump(exclude_none=True)
    )
    job = store.create(url, options)
    queue_.put(job["id"])
    return {"job": _public(job)}


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel(job_id: str) -> dict[str, Any]:
    if not store.get(job_id):
        raise HTTPException(404, "job not found")
    ok = store.request_cancel(job_id)
    return {"cancelled": ok}


@app.delete("/api/jobs/{job_id}")
def api_delete(job_id: str) -> dict[str, Any]:
    if not store.get(job_id):
        raise HTTPException(404, "job not found")
    store.request_cancel(job_id)
    import shutil

    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    store.delete(job_id)
    return {"deleted": True}


@app.get("/api/trends")
def api_trends() -> dict[str, Any]:
    try:
        return json.loads(TRENDS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"could not read trends: {exc}") from exc


@app.post("/api/trends/niches/{niche}")
def api_trends_add(niche: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = api_trends()
    niches = data.setdefault("niches", {})
    if niche not in niches:
        niches[niche] = {"label": niche.title(), "keywords": [], "hashtags": []}
    entry = niches[niche]
    for key in ("label", "keywords", "hashtags"):
        if key in payload:
            entry[key] = payload[key]
    TRENDS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "niches": list(niches)}


@app.get("/api/config")
def api_config() -> dict[str, Any]:
    cfg = load_config()
    cfg["models"] = [p.name for p in sorted(MODELS_DIR.glob("ggml-*.bin"))]
    cfg["llm_status"] = moments.llm_status(cfg)
    return cfg


@app.post("/api/config")
def api_set_config(request: ConfigRequest) -> dict[str, Any]:
    cfg = load_config()
    data = request.model_dump(exclude_none=True)
    if "llm_model" in data:
        cfg.setdefault("llm", {})["model"] = data.pop("llm_model")
    if "llm_enabled" in data:
        cfg.setdefault("llm", {})["enabled"] = data.pop("llm_enabled")
    if "whisper_model" in data and not (MODELS_DIR / data["whisper_model"]).exists():
        raise HTTPException(400, "model file not found in models/")
    cfg.update(data)
    save_config(cfg)
    return {"ok": True, "config": api_config()}


@app.get("/media/{job_id}/{rel:path}")
def media(job_id: str, rel: str, download: bool = Query(False)) -> FileResponse:
    base = (JOBS_DIR / job_id).resolve()
    target = (base / rel).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(403, "forbidden")
    if not target.is_file():
        raise HTTPException(404, "file not found")
    filename = target.name if download else None
    return FileResponse(
        target,
        filename=filename,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


spa_dir = WEB_DIST if (WEB_DIST / "index.html").exists() else STATIC_DIR
app.mount("/", StaticFiles(directory=str(spa_dir), html=True), name="web")


def main() -> None:
    import uvicorn

    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))
    status = health(cfg)
    print("\n  ClipForge")
    print(f"  -> http://{host}:{port}")
    print(f"  ffmpeg={status['ffmpeg']} whisper={status['whisper']} model={status['model']} device={status['device']}")
    if not status["ready"]:
        print("  !! setup incomplete - run:  .\\setup.ps1\n")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
