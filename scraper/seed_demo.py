"""Szintetikus ártörténet a frontend fejlesztéséhez.

MIÉRT VAN EZ: a valós adat napi 1 mérés, tehát az indulás után napokig egyetlen
pont van termékenként — grafikont fejleszteni így kényelmetlen. Ez a szkript
45 nap kitalált történetet generál, hogy a UI-t végig lehessen próbálni.

EZ NEM VALÓS ADAT. Külön fájlba (`db.demo.json`) írja, és a frontend csak akkor
használja, ha NEXT_PUBLIC_DEMO_DATA=1 — olyankor figyelmeztető sávot is kirak.
Éles demóban soha ne kapcsold be.

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

from store import REPO_ROOT, ProductRow, SnapshotRow, product_id_for

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "products.json"
OUT = REPO_ROOT / "web" / "public" / "data" / "db.demo.json"

# Fix seed: ugyanaz a parancs mindig ugyanazt a fájlt adja, így a demó-adat
# változása nem zajosítja a git diffet.
RNG = random.Random(20260810)

# A valós, 2026-08-10-én mért árak — ezekből indulunk visszafelé.
ANCHOR_PRICES = {
    "sony-wh-1000xm6-fekete": 134990,
    "sony-wh-ch720n-fekete": 31990,
    "sony-wf-1000xm6-ezust": 99990,
    "apple-airpods-4": 52990,
    "apple-airpods-4-anc": 74990,
    "apple-airpods-pro-3": 99990,
    "apple-airpods-max-2-ejfekete": 239990,
    "samsung-galaxy-buds3-ezust": 36990,
    "nothing-ear-a-black": 29990,
    "jbl-tune-530bt-black": 15990,
    "jbl-quantum-350-wireless-fekete": 24590,
    "jbl-wave-buds-2-fekete": 23890,
    "marshall-major-iv-fekete": 23990,
    "soundcore-q20i": 17390,
    "asus-rog-pelta": 38490,
}


def round_to_990(value: float) -> int:
    """A magyar webshopok árai .990-re végződnek – enélkül hamisan néz ki."""
    thousands = max(1, round(value / 1000))
    return thousands * 1000 - 10


def generate_series(anchor: int, days: int) -> list[int]:
    """Visszafelé generál: az utolsó nap mindig a valós, horgony ár.

    Három viselkedés keveredik, hogy a demó ne legyen egyhangú:
    lassú sodródás, néhol egy akciós völgy, és sok teljesen mozdulatlan nap
    (a valóságban is ez a gyakori).
    """
    drift = RNG.choice([-0.0015, -0.0008, 0.0, 0.0006, 0.0012])
    prices = [anchor]
    value = float(anchor)

    for _ in range(days - 1):
        value *= 1 - drift
        if RNG.random() < 0.12:  # ritka, nagyobb árlépés
            value *= 1 + RNG.uniform(-0.05, 0.05)
        prices.append(round_to_990(value))

    prices.reverse()

    # Egy akciós völgy a történet közepe tájára, 3-8 napig.
    if days > 14 and RNG.random() < 0.6:
        start = RNG.randint(5, days - 12)
        length = RNG.randint(3, 8)
        depth = RNG.uniform(0.07, 0.18)
        for i in range(start, min(start + length, days - 2)):
            prices[i] = round_to_990(prices[i] * (1 - depth))

    prices[-1] = anchor  # a mai nap maradjon a valós ár
    return prices


def main() -> None:
    ap = argparse.ArgumentParser(description="Szintetikus demó-ártörténet")
    ap.add_argument("--days", type=int, default=45, help="hány nap története")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    today = date(2026, 8, 10)
    dates = [
        (today - timedelta(days=args.days - 1 - i)).isoformat()
        for i in range(args.days)
    ]

    products, snapshots = [], []

    for product in catalog["products"]:
        slug = product["slug"]
        anchor = ANCHOR_PRICES.get(slug)
        if anchor is None:
            print(f"  ! nincs horgony ár ehhez: {slug} – kihagyom")
            continue

        pid = product_id_for(slug)
        products.append(
            {
                "id": pid,
                **asdict(
                    ProductRow(
                        slug=slug,
                        name=product["name"],
                        url=product["url"],
                        brand=product.get("brand"),
                        category=catalog["category"],
                        shop=catalog["shop"],
                        currency=catalog["currency"],
                    )
                ),
                "created_at": f"{dates[0]}T06:12:00+00:00",
            }
        )

        series = generate_series(anchor, args.days)
        for captured_on, price in zip(dates, series):
            snapshots.append(
                asdict(
                    SnapshotRow(
                        product_id=pid,
                        price=price,
                        # Akciós napokon legyen áthúzott ár is, hogy a UI
                        # kedvezmény-ága is látszódjon.
                        list_price=round_to_990(price * 1.15)
                        if price < anchor * 0.93
                        else None,
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
        f"{len(products)} termék × {args.days} nap = {len(snapshots)} snapshot"
    )


if __name__ == "__main__":
    main()
