"""Trend-aware moment detection.

Two engines:
  * heuristic  - always available, scores every candidate window against
                 hook / emotion / curiosity / energy / structure signals.
  * ollama     - optional local LLM refinement when Ollama is running.
"""
from __future__ import annotations

import array
import json
import math
import re
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Callable

from config import TRENDS_PATH, load_config

STOPWORDS = {
    "the", "and", "that", "this", "with", "have", "from", "they", "will", "would", "there",
    "their", "what", "about", "which", "when", "your", "just", "like", "been", "were", "them",
    "then", "than", "into", "only", "some", "could", "should", "because", "really", "very",
    "much", "more", "most", "also", "even", "still", "going", "gonna", "wanna", "know",
    "think", "want", "need", "make", "made", "here", "where", "does", "did", "doing", "done",
    "get", "got", "getting", "one", "two", "out", "for", "you", "are", "was", "his", "her",
    "its", "our", "not", "but", "all", "can", "how", "why", "who", "now", "yes", "yeah",
    "okay", "ok", "well", "right", "thing", "things", "stuff", "kind", "sort", "lot",
}

INTERROGATIVES = {"how", "why", "what", "when", "who", "which", "where"}
IMPERATIVES = {"stop", "never", "dont", "don't", "do", "look", "listen", "imagine", "try",
               "start", "avoid", "watch", "take", "use", "remember", "forget"}
CONJUNCTIONS = {"and", "but", "so", "because", "or", "then", "also", "plus"}


# --------------------------------------------------------------------------- trends
def load_trends() -> dict[str, Any]:
    try:
        return json.loads(TRENDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hook_patterns": [], "viral_keywords": [], "curiosity_markers": [],
                "cta": ["Follow for more."], "title_templates": ["{hook}"],
                "niches": {"generic": {"label": "General", "keywords": [], "hashtags": ["#viral"]}}}


def detect_niche(text: str, trends: dict[str, Any], requested: str = "auto") -> str:
    niches = trends.get("niches") or {}
    if requested and requested != "auto" and requested in niches:
        return requested
    low = " " + text.lower() + " "
    best, best_hits = "generic", 0
    for key, niche in niches.items():
        if key == "generic":
            continue
        hits = sum(low.count(" " + kw + " ") + low.count(" " + kw + "s ") for kw in niche.get("keywords", []))
        if hits > best_hits:
            best, best_hits = key, hits
    return best


# --------------------------------------------------------------------------- audio
def audio_energy(wav: str | Path, bucket: float = 0.25) -> list[float]:
    """Per-bucket RMS loudness, normalised to 0..1."""
    try:
        with wave.open(str(wav), "rb") as fh:
            rate = fh.getframerate()
            frames = fh.readframes(fh.getnframes())
    except Exception:
        return []
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    size = max(1, int(rate * bucket))
    stride = max(1, size // 120)
    out: list[float] = []
    for i in range(0, len(samples), size):
        chunk = samples[i : i + size : stride]
        if not chunk:
            break
        total = 0
        for value in chunk:
            total += value * value
        out.append(math.sqrt(total / len(chunk)) / 32768.0)
    peak = max(out) if out else 1.0
    return [min(1.0, v / peak) for v in out] if peak else out


def _env_stats(env: list[float], start: float, end: float, bucket: float = 0.25) -> tuple[float, float, float]:
    if not env:
        return 0.0, 0.0, 0.0
    a = max(0, int(start / bucket))
    b = min(len(env), max(a + 1, int(end / bucket)))
    window = env[a:b]
    if not window:
        return 0.0, 0.0, 0.0
    mean = sum(window) / len(window)
    peak = max(window)
    quiet = sum(1 for v in window if v < 0.08) / len(window)
    return mean, peak, quiet


# --------------------------------------------------------------------------- scoring
def _sat(value: float, k: float) -> float:
    return value / (value + k) if value > 0 else 0.0


def _hook_score(text: str, trends: dict[str, Any]) -> tuple[float, list[str]]:
    low = text.lower()
    score, tags = 0.0, []
    if "?" in low:
        score += 1.0
        tags.append("question hook")
    first = re.sub(r"[^a-z']", "", low.split(" ")[0] if low else "")
    if first in INTERROGATIVES:
        score += 0.8
        tags.append("opens with question")
    if first in IMPERATIVES:
        score += 0.7
        tags.append("imperative open")
    for pattern in trends.get("hook_patterns", []):
        if pattern.lower().strip(":") in low:
            score += 1.0
            tags.append(f"trend hook: {pattern}")
            break
    if re.search(r"\b(you|your|you're)\b", low):
        score += 0.45
    if re.search(r"\d", low):
        score += 0.45
        tags.append("number")
    if re.search(r"\b(nobody|everyone|most people|people don't)\b", low):
        score += 0.7
        tags.append("contrarian")
    return min(1.0, score / 2.6), tags


def _count_markers(text: str, markers: list[str]) -> int:
    low = " " + text.lower() + " "
    return sum(low.count(m.lower()) for m in markers)


def _score_window(
    window: list[dict[str, Any]],
    env: list[float],
    trends: dict[str, Any],
    niche_keywords: list[str],
    target: float,
) -> dict[str, Any]:
    text = " ".join(s["text"] for s in window)
    low = " " + text.lower() + " "
    duration = max(0.5, window[-1]["end"] - window[0]["start"])
    words = sum(len(s["text"].split()) for s in window)
    wps = words / duration

    hook, hook_tags = _hook_score(" ".join(s["text"] for s in window[:2]), trends)
    viral_hits = _count_markers(text, trends.get("viral_keywords", []))
    emotion = _sat(viral_hits / max(1.0, words / 90.0), 3.0)
    curiosity = _sat(_count_markers(text, trends.get("curiosity_markers", [])), 2.0)
    numbers = _sat(len(re.findall(r"\b\d[\d,\.]*\b", text)), 3.0)
    topic = _sat(sum(1 for kw in niche_keywords if kw in low), 2.0)

    mean_e, peak_e, quiet = _env_stats(env, window[0]["start"], window[-1]["end"])
    energy = min(1.0, mean_e * 0.65 + peak_e * 0.35)
    rate = max(0.0, 1.0 - min(1.0, abs(wps - 3.2) / 2.4))

    last = window[-1]["text"].strip()
    first_word = re.sub(r"[^a-z']", "", window[0]["text"].lower().split(" ")[0])
    complete = 0.55
    if re.search(r"[.!?][\"')\]]?$", last):
        complete += 0.45
    if first_word in CONJUNCTIONS:
        complete -= 0.35
    complete = max(0.0, min(1.0, complete))

    length_fit = math.exp(-((duration - target) ** 2) / (2 * (0.42 * target) ** 2))

    total = (
        0.20 * hook
        + 0.16 * emotion
        + 0.12 * curiosity
        + 0.08 * numbers
        + 0.14 * energy
        + 0.06 * rate
        + 0.08 * complete
        + 0.06 * length_fit
        + 0.10 * topic
        - 0.10 * quiet
    )
    total = max(0.0, min(1.0, total))

    reasons: list[str] = list(hook_tags)
    if emotion > 0.45:
        reasons.append(f"{viral_hits} emotional triggers")
    if curiosity > 0.4:
        reasons.append("curiosity gap")
    if energy > 0.55:
        reasons.append("high vocal energy")
    if numbers > 0.3:
        reasons.append("specific numbers")
    if topic > 0.4:
        reasons.append("on-niche topic")
    if quiet > 0.3:
        reasons.append("some dead air")
    if not reasons:
        reasons.append("balanced pacing")

    return {
        "start": round(window[0]["start"], 3),
        "end": round(window[-1]["end"], 3),
        "duration": round(duration, 2),
        "score": round(total * 100, 1),
        "text": text,
        "parts": {k: round(v, 3) for k, v in {
            "hook": hook, "emotion": emotion, "curiosity": curiosity, "numbers": numbers,
            "energy": energy, "rate": rate, "complete": complete, "length": length_fit, "topic": topic,
        }.items()},
        "reasons": reasons[:4],
        "wps": round(wps, 2),
    }


def _candidates(
    segments: list[dict[str, Any]],
    env: list[float],
    trends: dict[str, Any],
    niche_keywords: list[str],
    opts: dict[str, Any],
) -> list[dict[str, Any]]:
    target = float(opts["target_length"])
    min_len = float(opts["min_length"])
    max_len = float(opts["max_length"])
    out: list[dict[str, Any]] = []
    n = len(segments)
    for i in range(n):
        for j in range(i, n):
            duration = segments[j]["end"] - segments[i]["start"]
            if duration > max_len:
                break
            if duration < min_len:
                continue
            scored = _score_window(segments[i : j + 1], env, trends, niche_keywords, target)
            scored["i"], scored["j"] = i, j
            out.append(scored)
    return out


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    shorter = max(0.1, min(a["end"] - a["start"], b["end"] - b["start"]))
    return inter / shorter


def _select(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda c: c["score"], reverse=True)
    chosen: list[dict[str, Any]] = []
    for threshold in (0.2, 0.45, 0.75):
        for cand in ordered:
            if len(chosen) >= count:
                break
            if any(cand is c for c in chosen):
                continue
            if all(_overlap(cand, c) < threshold for c in chosen):
                chosen.append(cand)
        if len(chosen) >= count:
            break
    return sorted(chosen, key=lambda c: c["start"])


# --------------------------------------------------------------------------- metadata
def _keywords(text: str, limit: int = 4) -> list[str]:
    counts: dict[str, int] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", text):
        low = word.lower()
        if low in STOPWORDS:
            continue
        counts[low] = counts.get(low, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:limit]]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _first_sentence(text: str, max_words: int = 12) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.+?[.!?])(\s|$)", cleaned)
    sentence = match.group(1) if match else cleaned
    words = sentence.split()
    if len(words) > max_words:
        sentence = " ".join(words[:max_words])
    return sentence.rstrip(" ,;:")


def _local_metadata(clip: dict[str, Any], trends: dict[str, Any], niche: str, used_hooks: set[str]) -> None:
    niche_data = (trends.get("niches") or {}).get(niche) or {}
    hook_src = _first_sentence(clip["text"], 11)
    hook = hook_src
    if not re.search(r"[.!?]$", hook):
        hook = hook + "."
    if hook.lower() in used_hooks:
        hook = hook_src
    used_hooks.add(hook.lower())

    topic_words = _keywords(clip["text"], 3)
    topic = topic_words[0] if topic_words else (niche_data.get("label") or "this").lower()

    title = hook_src[:70].rstrip(" ,;:")
    if len(title.split()) < 4:
        template = (trends.get("title_templates") or ["{hook}"])[0]
        title = template.format(hook=hook_src, topic=topic)[:70]

    sentences = re.split(r"(?<=[.!?])\s+", clip["text"])
    caption_body = " ".join(sentences[:2]).strip()
    if len(caption_body) > 190:
        caption_body = caption_body[:187].rsplit(" ", 1)[0] + "..."
    ctas = trends.get("cta") or ["Follow for more."]
    cta = ctas[(len(clip["text"]) + int(clip["start"])) % len(ctas)]
    caption = f"{caption_body} {cta}".strip()

    tags: list[str] = []
    for tag in niche_data.get("hashtags", [])[:3]:
        tags.append(tag)
    for word in topic_words:
        slug = _slug(word)
        if slug and len(slug) > 3 and f"#{slug}" not in tags:
            tags.append(f"#{slug}")
    for tag in (trends.get("niches", {}).get("generic", {}).get("hashtags") or [])[:2]:
        if tag not in tags:
            tags.append(tag)

    clip.update(
        title=title or hook_src,
        hook=hook,
        caption=caption,
        hashtags=tags[:6],
        niche=niche,
    )


# --------------------------------------------------------------------------- ollama
def _http_json(url: str, payload: dict[str, Any] | None, timeout: float) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def llm_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    llm = cfg.get("llm") or {}
    base = (llm.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    want = llm.get("model") or ""
    try:
        data = _http_json(f"{base}/api/tags", None, 2.5)
    except Exception:
        return {"available": False, "model": want, "models": []}
    models = [m.get("name", "") for m in (data.get("models") or [])]
    match = next((m for m in models if m == want or m.split(":")[0] == want.split(":")[0]), "")
    return {"available": bool(match), "model": match or want, "models": models}


def _llm_refine(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    duration: float,
    cfg: dict[str, Any],
    trends: dict[str, Any],
    niche: str,
    log: Callable[[str], None],
    progress: Callable[[float, str], None] | None,
    cancel: Any,
) -> tuple[list[dict[str, Any]], str] | None:
    status = llm_status(cfg)
    if not status["available"]:
        return None
    llm = cfg.get("llm") or {}
    base = (llm.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = status["model"]

    shortlist = sorted(candidates, key=lambda c: c["score"], reverse=True)[: max(count * 2, 6)]
    shortlist.sort(key=lambda c: c["start"])
    lines = []
    for idx, cand in enumerate(shortlist):
        snippet = re.sub(r"\s+", " ", cand["text"])[:650]
        lines.append(f"[{idx}] {cand['start']:.1f}s-{cand['end']:.1f}s (heuristic {cand['score']:.0f})\n{snippet}")

    prompt = (
        "You are a short-form video editor who knows exactly what performs on TikTok, Reels and Shorts.\n"
        f"Pick the best {count} self-contained moments from these candidate clips of a {duration:.0f}s video.\n"
        "Rules: each clip 20-60s, must start with a strong hook in the first 3 seconds, never cut mid-sentence, "
        "no overlaps, prefer emotion, curiosity, concrete numbers and payoff. Return ONLY JSON.\n"
        f"Trend hook patterns: {', '.join(trends.get('hook_patterns', [])[:10])}\n"
        f"Niche: {niche}\n\n"
        "JSON shape: {\"clips\":[{\"index\":<candidate index>,\"start\":<sec>,\"end\":<sec>,"
        "\"title\":\"<=70 chars\",\"hook\":\"punchy 6-10 word overlay\",\"caption\":\"1-2 sentence caption with CTA\","
        "\"hashtags\":[\"#tag\"],\"score\":<0-100>,\"reason\":\"why it works\"}]}\n\n"
        + "\n\n".join(lines)
    )

    if progress:
        progress(10.0, f"Asking {model} to rank moments")
    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You output strict JSON only. No markdown."},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.55, "num_ctx": 8192},
        }
        data = _http_json(f"{base}/api/chat", payload, float(llm.get("timeout") or 600))
        content = ((data.get("message") or {}).get("content") or "").strip()
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
        parsed = json.loads(content)
        raw_clips = parsed.get("clips") or parsed.get("moments") or []
        if not isinstance(raw_clips, list) or not raw_clips:
            raise ValueError("LLM returned no clips")
    except Exception as exc:
        log(f"LLM refinement skipped: {exc}")
        return None

    refined: list[dict[str, Any]] = []
    used: set[int] = set()
    for item in raw_clips:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(shortlist) or idx in used:
            continue
        cand = shortlist[idx]
        start = float(item.get("start") or cand["start"])
        end = float(item.get("end") or cand["end"])
        start = max(cand["start"] - 3.0, min(start, cand["end"] - 15))
        end = min(cand["end"] + 3.0, max(end, start + 15))
        start = max(0.0, start)
        end = min(duration or end, end)
        if end - start < 12:
            continue
        if any(_overlap({"start": start, "end": end}, r) > 0.25 for r in refined):
            continue
        used.add(idx)
        merged = dict(cand)
        merged.update(start=round(start, 2), end=round(end, 2), duration=round(end - start, 2))
        merged["score"] = max(float(cand["score"]), min(99.0, float(item.get("score") or cand["score"])))
        for key in ("title", "hook", "caption", "reason"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                merged[key] = value.strip()[:220]
        tags = item.get("hashtags")
        if isinstance(tags, list):
            cleaned = []
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    tag = tag.strip()
                    cleaned.append(tag if tag.startswith("#") else "#" + _slug(tag))
            if cleaned:
                merged["hashtags"] = cleaned[:6]
        refined.append(merged)

    if not refined:
        return None
    refined = sorted(refined, key=lambda c: c["score"], reverse=True)[:count]
    refined.sort(key=lambda c: c["start"])
    return refined, f"ollama:{model}"


# --------------------------------------------------------------------------- public
def analyze(
    transcript: dict[str, Any],
    opts: dict[str, Any],
    *,
    wav: str | Path | None = None,
    duration: float = 0.0,
    log: Callable[[str], None] = lambda _m: None,
    progress: Callable[[float, str], None] | None = None,
    cancel: Any = None,
) -> tuple[list[dict[str, Any]], str]:
    cfg = load_config()
    trends = load_trends()
    segments = [s for s in transcript.get("segments") or [] if s.get("text")]
    if not segments:
        raise ValueError("transcript has no usable segments")
    duration = duration or segments[-1]["end"]

    niche = detect_niche(transcript.get("text", ""), trends, opts.get("niche", "auto"))
    niche_keywords = [k.lower() for k in (trends.get("niches", {}).get(niche, {}) or {}).get("keywords", [])]
    log(f"Detected niche: {niche}")

    env = audio_energy(wav) if wav and Path(wav).exists() else []
    if env:
        log(f"Audio energy map: {len(env)} buckets")

    count = int(opts.get("clip_count") or 5)
    min_len = float(opts.get("min_length") or 18)
    max_len = float(opts.get("max_length") or 60)

    # Very short source: one clip, whole thing.
    if duration <= max_len:
        if progress:
            progress(100.0, "Short video - using the whole clip")
        clip = _score_window(segments, env, trends, niche_keywords, max(duration, min_len))
        clip["start"], clip["end"] = round(segments[0]["start"], 2), round(segments[-1]["end"], 2)
        clips = [clip]
    else:
        if progress:
            progress(15.0, "Scoring candidate moments")
        candidates = _candidates(segments, env, trends, niche_keywords, opts)
        if cancel is not None and cancel.is_set():
            raise RuntimeError("cancelled")
        if not candidates:
            raise ValueError("could not build any candidate clip")
        max_possible = max(1, int(duration // max(min_len * 0.8, 8)))
        clips = _select(candidates, min(count, max_possible))
        log(f"Scored {len(candidates)} windows, kept {len(clips)}")

    used_hooks: set[str] = set()
    for clip in clips:
        _local_metadata(clip, trends, niche, used_hooks)

    engine = "heuristic"
    mode = str(opts.get("llm") or "auto").lower()
    if str((cfg.get("llm") or {}).get("enabled") or "auto").lower() == "off":
        mode = "off"
    if mode != "off" and len(clips) > 0 and duration > max_len:
        if progress:
            progress(35.0, "Checking local LLM")
        result = _llm_refine(
            clips, count=min(count, len(clips)), duration=duration, cfg=cfg, trends=trends,
            niche=niche, log=log, progress=progress, cancel=cancel,
        )
        if result:
            clips, engine = result
            log(f"LLM ranked clips with {engine}")
        else:
            log("Using heuristic ranking (LLM unavailable)")

    if cancel is not None and cancel.is_set():
        raise RuntimeError("cancelled")

    # Attach word timings + final tidy-up.
    all_words = transcript.get("words") or []
    final: list[dict[str, Any]] = []
    for index, clip in enumerate(clips):
        start = max(0.0, float(clip["start"]))
        end = min(duration, float(clip["end"]))
        if end - start < 6:
            continue
        words = [w for w in all_words if w["end"] > start and w["start"] < end]
        clip["start"], clip["end"] = round(start, 2), round(end, 2)
        clip["duration"] = round(end - start, 2)
        clip["index"] = len(final)
        clip["words"] = [
            {
                "start": round(max(0.0, w["start"] - start), 3),
                "end": round(min(end - start, w["end"] - start), 3),
                "text": w["text"],
            }
            for w in words
        ]
        clip["score"] = int(round(float(clip.get("score") or 0)))
        clip.setdefault("hashtags", [])
        clip.setdefault("niche", niche)
        final.append(clip)

    if not final:
        raise ValueError("no clips survived validation")
    if progress:
        progress(100.0, f"Selected {len(final)} moments")
    return final, engine
