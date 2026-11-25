import { cn } from "@/lib/utils";
import type { Health } from "@/lib/api";

function Pill({
  tone,
  children,
  title,
}: {
  tone: "ok" | "bad" | "muted";
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold",
        tone === "ok" && "border-brand/25 bg-brand/[0.07] text-[#dff7c4]",
        tone === "bad" && "border-destructive/30 bg-destructive/[0.08] text-[#ffc9cd]",
        tone === "muted" && "border-border bg-white/[0.02] text-muted-foreground",
      )}
    >
      <i
        className={cn(
          "size-1.5 rounded-full",
          tone === "ok" && "bg-brand shadow-[0_0_8px_rgba(200,255,77,0.7)]",
          tone === "bad" && "bg-destructive",
          tone === "muted" && "bg-muted-foreground/60",
        )}
      />
      {children}
    </span>
  );
}

export function HealthPills({ health }: { health: Health | null }) {
  if (!health) {
    return (
      <div className="flex gap-1.5" aria-hidden>
        <span className="h-6 w-16 animate-pulse rounded-full bg-white/[0.04]" />
        <span className="hidden h-6 w-20 animate-pulse rounded-full bg-white/[0.04] sm:block" />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Pill tone={health.ffmpeg ? "ok" : "bad"}>ffmpeg</Pill>
      <Pill tone={health.whisper ? "ok" : "bad"}>whisper</Pill>
      <Pill tone={health.model ? "ok" : "bad"} title={health.model_name}>
        {health.model ? health.model_name.replace(/^ggml-/, "").replace(/\.bin$/, "") : "model"}
      </Pill>
      <Pill tone={health.device === "cuda" ? "ok" : "muted"} title={health.gpu || "CPU transcription"}>
        {health.device === "cuda" ? "CUDA" : "CPU"}
      </Pill>
      <Pill
        tone={health.llm?.available ? "ok" : "muted"}
        title={health.llm?.available ? `Ollama · ${health.llm.model}` : "Ollama not running — heuristics only"}
      >
        {health.llm?.available ? "LLM" : "LLM off"}
      </Pill>
    </div>
  );
}
