import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { PriceChart } from "@/components/PriceChart";
import { VerdictCard } from "@/components/VerdictCard";
import { getDataset, getProduct } from "@/lib/data";
import { formatDate, formatDaysAgo, formatPercent, formatPrice } from "@/lib/format";
import { analyze } from "@/lib/stats";
import type { ProductWithHistory } from "@/lib/types";
import { getVerdict } from "@/lib/verdict";

export const revalidate = 43_200;

export async function generateStaticParams() {
  const { products } = await getDataset();
  return products.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: PageProps<"/termek/[slug]">) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) return { title: "Nem található" };

  const stats = analyze(product.history);
  return {
    title: `${product.name} ártörténet`,
    description: `${product.name} — jelenlegi ár ${formatPrice(stats.current)}, ${stats.sampleCount} mérés alapján.`,
  };
}

async function ProductVerdict({ product }: { product: ProductWithHistory }) {
  const verdict = await getVerdict(product, analyze(product.history));
  return <VerdictCard verdict={verdict} />;
}

export default async function ProductPage({ params }: PageProps<"/termek/[slug]">) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) notFound();

  const stats = analyze(product.history);

  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-8">
      <Link
        href="/"
        className="text-[13px] text-text-muted hover:text-text underline underline-offset-4 decoration-border-strong"
      >
        ← Összes termék
      </Link>

      <header className="mt-4 mb-6">
        {product.brand && (
          <p className="text-[12px] uppercase tracking-wider text-text-faint">
            {product.brand}
          </p>
        )}
        <h1 className="text-[26px] font-semibold tracking-tight leading-tight sm:text-[32px]">
          {product.name}
        </h1>

        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="tabular text-[30px] font-semibold tracking-tight">
            {formatPrice(stats.current)}
          </span>
          {stats.onSale && (
            <span className="tabular text-[16px] text-text-faint line-through">
              {formatPrice(product.history.at(-1)?.list_price ?? null)}
            </span>
          )}
          {stats.changeSinceLastPct != null &&
            Math.abs(stats.changeSinceLastPct) >= 0.05 && (
              <span
                className={`tabular text-[14px] font-medium ${
                  stats.changeSinceLastPct < 0 ? "text-down" : "text-up"
                }`}
              >
                {formatPercent(stats.changeSinceLastPct)} az előző méréshez képest
              </span>
            )}
        </div>

        <p className="mt-2 text-[13px] text-text-muted">
          {stats.lastSeenOn && `Utolsó mérés: ${formatDate(stats.lastSeenOn)}`}
          {" · "}
          <a
            href={product.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="underline underline-offset-4 decoration-border-strong hover:text-text"
          >
            Termékoldal · {product.shop} ↗
          </a>
        </p>
      </header>

      <div className="mb-6">
        <Suspense
          fallback={
            <div className="rounded-xl border border-border-base bg-surface p-5 text-[13px] text-text-faint">
              Verdikt készül…
            </div>
          }
        >
          <ProductVerdict product={product} />
        </Suspense>
      </div>

      <section className="rounded-xl border border-border-base bg-surface p-4 sm:p-5">
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <h2 className="text-[13px] font-medium uppercase tracking-wider text-text-muted">
            Ártörténet
          </h2>
          <span className="text-[12px] text-text-faint">
            {stats.sampleCount} mérés
            {stats.firstSeenOn && ` · ${formatDate(stats.firstSeenOn)} óta`}
          </span>
        </div>

        {product.history.length >= 2 && stats.min != null && stats.max != null ? (
          <PriceChart
            history={product.history}
            trend={stats.trend}
            min={stats.min}
            max={stats.max}
          />
        ) : (
          <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-border-strong px-6 text-center">
            <p className="max-w-sm text-[13px] leading-relaxed text-text-muted">
              Egyetlen mérés van eddig ({formatPrice(stats.current)}). A grafikon
              a második naptól rajzolódik ki — a scraper naponta egyszer fut.
            </p>
          </div>
        )}
      </section>

      <section className="mt-6 grid gap-px overflow-hidden rounded-xl border border-border-base bg-border-base sm:grid-cols-2 lg:grid-cols-4">
        <Fact
          label="Legalacsonyabb"
          value={formatPrice(stats.min)}
          hint={stats.minOn ? formatDate(stats.minOn) : undefined}
        />
        <Fact
          label="Legmagasabb"
          value={formatPrice(stats.max)}
          hint={stats.maxOn ? formatDate(stats.maxOn) : undefined}
        />
        <Fact
          label="30 napos átlag"
          value={formatPrice(stats.avg30)}
          hint={
            stats.pctVsAvg30 != null
              ? `most ${formatPercent(stats.pctVsAvg30)}`
              : undefined
          }
        />
        <Fact
          label={stats.isAllTimeLow ? "Rekord" : "Ilyen olcsón utoljára"}
          value={
            stats.isAllTimeLow
              ? "Mélypont"
              : stats.daysSinceCheaper != null
                ? formatDaysAgo(stats.daysSinceCheaper)
                : "—"
          }
          hint={
            !stats.isAllTimeLow && stats.pctAboveMin30 != null
              ? `${formatPercent(stats.pctAboveMin30, false)} a 30n minimum fölött`
              : undefined
          }
        />
      </section>
    </div>
  );
}

function Fact({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="bg-surface px-4 py-3">
      <p className="text-[11px] uppercase tracking-wider text-text-faint">{label}</p>
      <p className="mt-1 tabular text-[16px] font-medium">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-text-faint">{hint}</p>}
    </div>
  );
}
