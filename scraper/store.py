"""Adatréteg a scraper mögé.

Két backend, azonos felülettel:

* ``SupabaseStore`` – éles tárolás. Akkor aktiválódik, ha van SUPABASE_URL és
  SUPABASE_SERVICE_ROLE_KEY. Írni csak service_role kulccsal lehet, mert az
  RLS a publikus anon kulcsnak csak SELECT-et enged (lásd supabase/schema.sql).
* ``LocalStore`` – kulcs nélküli fallback. Egyetlen JSON fájlba ír, amit a
  Next.js app is be tud olvasni. Így a projekt Supabase-fiók nélkül is
  végigvihető, és a GitHub Actions is tud commit-back módban működni.

A hívó (scrape.py) nem tudja, melyik van alatta.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

# A lokális JSON-DB a Next.js public mappájában él: így a frontend build
# közben fs-sel be tudja olvasni, Vercelen is a deploy része lesz.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_DB = REPO_ROOT / "web" / "public" / "data" / "db.json"

# Determinisztikus product id-k a lokális módban: ugyanaz a slug mindig ugyanazt
# az uuid-t kapja, így a snapshotok újrafuttatás után is összeérnek.
_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


def product_id_for(slug: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, slug))


@dataclass
class ProductRow:
    slug: str
    name: str
    url: str
    brand: str | None = None
    category: str = "fejhallgato"
    shop: str = "alza.hu"
    currency: str = "HUF"
    image_url: str | None = None
    active: bool = True


@dataclass
class SnapshotRow:
    product_id: str
    price: int | None
    list_price: int | None
    availability: str | None
    captured_on: str  # ISO date
    source: str  # 'jsonld' | 'dom'


class Store(Protocol):
    name: str

    def sync_products(self, products: Iterable[ProductRow]) -> dict[str, str]:
        """Felviszi/frissíti a katalógust, és visszaad egy slug -> product_id mapet."""

    def upsert_snapshot(self, row: SnapshotRow) -> None:
        """Beírja a napi árat. Ugyanarra a (termék, nap) párra idempotens."""

    def finish(self) -> None:
        """Batch-backendek itt írnak lemezre. A többinek no-op."""


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
class SupabaseStore:
    name = "supabase"

    def __init__(self, url: str, service_key: str) -> None:
        from supabase import create_client  # lusta import: csak ha tényleg kell

        self.client = create_client(url, service_key)

    def sync_products(self, products: Iterable[ProductRow]) -> dict[str, str]:
        payload = []
        for p in products:
            row = asdict(p)
            # A DB generálja az id-t, de a slug egyedi -> arra tudunk upsertelni.
            payload.append({k: v for k, v in row.items() if v is not None})

        self.client.table("products").upsert(payload, on_conflict="slug").execute()

        slugs = [p.slug for p in products]
        result = (
            self.client.table("products")
            .select("id, slug")
            .in_("slug", slugs)
            .execute()
        )
        return {r["slug"]: r["id"] for r in result.data}

    def upsert_snapshot(self, row: SnapshotRow) -> None:
        self.client.table("price_snapshots").upsert(
            asdict(row), on_conflict="product_id,captured_on"
        ).execute()

    def finish(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Lokális JSON
# ---------------------------------------------------------------------------
class LocalStore:
    name = "local-json"

    def __init__(self, path: Path = DEFAULT_LOCAL_DB) -> None:
        self.path = path
        self.db: dict[str, Any] = {"products": [], "price_snapshots": []}
        if path.exists():
            try:
                self.db = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Sérült fájl esetén inkább újrakezdjük, mint hogy elhasaljon a cron.
                print(f"  ! {path.name} nem olvasható JSON-ként, új DB-t kezdek")
        self.db.setdefault("products", [])
        self.db.setdefault("price_snapshots", [])

    def sync_products(self, products: Iterable[ProductRow]) -> dict[str, str]:
        by_slug = {p["slug"]: p for p in self.db["products"]}
        mapping: dict[str, str] = {}

        for p in products:
            pid = product_id_for(p.slug)
            mapping[p.slug] = pid
            existing = by_slug.get(p.slug, {})
            merged = {"id": pid, **asdict(p)}
            # Ne írjuk felül a korábban kiszedett képet, ha most nem jött.
            if merged.get("image_url") is None and existing.get("image_url"):
                merged["image_url"] = existing["image_url"]
            merged["created_at"] = existing.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            )
            by_slug[p.slug] = merged

        self.db["products"] = list(by_slug.values())
        return mapping

    def upsert_snapshot(self, row: SnapshotRow) -> None:
        snaps = self.db["price_snapshots"]
        key = (row.product_id, row.captured_on)
        for i, s in enumerate(snaps):
            if (s["product_id"], s["captured_on"]) == key:
                snaps[i] = asdict(row)
                return
        snaps.append(asdict(row))

    def finish(self) -> None:
        self.db["generated_at"] = datetime.now(timezone.utc).isoformat()
        self.db["price_snapshots"].sort(key=lambda s: (s["captured_on"], s["product_id"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.db, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"  → {self.path.relative_to(REPO_ROOT)} frissítve "
              f"({len(self.db['price_snapshots'])} snapshot)")


def get_store() -> Store:
    """Supabase, ha van kulcs; egyébként lokális JSON."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if url and key:
        return SupabaseStore(url, key)

    override = os.environ.get("LOCAL_DB_PATH", "").strip()
    return LocalStore(Path(override) if override else DEFAULT_LOCAL_DB)


def today_budapest() -> str:
    """A snapshot dátuma budapesti nap szerint – a cron UTC-ben fut."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Budapest")).date().isoformat()
    except Exception:
        return date.today().isoformat()
