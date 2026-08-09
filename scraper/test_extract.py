"""Az árkiolvasó logika tesztjei – böngésző nélkül futnak.

    python test_extract.py

Szándékosan nincs pytest-függőség: egy fájl, egy parancs, nulla setup. A cél
az, hogy a layoutváltozás vagy a saját regressziónk itt bukjon el, ne egy
éles cron-futásban 15 sikertelen lekéréssel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from extract import extract_from_jsonld, extract_from_price_text, parse_price

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "alza_products.json"

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: várt {expected!r}, kapott {actual!r}")
        failures.append(label)


# ---------------------------------------------------------------------------
def test_parse_price() -> None:
    print("parse_price")
    cases = [
        ("134 990 Ft", 134990),          # sima szóköz
        ("134 990 Ft", 134990),     # nbsp – így jön a DOM-ból
        ("134 990 Ft", 134990),     # keskeny nbsp
        ("134.990 Ft", 134990),          # pont mint ezres elválasztó
        ("Szuper ár 14 890 Ft Kosárba", 14890),  # körbeszemetelt szöveg
        (17390, 17390),
        (17390.0, 17390),
        ("", None),
        ("Ft", None),
        (None, None),
        (True, None),                     # bool ne csússzon át int-ként
    ]
    for raw, expected in cases:
        check(f"parse_price({raw!r})", parse_price(raw), expected)


def test_fixtures() -> None:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    for case in data["cases"]:
        print(f"\nJSON-LD: {case['name']}")
        result = extract_from_jsonld(case["blocks"])
        if result is None:
            check(case["name"], None, "kiolvasott adat")
            continue
        for field, expected in case["expect"].items():
            check(f"{field}", result[field], expected)
        # A kép- és névmezőnek is meg kell lennie – ezekből lesz a katalógus.
        check("name kitöltve", bool(result["name"]), True)
        check("image_url kitöltve", bool(result["image_url"]), True)


def test_edge_cases() -> None:
    print("\nHibatűrés")
    check("üres lista", extract_from_jsonld([]), None)
    check("hibás JSON", extract_from_jsonld(["{nem json"]), None)
    check(
        "Product ár nélkül",
        extract_from_jsonld(['{"@type":"Product","name":"X"}']),
        None,
    )
    check(
        "hibás blokk után jó blokk",
        (extract_from_jsonld(
            ["{törött", '{"@type":"Product","offers":{"price":9990}}']
        ) or {}).get("price"),
        9990,
    )
    check(
        "offers tömbként",
        (extract_from_jsonld(
            ['{"@type":"Product","offers":[{"price":1290}]}']
        ) or {}).get("price"),
        1290,
    )
    check(
        "@type tömbként",
        (extract_from_jsonld(
            ['{"@type":["Product","Thing"],"offers":{"price":500}}']
        ) or {}).get("price"),
        500,
    )
    check(
        "listaár == ár esetén nincs kedvezmény",
        (extract_from_jsonld([json.dumps({
            "@type": "Product",
            "offers": {
                "price": 1000,
                "priceSpecification": [
                    {"priceType": "https://schema.org/StrikethroughPrice", "price": 1000}
                ],
            },
        })]) or {}).get("list_price"),
        None,
    )
    check("DOM fallback", (extract_from_price_text("31 990 Ft") or {}).get("price"), 31990)
    check("DOM fallback forrásjelölés",
          (extract_from_price_text("31 990 Ft") or {}).get("source"), "dom")
    check("DOM fallback üres szövegen", extract_from_price_text("—"), None)


if __name__ == "__main__":
    test_parse_price()
    test_fixtures()
    test_edge_cases()

    print()
    if failures:
        print(f"{len(failures)} teszt bukott: {', '.join(failures)}")
        sys.exit(1)
    print("Minden teszt zöld.")
