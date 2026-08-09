/**
 * Pénzformázás.
 *
 * Konvenció: az adatbázis mindig abban a legkisebb egységben tárolja az árat,
 * amiben a bolt jegyzi — EUR-nál cent, HUF-nál forint. Hogy melyik hány
 * tizedes, azt nem mi kódoljuk le, hanem az Intl API mondja meg
 * (HUF -> 0 tizedes, EUR -> 2), így új valuta hozzáadásához nem kell kód.
 */

const DEFAULT_CURRENCY = "EUR";

const fractionDigitsCache = new Map<string, number>();
const formatterCache = new Map<string, Intl.NumberFormat>();

function fractionDigits(currency: string): number {
  const cached = fractionDigitsCache.get(currency);
  if (cached !== undefined) return cached;

  let digits = 2;
  try {
    digits =
      new Intl.NumberFormat("hu-HU", { style: "currency", currency })
        .resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    // Ismeretlen valutakód – ne dőljön el az oldal miatta.
  }
  fractionDigitsCache.set(currency, digits);
  return digits;
}

function formatter(currency: string, compact: boolean): Intl.NumberFormat {
  const key = `${currency}:${compact}`;
  const cached = formatterCache.get(key);
  if (cached) return cached;

  const digits = fractionDigits(currency);
  const created = new Intl.NumberFormat("hu-HU", {
    style: "currency",
    currency,
    ...(compact
      ? { notation: "compact" as const, maximumFractionDigits: 1 }
      : { minimumFractionDigits: digits, maximumFractionDigits: digits }),
  });
  formatterCache.set(key, created);
  return created;
}

/** A legkisebb egységben tárolt értéket olvasható összeggé alakítja. */
export function toMajorUnits(minor: number, currency: string): number {
  return minor / 10 ** fractionDigits(currency);
}

export function formatPrice(
  minor: number | null | undefined,
  currency: string = DEFAULT_CURRENCY,
): string {
  if (minor == null) return "—";
  return formatter(currency, false).format(toMajorUnits(minor, currency));
}

/**
 * Grafikon-tengelyhez: rövid alak, hogy elférjen a keskeny y tengelyen.
 *
 * Ezres alatt a compact jelölés csak ront (egy 18–60 eurós skálán a "23,3 E"
 * értelmetlen), ezért ott sima, tizedes nélküli formát adunk. HUF-nál a
 * tipikus árak jóval ezer fölött vannak, ott marad a compact ("135 E").
 */
export function formatPriceCompact(
  minor: number,
  currency: string = DEFAULT_CURRENCY,
): string {
  const major = toMajorUnits(minor, currency);
  return formatter(currency, Math.abs(major) >= 1000).format(major);
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${y}. ${m}. ${d}.`;
}

export function formatShortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}.${Number(d)}.`;
}

/** "3 hete" / "5 napja" / "ma" – a verdikt szövegéhez és a UI-hoz egyaránt. */
export function formatDaysAgo(days: number): string {
  if (days <= 0) return "ma";
  if (days === 1) return "tegnap";
  if (days < 14) return `${days} napja`;
  const weeks = Math.round(days / 7);
  if (weeks < 9) return `${weeks} hete`;
  return `${Math.round(days / 30)} hónapja`;
}

export function formatPercent(value: number, withSign = true): string {
  const rounded = Math.round(value * 10) / 10;
  const sign = withSign && rounded > 0 ? "+" : "";
  return `${sign}${rounded.toLocaleString("hu-HU")}%`;
}
