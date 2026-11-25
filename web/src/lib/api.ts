export type JobStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "analyzing"
  | "rendering"
  | "done"
  | "error"
  | "cancelled";

export interface Stage {
  key: string;
  label: string;
}

export interface VideoMeta {
  title?: string;
  channel?: string;
  duration?: number;
  thumbnail?: string;
  view_count?: number;
  upload_date?: string;
  webpage_url?: string;
}

export interface Clip {
  id: string;
  index: number;
  start: number;
  end: number;
  duration: number;
  title: string;
  hook: string;
  caption: string;
  hashtags: string[];
  score: number;
  reason: string;
  niche: string;
  file: string;
  thumb: string;
  bytes: number;
}

export interface Job {
  id: string;
  url: string;
  options: Record<string, unknown>;
  status: JobStatus;
  stage: string;
  progress: number;
  message: string;
  error: string;
  created_at: number;
  updated_at: number;
  started_at: number | null;
  finished_at: number | null;
  video: VideoMeta;
  transcript: {
    segments?: { start: number; end: number; text: string }[];
    text?: string;
    word_count?: number;
    language?: string;
  };
  clips: Clip[];
  llm: string;
  log_tail: string[];
  stages: Stage[];
}

export interface LlmStatus {
  available: boolean;
  model: string;
  models: string[];
}

export interface Health {
  ffmpeg: boolean;
  ffprobe: boolean;
  whisper: boolean;
  model: boolean;
  model_name: string;
  device: string;
  gpu: string;
  ready: boolean;
  data_dir: string;
  llm: LlmStatus;
  defaults: Record<string, unknown>;
  queue: number;
  stages: Stage[];
}

export interface AppConfig {
  host: string;
  port: number;
  whisper_model: string;
  whisper_device: string;
  workers: number;
  keep_source?: boolean;
  llm: {
    enabled: string;
    base_url: string;
    model: string;
    timeout: number;
  };
  defaults: {
    clip_count: number;
    target_length: number;
    captions: boolean;
    hook_header: boolean;
    niche: string;
    llm: string;
  };
  models: string[];
  llm_status: LlmStatus;
}

export interface Niche {
  label: string;
  keywords: string[];
  hashtags: string[];
}

export interface Trends {
  version: number;
  hook_patterns: string[];
  niches: Record<string, Niche>;
}

export interface CreateJobInput {
  url: string;
  clip_count: number;
  target_length: number;
  niche: string;
  captions: boolean;
  hook_header: boolean;
  llm: "auto" | "off";
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload as T;
}

export const getJobs = () => api<{ jobs: Job[] }>("/api/jobs");
export const getHealth = () => api<Health>("/api/health");
export const getConfig = () => api<AppConfig>("/api/config");
export const getTrends = () => api<Trends>("/api/trends");

export const createJob = (input: CreateJobInput) =>
  api<{ job: Job }>("/api/jobs", { method: "POST", body: JSON.stringify(input) });

export const cancelJob = (id: string) =>
  api<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" });

export const deleteJob = (id: string) =>
  api<{ deleted: boolean }>(`/api/jobs/${id}`, { method: "DELETE" });

export const saveConfig = (input: Record<string, unknown>) =>
  api<{ ok: boolean; config: AppConfig }>("/api/config", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const mediaUrl = (jobId: string, file: string) => `/media/${jobId}/${file}`;
export const downloadUrl = (jobId: string, file: string) =>
  `/media/${jobId}/${file}?download=1`;
