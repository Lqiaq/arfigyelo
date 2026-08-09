import type { Snapshot, Trend } from "./types";

/**
 * Az ártörténetből számolt tények. Két helyen használjuk:
 *
 *  1. a UI közvetlenül kiírja őket (min/max, "x napja nem volt ilyen olcsó"),
 *  2. ezt a struktúrát kapja meg a Claude a verdikthez.
 *
 * A (2) miatt fontos, hogy a modell **ne** nyers idősorból következtessen:
 * a számolást determinisztikus kód végzi, a modell dolga csak az, hogy
 * emberi mondatot írjon a kész tényekből. Így a verdikt nem tud számot
 * félrehallucinálni.
 */
export interface PriceStats {
  current: number | null;
  /** Az utolsó előtti mérés ára – ebből jön a napi változás. */
  previous: number | null;
  changeSinceLast: number | null;
  changeSinceLastPct: number | null;

  min: number | null;
  max: number | null;
  minOn: string | null;
  maxOn: string | null;

  min30: number | null;
  max30: number | null;
  avg30: number | null;

  /** Mennyivel van a jelenlegi ár a 30 napos minimum fölött, százalékban. */
  pctAboveMin30: number | null;
  /**
   * true, ha az ár a 30 napos ablakban egyáltalán nem mozdult. Enélkül a
   * "most a 30 napos minimumon van" állítás triviálisan igaz lenne egy
   * végig változatlan árra is — és félrevezető.
   */
  isFlat30: boolean;
  /** true, ha a mostani ár a 30 napos ablak minimuma ÉS az ár tényleg mozgott. */
  isAtMonthLow: boolean;
  /** Mennyivel tér el a 30 napos átlagtól (negatív = olcsóbb az átlagnál). */
  pctVsAvg30: number | null;

  /**
   * Hány napja nem volt ilyen olcsó. null = nincs elég adat.
   * Ha soha nem volt ennyire olcsó, ez a mérési előzmény teljes hossza.
   */
  daysSinceCheaper: number | null;
  /** true, ha a mostani ár a valaha mért legalacsonyabb. */
  isAllTimeLow: boolean;

  trend: Trend;
  /** A trend számításának alapja: 7 napos átlagok eltérése, százalékban. */
  trendPct: number | null;

  onSale: boolean;
  discountPct: number | null;

  sampleCount: number;
  firstSeenOn: string | null;
  lastSeenOn: string | null;
  /** Legalább ennyi mérés kell, hogy a trend/verdikt értelmes legyen. */
  hasEnoughData: boolean;
}

export const MIN_SAMPLES_FOR_TREND = 4;

function daysBetween(fromIso: string, toIso: string): number {
  const from = Date.parse(`${fromIso}T00:00:00Z`);
  const to = Date.parse(`${toIso}T00:00:00Z`);
  return Math.round((to - from) / 86_400_000);
}

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function analyze(history: Snapshot[]): PriceStats {
  // Idősorrend garantálása: a hívó nem feltétlenül rendezve adja át.
  const series = [...history]
    .filter((s) => typeof s.price === "number" && s.price > 0)
    .sort((a, b) => a.captured_on.localeCompare(b.captured_on));

  const empty: PriceStats = {
    current: null, previous: null, changeSinceLast: null, changeSinceLastPct: null,
    min: null, max: null, minOn: null, maxOn: null,
    min30: null, max30: null, avg30: null,
    pctAboveMin30: null, pctVsAvg30: null,
    isFlat30: false, isAtMonthLow: false,
    daysSinceCheaper: null, isAllTimeLow: false,
    trend: "stabil", trendPct: null,
    onSale: false, discountPct: null,
    sampleCount: 0, firstSeenOn: null, lastSeenOn: null, hasEnoughData: false,
  };

  if (series.length === 0) return empty;

  const latest = series[series.length - 1];
  const current = latest.price;
  const previous = series.length > 1 ? series[series.length - 2].price : null;

  const prices = series.map((s) => s.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const minOn = series.find((s) => s.price === min)!.captured_on;
  const maxOn = series.find((s) => s.price === max)!.captured_on;

  // 30 napos ablak a legutolsó mérés dátumához képest, nem a mai naphoz –
  // így egy leállt scraper mellett sem tűnik el az összes adat.
  const window = series.filter(
    (s) => daysBetween(s.captured_on, latest.captured_on) <= 30,
  );
  const windowPrices = window.map((s) => s.price);
  const min30 = Math.min(...windowPrices);
  const max30 = Math.max(...windowPrices);
  const avg30 = Math.round(mean(windowPrices));

  // Hány napja nem volt ilyen olcsó: a legutolsó korábbi mérés, ami
  // nem volt drágább a mostaninál.
  let daysSinceCheaper: number | null = null;
  let isAllTimeLow = false;
  if (series.length > 1) {
    let cheaperIdx = -1;
    for (let i = series.length - 2; i >= 0; i--) {
      if (series[i].price <= current) {
        cheaperIdx = i;
        break;
      }
    }
    isAllTimeLow = cheaperIdx === -1;
    const reference = cheaperIdx === -1 ? series[0] : series[cheaperIdx];
    daysSinceCheaper = daysBetween(reference.captured_on, latest.captured_on);
  }

  // Trend: utolsó 7 nap átlaga vs. az azt megelőző 7 nap átlaga.
  // Kevés méréshez ez zajos lenne, ezért a küszöb alatt "stabil".
  let trend: Trend = "stabil";
  let trendPct: number | null = null;
  if (series.length >= MIN_SAMPLES_FOR_TREND) {
    const recent = series.filter(
      (s) => daysBetween(s.captured_on, latest.captured_on) <= 7,
    );
    const prior = series.filter((s) => {
      const age = daysBetween(s.captured_on, latest.captured_on);
      return age > 7 && age <= 14;
    });
    // Ha nincs előző heti ablak (rövid a történet), a legrégebbi méréshez mérünk.
    const baseline = prior.length > 0 ? mean(prior.map((s) => s.price)) : series[0].price;
    const recentAvg = mean(recent.map((s) => s.price));
    trendPct = ((recentAvg - baseline) / baseline) * 100;
    if (trendPct <= -1.5) trend = "csokkeno";
    else if (trendPct >= 1.5) trend = "emelkedo";
  }

  const listPrice = latest.list_price;
  const onSale = listPrice != null && listPrice > current;

  return {
    current,
    previous,
    changeSinceLast: previous == null ? null : current - previous,
    changeSinceLastPct:
      previous == null ? null : ((current - previous) / previous) * 100,
    min, max, minOn, maxOn,
    min30, max30, avg30,
    pctAboveMin30: ((current - min30) / min30) * 100,
    pctVsAvg30: ((current - avg30) / avg30) * 100,
    isFlat30: min30 === max30,
    isAtMonthLow: min30 !== max30 && current === min30,
    daysSinceCheaper,
    isAllTimeLow,
    trend,
    trendPct,
    onSale,
    discountPct: onSale ? ((listPrice! - current) / listPrice!) * 100 : null,
    sampleCount: series.length,
    firstSeenOn: series[0].captured_on,
    lastSeenOn: latest.captured_on,
    hasEnoughData: series.length >= MIN_SAMPLES_FOR_TREND,
  };
}

export const TREND_LABEL: Record<Trend, string> = {
  csokkeno: "Csökkenő",
  emelkedo: "Emelkedő",
  stabil: "Stabil",
};
