import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** Inset panel rather than a blank area, so empty regions still read as UI. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  className,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "border-border/70 bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center",
        className,
      )}
    >
      {Icon ? <Icon className="text-muted-foreground/60 size-5" /> : null}
      <p className="text-foreground/90 text-[13px] font-medium">{title}</p>
      {description ? (
        <p className="text-muted-foreground max-w-[38ch] text-xs leading-relaxed">
          {description}
        </p>
      ) : null}
      {children}
    </div>
  );
}
