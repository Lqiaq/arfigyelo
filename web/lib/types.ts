export type Trend = "csokkeno" | "emelkedo" | "stabil";

export interface Product {
  id: string;
  slug: string;
  name: string;
  brand: string | null;
  category: string;
  url: string;
  image_url: string | null;
  shop: string;
  currency: string;
  active: boolean;
}

export interface Snapshot {
  /** ISO dátum, budapesti nap szerint (YYYY-MM-DD) */
  captured_on: string;
  price: number;
  /** Áthúzott/eredeti ár, ha akciós. */
  list_price: number | null;
  availability: string | null;
}

export interface ProductWithHistory extends Product {
  history: Snapshot[];
}

export interface Verdict {
  trend: Trend;
  /** Rövid címke, pl. "Most jó vétel" */
  headline: string;
  /** 1-2 mondatos, emberi nyelvű összefoglaló. */
  verdict: string;
  /** 'claude' = a modell írta, 'heuristic' = kulcs nélküli tartalék. */
  source: "claude" | "heuristic";
  model: string | null;
}
