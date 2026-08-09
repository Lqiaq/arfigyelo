import { ProductCard } from "@/components/ProductCard";
import { getDataset } from "@/lib/data";
import { formatDate } from "@/lib/format";
import { analyze } from "@/lib/stats";
import { hasClaude } from "@/lib/verdict";

/**
 * ISR: az adat naponta egyszer frissül (GitHub Actions cron), így nincs értelme
 * kérésenként újraszámolni. 12 óra egyben a modellhívások plafonja is:
 * legrosszabb esetben napi 2 újragenerálás × 15 termék.
 */
export const revalidate = 43_200;

export default async function HomePage() {
  const { products, source, generatedAt, isDemo } = await getDataset();

  const withData = products.filter((p) => p.history.length > 0);
  const lastCheck = withData
    .map((p) => p.history.at(-1)!.captured_on)
    .sort()
    .pop();
  const deals = withData.filter((p) => {
    const stats = analyze(p.history);
    return stats.isAllTimeLow || (stats.daysSinceCheaper ?? 0) >= 14;
  }).length;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      {isDemo && (
        <div className="mb-6 rounded-lg border border-up bg-up-soft px-4 py-3 text-[13px] text-up">
          <strong className="font-semibold">Demó-adat.</strong> Ez a nézet
          szintetikus ártörténetet mutat (<code>NEXT_PUBLIC_DEMO_DATA=1</code>),
          nem valós méréseket. A UI kipróbálásához van, éles demóban kapcsold ki.
        </div>
      )}

      <section className="mb-8 max-w-2xl">
        <h1 className="text-[28px] font-semibold tracking-tight leading-tight sm:text-[34px]">
          Mikor éri meg megvenni?
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-text-muted">
          Napi egy árlekérés {products.length} fejhallgatóra az Alza.hu-ról.
          A grafikon mutatja a trendet, a verdikt megmondja, hogy a mai ár jó
          belépő-e — vagy érdemesebb kivárni.
        </p>
      </section>

      <dl className="mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border-base bg-border-base sm:grid-cols-4">
        <Stat label="Figyelt termék" value={String(products.length)} />
        <Stat
          label="Utolsó mérés"
          value={lastCheck ? formatDate(lastCheck) : "—"}
        />
        <Stat
          label="Most jó belépő"
          value={`${deals} db`}
          hint="mélyponton vagy 2+ hete nem volt ilyen olcsó"
        />
        <Stat
          label="Verdikt"
          value={hasClaude() ? "Claude API" : "szabályalapú"}
          hint={hasClaude() ? undefined : "nincs ANTHROPIC_API_KEY"}
        />
      </dl>

      {withData.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {withData.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}

      <p className="mt-8 text-[12px] text-text-faint">
        Adatforrás:{" "}
        {source === "supabase"
          ? "Supabase"
          : source === "demo"
            ? "lokális demó-JSON"
            : "lokális JSON pillanatkép"}
        {generatedAt && ` · generálva ${formatDate(generatedAt.slice(0, 10))}`}
      </p>
    </div>
  );
}

function Stat({
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
      <dt className="text-[11px] uppercase tracking-wider text-text-faint">
        {label}
      </dt>
      <dd className="mt-1 text-[15px] font-medium tabular">{value}</dd>
      {hint && <p className="mt-0.5 text-[11px] text-text-faint">{hint}</p>}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-border-strong p-10 text-center">
      <p className="text-[15px] font-medium">Még nincs árpillanatkép.</p>
      <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-muted">
        Futtasd a scrapert (<code>python scraper/scrape.py</code>), vagy indítsd
        el a GitHub Actions workflow-t kézzel. A demó-adat kipróbálásához:{" "}
        <code>NEXT_PUBLIC_DEMO_DATA=1</code>.
      </p>
    </div>
  );
}
