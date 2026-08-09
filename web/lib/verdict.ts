import "server-only";

import Anthropic from "@anthropic-ai/sdk";
import { createHash } from "node:crypto";

import { formatDaysAgo, formatPercent, formatPrice as formatMoney } from "./format";
import type { PriceStats } from "./stats";
import type { ProductWithHistory, Trend, Verdict } from "./types";

/**
 * A projekt megkülönböztető rétege: az ártörténetből 1-2 mondatos, emberi
 * verdikt.
 *
 * Két tervezési döntés, ami miatt ez nem "csak egy promptolás":
 *
 *  1. **A modell nem lát nyers idősort.** A statisztikát (min/max, hány napja
 *     nem volt ilyen olcsó, trend) determinisztikus kód számolja, a modell
 *     csak megfogalmaz. Így nem tud számot félrehallucinálni.
 *  2. **Structured output + cache.** A válasz JSON sémára van kényszerítve,
 *     és az ártörténet ujjlenyomatára cache-eljük — ugyanarra az idősorra
 *     soha nem hívjuk kétszer a modellt.
 */

const MODEL = process.env.ANTHROPIC_MODEL?.trim() || "claude-opus-5";
const API_KEY = process.env.ANTHROPIC_API_KEY?.trim();

export function hasClaude(): boolean {
  return Boolean(API_KEY);
}

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------
/**
 * A cache kulcsa az ártörténet ujjlenyomata: ha nem jött új mérés, a verdikt
 * sem változhat. Napi 1 scrape mellett ez termékenként napi 1 modellhívás.
 */
function historyHash(product: ProductWithHistory): string {
  const payload = product.history
    .map((s) => `${s.captured_on}:${s.price}`)
    .join("|");
  return createHash("sha256").update(`${MODEL}|${payload}`).digest("hex");
}

/** Process-szintű cache. Serverless alatt instance-onként külön, de olcsó. */
const memoryCache = new Map<string, Verdict>();

/**
 * Tartós cache Supabase-ben. Csak akkor aktív, ha van service_role kulcs:
 * az `ai_verdicts` táblába az RLS miatt az anon kulcs nem írhat, és a
 * service_role kulcsot szándékosan nem tesszük ki a kliensre.
 */
async function supabaseAdmin() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !key) return null;
  const { createClient } = await import("@supabase/supabase-js");
  return createClient(url, key);
}

async function readCache(productId: string, hash: string): Promise<Verdict | null> {
  const client = await supabaseAdmin();
  if (!client) return null;
  const { data, error } = await client
    .from("ai_verdicts")
    .select("trend, headline, verdict, model")
    .eq("product_id", productId)
    .eq("history_hash", hash)
    .maybeSingle();
  if (error || !data) return null;
  return { ...data, source: "claude" } as Verdict;
}

async function writeCache(productId: string, hash: string, verdict: Verdict) {
  const client = await supabaseAdmin();
  if (!client) return;
  await client.from("ai_verdicts").upsert(
    {
      product_id: productId,
      history_hash: hash,
      trend: verdict.trend,
      headline: verdict.headline,
      verdict: verdict.verdict,
      model: verdict.model ?? MODEL,
    },
    { onConflict: "product_id,history_hash" },
  );
}

// ---------------------------------------------------------------------------
// Heurisztikus tartalék
// ---------------------------------------------------------------------------
/**
 * Kulcs nélkül (és a modell hibája esetén) ez fut. Szándékosan nem próbál
 * úgy tenni, mintha AI írta volna — a UI külön jelöli.
 */
export function heuristicVerdict(stats: PriceStats, currency: string): Verdict {
  const formatPrice = (minor: number | null) => formatMoney(minor, currency);

  if (stats.current == null) {
    return {
      trend: "stabil",
      headline: "Nincs adat",
      verdict: "Erről a termékről még nincs sikeres árlekérés.",
      source: "heuristic",
      model: null,
    };
  }

  if (!stats.hasEnoughData) {
    return {
      trend: "stabil",
      headline: "Gyűlik az adat",
      verdict: `Egyelőre ${stats.sampleCount} mérés van, ez még kevés trendhez. Néhány nap múlva nézz vissza.`,
      source: "heuristic",
      model: null,
    };
  }

  const price = formatPrice(stats.current);

  if (stats.isAllTimeLow) {
    return {
      trend: stats.trend,
      headline: "Eddigi legalacsonyabb ár",
      verdict: `${price} — ennél olcsóbb nem volt, mióta figyeljük (${stats.sampleCount} mérés).`,
      source: "heuristic",
      model: null,
    };
  }

  // Végig változatlan ár: ilyenkor a "30 napos minimumon van" triviálisan
  // igaz, de semmit nem mond. Mondjuk ki inkább, hogy nem mozdult.
  if (stats.isFlat30) {
    return {
      trend: "stabil",
      headline: "Nem mozdult",
      verdict: `${price} — az elmúlt 30 napban végig ennyi volt. Egyelőre nincs jele akciónak.`,
      source: "heuristic",
      model: null,
    };
  }

  // Az ár a 30 napos minimumon (vagy fél százalékon belül). Ez akkor is hír,
  // ha korábban, a 30 napos ablakon kívül volt már olcsóbb.
  if (stats.isAtMonthLow || (stats.pctAboveMin30 ?? 0) < 0.5) {
    return {
      trend: stats.trend,
      headline: "30 napos mélyponton",
      verdict: `${price} — az elmúlt hónap legalacsonyabb ára. A 30 napos átlag ${formatPrice(stats.avg30)}.`,
      source: "heuristic",
      model: null,
    };
  }

  if (stats.daysSinceCheaper != null && stats.daysSinceCheaper >= 7) {
    return {
      trend: stats.trend,
      headline: "Jó belépő",
      verdict: `${price} — ${formatDaysAgo(stats.daysSinceCheaper)} volt utoljára ilyen olcsó.`,
      source: "heuristic",
      model: null,
    };
  }

  if (stats.trend === "emelkedo") {
    return {
      trend: "emelkedo",
      headline: "Emelkedik",
      verdict: `${price}, az elmúlt hét átlaga ${formatPercent(stats.trendPct ?? 0)} az azt megelőzőhöz képest. Érdemes kivárni.`,
      source: "heuristic",
      model: null,
    };
  }

  // Játékoknál a "hány százalékkal drágább a minimumnál" félrevezető tud
  // lenni (egy -80%-os sale után a teljes ár +400%). Sokkal beszédesebb,
  // hogy mennyiért lehetett megkapni a legutóbbi mélyponton.
  if ((stats.pctAboveMin30 ?? 0) >= 15) {
    return {
      trend: stats.trend,
      headline: "Most nem akciós",
      verdict: `${price} — az elmúlt 30 napban ${formatPrice(stats.min30)}-ért is elvihető volt. Ha nem sürgős, érdemes kivárni a következő akciót.`,
      source: "heuristic",
      model: null,
    };
  }

  const aboveMin = formatPercent(stats.pctAboveMin30 ?? 0, false);
  return {
    trend: stats.trend,
    headline: stats.trend === "csokkeno" ? "Csökken, de még nem mélypont" : "Stabil ár",
    verdict: `${price}, ez ${aboveMin}-kal van a 30 napos minimum (${formatPrice(stats.min30)}) fölött. Nincs most kiugró alkalom.`,
    source: "heuristic",
    model: null,
  };
}

// ---------------------------------------------------------------------------
// Claude
// ---------------------------------------------------------------------------
const SYSTEM_PROMPT = `Ártrend-figyelő asszisztens vagy egy Steam-játékokat követő oldalhoz.

Kapsz egy címről előre kiszámolt ártény-halmazt, és írsz belőle egy rövid, magyar nyelvű vásárlói verdiktet.

Szabályok:
- KIZÁRÓLAG a megadott tényekre támaszkodj. Ne találj ki árat, dátumot, százalékot vagy összehasonlítást.
- A "verdict" mező 1-2 mondat, természetes magyar, tegező hangnem, marketingszöveg nélkül. Mondd meg, most éri-e meg venni, és miért.
- A "headline" legfeljebb 4 szó, nagybetűs mondatkezdés, felkiáltójel nélkül.
- A "trend" mezőben add vissza a megadott trend-értéket változatlanul.
- Ha kevés a mérés, ezt mondd ki nyíltan ahelyett, hogy magabiztos következtetést vonnál le.
- A Steamen ismétlődő szezonális akciók vannak; ha a mostani ár messze van a mért minimumtól, ezt nyugodtan említsd meg indokként a kivárásra.
- Ne írj disclaimert, ne ajánlj más terméket, ne kérdezz vissza.`;

const OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    trend: { type: "string", enum: ["csokkeno", "emelkedo", "stabil"] },
    headline: { type: "string" },
    verdict: { type: "string" },
  },
  required: ["trend", "headline", "verdict"],
  additionalProperties: false,
} as const;

/** Csak azok a tények, amikre a modellnek szüksége van – tömören, magyarul. */
function buildFacts(product: ProductWithHistory, stats: PriceStats): string {
  const formatPrice = (minor: number | null) => formatMoney(minor, product.currency);

  const lines: string[] = [
    `Termék: ${product.name}`,
    `Jelenlegi ár: ${formatPrice(stats.current)}`,
    `Mérések száma: ${stats.sampleCount} (${stats.firstSeenOn} óta, napi 1 lekérés)`,
    `Valaha mért legalacsonyabb: ${formatPrice(stats.min)} (${stats.minOn})`,
    `Valaha mért legmagasabb: ${formatPrice(stats.max)} (${stats.maxOn})`,
    `30 napos min / átlag / max: ${formatPrice(stats.min30)} / ${formatPrice(stats.avg30)} / ${formatPrice(stats.max30)}`,
    `A jelenlegi ár a 30 napos minimumnál ${formatPercent(stats.pctAboveMin30 ?? 0, false)}-kal magasabb`,
    `A jelenlegi ár a 30 napos átlaghoz képest: ${formatPercent(stats.pctVsAvg30 ?? 0)}`,
    `Számított trend: ${stats.trend} (7 napos átlagok eltérése: ${formatPercent(stats.trendPct ?? 0)})`,
  ];

  if (stats.changeSinceLast != null && stats.changeSinceLast !== 0) {
    lines.push(
      `Változás az előző méréshez képest: ${stats.changeSinceLast > 0 ? "+" : ""}${formatPrice(stats.changeSinceLast)}`,
    );
  } else if (stats.previous != null) {
    lines.push("Az előző méréshez képest nem változott az ár");
  }

  if (stats.isFlat30) {
    lines.push(
      "FONTOS: az ár az elmúlt 30 napban egyáltalán nem mozdult — ne nevezd " +
        "'mélypontnak' vagy 'jó vételnek', egyszerűen nem volt akció",
    );
  }

  if (stats.isAllTimeLow) {
    lines.push("Ez a legalacsonyabb ár, amit a figyelés kezdete óta mértünk");
  } else if (stats.daysSinceCheaper != null) {
    lines.push(
      `Utoljára ${formatDaysAgo(stats.daysSinceCheaper)} (${stats.daysSinceCheaper} napja) volt ilyen olcsó vagy olcsóbb`,
    );
  }

  if (stats.onSale) {
    lines.push(
      `Akciós: az áthúzott ár ${formatPrice(product.history.at(-1)?.list_price ?? null)}, a kedvezmény ${formatPercent(stats.discountPct ?? 0, false)}`,
    );
  }

  if (!stats.hasEnoughData) {
    lines.push(
      "FIGYELEM: kevés a mérés, a trend még nem megbízható — ezt említsd meg a verdiktben",
    );
  }

  return lines.join("\n");
}

async function askClaude(
  product: ProductWithHistory,
  stats: PriceStats,
): Promise<Verdict | null> {
  const client = new Anthropic({ apiKey: API_KEY });

  const response = await client.beta.messages.create({
    model: MODEL,
    max_tokens: 8000,
    system: SYSTEM_PROMPT,
    // Alacsony effort: a feladat egy rövid megfogalmazás kész tényekből,
    // nem igényel mély gondolkodást. Így gyors és olcsó marad.
    output_config: {
      effort: "low",
      format: { type: "json_schema", schema: OUTPUT_SCHEMA },
    },
    // A biztonsági osztályozó elvi eséllyel visszautasíthat; ilyenkor a
    // szerver oldali fallback újrafuttatja egy másik modellen.
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    messages: [{ role: "user", content: buildFacts(product, stats) }],
  });

  if (response.stop_reason === "refusal") {
    console.warn(`Verdikt elutasítva (${product.slug}):`, response.stop_details);
    return null;
  }

  const text = response.content.find((b) => b.type === "text")?.text;
  if (!text) return null;

  const parsed = JSON.parse(text) as {
    trend: Trend;
    headline: string;
    verdict: string;
  };

  return {
    // A trendet a saját számításunk dönti el, nem a modell — a mező csak
    // azért van a sémában, hogy a szöveg és a címke ne mondjon ellent.
    trend: stats.trend,
    headline: parsed.headline.trim(),
    verdict: parsed.verdict.trim(),
    source: "claude",
    model: response.model,
  };
}

// ---------------------------------------------------------------------------
// Belépési pont
// ---------------------------------------------------------------------------
export async function getVerdict(
  product: ProductWithHistory,
  stats: PriceStats,
): Promise<Verdict> {
  if (!hasClaude() || stats.current == null) {
    return heuristicVerdict(stats, product.currency);
  }

  const hash = historyHash(product);
  const cacheKey = `${product.id}:${hash}`;

  const cached = memoryCache.get(cacheKey) ?? (await readCache(product.id, hash));
  if (cached) {
    memoryCache.set(cacheKey, cached);
    return cached;
  }

  try {
    const verdict = await askClaude(product, stats);
    if (!verdict) return heuristicVerdict(stats, product.currency);

    memoryCache.set(cacheKey, verdict);
    void writeCache(product.id, hash, verdict).catch((error) =>
      console.error("Verdikt cache írás sikertelen:", error),
    );
    return verdict;
  } catch (error) {
    // A dashboard soha ne dőljön el egy modellhívás miatt.
    if (error instanceof Anthropic.RateLimitError) {
      console.warn(`Claude rate limit (${product.slug}) – heurisztikára váltok`);
    } else if (error instanceof Anthropic.APIError) {
      console.error(`Claude API hiba ${error.status} (${product.slug}):`, error.message);
    } else {
      console.error(`Verdikt generálás sikertelen (${product.slug}):`, error);
    }
    return heuristicVerdict(stats, product.currency);
  }
}
