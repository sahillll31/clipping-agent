import * as React from "react";
import { Drawer } from "vaul";
import { Cpu, HardDrive, Layers, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { AppConfig, Health } from "@/lib/api";

interface SettingsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: AppConfig | null;
  health: Health | null;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="mb-4 block">
      <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/70">
        {label}
      </span>
      <div className="mt-1.5">{children}</div>
      {hint ? (
        <span className="mt-1.5 block text-[11px] leading-relaxed text-muted-foreground/70">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-white/[0.02] px-3 py-2.5">
      <span className="flex items-center gap-1.5 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/60">
        <Icon className="size-3" />
        {label}
      </span>
      <p className="mt-1 truncate text-[11.5px] font-medium" title={value}>
        {value}
      </p>
    </div>
  );
}

export function SettingsDrawer({
  open,
  onOpenChange,
  config,
  health,
  onSave,
}: SettingsDrawerProps) {
  const [model, setModel] = React.useState("");
  const [device, setDevice] = React.useState("auto");
  const [workers, setWorkers] = React.useState("1");
  const [keep, setKeep] = React.useState(false);
  const [llm, setLlm] = React.useState(true);
  const [llmModel, setLlmModel] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!open || !config) return;
    setModel(config.whisper_model ?? "");
    setDevice(config.whisper_device ?? "auto");
    setWorkers(String(config.workers ?? 1));
    setKeep(Boolean(config.keep_source));
    setLlm((config.llm?.enabled ?? "auto") !== "off");
    setLlmModel(config.llm?.model ?? "");
  }, [open, config]);

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        whisper_model: model,
        whisper_device: device,
        workers: Number(workers),
        keep_source: keep,
        llm_enabled: llm ? "auto" : "off",
        llm_model: llmModel.trim() || undefined,
      });
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  const models = config?.models?.length ? config.models : config?.whisper_model ? [config.whisper_model] : [];

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange} direction="right">
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Drawer.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(410px,92vw)] flex-col border-l border-border bg-[#0b0d12] outline-none">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div>
              <Drawer.Title className="text-[15px] font-semibold">Settings</Drawer.Title>
              <Drawer.Description className="mt-0.5 text-[11.5px] text-muted-foreground">
                Applies to new jobs.
              </Drawer.Description>
            </div>
            <Drawer.Close className={cn("grid size-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground")}>
              <X className="size-4" />
            </Drawer.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            <Row label="Whisper model" hint="Bigger models are more accurate but slower. `.en` models are English-only.">
              <Select value={model} onChange={(event) => setModel(event.target.value)}>
                {models.map((name) => (
                  <option key={name} value={name}>
                    {name.replace(/^ggml-/, "").replace(/\.bin$/, "")}
                  </option>
                ))}
              </Select>
            </Row>

            <Row label="Compute device" hint="CUDA needs the CUDA whisper build from setup.">
              <Select value={device} onChange={(event) => setDevice(event.target.value)}>
                <option value="auto">Auto</option>
                <option value="cpu">CPU</option>
                <option value="cuda">CUDA</option>
              </Select>
            </Row>

            <Row label="Parallel jobs" hint="One worker keeps CPU/GPU contention down. Restart the server to apply.">
              <Select value={workers} onChange={(event) => setWorkers(event.target.value)}>
                <option value="1">1</option>
                <option value="2">2</option>
              </Select>
            </Row>

            <div className="mb-4 flex items-center justify-between gap-4">
              <span className="text-[11.5px] text-muted-foreground">
                Keep source video after rendering
              </span>
              <Switch checked={keep} onCheckedChange={setKeep} aria-label="Keep source video" />
            </div>

            <div className="my-5 h-px bg-border" />

            <div className="mb-3 flex items-center justify-between gap-4">
              <div>
                <p className="text-[12.5px] font-medium">Ollama ranking</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {health?.llm?.available
                    ? `Detected · ${health.llm.model}`
                    : "Not running — heuristics still work"}
                </p>
              </div>
              <Switch checked={llm} onCheckedChange={setLlm} aria-label="Use Ollama" />
            </div>

            <Row label="Ollama model">
              <Input
                value={llmModel}
                onChange={(event) => setLlmModel(event.target.value)}
                placeholder="qwen2.5:3b"
                disabled={!llm}
              />
            </Row>

            <div className="my-5 h-px bg-border" />

            <div className="grid grid-cols-2 gap-2">
              <Stat
                icon={Cpu}
                label="Device"
                value={health?.device === "cuda" ? "CUDA" : "CPU"}
              />
              <Stat icon={Layers} label="GPU" value={health?.gpu || "Not detected"} />
              <Stat icon={HardDrive} label="ffmpeg" value={health?.ffmpeg ? "Ready" : "Missing"} />
              <Stat icon={HardDrive} label="Storage" value="Local disk" />
            </div>
          </div>

          <div className="border-t border-border px-5 py-4">
            <Button className="w-full" onClick={save} disabled={saving || !config}>
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
