import type { Snapshot, Trend } from "@/lib/types";

/**
 * Mini árgörbe a terméklistához.
 *
 * Szándékosan sima SVG és nem recharts: 15 kártyához 15 chart-példány
 * indokolatlanul sok kliensoldali JS lenne egy olyan grafikonért, amin nincs
 * interakció. A részletes, tooltipes grafikon a termékoldalon fut (PriceChart).
 */

const WIDTH = 132;
const HEIGHT = 36;
const PADDING = 3;

const STROKE: Record<Trend, string> = {
  csokkeno: "var(--down)",
  emelkedo: "var(--up)",
  stabil: "var(--flat)",
};

export function Sparkline({
  history,
  trend,
}: {
  history: Snapshot[];
  trend: Trend;
}) {
  if (history.length < 2) {
    return (
      <div
        className="flex items-center justify-center text-[11px] text-text-faint"
        style={{ width: WIDTH, height: HEIGHT }}
      >
        gyűlik az adat
      </div>
    );
  }

  const prices = history.map((s) => s.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const stepX = (WIDTH - PADDING * 2) / (prices.length - 1);

  const points = prices.map((price, i) => {
    const x = PADDING + i * stepX;
    const y = PADDING + (1 - (price - min) / span) * (HEIGHT - PADDING * 2);
    return [x, y] as const;
  });

  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${PADDING},${HEIGHT} ${line} ${(WIDTH - PADDING).toFixed(1)},${HEIGHT}`;
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={`Árgörbe ${history.length} mérésből, trend: ${trend}`}
      className="overflow-visible"
    >
      <polygon points={area} fill={STROKE[trend]} opacity={0.08} />
      <polyline
        points={line}
        fill="none"
        stroke={STROKE[trend]}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={2.5} fill={STROKE[trend]} />
    </svg>
  );
}
