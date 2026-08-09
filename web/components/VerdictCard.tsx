import { TrendBadge } from "./TrendBadge";
import type { Verdict } from "@/lib/types";

/**
 * Az AI-verdikt. A forrás (modell vs. heurisztika) mindig látszik — egy
 * demóban fontos, hogy ne lehessen összekeverni a kettőt.
 */
export function VerdictCard({
  verdict,
  compact = false,
}: {
  verdict: Verdict;
  compact?: boolean;
}) {
  const byClaude = verdict.source === "claude";

  if (compact) {
    return (
      <p className="text-[13px] leading-relaxed text-text-muted">
        <span className="font-medium text-text">{verdict.headline}.</span>{" "}
        {verdict.verdict}
      </p>
    );
  }

  return (
    <section className="rounded-xl border border-border-base bg-surface p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-text-muted">
          Verdikt
        </h2>
        <TrendBadge trend={verdict.trend} />
      </div>

      <p className="text-[19px] font-semibold tracking-tight mb-1.5">
        {verdict.headline}
      </p>
      <p className="text-[15px] leading-relaxed text-text-muted">{verdict.verdict}</p>

      <p className="mt-4 pt-3 border-t border-border-base text-[11px] text-text-faint">
        {byClaude ? (
          <>
            Generálta a <span className="font-mono">{verdict.model}</span> az
            előre kiszámolt árstatisztikákból. A számokat determinisztikus kód
            adja, a modell csak megfogalmaz.
          </>
        ) : (
          <>
            Szabályalapú összefoglaló — ehhez a termékhez most nem futott
            modellhívás.
          </>
        )}
      </p>
    </section>
  );
}
