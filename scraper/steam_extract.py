"""A Steam appdetails válaszának feldolgozása – hálózat nélkül.

Ugyanaz a mintázat, mint az `extract.py`-nál: a parse-olás tiszta függvény,
hogy mentett válaszokon tesztelhető legyen. Lásd `test_steam.py`.

A Steam árakat a legkisebb egységben adja (cent), ezért minden árat
`price_minor` néven, egész számként tárolunk — a formázás a frontend dolga.
"""

from __future__ import annotations

from typing import Any, TypedDict


class SteamPrice(TypedDict):
    appid: int
    name: str
    price: int  # legkisebb egységben (cent), a DB-ben is így
    list_price: int | None  # akció előtti ár, ha van kedvezmény
    currency: str
    discount_percent: int
    availability: str
    image_url: str | None
    source: str


class SteamError(Exception):
    """A Steam nem adott értékelhető választ erre az appid-re."""


def parse_appdetails(payload: dict[str, Any], appid: int) -> SteamPrice:
    """A `/api/appdetails?appids=X` válaszából csinál egy árrekordot.

    Raises:
        SteamError: ha a válasz sikertelen, vagy nincs benne ár.
    """
    entry = payload.get(str(appid))
    if not isinstance(entry, dict):
        raise SteamError(f"nincs {appid} kulcs a válaszban")
    if not entry.get("success"):
        raise SteamError("success=false (ismeretlen vagy régiózárt appid)")

    data = entry.get("data")
    if not isinstance(data, dict):
        raise SteamError("hiányzó data mező")

    name = data.get("name") or ""

    # Ingyenes játékok: nincs price_overview. Ez nem hiba, csak nem árkövethető.
    if data.get("is_free"):
        raise SteamError("ingyenes cím, nincs követhető ár")

    price = data.get("price_overview")
    if not isinstance(price, dict):
        raise SteamError("hiányzó price_overview (ingyenes, vagy nem elérhető a régióban)")

    final = price.get("final")
    initial = price.get("initial")
    if not isinstance(final, int):
        raise SteamError(f"érvénytelen 'final' ár: {final!r}")

    discount = price.get("discount_percent") or 0

    return {
        "appid": appid,
        "name": name,
        "price": final,
        # Csak akkor listaár, ha tényleg magasabb – így a frontend
        # kedvezmény-ága nem villog fals pozitívtól.
        "list_price": initial if isinstance(initial, int) and initial > final else None,
        "currency": price.get("currency") or "EUR",
        "discount_percent": int(discount),
        # A Steamen a boltban lévő cím mindig megvásárolható.
        "availability": "InStock",
        "image_url": data.get("header_image"),
        "source": "steam-api",
    }


def store_url(appid: int) -> str:
    return f"https://store.steampowered.com/app/{appid}/"
