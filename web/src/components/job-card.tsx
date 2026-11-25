import * as React from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { ExternalLink, Film, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ClipCard } from "@/components/clip-card";
import { cn, formatCount, formatDuration } from "@/lib/utils";
import type { Job, JobStatus } from "@/lib/api";

const FLOW = ["queued", "downloading", "transcribing", "analyzing", "rendering", "done"] as const;

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  downloading: "Downloading",
  transcribing: "Transcribing",
  analyzing: "Scoring moments",
  rendering: "Rendering",
  done: "Complete",
  error: "Failed",
  cancelled: "Cancelled",
};

const STAGE_LABEL: Record<string, string> = {
  queued: "Queue",
  downloading: "Download",
  transcribing: "Transcribe",
  analyzing: "Score",
  rendering: "Render",
  done: "Done",
};

function stageState(
  key: string,
  job: Job,
): "done" | "active" | "pending" | "error" {
  const current = FLOW.indexOf(job.status as (typeof FLOW)[number]);
  const index = FLOW.indexOf(key as (typeof FLOW)[number]);
  if (job.status === "done") return "done";
  if (job.status === "error" || job.status === "cancelled") {
    if (index < current) return "done";
    if (index === current) return "error";
    return "pending";
  }
  if (index < current) return "done";
  if (index === current) return "active";
  return "pending";
}

export function JobCard({
  job,
  onCancel,
  onDelete,
}: {
  job: Job;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const active = job.status !== "done" && job.status !== "error" && job.status !== "cancelled";
  const tone =
    job.status === "done"
      ? "brand"
      : job.status === "error"
        ? "danger"
        : job.status === "cancelled"
          ? "muted"
          : "violet";

  const sub = [
    job.video?.channel,
    job.video?.duration ? formatDuration(job.video.duration) : null,
    job.video?.view_count ? `${formatCount(job.video.view_count)} views` : null,
    formatDistanceToNowStrict(new Date(job.created_at * 1000), { addSuffix: true }),
  ].filter(Boolean);

  const stages = job.stages?.length
    ? job.stages
    : FLOW.map((key) => ({ key, label: STAGE_LABEL[key] ?? key }));

  const progress = job.status === "done" ? 100 : Math.max(0, Math.min(100, job.progress || 0));

  return (
    <article className="animate-rise rounded-2xl border border-border bg-card/70 p-4 backdrop-blur-sm">
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative aspect-video w-full shrink-0 overflow-hidden rounded-lg border border-border bg-black/40 sm:w-[168px]">
          {job.video?.thumbnail ? (
            <img
              src={job.video.thumbnail}
              alt=""
              loading="lazy"
              className="size-full object-cover"
            />
          ) : (
            <div className="grid size-full place-items-center text-muted-foreground/50">
              <Film className="size-6" />
            </div>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2.5">
            <h3 className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-[-0.01em]">
              {job.video?.title || job.url}
            </h3>
            <Badge variant={tone} className={cn(active && "shrink-0")}>
              <i
                className={cn(
                  "size-1.5 rounded-full",
                  active && "animate-[pulse-dot_1.4s_ease-in-out_infinite] bg-[#b9a3ff]",
                  job.status === "done" && "bg-brand",
                  job.status === "error" && "bg-destructive",
                  job.status === "cancelled" && "bg-muted-foreground/60",
                )}
              />
              {STATUS_LABEL[job.status] ?? job.status}
            </Badge>
          </div>

          <p className="mt-1 truncate text-[11.5px] text-muted-foreground">
            {sub.length ? sub.join("  ·  ") : job.url}
          </p>

          <div className="mt-3 flex items-center gap-3">
            <Progress value={progress} className="flex-1" />
            <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
              {Math.round(progress)}%
            </span>
          </div>

          <p
            className={cn(
              "mt-2 min-h-4 truncate text-[12px]",
              job.status === "error" ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {job.status === "error" ? job.error || "Something went wrong" : job.message}
          </p>
        </div>

        <div className="flex shrink-0 gap-1 sm:flex-col">
          {job.url ? (
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              title="Open source"
              className={cn(buttonVariants({ variant: "ghost", size: "icon" }))}
            >
              <ExternalLink />
            </a>
          ) : null}
          {active ? (
            <Button variant="ghost" size="icon" onClick={() => onCancel(job.id)} title="Cancel job">
              <X />
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                if (window.confirm("Remove this job and its clips?")) onDelete(job.id);
              }}
              title="Delete job"
            >
              <Trash2 />
            </Button>
          )}
        </div>
      </div>

      {active ? (
        <ol className="mt-3.5 flex flex-wrap items-center gap-1">
          {stages.map((stage) => {
            const state = stageState(stage.key, job);
            return (
              <li
                key={stage.key}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border border-transparent px-2 py-1 text-[10px] font-semibold",
                  state === "done" && "text-brand/75",
                  state === "active" && "border-[#8b5cff]/30 bg-[#8b5cff]/10 text-[#d9ccff]",
                  state === "pending" && "text-muted-foreground/50",
                  state === "error" && "text-destructive",
                )}
              >
                <i
                  className={cn(
                    "size-1.5 rounded-full",
                    state === "done" && "bg-brand/70",
                    state === "active" && "bg-[#b9a3ff]",
                    state === "pending" && "bg-white/20",
                    state === "error" && "bg-destructive",
                  )}
                />
                {stage.label}
              </li>
            );
          })}
        </ol>
      ) : null}

      {job.clips?.length ? (
        <div className="mt-4">
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/70">
              {job.clips.length} clip{job.clips.length === 1 ? "" : "s"}
            </h4>
            <span className="text-[10.5px] text-muted-foreground/60">
              ranked by {job.llm === "heuristic" ? "heuristic scorer" : job.llm}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {job.clips.map((clip) => (
              <ClipCard key={clip.id} job={job} clip={clip} index={clip.index} />
            ))}
          </div>
        </div>
      ) : null}

      <details className="group mt-3">
        <summary className="cursor-pointer select-none text-[11px] text-muted-foreground/70 transition-colors hover:text-muted-foreground">
          Run log
        </summary>
        <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-black/30 p-3 text-[10.5px] leading-relaxed text-muted-foreground">
          {(job.log_tail ?? []).join("\n") || "No output yet."}
        </pre>
      </details>
    </article>
  );
}
