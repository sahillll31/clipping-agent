import * as React from "react";

import { cn } from "@/lib/utils";

interface SwitchProps extends Omit<React.ComponentProps<"button">, "onChange"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

function Switch({ checked, onCheckedChange, className, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        checked
          ? "border-brand/50 bg-brand/25"
          : "border-border bg-white/10",
        className,
      )}
      {...props}
    >
      <span
        className={cn(
          "block size-[15px] rounded-full transition-transform",
          checked ? "translate-x-[18px] bg-brand" : "translate-x-[3px] bg-white/50",
        )}
      />
    </button>
  );
}

export { Switch };
