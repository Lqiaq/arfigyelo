import { NextResponse } from "next/server";

import { getProduct } from "@/lib/data";
import { analyze } from "@/lib/stats";
import { getVerdict, hasClaude } from "@/lib/verdict";

/**
 * GET /api/verdict?slug=sony-wh-1000xm6-fekete
 *
 * Az oldalak szerver-oldalon már meghívják a `getVerdict`-et, ez a route
 * azért van, hogy a verdikt-réteg önmagában is demózható és tesztelhető
 * legyen (curl, Postman), illetve hogy egy jövőbeli kliens is használhassa.
 *
 * A modellhívás ugyanazon a hash-alapú cache-en megy át, mint az oldalaké.
 */
export const revalidate = 43_200;

export async function GET(request: Request) {
  const slug = new URL(request.url).searchParams.get("slug");

  if (!slug) {
    return NextResponse.json(
      { error: "Hiányzó 'slug' query paraméter." },
      { status: 400 },
    );
  }

  const product = await getProduct(slug);
  if (!product) {
    return NextResponse.json(
      { error: `Nincs ilyen termék: ${slug}` },
      { status: 404 },
    );
  }

  const stats = analyze(product.history);
  const verdict = await getVerdict(product, stats);

  return NextResponse.json(
    {
      slug: product.slug,
      name: product.name,
      verdict,
      stats: {
        current: stats.current,
        min: stats.min,
        max: stats.max,
        min30: stats.min30,
        avg30: stats.avg30,
        trend: stats.trend,
        daysSinceCheaper: stats.daysSinceCheaper,
        isAllTimeLow: stats.isAllTimeLow,
        sampleCount: stats.sampleCount,
      },
      meta: {
        aiEnabled: hasClaude(),
        lastCheckedOn: stats.lastSeenOn,
      },
    },
    {
      headers: {
        // A kliens és a CDN is nyugodtan tarthatja 12 órán át: az adat
        // naponta egyszer frissül.
        "Cache-Control": "public, s-maxage=43200, stale-while-revalidate=86400",
      },
    },
  );
}
