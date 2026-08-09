"""Szintetikus ártörténet a frontend fejlesztéséhez.

MIÉRT VAN EZ: a valós adat napi 1 mérés, tehát az indulás után napokig egyetlen
pont van címenként — grafikont fejleszteni így kényelmetlen. Ez a szkript
45 nap kitalált történetet generál, hogy a UI-t végig lehessen próbálni.

EZ NEM VALÓS ADAT. Külön fájlba (`db.demo.json`) írja, és a frontend csak akkor
használja, ha NEXT_PUBLIC_DEMO_DATA=1 — olyankor figyelmeztető sávot is kirak.
Éles demóban soha ne kapcsold be.

A generált mintázat a Steam árazását utánozza: hosszú, teljesen mozdulatlan
szakaszok, közben 1-2 éles, néhány napos akció — nem folytonos sodródás.

Futtatás:
    python seed_demo.py [--days 45]
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from steam_extract import store_url
from store import REPO_ROOT, ProductRow, SnapshotRow, product_id_for

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "games.json"
LIVE_DB = REPO_ROOT / "web" / "public" / "data" / "db.json"
OUT = REPO_ROOT / "web" / "public" / "data" / "db.demo.json"

# Fix seed: ugyanaz a parancs mindig ugyanazt a fájlt adja, így a demó-adat
# változása nem zajosítja a git diffet.
RNG = random.Random(20260810)

# Tipikus Steam kedvezmény-lépcsők.
DISCOUNTS = [0.10, 0.20, 0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75, 0.80]


def load_anchors() -> dict[str, tuple[int, int, str]]:
    """slug -> (mai ár, teljes ár, valuta) a valós, lekért pillanatképből.

    Így a demó-görbe a valódi mai árban végződik, és nem kell külön
    karbantartani egy második árlistát.
    """
    if not LIVE_DB.exists():
        raise SystemExit(
            f"Nincs {LIVE_DB.name}. Futtasd előbb: python fetch_steam.py"
        )

    db = json.loads(LIVE_DB.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in db["products"]}
    anchors: dict[str, tuple[int, int, str]] = {}

    for snap in db["price_snapshots"]:
        product = by_id.get(snap["product_id"])
        if not product:
            continue
        price = snap["price"]
        full = snap.get("list_price") or price
        anchors[product["slug"]] = (price, full, product.get("currency", "EUR"))

    return anchors


def sale_price(base: int, depth: float) -> int:
    """Teljes árból akciós ár, x,99-re kerekítve – ahogy a Steam is teszi."""
    return max(99, int(round(base * (1 - depth) / 100) * 100 - 1))


def generate_series(current: int, full_price: int, days: int) -> list[tuple[int, int | None]]:
    """(ár, listaár) párok napra bontva. Az utolsó nap a valós, mai ár.

    A Steam árazása lépcsős, nem sodródó: hosszú mozdulatlan szakaszok,
    közben egy-egy néhány napos akció. Szándékosan csak EGY korábbi akció
    van, és az nem lóghat rá a mostanira — az átfedő akciók abszurd
    heti-változás számokat szülnének a statisztikában.
    """
    series: list[tuple[int, int | None]] = [(full_price, None)] * days
    currently_on_sale = current < full_price

    # A mostani akció a történet végén fut, ha ma tényleg akciós az ár.
    current_sale_len = RNG.randint(3, 6) if currently_on_sale else 1
    quiet_zone_start = days - current_sale_len - 3  # legyen szünet a kettő közt

    # Egy korábbi akció, biztonságos távolságban a mostanitól.
    past_len = RNG.randint(4, 8)
    if quiet_zone_start - past_len > 2:
        start = RNG.randint(2, quiet_zone_start - past_len)
        past = sale_price(full_price, RNG.choice(DISCOUNTS))
        for i in range(start, start + past_len):
            series[i] = (past, full_price)

    if currently_on_sale:
        for i in range(days - current_sale_len, days):
            series[i] = (current, full_price)
    else:
        series[-1] = (current, None)

    return series


def main() -> None:
    ap = argparse.ArgumentParser(description="Szintetikus demó-ártörténet")
    ap.add_argument("--days", type=int, default=45, help="hány nap története")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    anchors = load_anchors()

    today = date.today()
    dates = [
        (today - timedelta(days=args.days - 1 - i)).isoformat()
        for i in range(args.days)
    ]

    products, snapshots = [], []

    for game in catalog["products"]:
        slug = game["slug"]
        anchor = anchors.get(slug)
        if anchor is None:
            print(f"  ! nincs valós mérés ehhez: {slug} – kihagyom")
            continue
        current, full_price, currency = anchor

        pid = product_id_for(slug)
        products.append(
            {
                "id": pid,
                **asdict(
                    ProductRow(
                        slug=slug,
                        name=game["name"],
                        url=store_url(game["appid"]),
                        brand=None,
                        category=catalog["category"],
                        shop=catalog["shop"],
                        currency=currency,
                    )
                ),
                "created_at": f"{dates[0]}T06:12:00+00:00",
            }
        )

        for captured_on, (price, list_price) in zip(
            dates, generate_series(current, full_price, args.days)
        ):
            snapshots.append(
                asdict(
                    SnapshotRow(
                        product_id=pid,
                        price=price,
                        list_price=list_price,
                        availability="InStock",
                        captured_on=captured_on,
                        source="demo",
                    )
                )
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "_warning": "SZINTETIKUS DEMÓ-ADAT, nem valós mérés. Lásd scraper/seed_demo.py",
                "is_demo": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "products": products,
                "price_snapshots": snapshots,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(
        f"→ {OUT.relative_to(REPO_ROOT)} kész: "
        f"{len(products)} cím × {args.days} nap = {len(snapshots)} snapshot"
    )


if __name__ == "__main__":
    main()
