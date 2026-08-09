import { TREND_LABEL } from "@/lib/stats";
import type { Trend } from "@/lib/types";

const STYLES: Record<Trend, string> = {
  csokkeno: "bg-down-soft text-down",
  emelkedo: "bg-up-soft text-up",
  stabil: "bg-flat-soft text-flat",
};

const ARROW: Record<Trend, string> = {
  csokkeno: "↓",
  emelkedo: "↑",
  stabil: "→",
};

export function TrendBadge({
  trend,
  size = "sm",
}: {
  trend: Trend;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${STYLES[trend]} ${
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-[13px]"
      }`}
    >
      <span aria-hidden>{ARROW[trend]}</span>
      {TREND_LABEL[trend]}
    </span>
  );
}
