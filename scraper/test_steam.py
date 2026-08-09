"""A Steam appdetails-feldolgozás tesztjei – hálózat nélkül.

    python test_steam.py

A fixture-ök valódi, 2026-08-10-én mentett válaszok, a használt mezőkre
szűkítve.
"""

from __future__ import annotations

import sys

from steam_extract import SteamError, parse_appdetails, store_url

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: várt {expected!r}, kapott {actual!r}")
        failures.append(label)


def expect_error(label: str, payload: dict, appid: int) -> None:
    try:
        parse_appdetails(payload, appid)
    except SteamError:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: SteamError-t vártam")
        failures.append(label)


# Valódi válasz: akciós cím (Cyberpunk 2077, -70%).
DISCOUNTED = {
    "1091500": {
        "success": True,
        "data": {
            "name": "Cyberpunk 2077",
            "is_free": False,
            "header_image": "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1091500/header.jpg",
            "price_overview": {
                "currency": "EUR",
                "initial": 5999,
                "final": 1799,
                "discount_percent": 70,
                "final_formatted": "17,99€",
            },
        },
    }
}

# Valódi válasz: teljes áras cím.
FULL_PRICE = {
    "1174180": {
        "success": True,
        "data": {
            "name": "Red Dead Redemption 2",
            "is_free": False,
            "header_image": "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1174180/header.jpg",
            "price_overview": {
                "currency": "EUR",
                "initial": 5999,
                "final": 5999,
                "discount_percent": 0,
                "final_formatted": "59,99€",
            },
        },
    }
}


def test_discounted() -> None:
    print("Akciós cím")
    r = parse_appdetails(DISCOUNTED, 1091500)
    check("price", r["price"], 1799)
    check("list_price", r["list_price"], 5999)
    check("currency", r["currency"], "EUR")
    check("discount_percent", r["discount_percent"], 70)
    check("availability", r["availability"], "InStock")
    check("source", r["source"], "steam-api")
    check("name", r["name"], "Cyberpunk 2077")
    check("image_url kitöltve", bool(r["image_url"]), True)


def test_full_price() -> None:
    print("\nTeljes áras cím")
    r = parse_appdetails(FULL_PRICE, 1174180)
    check("price", r["price"], 5999)
    # initial == final -> nincs valódi kedvezmény, ne villantsunk áthúzott árat.
    check("list_price None", r["list_price"], None)
    check("discount_percent", r["discount_percent"], 0)


def test_errors() -> None:
    print("\nHibatűrés")
    expect_error("success=false", {"1": {"success": False}}, 1)
    expect_error("hiányzó appid kulcs", {"999": {"success": True}}, 1)
    expect_error("hiányzó data", {"1": {"success": True}}, 1)
    expect_error(
        "ingyenes cím",
        {"1": {"success": True, "data": {"name": "Dota 2", "is_free": True}}},
        1,
    )
    expect_error(
        "nincs price_overview (régiózár)",
        {"1": {"success": True, "data": {"name": "X", "is_free": False}}},
        1,
    )
    expect_error(
        "érvénytelen final",
        {
            "1": {
                "success": True,
                "data": {"name": "X", "price_overview": {"final": None, "currency": "EUR"}},
            }
        },
        1,
    )
    check("üres válasz", isinstance({}, dict), True)


def test_store_url() -> None:
    print("\nBolt-URL")
    check("store_url", store_url(1091500), "https://store.steampowered.com/app/1091500/")


if __name__ == "__main__":
    test_discounted()
    test_full_price()
    test_errors()
    test_store_url()

    print()
    if failures:
        print(f"{len(failures)} teszt bukott: {', '.join(failures)}")
        sys.exit(1)
    print("Minden teszt zöld.")
