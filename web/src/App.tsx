import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, WifiOff } from "lucide-react";
import { Toaster, toast } from "sonner";

import { CommandPalette } from "@/components/command-palette";
import { Hero } from "@/components/hero";
import { JobsSection } from "@/components/jobs-section";
import { SettingsDrawer } from "@/components/settings-drawer";
import { Topbar } from "@/components/topbar";
import {
  cancelJob,
  createJob as postJob,
  deleteJob,
  getConfig,
  getHealth,
  getJobs,
  getTrends,
  saveConfig,
  type CreateJobInput,
} from "@/lib/api";
import { queryClient } from "@/lib/query";

export default function App() {
  const qc = useQueryClient();
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: getJobs,
    refetchInterval: 2000,
  });
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
  });
  const configQuery = useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
    staleTime: 30_000,
  });
  const trendsQuery = useQuery({
    queryKey: ["trends"],
    queryFn: getTrends,
    staleTime: Infinity,
  });

  const createMutation = useMutation({
    mutationFn: postJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Job queued — transcribing locally");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast("Cancellation requested");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast("Job removed");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const saveMutation = useMutation({
    mutationFn: saveConfig,
    onSuccess: ({ config }) => {
      qc.setQueryData(["config"], config);
      qc.invalidateQueries({ queryKey: ["health"] });
      toast.success("Settings saved");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const jobs = jobsQuery.data?.jobs ?? [];
  const health = healthQuery.data ?? null;
  const config = configQuery.data ?? null;
  const ready = Boolean(health?.ready);

  const missing = health
    ? [
        !health.ffmpeg ? "ffmpeg" : null,
        !health.ffprobe ? "ffprobe" : null,
        !health.whisper ? "whisper.cpp" : null,
        !health.model ? "whisper model" : null,
      ].filter(Boolean)
    : [];

  const focusComposer = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => {
      document.querySelector<HTMLInputElement>('input[name="url"]')?.focus();
    }, 260);
  };

  return (
    <div className="min-h-screen">
      <Topbar
        health={health}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenPalette={() => setPaletteOpen(true)}
      />

      <main>
        <Hero
          trends={trendsQuery.data ?? null}
          ready={ready}
          submitting={createMutation.isPending}
          onCreate={async (input: CreateJobInput) => {
            await createMutation.mutateAsync(input);
          }}
        />

        {healthQuery.isError ? (
          <div className="mx-auto w-full max-w-5xl px-5 pb-2">
            <div className="flex items-center gap-2.5 rounded-xl border border-destructive/30 bg-destructive/[0.07] px-4 py-3 text-[12.5px]">
              <WifiOff className="size-4 shrink-0 text-destructive" />
              <span className="flex-1">
                Cannot reach the ClipForge API. Start it with{" "}
                <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-[11.5px] text-brand">
                  .\run.ps1
                </code>
                .
              </span>
            </div>
          </div>
        ) : null}

        {health && !health.ready ? (
          <div className="mx-auto w-full max-w-5xl px-5 pb-2">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/[0.07] px-4 py-3 text-[12.5px]">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="size-4 shrink-0 text-destructive" />
                <span>
                  Toolchain incomplete
                  {missing.length ? ` — missing ${missing.join(", ")}` : ""}. Run the installer
                  once, then restart.
                </span>
              </div>
              <code className="rounded-md border border-border bg-black/40 px-2.5 py-1 font-mono text-[11.5px] text-brand">
                .\setup.ps1
              </code>
            </div>
          </div>
        ) : null}

        <JobsSection
          jobs={jobs}
          onCancel={(id) => cancelMutation.mutate(id)}
          onDelete={(id) => deleteMutation.mutate(id)}
        />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-6 text-[11.5px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>
            ClipForge <span className="px-1 text-white/20">·</span> local clip studio
          </span>
          <span className="text-muted-foreground/60">
            Only clip content you have the rights to use.
          </span>
        </div>
      </footer>

      <SettingsDrawer
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        config={config}
        health={health}
        onSave={async (payload) => {
          await saveMutation.mutateAsync(payload);
        }}
      />

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onFocusComposer={focusComposer}
        onOpenSettings={() => setSettingsOpen(true)}
        onRefresh={() => {
          qc.invalidateQueries();
          toast("Refreshed");
        }}
      />

      <Toaster
        theme="dark"
        position="bottom-center"
        toastOptions={{
          style: {
            background: "#12151d",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#edf0f6",
          },
        }}
      />
    </div>
  );
}
