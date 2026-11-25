"""Headless runner: python cli.py <url> [--clips 5] [--length 40]"""
from __future__ import annotations

import argparse
import sys
import time

import pipeline
from config import load_config
from store import JobStore


def main() -> int:
    parser = argparse.ArgumentParser(description="ClipForge headless clipping")
    parser.add_argument("url", help="video URL")
    parser.add_argument("--clips", type=int, default=None)
    parser.add_argument("--length", type=int, default=None)
    parser.add_argument("--niche", default="auto")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--no-hook", action="store_true")
    parser.add_argument("--llm", default="auto", choices=["auto", "off"])
    args = parser.parse_args()

    cfg = load_config()
    store = JobStore()
    raw = {
        "clip_count": args.clips,
        "target_length": args.length,
        "niche": args.niche,
        "captions": not args.no_captions,
        "hook_header": not args.no_hook,
        "llm": args.llm,
    }
    options = pipeline.build_options(cfg, {k: v for k, v in raw.items() if v is not None})
    job = store.create(args.url, options)
    print(f"job {job['id']} -> {args.url}")

    pipeline.process_job(store, job["id"])
    seen = ""
    while True:
        current = store.get(job["id"]) or {}
        if current.get("message") != seen:
            seen = current.get("message", "")
            print(f"[{current.get('stage')}] {current.get('progress')}% {seen}")
        if current.get("status") in ("done", "error", "cancelled"):
            break
        time.sleep(0.5)

    if current.get("status") == "error":
        print("FAILED:", current.get("error"))
        return 1
    if current.get("status") == "cancelled":
        print("cancelled")
        return 130
    for clip in current.get("clips", []):
        print(f"\n#{clip['index'] + 1} score={clip['score']} {clip['start']:.1f}-{clip['end']:.1f}s")
        print(f"  title : {clip['title']}")
        print(f"  hook  : {clip['hook']}")
        print(f"  file  : data/jobs/{job['id']}/{clip['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
