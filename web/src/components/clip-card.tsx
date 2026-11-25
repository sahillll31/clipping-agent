import * as React from "react";
import { Copy, Download, Loader2, Pause, Play } from "lucide-react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn, formatTime, slugify } from "@/lib/utils";
import { downloadUrl, mediaUrl, type Clip, type Job } from "@/lib/api";

function scoreTone(score: number) {
  if (score >= 65) return "border-brand/45 text-brand";
  if (score >= 45) return "border-amber-300/45 text-amber-300";
  return "border-white/20 text-white/70";
}

export function ClipCard({
  job,
  clip,
  index,
}: {
  job: Job;
  clip: Clip;
  index: number;
}) {
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const play = React.useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.play().catch(() => {});
  }, []);

  const pause = React.useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.currentTime = 0;
  }, []);

  const toggle = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) play();
    else pause();
  };

  const copy = async () => {
    const text = [clip.caption, (clip.hashtags ?? []).join(" ")].filter(Boolean).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Caption copied");
    } catch {
      toast.error("Clipboard is blocked in this browser");
    }
  };

  return (
    <article
      className="animate-rise group flex flex-col overflow-hidden rounded-xl border border-white/[0.07] bg-[#0a0c11]/70 transition-colors hover:border-brand/25"
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div
        className="relative aspect-[9/16] cursor-pointer overflow-hidden bg-black"
        onMouseEnter={play}
        onMouseLeave={pause}
        onClick={toggle}
      >
        <video
          ref={videoRef}
          src={mediaUrl(job.id, clip.file)}
          poster={mediaUrl(job.id, clip.thumb)}
          muted
          loop
          playsInline
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onWaiting={() => setLoading(true)}
          onCanPlay={() => setLoading(false)}
          className="size-full object-cover"
        />

        {!playing ? (
          <span className="pointer-events-none absolute inset-0 grid place-items-center bg-gradient-to-t from-black/45 via-transparent to-transparent">
            <span className="grid size-12 place-items-center rounded-full border border-white/20 bg-black/45 text-white/90 backdrop-blur-sm transition-transform duration-200 group-hover:scale-105">
              {loading ? <Loader2 className="size-5 animate-spin" /> : <Play className="ml-0.5 size-5" />}
            </span>
          </span>
        ) : (
          <span className="pointer-events-none absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-black/45 text-white/80 opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100">
            <Pause className="size-3.5" />
          </span>
        )}

        <span
          className={cn(
            "absolute left-2 top-2 rounded-full border bg-black/55 px-2 py-0.5 text-[10.5px] font-bold backdrop-blur-sm",
            scoreTone(clip.score),
          )}
          title={`Trend score ${clip.score}/100${clip.reason ? ` — ${clip.reason}` : ""}`}
        >
          {clip.score}
        </span>

        <span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-white/75 backdrop-blur-sm">
          {formatTime(clip.start)}–{formatTime(clip.end)}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <h4 className="text-[12.5px] font-semibold leading-snug tracking-[-0.01em]" title={clip.reason}>
          {clip.title || `Clip ${clip.index + 1}`}
        </h4>
        {clip.hook ? (
          <p className="text-[11px] font-medium leading-snug text-brand/90">{clip.hook}</p>
        ) : null}
        {clip.caption ? (
          <p className="line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">
            {clip.caption}
          </p>
        ) : null}

        {clip.hashtags?.length ? (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {clip.hashtags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[#8b5cff]/20 bg-[#8b5cff]/10 px-1.5 py-0.5 text-[9.5px] font-medium text-[#b9a8ee]"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}

        <div className="mt-auto flex gap-1.5 pt-2">
          <a
            href={downloadUrl(job.id, clip.file)}
            download={`${slugify(clip.title || `clip-${clip.index + 1}`) || "clip"}.mp4`}
            className={cn(
              buttonVariants({ variant: "default", size: "sm" }),
              "h-8 flex-1 gap-1.5 rounded-md px-2 text-[11.5px]",
            )}
          >
            <Download className="size-3.5" />
            Download
          </a>
          <Button
            variant="secondary"
            size="sm"
            onClick={copy}
            className="h-8 flex-1 rounded-md px-2 text-[11.5px]"
          >
            <Copy className="size-3.5" />
            Copy
          </Button>
        </div>
      </div>
    </article>
  );
}
