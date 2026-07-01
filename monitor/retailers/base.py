"""Basis-Klassen fuer Baumarkt-Module.

Jede Kette ist ein eigenes Modul mit einer Retailer-Unterklasse. So bleibt das
System wartbar: aendert eine Kette ihre Seite/API, ist nur ihr Modul betroffen.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Optional

from ..models import Product, StoreAvailability
from ..web import get, make_session

# schema.org availability -> (verfuegbar?, Klartext)
SCHEMA_AVAILABILITY = {
    "instock": True,
    "instoreonly": True,
    "onlineonly": True,
    "limitedavailability": True,
    "preorder": True,
    "backorder": False,
    "outofstock": False,
    "soldout": False,
    "discontinued": False,
}


class Retailer(ABC):
    name: str = "base"

    def __init__(self, cfg: dict, plz: str, radius_km: float):
        self.cfg = cfg
        self.plz = plz
        self.radius_km = radius_km
        self.session = make_session()

    def product_url(self, product_key: str) -> str:
        return (self.cfg.get("products") or {}).get(product_key, "") or ""

    @abstractmethod
    def check(self, products: list[Product]) -> list[StoreAvailability]:
        ...


class SchemaOrgRetailer(Retailer):
    """Liest die server-seitige schema.org-Verfuegbarkeit von der Produktseite.

    Verlaesslich fuer Ketten, die <script type="application/ld+json"> mit
    offers.availability ausliefern (z. B. Bauhaus, OBI). Liefert ein
    Online-/Liefer-Signal (store_id = "online").
    """

    def parse_availability(self, html: str) -> Optional[bool]:
        for raw in re.findall(
            r'"availability"\s*:\s*"([^"]+)"', html, flags=re.IGNORECASE
        ):
            token = raw.rsplit("/", 1)[-1].strip().lower()
            if token in SCHEMA_AVAILABILITY:
                return SCHEMA_AVAILABILITY[token]
        return None

    def parse_price(self, html: str) -> Optional[float]:
        m = re.search(r'"price"\s*:\s*"?(\d+[.,]?\d*)"?', html)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                return None
        return None

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        out: list[StoreAvailability] = []
        for p in products:
            url = self.product_url(p.key)
            if not url:
                continue
            try:
                resp = get(self.session, url)
            except Exception as exc:  # noqa: BLE001
                print(f"[{self.name}] {p.key}: Abruf fehlgeschlagen: {exc}")
                continue
            if resp.status_code != 200:
                print(f"[{self.name}] {p.key}: HTTP {resp.status_code}")
                out.append(self._unknown(p, url))
                continue
            avail = self.parse_availability(resp.text)
            out.append(
                StoreAvailability(
                    retailer=self.name,
                    product_key=p.key,
                    product_label=p.label,
                    store_id="online",
                    store_name=f"{self.name} Online",
                    available=avail,
                    price=self.parse_price(resp.text),
                    url=url,
                )
            )
        return out

    def _unknown(self, p: Product, url: str) -> StoreAvailability:
        return StoreAvailability(
            retailer=self.name,
            product_key=p.key,
            product_label=p.label,
            store_id="online",
            store_name=f"{self.name} Online",
            available=None,
            url=url,
        )
