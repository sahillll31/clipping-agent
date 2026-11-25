const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const STAGE_ORDER = ["queued", "downloading", "transcribing", "analyzing", "rendering", "done"];

const state = {
  health: null,
  config: null,
  trends: null,
  jobs: [],
  nodes: new Map(),
  pollTimer: null,
  busy: false,
};

const jobsEl = $("#jobs");
const emptyEl = $("#empty");
const jobTemplate = $("#jobTemplate");
const clipTemplate = $("#clipTemplate");
const toastEl = $("#toast");

/* ------------------------------------------------------------------ utils */
async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw new Error((payload && payload.detail) || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toastEl.classList.remove("show"), 2200);
}

function fmtTime(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}h ${m}m` : `${m}m ${String(r).padStart(2, "0")}s`;
}

function fmtCount(n) {
  n = Number(n) || 0;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

/* ------------------------------------------------------------------ health */
function pill(label, okState, text) {
  const span = document.createElement("span");
  span.className = `pill ${okState}`;
  span.innerHTML = "<i></i>";
  span.append(document.createTextNode(text || label));
  return span;
}

function renderHealth() {
  const health = state.health;
  const container = $("#health");
  container.textContent = "";
  if (!health) return;

  container.append(pill("ffmpeg", health.ffmpeg ? "ok" : "bad", "ffmpeg"));
  container.append(pill("whisper", health.whisper ? "ok" : "bad", "whisper"));
  container.append(pill("model", health.model ? "ok" : "bad", health.model ? (health.model_name || "model") : "model"));

  const deviceText = health.device === "cuda" ? "GPU · CUDA" : "CPU";
  container.append(pill("device", health.device === "cuda" ? "ok" : "muted", deviceText));

  const llm = health.llm || {};
  if (llm.available) {
    container.append(pill("llm", "ok", `LLM · ${llm.model}`));
  } else {
    container.append(pill("llm", "muted", "LLM off"));
  }

  const missing = [];
  if (!health.ffmpeg) missing.push("ffmpeg");
  if (!health.ffprobe) missing.push("ffprobe");
  if (!health.whisper) missing.push("whisper.cpp");
  if (!health.model) missing.push("whisper model");
  const notice = $("#setupNotice");
  if (missing.length) {
    notice.hidden = false;
    $("#setupDetail").textContent = `Missing: ${missing.join(", ")}. Run the installer once:`;
  } else {
    notice.hidden = true;
  }

  const queueBadge = $("#queueBadge");
  const active = state.jobs.filter((j) => ["queued", "downloading", "transcribing", "analyzing", "rendering"].includes(j.status)).length;
  if (active) {
    queueBadge.hidden = false;
    queueBadge.textContent = `${active} in progress · ${health.queue || 0} queued`;
  } else {
    queueBadge.hidden = true;
  }
}

/* ------------------------------------------------------------------ jobs */
function createJobNode(job) {
  const node = jobTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.id = job.id;

  $(".cancel-btn", node).addEventListener("click", async () => {
    try {
      await api(`/api/jobs/${job.id}/cancel`, { method: "POST" });
      toast("Cancellation requested");
    } catch (err) { toast(err.message); }
  });

  $(".delete-btn", node).addEventListener("click", async () => {
    if (!confirm("Remove this job and its clips?")) return;
    try {
      await api(`/api/jobs/${job.id}`, { method: "DELETE" });
      state.nodes.get(job.id)?.remove();
      state.nodes.delete(job.id);
      toast("Job removed");
      await poll();
    } catch (err) { toast(err.message); }
  });

  return node;
}

function stageIndex(status) {
  const idx = STAGE_ORDER.indexOf(status);
  return idx === -1 ? 0 : idx;
}

function updateJobNode(node, job) {
  const done = job.status === "done";
  const failed = job.status === "error";
  const cancelled = job.status === "cancelled";
  const active = !done && !failed && !cancelled;

  const img = $(".job-thumb img", node);
  const thumb = job.video?.thumbnail || "";
  if (thumb && img.dataset.src !== thumb) {
    img.dataset.src = thumb;
    img.src = thumb;
    img.alt = job.video?.title || "";
  } else if (!thumb) {
    img.removeAttribute("src");
  }

  $(".job-title", node).textContent = job.video?.title || job.url;
  const sub = [];
  if (job.video?.channel) sub.push(job.video.channel);
  if (job.video?.duration) sub.push(fmtDuration(job.video.duration));
  if (job.video?.view_count) sub.push(`${fmtCount(job.video.view_count)} views`);
  if (!sub.length) sub.push(job.url.replace(/^https?:\/\/(www\.)?/, "").slice(0, 70));
  $(".job-sub", node).textContent = sub.join("  ·  ");

  const badge = $(".stage-pill", node);
  let label = job.status === "done" ? "complete" : job.status;
  if (cancelled) label = "cancelled";
  if (failed) label = "failed";
  badge.textContent = label;
  badge.className = "pill stage-pill";
  if (done) badge.classList.add("done");
  else if (failed || cancelled) badge.classList.add("error");
  else badge.classList.add("active");

  const pct = Math.max(0, Math.min(100, Number(job.progress) || 0));
  $(".bar i", node).style.width = `${done ? 100 : pct}%`;
  $(".pct", node).textContent = `${Math.round(done ? 100 : pct)}%`;

  let message = job.message || "";
  if (failed) message = job.error || "Something went wrong";
  if (cancelled) message = "Cancelled";
  $(".job-msg", node).textContent = message;
  $(".job-msg", node).style.color = failed ? "#ff9aa3" : "";

  const stages = $(".stages", node);
  if (!stages.children.length) {
    (job.stages || STAGE_ORDER.map((k) => ({ key: k, label: k }))).forEach((stage) => {
      const li = document.createElement("li");
      li.dataset.key = stage.key;
      li.innerHTML = "<i></i>";
      li.append(document.createTextNode(stage.label));
      stages.append(li);
    });
  }
  const current = stageIndex(job.status);
  $$("li", stages).forEach((li) => {
    const idx = STAGE_ORDER.indexOf(li.dataset.key);
    li.className = "";
    if (failed || cancelled) {
      if (idx < current || idx === current) li.classList.add(idx === current ? "error" : "done");
    } else if (done || idx < current) {
      li.classList.add("done");
    } else if (idx === current) {
      li.classList.add("active");
    }
  });

  const log = $(".log pre", node);
  const tail = (job.log_tail || []).join("\n");
  if (log.textContent !== tail) {
    log.textContent = tail || "No output yet.";
  }

  const cancelBtn = $(".cancel-btn", node);
  cancelBtn.hidden = !active;
  const deleteBtn = $(".delete-btn", node);
  deleteBtn.hidden = active;
  const openSrc = $(".open-src", node);
  if (job.url) {
    openSrc.hidden = false;
    openSrc.href = job.url;
  }

  if (job.clips?.length && Number(node.dataset.clipCount || -1) !== job.clips.length) {
    node.dataset.clipCount = String(job.clips.length);
    renderClips($(".clips", node), job);
  }
  if (job.clips?.length) {
    $(".stages", node).style.display = "none";
  }
}

function renderClips(container, job) {
  container.textContent = "";
  job.clips.forEach((clip) => {
    const card = clipTemplate.content.firstElementChild.cloneNode(true);
    const video = $("video", card);
    video.src = `/media/${job.id}/${clip.file}`;
    video.poster = `/media/${job.id}/${clip.thumb}`;

    video.addEventListener("mouseenter", () => { video.play().catch(() => {}); });
    video.addEventListener("mouseleave", () => { video.pause(); video.currentTime = 0; });

    const score = Number(clip.score) || 0;
    const badge = $(".score-badge", card);
    badge.textContent = String(score);
    badge.title = `Trend score ${score}/100 — ${clip.reason || ""}`;
    if (score < 45) badge.classList.add("low");
    else if (score < 65) badge.classList.add("mid");

    $(".clip-time", card).textContent = `${fmtTime(clip.start)}–${fmtTime(clip.end)}`;
    $(".clip-title", card).textContent = clip.title || `Clip ${clip.index + 1}`;
    $(".clip-hook", card).textContent = clip.hook || "";
    $(".clip-caption", card).textContent = clip.caption || "";
    if (clip.reason) {
      $(".clip-title", card).title = `Why: ${clip.reason}`;
    }

    const tags = $(".tags", card);
    (clip.hashtags || []).forEach((tag) => {
      const span = document.createElement("span");
      span.textContent = tag;
      tags.append(span);
    });

    const dl = $(".dl", card);
    dl.href = `/media/${job.id}/${clip.file}?download=1`;
    dl.download = `${(clip.title || "clip").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-").slice(0, 50) || "clip"}.mp4`;

    $(".copy", card).addEventListener("click", async () => {
      const text = `${clip.caption || ""}\n\n${(clip.hashtags || []).join(" ")}`.trim();
      try {
        await navigator.clipboard.writeText(text);
        toast("Caption copied");
      } catch {
        toast("Could not access clipboard");
      }
    });

    container.append(card);
  });
}

function renderJobs() {
  const seen = new Set();
  state.jobs.forEach((job) => {
    seen.add(job.id);
    let node = state.nodes.get(job.id);
    if (!node) {
      node = createJobNode(job);
      state.nodes.set(job.id, node);
      jobsEl.append(node);
    }
    updateJobNode(node, job);
  });
  for (const [id, node] of state.nodes) {
    if (!seen.has(id)) {
      node.remove();
      state.nodes.delete(id);
    }
  }
  // keep DOM order in sync with newest-first list
  state.jobs.forEach((job) => {
    const node = state.nodes.get(job.id);
    if (node) jobsEl.append(node);
  });
  emptyEl.hidden = state.jobs.length > 0;
}

/* ------------------------------------------------------------------ polling */
async function poll() {
  try {
    const [jobsPayload, health] = await Promise.all([
      api("/api/jobs"),
      api("/api/health"),
    ]);
    state.jobs = jobsPayload.jobs || [];
    state.health = health;
    renderHealth();
    renderJobs();
  } catch (err) {
    console.error(err);
  }
}

function schedulePoll() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if (!document.hidden) poll();
  }, 2000);
}

/* ------------------------------------------------------------------ form */
async function submitJob(event) {
  event.preventDefault();
  if (state.busy) return;
  const url = $("#url").value.trim();
  if (!url) return;

  state.busy = true;
  const btn = $("#forgeBtn");
  btn.disabled = true;
  $(".spinner", btn).hidden = false;

  const payload = {
    url,
    niche: $("#niche").value,
    clip_count: Number($("#clips").value),
    target_length: Number($("#length").value),
    captions: $("#captions").checked,
    hook_header: $("#hook").checked,
    llm: $("#llm").checked ? "auto" : "off",
  };

  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    $("#url").value = "";
    toast("Job queued — transcribing locally");
    await poll();
  } catch (err) {
    toast(err.message);
  } finally {
    state.busy = false;
    btn.disabled = false;
    $(".spinner", btn).hidden = true;
  }
}

/* ------------------------------------------------------------------ settings */
function openDrawer() {
  const cfg = state.config;
  if (cfg) {
    const modelSelect = $("#setModel");
    modelSelect.textContent = "";
    const models = cfg.models?.length ? cfg.models : [cfg.whisper_model].filter(Boolean);
    models.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name.replace(/^ggml-/, "").replace(/\.bin$/, "");
      option.selected = name === cfg.whisper_model;
      modelSelect.append(option);
    });
    $("#setDevice").value = cfg.whisper_device || "auto";
    $("#setWorkers").value = String(cfg.workers || 1);
    $("#setKeep").checked = Boolean(cfg.keep_source);
    const llmCfg = cfg.llm || {};
    $("#setLlm").checked = (llmCfg.enabled || "auto") !== "off";
    $("#setLlmModel").value = llmCfg.model || "";
  }
  const llm = state.health?.llm || {};
  $("#llmStatusLine").textContent = llm.available
    ? `Ollama ready · ${llm.model}`
    : "Ollama not detected — heuristic ranking will be used (still fully automatic).";

  const grid = $("#statGrid");
  grid.textContent = "";
  const stats = [
    ["Device", state.health?.device === "cuda" ? "CUDA" : "CPU"],
    ["GPU", state.health?.gpu || "—"],
    ["ffmpeg", state.health?.ffmpeg ? "ready" : "missing"],
    ["Data", state.health?.data_dir ? "local" : "—"],
  ];
  stats.forEach(([label, value]) => {
    const cell = document.createElement("div");
    cell.className = "stat";
    const span = document.createElement("span");
    span.textContent = label;
    const b = document.createElement("b");
    b.textContent = value;
    cell.append(span, b);
    grid.append(cell);
  });

  $("#drawer").hidden = false;
  $("#drawerBackdrop").hidden = false;
}

function closeDrawer() {
  $("#drawer").hidden = true;
  $("#drawerBackdrop").hidden = true;
}

async function saveSettings() {
  try {
    const payload = {
      whisper_model: $("#setModel").value,
      whisper_device: $("#setDevice").value,
      workers: Number($("#setWorkers").value),
      keep_source: $("#setKeep").checked,
      llm_enabled: $("#setLlm").checked ? "auto" : "off",
      llm_model: $("#setLlmModel").value.trim() || undefined,
    };
    const result = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
    state.config = result.config;
    closeDrawer();
    toast("Settings saved (worker count applies after restart)");
  } catch (err) {
    toast(err.message);
  }
}

/* ------------------------------------------------------------------ init */
async function init() {
  $("#composer").addEventListener("submit", submitJob);
  $("#settingsBtn").addEventListener("click", openDrawer);
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawerBackdrop").addEventListener("click", closeDrawer);
  $("#saveSettings").addEventListener("click", saveSettings);

  $("#pasteBtn").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        $("#url").value = text.trim();
        $("#url").focus();
      }
    } catch {
      $("#url").focus();
      toast("Press Ctrl+V to paste the link");
    }
  });

  try {
    const [config, trends] = await Promise.all([api("/api/config"), api("/api/trends")]);
    state.config = config;
    state.trends = trends;
    const niche = $("#niche");
    Object.entries(trends.niches || {}).forEach(([key, value]) => {
      if (key === "generic") return;
      const option = document.createElement("option");
      option.value = key;
      option.textContent = value.label || key;
      niche.append(option);
    });
  } catch (err) {
    console.error(err);
  }

  await poll();
  schedulePoll();
}

init();
