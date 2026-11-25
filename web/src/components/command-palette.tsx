import * as React from "react";
import { Command } from "cmdk";
import { Link2, ListVideo, RefreshCw, Search, Settings } from "lucide-react";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFocusComposer: () => void;
  onOpenSettings: () => void;
  onRefresh: () => void;
}

function Item({
  icon: Icon,
  label,
  hint,
  onSelect,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  hint?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12.5px] text-muted-foreground outline-none transition-colors aria-selected:bg-white/[0.06] aria-selected:text-foreground"
    >
      <Icon className="size-4 shrink-0" />
      <span className="flex-1">{label}</span>
      {hint ? <span className="text-[10px] text-muted-foreground/50">{hint}</span> : null}
    </Command.Item>
  );
}

export function CommandPalette({
  open,
  onOpenChange,
  onFocusComposer,
  onOpenSettings,
  onRefresh,
}: CommandPaletteProps) {
  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
      if (event.key === "Escape" && open) onOpenChange(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onOpenChange]);

  if (!open) return null;

  const run = (action: () => void) => () => {
    onOpenChange(false);
    action();
  };

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center bg-black/60 px-4 pt-[16vh] backdrop-blur-sm"
      onMouseDown={() => onOpenChange(false)}
    >
      <div
        onMouseDown={(event) => event.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-[#0c0f15] shadow-[0_48px_120px_-40px_rgba(0,0,0,1)]"
      >
        <Command label="Command menu">
          <div className="flex items-center gap-2 border-b border-border px-3.5">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <Command.Input
              autoFocus
              placeholder="Type a command…"
              className="h-12 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/50"
            />
            <kbd className="rounded border border-border bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-muted-foreground">
              esc
            </kbd>
          </div>
          <Command.List className="max-h-[300px] overflow-y-auto p-1.5">
            <Command.Empty className="py-8 text-center text-[12.5px] text-muted-foreground">
              No matching command.
            </Command.Empty>
            <Command.Group
              heading="Actions"
              className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-1.5 [&_[cmdk-group-heading]]:text-[9.5px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.1em] [&_[cmdk-group-heading]]:text-muted-foreground/50"
            >
              <Item icon={Link2} label="Paste a new link" hint="focus" onSelect={run(onFocusComposer)} />
              <Item icon={ListVideo} label="Jump to queue" hint="G Q" onSelect={run(() => {
                document.getElementById("queue")?.scrollIntoView({ behavior: "smooth", block: "start" });
              })} />
              <Item icon={Settings} label="Open settings" hint="⌘ ," onSelect={run(onOpenSettings)} />
              <Item icon={RefreshCw} label="Refresh status" hint="R" onSelect={run(onRefresh)} />
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
