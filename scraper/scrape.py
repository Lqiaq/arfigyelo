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

from extract import extract_from_jsonld, extract_from_price_text
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
# A tényleges parse-olás az extract.py-ban él (böngésző nélkül tesztelhető).
# Itt csak a Playwright-oldali "hozd ide a szöveget" rész van.


def read_jsonld(page) -> dict | None:
    blocks = page.locator('script[type="application/ld+json"]').all_text_contents()
    return extract_from_jsonld(blocks)


def read_dom_price(page) -> dict | None:
    for selector in DOM_PRICE_SELECTORS:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=2_000)
        except (PlaywrightError, PlaywrightTimeout):
            continue
        result = extract_from_price_text(text)
        if result:
            return result
    return None


class Blocked(Exception):
    """A szerver visszautasított minket (403/429 vagy bot-challenge oldal).

    Ez nem hiba, amit újrapróbálkozással kell legyőzni — ez egy "ne most"
    üzenet. A futás azonnal leáll: sem megkerülni nem akarjuk, sem tovább
    terhelni az oldalt.
    """


def scrape_product(page, product: dict) -> dict | None:
    """Egy termékoldal kiolvasása. None = nem sikerült; Blocked = leállunk."""
    for attempt in range(1, RETRIES + 2):
        try:
            response = page.goto(
                product["url"], timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded"
            )
            status = response.status if response else 0

            if status in (403, 429):
                retry_after = (response.headers.get("retry-after") if response else None)
                raise Blocked(
                    f"HTTP {status} a(z) {product['url']} kérésre"
                    + (f" (Retry-After: {retry_after})" if retry_after else "")
                )
            if status >= 400:
                print(f"    HTTP {status} – kihagyom (rossz URL?)")
                return None

            data = read_jsonld(page) or read_dom_price(page)
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
    ap.add_argument(
        "--delay",
        type=float,
        help=f"fix szünet másodpercben a lekérések között "
        f"(alap: véletlen {MIN_DELAY_S}–{MAX_DELAY_S} s)",
    )
    ap.add_argument(
        "--catalog",
        default="products.mock.json",
        help="melyik katalógusfájlt scrape-elje (alap: products.mock.json)",
    )
    args = ap.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.is_absolute():
        catalog_path = HERE / catalog_path
    if not catalog_path.exists():
        print(f"Nincs ilyen katalógus: {catalog_path}")
        print("Mock shop esetén futtasd előbb: python ../mock-shop/generate.py")
        return 2

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
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

        blocked_at: str | None = None

        for i, product in enumerate(products, 1):
            print(f"[{i}/{len(products)}] {product['name']}")
            try:
                data = scrape_product(page, product)
            except Blocked as exc:
                blocked_at = str(exc)
                break

            results.append((product, data))

            if data:
                huf = f"{data['price']:,}".replace(",", " ")
                extra = f" (listaár {data['list_price']:,})".replace(",", " ") if data["list_price"] else ""
                print(f"    {huf} Ft{extra} · {data['availability'] or 'n/a'} · {data['source']}")
            else:
                print("    SIKERTELEN")

            if i < len(products):
                if args.delay is not None:
                    pause = args.delay
                else:
                    pause = crawl_delay or random.uniform(MIN_DELAY_S, MAX_DELAY_S)
                time.sleep(pause)

        context.close()
        browser.close()

    if blocked_at:
        print(f"\n⨯ A szerver visszautasított: {blocked_at}")
        print(
            "  A futás leállt. Ez nem hiba, hanem az oldal bot-védelme.\n"
            "  Amit tenni lehet: ritkítsd a lekéréseket (--delay), futtasd\n"
            "  ritkábban, vagy keress hivatalos adatforrást (feed/affiliate API).\n"
            "  Amit NEM: a védelem megkerülése."
        )
        # A már kiolvasott termékeket még elmentjük – ne dobjuk el a munkát.

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

    # Külön kilépőkód a blokkolásra: a cron logjában azonnal látszódjon,
    # hogy nem a kódunk romlott el, hanem a szerver zárt ki.
    if blocked_at:
        return 3

    # A cron akkor bukjon el, ha a termékek több mint felét nem sikerült
    # kiolvasni – az már layoutváltozásra utal, nem zajra.
    if results and len(ok) < len(results) / 2:
        print("! A termékek több mint fele sikertelen – valószínűleg változott az oldal.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
