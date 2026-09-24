/** Barra di avanzamento accessibile con colori coerenti ai badge di stato. */
import { cn } from "@/lib/cn";
import type { BadgeTone } from "./Badge";

const barTone: Record<BadgeTone, string> = {
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
  info: "text-info",
  neutral: "text-outline",
  primary: "text-primary",
};

export default function ProgressBar({
  value,
  tone = "primary",
  className,
}: {
  value: number;
  tone?: BadgeTone;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <svg
      className={cn("h-2 w-full overflow-hidden rounded-full", className)}
      viewBox="0 0 100 8"
      preserveAspectRatio="none"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <rect width="100" height="8" rx="4" className="fill-current text-surface-container-high" />
      <rect width={clamped} height="8" rx="4" className={cn("fill-current", barTone[tone])} />
    </svg>
  );
}
