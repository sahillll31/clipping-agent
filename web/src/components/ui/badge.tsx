import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold leading-none tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "border-border bg-white/[0.03] text-muted-foreground",
        brand: "border-brand/25 bg-brand/10 text-brand",
        violet: "border-[#8b5cff]/30 bg-[#8b5cff]/12 text-[#cbb8ff]",
        danger: "border-destructive/30 bg-destructive/10 text-destructive",
        muted: "border-white/5 bg-white/[0.02] text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.ComponentProps<"span">,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
