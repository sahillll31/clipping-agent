import * as React from "react";

import { cn } from "@/lib/utils";

interface ProgressProps extends React.ComponentProps<"div"> {
  value: number;
}

function Progress({ value, className, ...props }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]",
        className,
      )}
      {...props}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-[#8b5cff] via-[#6fe3a1] to-brand transition-[width] duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export { Progress };
