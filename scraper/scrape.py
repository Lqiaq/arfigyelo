"""Napi árpillanatkép-készítő az Alza.hu fejhallgató-kategóriájából.

Használat:
    python scrape.py                 # teljes futás
    python scrape.py --limit 3       # gyors füstteszt 3 termékre
    python scrape.py --dry-run       # kiolvas, de nem ír adatbázisba
    python scrape.py --headed        # látható böngésző, debughoz

Az ár kiolvasása elsődlegesen a termékoldal JSON-LD (schema.org/Product)
blokkjából történik – az strukturált adat, amit az Alza maga tesz ki a
keresőknek, tehát jóval stabilabb, mint bármelyik CSS-osztály. DOM-selector
csak fallback, ha a JSON-LD hiányzik vagy hibás.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from store import ProductRow, SnapshotRow, get_store, today_budapest

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "products.json"

# Udvariassági beállítások. Napi 1 futás, 15 oldal, ~3 mp szünettel: nagyjából
# annyi forgalom, mint egy ember, aki végignézi a kategóriát. Lásd README.
MIN_DELAY_S = 2.0
MAX_DELAY_S = 4.0
PAGE_TIMEOUT_MS = 30_000
RETRIES = 2

USER_AGENT = (
    "arfigyelo-portfolio/1.0 (+https://github.com/;  napi 1 lekeres, 15 termek) "
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# A JSON-LD-ből kiolvasott ár után ez a DOM-hook a tartalék. A `js-` prefixű
# osztályok az Alzánál JS-hookok, ezért ritkábban változnak, mint a stílusosztályok.
DOM_PRICE_SELECTORS = [
    "span.js-price-box__primary-price__value",
    ".price-box__primary-price__value",
    "#pricePane .price-box__price",
]

PRICE_RE = re.compile(r"(\d[\d\s  .]*)")


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------
def check_robots(page, urls: list[str]) -> tuple[list[str], float | None]:
    """Kiszűri azokat az URL-eket, amiket a robots.txt tilt.

    A robots.txt-t magával a böngészővel kérjük le: az Alza a "csupasz" HTTP
    klienseket 403-mal fogadja, így a urllib önmagában elhasalna rajta.
    """
    origin = "{0.scheme}://{0.netloc}".format(urlparse(urls[0]))
    robots_url = f"{origin}/robots.txt"

    parser = urllib.robotparser.RobotFileParser()
    try:
        response = page.goto(robots_url, timeout=PAGE_TIMEOUT_MS)
        body = response.text() if response else ""
        parser.parse(body.splitlines())
    except (PlaywrightError, PlaywrightTimeout) as exc:
        print(f"! robots.txt nem elérhető ({exc.__class__.__name__}) – megszakítom.")
        print("  Ha nem tudjuk ellenőrizni a szabályokat, nem scrapelünk.")
        sys.exit(2)

    allowed, blocked = [], []
    for url in urls:
        (allowed if parser.can_fetch(USER_AGENT, url) else blocked).append(url)

    print(f"robots.txt: {len(allowed)} engedélyezett, {len(blocked)} tiltott URL")
    for url in blocked:
        print(f"  ⨯ kihagyva (robots.txt): {url}")

    delay = parser.crawl_delay(USER_AGENT)
    if delay:
        print(f"  crawl-delay: {delay}s (betartjuk)")
    return allowed, float(delay) if delay else None


# ---------------------------------------------------------------------------
# Kiolvasás
# ---------------------------------------------------------------------------
def parse_price(raw) -> int | None:
    """'134 990 Ft' / 134990 / '134990.0' -> 134990"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw))
    match = PRICE_RE.search(str(raw))
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    return int(digits) if digits else None


def find_product_node(data):
    """Rekurzívan megkeresi a schema.org Product node-ot a JSON-LD-ben."""
    if isinstance(data, list):
        for item in data:
            found = find_product_node(item)
            if found:
                return found
    elif isinstance(data, dict):
        types = data.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" in types:
            return data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                found = find_product_node(data[key])
                if found:
                    return found
    return None


def extract_from_jsonld(page) -> dict | None:
    blocks = page.locator('script[type="application/ld+json"]').all_text_contents()
    for block in blocks:
        try:
            node = find_product_node(json.loads(block))
        except json.JSONDecodeError:
            continue
        if not node:
            continue

        offers = node.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        price = parse_price(offers.get("price"))
        if price is None:
            continue

        # Áthúzott ár: a priceSpecification tömbben StrikethroughPrice típussal jön.
        list_price = None
        for spec in offers.get("priceSpecification") or []:
            if isinstance(spec, dict) and "StrikethroughPrice" in str(spec.get("priceType", "")):
                list_price = parse_price(spec.get("price"))

        images = node.get("image") or []
        images = images if isinstance(images, list) else [images]
        image_url = None
        if images:
            first = images[0]
            image_url = first.get("url") if isinstance(first, dict) else str(first)

        brand = node.get("brand")
        brand_name = brand.get("name") if isinstance(brand, dict) else brand

        availability = str(offers.get("availability") or "").rsplit("/", 1)[-1] or None

        return {
            "price": price,
            "list_price": list_price if list_price != price else None,
            "availability": availability,
            "name": node.get("name"),
            "brand": brand_name,
            "image_url": image_url,
            "source": "jsonld",
        }
    return None


def extract_from_dom(page) -> dict | None:
    for selector in DOM_PRICE_SELECTORS:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            price = parse_price(locator.inner_text(timeout=2_000))
        except (PlaywrightError, PlaywrightTimeout):
            continue
        if price:
            return {
                "price": price,
                "list_price": None,
                "availability": None,
                "name": None,
                "brand": None,
                "image_url": None,
                "source": "dom",
            }
    return None


def scrape_product(page, product: dict) -> dict | None:
    """Egy termékoldal kiolvasása, retryval. None = nem sikerült."""
    for attempt in range(1, RETRIES + 2):
        try:
            page.goto(product["url"], timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            data = extract_from_jsonld(page) or extract_from_dom(page)
            if data:
                return data
            print(f"    nem találtam árat (próba {attempt}/{RETRIES + 1})")
        except (PlaywrightError, PlaywrightTimeout) as exc:
            print(f"    {exc.__class__.__name__} (próba {attempt}/{RETRIES + 1})")
        if attempt <= RETRIES:
            time.sleep(2 * attempt)
    return None


# ---------------------------------------------------------------------------
# Fő folyamat
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Alza.hu fejhallgató ár-scraper")
    ap.add_argument("--limit", type=int, help="csak az első N terméket nézd meg")
    ap.add_argument("--dry-run", action="store_true", help="ne írj adatbázisba")
    ap.add_argument("--headed", action="store_true", help="látható böngésző")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    products = catalog["products"][: args.limit] if args.limit else catalog["products"]
    captured_on = today_budapest()

    print(f"Árfigyelő scraper – {catalog['shop']} / {catalog['category']}")
    print(f"Dátum: {captured_on} | Termékek: {len(products)}")

    store = None if args.dry_run else get_store()
    if store:
        print(f"Tároló: {store.name}")
    else:
        print("Tároló: — (dry run)")

    results: list[tuple[dict, dict | None]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="hu-HU",
            timezone_id="Europe/Budapest",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        # Képek/fontok/média blokkolása: gyorsabb futás, kevesebb sávszélesség
        # az ő oldalukon is.
        page.route(
            re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4|avif)(\?|$)"),
            lambda route: route.abort(),
        )

        urls = [p["url"] for p in products]
        allowed_urls, crawl_delay = check_robots(page, urls)
        allowed = set(allowed_urls)
        products = [p for p in products if p["url"] in allowed]

        for i, product in enumerate(products, 1):
            print(f"[{i}/{len(products)}] {product['name']}")
            data = scrape_product(page, product)
            results.append((product, data))

            if data:
                huf = f"{data['price']:,}".replace(",", " ")
                extra = f" (listaár {data['list_price']:,})".replace(",", " ") if data["list_price"] else ""
                print(f"    {huf} Ft{extra} · {data['availability'] or 'n/a'} · {data['source']}")
            else:
                print("    SIKERTELEN")

            if i < len(products):
                time.sleep(crawl_delay or random.uniform(MIN_DELAY_S, MAX_DELAY_S))

        context.close()
        browser.close()

    ok = [(p, d) for p, d in results if d]
    print(f"\nKiolvasva: {len(ok)}/{len(results)}")

    if store:
        rows = [
            ProductRow(
                slug=p["slug"],
                name=p["name"],
                url=p["url"],
                brand=p.get("brand") or (d or {}).get("brand"),
                category=catalog["category"],
                shop=catalog["shop"],
                currency=catalog["currency"],
                image_url=(d or {}).get("image_url"),
            )
            for p, d in results
        ]
        ids = store.sync_products(rows)

        for product, data in ok:
            store.upsert_snapshot(
                SnapshotRow(
                    product_id=ids[product["slug"]],
                    price=data["price"],
                    list_price=data["list_price"],
                    availability=data["availability"],
                    captured_on=captured_on,
                    source=data["source"],
                )
            )
        store.finish()
        print("Mentve.")

    # A cron akkor bukjon el, ha a termékek több mint felét nem sikerült
    # kiolvasni – az már layoutváltozásra vagy blokkolásra utal, nem zajra.
    if results and len(ok) < len(results) / 2:
        print("! A termékek több mint fele sikertelen – valószínűleg változott az oldal.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
