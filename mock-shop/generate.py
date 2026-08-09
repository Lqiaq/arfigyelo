"""Statikus mock-webshop a Playwright scraper teszteléséhez.

MIÉRT VAN EZ: az élő adat a Steam publikus API-jából jön (lásd
`scraper/fetch_steam.py`). A böngészős scraper-ág viszont megmarad — ez a
mock shop a célpontja. Ugyanaz a JSON-LD szerkezet, mint egy valódi
webshopé, tehát a scraper és a parse-logika ténylegesen végig van próbálva,
anélkül hogy bárki szerverét terhelnénk vagy a bot-védelmét feszegetnénk.

Használat:
    python generate.py            # HTML-ek legenerálása a site/ mappába
    python -m http.server 8000 --directory site
    cd ../scraper && python scrape.py --catalog products.mock.json
"""

from __future__ import annotations

import argparse
import html
import json
import random
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / "site"
CATALOG_OUT = HERE.parent / "scraper" / "products.mock.json"

RNG = random.Random(20260810)

# Ugyanaz a kategória, mint az eredeti koncepcióban – a scraper szempontjából
# a lényeg a JSON-LD szerkezet, nem a termék.
PRODUCTS = [
    ("sony-wh-1000xm6", "Sony WH-1000XM6 Noise Cancelling", "Sony", 134990, 149990),
    ("sony-wh-ch720n", "Sony WH-CH720N Noise Cancelling", "Sony", 31990, None),
    ("sony-wf-1000xm6", "Sony WF-1000XM6", "Sony", 99990, None),
    ("apple-airpods-4", "Apple AirPods 4", "Apple", 52990, None),
    ("apple-airpods-pro-3", "Apple AirPods Pro 3", "Apple", 99990, None),
    ("apple-airpods-max-2", "Apple AirPods Max 2", "Apple", 239990, 259990),
    ("samsung-galaxy-buds3", "Samsung Galaxy Buds3", "Samsung", 36990, None),
    ("nothing-ear-a", "Nothing Ear (a)", "Nothing", 29990, 34990),
    ("jbl-tune-530bt", "JBL Tune 530BT", "JBL", 15990, None),
    ("jbl-quantum-350", "JBL Quantum 350 Wireless", "JBL", 24590, None),
    ("jbl-wave-buds-2", "JBL Wave Buds 2", "JBL", 23890, None),
    ("marshall-major-iv", "Marshall Major IV Bluetooth", "Marshall", 23990, None),
    ("soundcore-q20i", "Soundcore Q20i", "Soundcore", 17390, 21990),
    ("asus-rog-pelta", "ASUS ROG Pelta", "ASUS", 38490, 61690),
    ("beyerdynamic-dt-770", "beyerdynamic DT 770 PRO", "beyerdynamic", 44990, None),
]

PAGE = """<!doctype html>
<html lang="hu">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} {price_text} – Mock Shop</title>

<!-- Ez a blokk a scraper elsődleges célpontja. Ugyanaz a szerkezet, amit egy
     valódi webshop is kitesz a keresőknek: @graph több node-dal, a Product
     nem az első, az akciós ár pedig priceSpecification/StrikethroughPrice. -->
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
  <nav><a href="/">Mock Shop</a> / <a href="/index.html">Fejhallgatók</a></nav>
  <main>
    <h1>{name}</h1>
    <p class="brand">{brand}</p>
    <div id="pricePane">
      <span class="js-price-box__primary-price__value">{price_text}</span>
      {strike_html}
    </div>
    <p class="avlVal">{availability_text}</p>
  </main>
  <footer>
    <p>Ez egy generált mock termékoldal a scraper teszteléséhez.
       Nem valódi bolt, az árak kitaláltak.</p>
  </footer>
</body>
</html>
"""

INDEX = """<!doctype html>
<html lang="hu">
<head><meta charset="utf-8"><title>Mock Shop – Fejhallgatók</title></head>
<body>
  <h1>Mock Shop – Fejhallgatók</h1>
  <p>Generált tesztoldalak a Playwright scraperhez. Generálva: {today}.</p>
  <ul>{items}</ul>
</body>
</html>
"""


def huf(value: int) -> str:
    """134990 -> '134 990 Ft' – nem törő szóközzel, mint a valódi shopok."""
    return f"{value:,}".replace(",", " ") + " Ft"


def build_jsonld(slug: str, name: str, brand: str, price: int, list_price: int | None,
                 base_url: str, availability: str) -> str:
    specs = [
        {
            "@type": "UnitPriceSpecification",
            "priceType": "https://schema.org/SalePrice",
            "price": price,
            "priceCurrency": "HUF",
            "valueAddedTaxIncluded": True,
        }
    ]
    if list_price:
        specs.insert(
            0,
            {
                "@type": "UnitPriceSpecification",
                "priceType": "https://schema.org/StrikethroughPrice",
                "price": list_price,
                "priceCurrency": "HUF",
                "valueAddedTaxIncluded": True,
            },
        )

    graph = [
        {"@type": "Organization", "name": "Mock Shop"},
        {"@type": "WebPage", "name": name},
        {
            "@type": "Product",
            "name": name,
            "sku": slug.upper().replace("-", "")[:12],
            "brand": {"@type": "Brand", "name": brand},
            "image": [
                {
                    "@type": "ImageObject",
                    "url": f"{base_url}/img/{slug}.jpg",
                    "name": f"{name} – Fő fotó",
                }
            ],
            "offers": {
                "@type": "Offer",
                "url": f"{base_url}/{slug}.html",
                "itemCondition": "https://schema.org/NewCondition",
                "availability": f"https://schema.org/{availability}",
                "price": price,
                "priceCurrency": "HUF",
                "priceSpecification": specs,
            },
        },
    ]
    return json.dumps(
        {"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Mock shop generátor")
    ap.add_argument(
        "--base-url", default="http://localhost:8000", help="a kiszolgálás base URL-je"
    )
    ap.add_argument(
        "--jitter",
        action="store_true",
        help="±5%% véletlen árelmozdítás – így az újragenerálás új mérést ad",
    )
    args = ap.parse_args()

    SITE.mkdir(parents=True, exist_ok=True)
    catalog_entries = []
    links = []

    for slug, name, brand, price, list_price in PRODUCTS:
        if args.jitter:
            price = int(round(price * RNG.uniform(0.95, 1.05) / 10) * 10 - 10)
            if list_price and list_price <= price:
                list_price = None

        availability = "InStock" if RNG.random() > 0.1 else "OutOfStock"
        strike = (
            f'<span class="price-box__strike">{html.escape(huf(list_price))}</span>'
            if list_price
            else ""
        )

        (SITE / f"{slug}.html").write_text(
            PAGE.format(
                name=html.escape(name),
                brand=html.escape(brand),
                price_text=html.escape(huf(price)),
                strike_html=strike,
                availability_text="Raktáron" if availability == "InStock" else "Elfogyott",
                jsonld=build_jsonld(
                    slug, name, brand, price, list_price, args.base_url, availability
                ),
            ),
            encoding="utf-8",
        )

        catalog_entries.append(
            {
                "slug": slug,
                "name": name,
                "brand": brand,
                "url": f"{args.base_url}/{slug}.html",
            }
        )
        links.append(f'<li><a href="{slug}.html">{html.escape(name)}</a></li>')

    (SITE / "index.html").write_text(
        INDEX.format(today=date.today().isoformat(), items="\n    ".join(links)),
        encoding="utf-8",
    )
    (SITE / "robots.txt").write_text(
        "# Mock shop – a scraper ezt is ellenőrzi, mint egy valódi oldalnál.\n"
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Crawl-delay: 1\n",
        encoding="utf-8",
    )

    CATALOG_OUT.write_text(
        json.dumps(
            {
                "shop": "mock-shop",
                "category": "fejhallgato",
                "currency": "HUF",
                "note": "Generált mock termékoldalak – lásd mock-shop/generate.py. Nem valódi bolt.",
                "products": catalog_entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"→ {len(PRODUCTS)} oldal + index + robots.txt: {SITE}")
    print(f"→ katalógus: {CATALOG_OUT}")
    print("\nKiszolgálás és scrape:")
    print(f"  python -m http.server 8000 --directory {SITE}")
    print("  cd ../scraper && python scrape.py --catalog products.mock.json --dry-run")


if __name__ == "__main__":
    main()
