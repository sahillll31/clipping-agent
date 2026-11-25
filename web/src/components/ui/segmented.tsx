import * as React from "react";

import { cn } from "@/lib/utils";

export interface SegmentedOption<T extends string | number> {
  value: T;
  label: string;
}

interface SegmentedProps<T extends string | number> {
  label?: string;
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
  className,
}: SegmentedProps<T>) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label ? (
        <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/70">
          {label}
        </span>
      ) : null}
      <div className="inline-flex rounded-lg border border-border bg-black/25 p-0.5">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={String(option.value)}
              type="button"
              onClick={() => onChange(option.value)}
              aria-pressed={active}
              className={cn(
                "rounded-[6px] px-2.5 py-1.5 text-xs font-semibold transition-colors",
                active
                  ? "bg-white/[0.09] text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export { Segmented };
