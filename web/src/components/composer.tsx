import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Captions,
  ClipboardPaste,
  Link2,
  Loader2,
  Scissors,
  Sparkles,
  Wand2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { CreateJobInput, Trends } from "@/lib/api";

const schema = z.object({
  url: z
    .string()
    .min(8, "Paste a video link first")
    .refine((value) => /^https?:\/\/.+\..+/i.test(value.trim()), {
      message: "That doesn't look like a full link",
    }),
});

type FormValues = z.infer<typeof schema>;

interface ComposerProps {
  trends: Trends | null;
  ready: boolean;
  submitting: boolean;
  onCreate: (input: CreateJobInput) => Promise<void>;
}

function Toggle({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[11px] font-semibold transition-colors",
        active
          ? "border-brand/40 bg-brand/10 text-brand"
          : "border-border text-muted-foreground hover:border-white/20 hover:text-foreground",
      )}
    >
      <Icon className="size-3.5" />
      {children}
    </button>
  );
}

export function Composer({ trends, ready, submitting, onCreate }: ComposerProps) {
  const [clips, setClips] = React.useState(5);
  const [length, setLength] = React.useState(45);
  const [niche, setNiche] = React.useState("auto");
  const [captions, setCaptions] = React.useState(true);
  const [hook, setHook] = React.useState(true);
  const [llm, setLlm] = React.useState(true);
  const [serverError, setServerError] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { url: "" },
  });

  const busy = submitting || isSubmitting;

  const onSubmit = handleSubmit(async ({ url }) => {
    setServerError(null);
    try {
      await onCreate({
        url: url.trim(),
        clip_count: clips,
        target_length: length,
        niche,
        captions,
        hook_header: hook,
        llm: llm ? "auto" : "off",
      });
      reset();
    } catch (error) {
      setServerError(error instanceof Error ? error.message : "Could not start the job");
    }
  });

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setValue("url", text.trim(), { shouldValidate: true });
    } catch {
      document.querySelector<HTMLInputElement>('input[name="url"]')?.focus();
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-[#0a0c11]/85 p-2.5 shadow-[0_48px_120px_-48px_rgba(0,0,0,1)] backdrop-blur-xl">
      <form onSubmit={onSubmit} noValidate>
        <div className="flex items-center gap-1.5 rounded-xl border border-white/[0.06] bg-black/30 p-1.5">
          <Link2 className="ml-2 size-4 shrink-0 text-white/30" aria-hidden />
          <Input
            {...register("url")}
            placeholder="Paste a YouTube link"
            autoComplete="off"
            spellCheck={false}
            disabled={!ready}
            aria-invalid={Boolean(errors.url)}
            className="h-10 min-w-0 flex-1 border-0 bg-transparent px-1 shadow-none focus:ring-0 disabled:opacity-60"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={paste}
            className="hidden h-9 px-2.5 sm:inline-flex"
          >
            <ClipboardPaste />
            Paste
          </Button>
          <Button
            type="submit"
            disabled={busy || !ready}
            className="h-10 px-4"
            title={ready ? "Start clipping" : "Run setup first"}
          >
            {busy ? <Loader2 className="animate-spin" /> : <Scissors />}
            <span>{busy ? "Forging" : "Forge clips"}</span>
          </Button>
        </div>

        {errors.url ? (
          <p className="px-2 pt-2 text-xs text-destructive">{errors.url.message}</p>
        ) : null}
        {serverError ? (
          <p className="px-2 pt-2 text-xs text-destructive">{serverError}</p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-end gap-x-5 gap-y-3 px-1.5 pb-1">
          <Segmented
            label="Clips"
            value={clips}
            onChange={setClips}
            options={[3, 5, 8, 10].map((value) => ({ value, label: String(value) }))}
          />
          <Segmented
            label="Length"
            value={length}
            onChange={setLength}
            options={[25, 35, 45, 60].map((value) => ({ value, label: `${value}s` }))}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/70">
              Niche
            </span>
            <Select
              value={niche}
              onChange={(event) => setNiche(event.target.value)}
              className="h-8 w-[134px] rounded-[7px] text-xs"
              aria-label="Niche"
            >
              <option value="auto">Auto-detect</option>
              {Object.entries(trends?.niches ?? {})
                .filter(([key]) => key !== "generic")
                .map(([key, value]) => (
                  <option key={key} value={key}>
                    {value.label}
                  </option>
                ))}
            </Select>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            <Toggle active={captions} onClick={() => setCaptions((v) => !v)} icon={Captions}>
              Captions
            </Toggle>
            <Toggle active={hook} onClick={() => setHook((v) => !v)} icon={Sparkles}>
              Hook
            </Toggle>
            <Toggle active={llm} onClick={() => setLlm((v) => !v)} icon={Wand2}>
              LLM rank
            </Toggle>
          </div>
        </div>
      </form>
    </div>
  );
}
