import { useAutoAnimate } from "@formkit/auto-animate/react";
import { Inbox } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { JobCard } from "@/components/job-card";
import type { Job } from "@/lib/api";

const STEPS = [
  { n: "01", title: "Download", body: "yt-dlp pulls the best 1080p stream." },
  { n: "02", title: "Transcribe", body: "whisper.cpp timestamps every word, locally." },
  { n: "03", title: "Score & cut", body: "Trend signals pick moments, ffmpeg cuts them vertical." },
];

export function JobsSection({
  jobs,
  onCancel,
  onDelete,
}: {
  jobs: Job[];
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [listRef] = useAutoAnimate<HTMLDivElement>({ duration: 240 });
  const active = jobs.filter((job) =>
    ["queued", "downloading", "transcribing", "analyzing", "rendering"].includes(job.status),
  ).length;

  return (
    <section id="queue" className="mx-auto w-full max-w-6xl px-5 pb-24 pt-10">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-[-0.01em]">Queue</h2>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            Jobs run one at a time on this machine. Output stays under{" "}
            <code className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              data/jobs
            </code>
            .
          </p>
        </div>
        {active ? (
          <Badge variant="violet" className="shrink-0">
            {active} running
          </Badge>
        ) : jobs.length ? (
          <Badge variant="muted" className="shrink-0">
            {jobs.length} total
          </Badge>
        ) : null}
      </div>

      {jobs.length ? (
        <div ref={listRef} className="flex flex-col gap-3.5">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} onCancel={onCancel} onDelete={onDelete} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-white/[0.015] p-6 sm:p-8">
          <div className="flex items-start gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-brand/20 bg-brand/[0.06] text-brand">
              <Inbox className="size-4" />
            </div>
            <div>
              <p className="text-sm font-medium">Nothing queued yet</p>
              <p className="mt-1 max-w-xl text-[12.5px] leading-relaxed text-muted-foreground">
                Paste a link above and set your requirements. The first job downloads,
                transcribes and renders while you watch.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-6 border-t border-border pt-5 sm:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.n} className="flex gap-3">
                <span className="font-mono text-[11px] text-brand/60">{step.n}</span>
                <div>
                  <p className="text-[12.5px] font-semibold">{step.title}</p>
                  <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted-foreground">
                    {step.body}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
