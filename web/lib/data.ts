import "server-only";

import liveDb from "@/public/data/db.json";
import demoDb from "@/public/data/db.demo.json";
import type { Product, ProductWithHistory, Snapshot } from "./types";

export type DataSource = "supabase" | "local" | "demo";

export interface Dataset {
  products: ProductWithHistory[];
  source: DataSource;
  generatedAt: string | null;
  /** true, ha az adat nem valós mérésekből származik – a UI ilyenkor figyelmeztet. */
  isDemo: boolean;
}

interface RawDb {
  products: unknown[];
  price_snapshots: unknown[];
  generated_at?: string;
}

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
const USE_DEMO_DATA = process.env.NEXT_PUBLIC_DEMO_DATA === "1";

export function hasSupabase(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

// ---------------------------------------------------------------------------
// Közös összefűzés: termékek + hozzájuk tartozó snapshotok
// ---------------------------------------------------------------------------
function joinHistory(
  products: Product[],
  snapshots: Array<Snapshot & { product_id: string }>,
): ProductWithHistory[] {
  const byProduct = new Map<string, Snapshot[]>();
  for (const s of snapshots) {
    const list = byProduct.get(s.product_id) ?? [];
    list.push({
      captured_on: s.captured_on,
      price: s.price,
      list_price: s.list_price ?? null,
      availability: s.availability ?? null,
    });
    byProduct.set(s.product_id, list);
  }

  return products.map((p) => ({
    ...p,
    history: (byProduct.get(p.id) ?? []).sort((a, b) =>
      a.captured_on.localeCompare(b.captured_on),
    ),
  }));
}

// ---------------------------------------------------------------------------
// Lokális JSON (a scraper írja, a repóban van)
// ---------------------------------------------------------------------------
function fromLocal(db: RawDb, source: DataSource): Dataset {
  const products = (db.products as Product[]).filter((p) => p.active !== false);
  const snapshots = db.price_snapshots as Array<Snapshot & { product_id: string }>;
  return {
    products: joinHistory(products, snapshots),
    source,
    generatedAt: db.generated_at ?? null,
    isDemo: source === "demo",
  };
}

// ---------------------------------------------------------------------------
// Supabase (anon kulcs, csak olvasás – az RLS ezt engedi)
// ---------------------------------------------------------------------------
async function fromSupabase(): Promise<Dataset> {
  const { createClient } = await import("@supabase/supabase-js");
  const client = createClient(SUPABASE_URL!, SUPABASE_ANON_KEY!);

  const { data: products, error: productsError } = await client
    .from("products")
    .select("id, slug, name, brand, category, url, image_url, shop, currency, active")
    .eq("active", true)
    .order("name");

  if (productsError) throw new Error(`Supabase products: ${productsError.message}`);

  const ids = (products ?? []).map((p) => p.id);
  if (ids.length === 0) {
    return { products: [], source: "supabase", generatedAt: null, isDemo: false };
  }

  const { data: snapshots, error: snapshotsError } = await client
    .from("price_snapshots")
    .select("product_id, price, list_price, availability, captured_on")
    .in("product_id", ids)
    .not("price", "is", null)
    .order("captured_on");

  if (snapshotsError) throw new Error(`Supabase snapshots: ${snapshotsError.message}`);

  const joined = joinHistory(
    products as Product[],
    (snapshots ?? []) as Array<Snapshot & { product_id: string }>,
  );
  const latest = joined
    .flatMap((p) => p.history.map((s) => s.captured_on))
    .sort()
    .pop();

  return {
    products: joined,
    source: "supabase",
    generatedAt: latest ? `${latest}T00:00:00Z` : null,
    isDemo: false,
  };
}

// ---------------------------------------------------------------------------
// Belépési pont
// ---------------------------------------------------------------------------
export async function getDataset(): Promise<Dataset> {
  if (USE_DEMO_DATA) return fromLocal(demoDb as RawDb, "demo");

  if (hasSupabase()) {
    try {
      return await fromSupabase();
    } catch (error) {
      // Ha a Supabase nem elérhető, a dashboard inkább mutassa a lokális
      // pillanatképet, mint hogy 500-zal elszálljon.
      console.error("Supabase lekérés sikertelen, lokális adatra váltok:", error);
    }
  }

  return fromLocal(liveDb as RawDb, "local");
}

export async function getProduct(slug: string): Promise<ProductWithHistory | null> {
  const { products } = await getDataset();
  return products.find((p) => p.slug === slug) ?? null;
}
