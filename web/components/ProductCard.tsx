import Link from "next/link";
import { Suspense } from "react";

import { formatDaysAgo, formatPercent, formatPrice } from "@/lib/format";
import { analyze } from "@/lib/stats";
import type { ProductWithHistory } from "@/lib/types";
import { getVerdict } from "@/lib/verdict";
import { Sparkline } from "./Sparkline";
import { TrendBadge } from "./TrendBadge";
import { VerdictCard } from "./VerdictCard";

/**
 * A verdikt külön async komponens, saját Suspense-határral: a kártyák
 * azonnal megjelennek, a modellhívás eredménye utólag folyik be.
 */
async function CardVerdict({ product }: { product: ProductWithHistory }) {
  const verdict = await getVerdict(product, analyze(product.history));
  return <VerdictCard verdict={verdict} compact />;
}

export function ProductCard({ product }: { product: ProductWithHistory }) {
  const stats = analyze(product.history);
  const change = stats.changeSinceLastPct;
  const price = (minor: number | null) => formatPrice(minor, product.currency);

  return (
    <article className="flex flex-col rounded-xl border border-border-base bg-surface p-4 transition-colors hover:border-border-strong">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {product.brand && (
            <p className="text-[11px] uppercase tracking-wider text-text-faint">
              {product.brand}
            </p>
          )}
          <h2 className="text-[15px] font-medium leading-snug">
            <Link
              href={`/termek/${product.slug}`}
              className="hover:underline underline-offset-4 decoration-border-strong"
            >
              {product.name}
            </Link>
          </h2>
        </div>
        <TrendBadge trend={stats.trend} />
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div>
          <div className="tabular text-[22px] font-semibold tracking-tight leading-none">
            {price(stats.current)}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-[12px]">
            {stats.onSale && (
              <span className="tabular text-text-faint line-through">
                {price(product.history.at(-1)?.list_price ?? null)}
              </span>
            )}
            {change != null && Math.abs(change) >= 0.05 ? (
              <span
                className={`tabular font-medium ${change < 0 ? "text-down" : "text-up"}`}
              >
                {formatPercent(change)}
              </span>
            ) : (
              <span className="text-text-faint">változatlan</span>
            )}
          </div>
        </div>
        <Sparkline history={product.history} trend={stats.trend} />
      </div>

      {stats.hasEnoughData && (
        <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-border-base pt-3 text-[11px]">
          <div>
            <dt className="text-text-faint">30n min</dt>
            <dd className="tabular text-text-muted">{price(stats.min30)}</dd>
          </div>
          <div>
            <dt className="text-text-faint">30n átlag</dt>
            <dd className="tabular text-text-muted">{price(stats.avg30)}</dd>
          </div>
          <div>
            <dt className="text-text-faint">
              {stats.isFlat30
                ? "30n mozgás"
                : stats.isAllTimeLow || stats.isAtMonthLow
                  ? "állapot"
                  : "ilyen olcsón"}
            </dt>
            <dd className="text-text-muted">
              {stats.isFlat30
                ? "nincs"
                : stats.isAllTimeLow || stats.isAtMonthLow
                  ? "mélypont"
                  : stats.daysSinceCheaper != null
                    ? formatDaysAgo(stats.daysSinceCheaper)
                    : "—"}
            </dd>
          </div>
        </dl>
      )}

      <div className="mt-3 border-t border-border-base pt-3">
        <Suspense
          fallback={
            <p className="text-[13px] text-text-faint">Verdikt készül…</p>
          }
        >
          <CardVerdict product={product} />
        </Suspense>
      </div>
    </article>
  );
}
