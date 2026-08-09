const HUF = new Intl.NumberFormat("hu-HU", {
  style: "currency",
  currency: "HUF",
  maximumFractionDigits: 0,
});

const HUF_COMPACT = new Intl.NumberFormat("hu-HU", {
  notation: "compact",
  maximumFractionDigits: 0,
});

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return HUF.format(value);
}

/** Grafikon-tengelyhez: "135 E" – elfér a keskeny y tengelyen is. */
export function formatPriceCompact(value: number): string {
  return HUF_COMPACT.format(value);
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
