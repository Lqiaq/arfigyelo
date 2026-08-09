"""Napi árpillanatkép a Steam Store publikus API-jából.

Használat:
    python fetch_steam.py                 # teljes futás
    python fetch_steam.py --limit 3       # gyors ellenőrzés
    python fetch_steam.py --dry-run       # lekér, de nem ír adatbázisba

Miért API és nem scraping: a Steam boltoldalai kor-kapu mögött vannak, és a
`/api/appdetails` végpont ugyanazt az adatot adja strukturáltan, HTML-parse
nélkül. Ez kevesebb terhelés nekik és stabilabb kód nekünk.

A böngészős scraper-ág (`scrape.py`) megmarad, egy self-hosted mock shop ellen
– lásd README.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from steam_extract import SteamError, parse_appdetails, store_url
from store import ProductRow, SnapshotRow, get_store, today_budapest

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "games.json"

API = "https://store.steampowered.com/api/appdetails"
# A Steam nagyjából 200 kérést enged 5 percenként. Napi 15 kérésnél ez bőven
# belefér, de a szünetet így is megtartjuk.
DELAY_S = 1.5
TIMEOUT_S = 20
RETRIES = 2

USER_AGENT = "arfigyelo-portfolio/1.0 (napi 1 lekeres, 15 cim)"


def fetch_appdetails(appid: int, country_code: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "appids": appid,
            "cc": country_code,
            "l": "hungarian",
            # Csak amire szükségünk van – kisebb válasz mindkét oldalon.
            "filters": "basic,price_overview",
        }
    )
    request = urllib.request.Request(
        f"{API}?{query}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_with_retry(appid: int, country_code: str):
    """Lekérés újrapróbálkozással. 429 esetén megvárjuk a Retry-After-t."""
    for attempt in range(1, RETRIES + 2):
        try:
            return parse_appdetails(fetch_appdetails(appid, country_code), appid)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = int(exc.headers.get("Retry-After") or 30)
                print(f"    429 – várok {wait} mp-et")
                time.sleep(wait)
            else:
                print(f"    HTTP {exc.code} (próba {attempt}/{RETRIES + 1})")
                time.sleep(2 * attempt)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"    hálózati hiba: {exc} (próba {attempt}/{RETRIES + 1})")
            time.sleep(2 * attempt)
        except SteamError as exc:
            # Ez nem múlik el újrapróbálkozástól (rossz appid, ingyenes cím).
            print(f"    {exc}")
            return None
        except json.JSONDecodeError:
            print(f"    nem JSON válasz (próba {attempt}/{RETRIES + 1})")
            time.sleep(2 * attempt)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Steam ár-pillanatkép")
    ap.add_argument("--limit", type=int, help="csak az első N címet")
    ap.add_argument("--dry-run", action="store_true", help="ne írj adatbázisba")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    games = catalog["products"][: args.limit] if args.limit else catalog["products"]
    country = catalog.get("country_code", "hu")
    captured_on = today_budapest()

    print(f"Árfigyelő – {catalog['shop']} / {catalog['category']} (cc={country})")
    print(f"Dátum: {captured_on} | Címek: {len(games)}")

    store = None if args.dry_run else get_store()
    print(f"Tároló: {store.name if store else '— (dry run)'}")

    results = []
    for i, game in enumerate(games, 1):
        print(f"[{i}/{len(games)}] {game['name']}")
        price = fetch_with_retry(game["appid"], country)
        results.append((game, price))

        if price:
            major = price["price"] / 100
            extra = ""
            if price["list_price"]:
                extra = f" (listaár {price['list_price'] / 100:.2f}, -{price['discount_percent']}%)"
            print(f"    {major:.2f} {price['currency']}{extra}")
        else:
            print("    SIKERTELEN")

        if i < len(games):
            time.sleep(DELAY_S)

    ok = [(g, p) for g, p in results if p]
    print(f"\nLekérve: {len(ok)}/{len(results)}")

    if store:
        rows = [
            ProductRow(
                slug=g["slug"],
                name=g["name"],
                url=store_url(g["appid"]),
                brand=None,
                category=catalog["category"],
                shop=catalog["shop"],
                currency=(p or {}).get("currency", "EUR"),
                image_url=(p or {}).get("image_url"),
            )
            for g, p in results
        ]
        ids = store.sync_products(rows)

        for game, price in ok:
            store.upsert_snapshot(
                SnapshotRow(
                    product_id=ids[game["slug"]],
                    price=price["price"],
                    list_price=price["list_price"],
                    availability=price["availability"],
                    captured_on=captured_on,
                    source=price["source"],
                )
            )
        store.finish()
        print("Mentve.")

    if results and len(ok) < len(results) / 2:
        print("! A címek több mint fele sikertelen – nézd meg a válaszokat.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
