"""Tiszta árkiolvasó logika – böngésző nélkül.

Szándékosan külön van a `scrape.py`-tól: ezek a függvények csak stringeket
kapnak, tehát Playwright (és futó böngésző) nélkül tesztelhetők. A layout-
változásokat itt kell elkapni, nem éles cron-futásban.

Lásd: `test_extract.py` – valódi, az Alza.hu-ról mentett JSON-LD fixture-ökön fut.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

# A számot elkapjuk akkor is, ha sima szóköz, nbsp, keskeny nbsp vagy pont
# a ezres elválasztó ("134 990 Ft", "134.990 Ft", "134 990 Ft").
PRICE_RE = re.compile(r"(\d[\d\s  .]*)")


class Extracted(TypedDict):
    price: int
    list_price: int | None
    availability: str | None
    name: str | None
    brand: str | None
    image_url: str | None
    source: str


def parse_price(raw: Any) -> int | None:
    """'134 990 Ft' / 134990 / '134990.0' -> 134990. Nem szám esetén None."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw))

    match = PRICE_RE.search(str(raw))
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    return int(digits) if digits else None


def find_product_node(data: Any) -> dict | None:
    """Rekurzívan megkeresi a schema.org Product node-ot a JSON-LD-ben.

    Az Alza egy `@graph` tömbben adja a BreadcrumbList / Organization /
    WebSite / WebPage / Product node-okat, de más shopok másképp – ezért
    a bejárás általános.
    """
    if isinstance(data, list):
        for item in data:
            found = find_product_node(item)
            if found:
                return found
        return None

    if isinstance(data, dict):
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


def extract_from_jsonld(blocks: list[str]) -> Extracted | None:
    """Végigmegy a `<script type="application/ld+json">` blokkok tartalmán.

    Az első olyan Product node nyer, amiből tényleg kijön egy ár – így a
    hibás/üres JSON-LD blokk nem blokkolja a kiolvasást.
    """
    for block in blocks:
        try:
            node = find_product_node(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
        if not node:
            continue

        offers = node.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            continue

        price = parse_price(offers.get("price"))
        if price is None:
            continue

        # Áthúzott ár: a priceSpecification tömbben, StrikethroughPrice típussal.
        list_price = None
        specs = offers.get("priceSpecification") or []
        if isinstance(specs, dict):
            specs = [specs]
        for spec in specs:
            if isinstance(spec, dict) and "StrikethroughPrice" in str(
                spec.get("priceType", "")
            ):
                list_price = parse_price(spec.get("price"))

        images = node.get("image") or []
        if not isinstance(images, list):
            images = [images]
        image_url = None
        if images:
            first = images[0]
            image_url = first.get("url") if isinstance(first, dict) else str(first)

        brand = node.get("brand")
        brand_name = brand.get("name") if isinstance(brand, dict) else brand

        # "https://schema.org/InStock" -> "InStock"
        availability = str(offers.get("availability") or "").rsplit("/", 1)[-1] or None

        return {
            "price": price,
            # Ha a listaár megegyezik az árral, nincs valódi kedvezmény.
            "list_price": list_price if list_price and list_price > price else None,
            "availability": availability,
            "name": node.get("name"),
            "brand": brand_name if isinstance(brand_name, str) else None,
            "image_url": image_url,
            "source": "jsonld",
        }

    return None


def extract_from_price_text(text: str | None) -> Extracted | None:
    """DOM-fallback: egy árnak szánt szövegcsomóból csinál számot."""
    price = parse_price(text)
    if price is None:
        return None
    return {
        "price": price,
        "list_price": None,
        "availability": None,
        "name": None,
        "brand": None,
        "image_url": None,
        "source": "dom",
    }
