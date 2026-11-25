import { Search, Settings } from "lucide-react";

import { HealthPills } from "@/components/health-pills";
import { Button } from "@/components/ui/button";
import type { Health } from "@/lib/api";

export function Topbar({
  health,
  onOpenSettings,
  onOpenPalette,
}: {
  health: Health | null;
  onOpenSettings: () => void;
  onOpenPalette: () => void;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-5">
        <a href="/" className="flex items-center gap-2.5" aria-label="ClipForge home">
          <img
            src="/brand/mark.png"
            alt=""
            width={120}
            height={63}
            className="h-7 w-auto drop-shadow-[0_2px_14px_rgba(200,255,77,0.18)]"
          />
          <span className="hidden flex-col leading-none sm:flex">
            <span className="text-[15px] font-semibold tracking-[-0.01em]">ClipForge</span>
            <span className="mt-1 text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground/70">
              local clip studio
            </span>
          </span>
        </a>

        <nav className="ml-3 hidden items-center gap-0.5 md:flex">
          <a
            href="#queue"
            className="rounded-md px-2.5 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
          >
            Queue
          </a>
        </nav>

        <div className="ml-auto hidden items-center lg:flex">
          <HealthPills health={health} />
        </div>

        <button
          type="button"
          onClick={onOpenPalette}
          className="hidden items-center gap-2 rounded-lg border border-border bg-white/[0.03] px-2.5 py-1.5 text-[11.5px] text-muted-foreground transition-colors hover:border-white/20 hover:text-foreground sm:flex"
        >
          <Search className="size-3.5" />
          Commands
          <kbd className="rounded border border-border bg-black/30 px-1.5 py-0.5 text-[9.5px] text-muted-foreground/70">
            Ctrl K
          </kbd>
        </button>

        <Button variant="ghost" size="icon" onClick={onOpenSettings} aria-label="Settings">
          <Settings />
        </Button>
      </div>
    </header>
  );
}
