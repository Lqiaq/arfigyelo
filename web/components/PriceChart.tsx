"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDate, formatPrice, formatPriceCompact, formatShortDate } from "@/lib/format";
import type { Snapshot, Trend } from "@/lib/types";

const STROKE: Record<Trend, string> = {
  csokkeno: "var(--down)",
  emelkedo: "var(--up)",
  stabil: "var(--accent)",
};

interface Point {
  date: string;
  price: number;
  listPrice: number | null;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Point }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;

  return (
    <div className="rounded-lg border border-border-strong bg-surface px-3 py-2 shadow-lg">
      <div className="text-[11px] text-text-muted">{formatDate(point.date)}</div>
      <div className="tabular text-[15px] font-semibold">
        {formatPrice(point.price)}
      </div>
      {point.listPrice != null && point.listPrice > point.price && (
        <div className="tabular text-[11px] text-text-faint line-through">
          {formatPrice(point.listPrice)}
        </div>
      )}
    </div>
  );
}

export function PriceChart({
  history,
  trend,
  min,
  max,
}: {
  history: Snapshot[];
  trend: Trend;
  min: number;
  max: number;
}) {
  const data: Point[] = history.map((s) => ({
    date: s.captured_on,
    price: s.price,
    listPrice: s.list_price,
  }));

  // Az y tengely ne 0-tól induljon — pár százalékos árváltozás úgy
  // lapos vonalnak látszana. 8% levegő az adat körül.
  const pad = Math.max((max - min) * 0.35, max * 0.02);
  const color = STROKE[trend];

  return (
    <div className="h-[280px] w-full sm:h-[340px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.18} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="var(--grid)" strokeDasharray="2 4" vertical={false} />

          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            tick={{ fill: "var(--text-faint)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--grid)" }}
            minTickGap={28}
          />
          <YAxis
            domain={[Math.floor(min - pad), Math.ceil(max + pad)]}
            tickFormatter={formatPriceCompact}
            tick={{ fill: "var(--text-faint)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={54}
          />

          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--border-strong)" }} />

          <ReferenceLine
            y={min}
            stroke="var(--down)"
            strokeDasharray="3 3"
            strokeOpacity={0.5}
            label={{
              value: "min",
              position: "insideBottomLeft",
              fill: "var(--down)",
              fontSize: 10,
            }}
          />

          <Area
            type="stepAfter"
            dataKey="price"
            stroke="none"
            fill="url(#priceFill)"
            isAnimationActive={false}
          />
          {/* stepAfter, nem sima görbe: az ár egy adott napon ugrik,
              a köztes napokra nincs mérés — az interpoláció hazudna. */}
          <Line
            type="stepAfter"
            dataKey="price"
            stroke={color}
            strokeWidth={2}
            dot={data.length <= 20 ? { r: 2.5, fill: color, strokeWidth: 0 } : false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
