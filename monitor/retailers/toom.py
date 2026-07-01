"""toom: echte Filial-Verfuegbarkeit (Bestand pro Markt im Umkreis).

Datenquellen (oeffentlich, reverse-engineered von toom.de):
  * Marktliste:  GET  https://api.toom.de/public/api/markets
                 -> 290 Maerkte je mit lat/lon -> Umkreis selbst rechnen.
  * Bestand:     POST https://toom.de/shop/rest/V1/toom/stocks/availability
                 Body: [{"articleId","marketId","deliveryType":"PICKUP","quantity":1}, ...]
                 -> [{"articleId","deliveryType","availableQuantity"}]
                 availableQuantity > 0  ==  im Markt abholbar.

Status: VERIFIZIERT gegen echte Maerkte (Raum Koeln). articleId = letzte
Zahl der Produkt-URL (z. B. .../9350668).
"""
from __future__ import annotations

import json
import re

from ..geo import geocode_plz, haversine_km
from ..models import Product, StoreAvailability
from .base import Retailer

MARKETS_URL = "https://api.toom.de/public/api/markets"
STOCK_URL = "https://toom.de/shop/rest/V1/toom/stocks/availability"
POST_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://toom.de",
    "Referer": "https://toom.de/",
    "X-Requested-With": "XMLHttpRequest",
}


class Toom(Retailer):
    name = "toom"

    @staticmethod
    def _article_id(url: str) -> str:
        m = re.search(r"/(\d{5,9})(?:[/?#]|$)", url)
        return m.group(1) if m else ""

    def _markets_in_radius(self) -> list[tuple[float, dict]]:
        coords = geocode_plz(self.plz, self.session)
        if not coords:
            return []
        lat, lon = coords
        try:
            markets = self.session.get(MARKETS_URL, timeout=25).json().get("markets", [])
        except Exception as exc:  # noqa: BLE001
            print(f"[toom] Marktliste fehlgeschlagen: {exc}")
            return []
        found = []
        for m in markets:
            a = m.get("address", {})
            try:
                d = haversine_km(lat, lon, float(a["latitude"]), float(a["longitude"]))
            except (KeyError, TypeError, ValueError):
                continue
            if d <= self.radius_km:
                found.append((d, m))
        found.sort(key=lambda x: x[0])
        return found

    def _stock_for_market(self, article_ids: list[str], market_id: int) -> dict[str, int]:
        body = [
            {"articleId": a, "marketId": market_id, "deliveryType": "PICKUP", "quantity": 1}
            for a in article_ids
        ]
        try:
            r = self.session.post(
                STOCK_URL, data=json.dumps(body), headers=POST_HEADERS, timeout=25
            )
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[toom] Bestand Markt {market_id} fehlgeschlagen: {exc}")
            return {}
        out = {}
        if isinstance(data, list):
            for item in data:
                aid = str(item.get("articleId", ""))
                qty = item.get("availableQuantity")
                if aid and isinstance(qty, int):
                    out[aid] = qty
        return out

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        results: list[StoreAvailability] = []
        # articleId je Produkt aus der URL
        art_by_product = {}
        for p in products:
            art = self._article_id(self.product_url(p.key))
            if art:
                art_by_product[p.key] = art
        if not art_by_product:
            return results

        markets = self._markets_in_radius()
        if not markets:
            print("[toom] keine Maerkte im Umkreis (oder Geocoding fehlgeschlagen)")
            return results
        print(f"[toom] {len(markets)} Maerkte im {self.radius_km:.0f}-km-Umkreis")

        # Session/Cookies aufwaermen
        try:
            self.session.get("https://toom.de/", timeout=25)
        except Exception:  # noqa: BLE001
            pass

        article_ids = list(art_by_product.values())
        for dist, m in markets:
            qty_by_art = self._stock_for_market(article_ids, m["id"])
            a = m.get("address", {})
            for pkey, art in art_by_product.items():
                if art not in qty_by_art:
                    continue
                qty = qty_by_art[art]
                label = next((p.label for p in products if p.key == pkey), pkey)
                results.append(
                    StoreAvailability(
                        retailer=self.name,
                        product_key=pkey,
                        product_label=label,
                        store_id=str(m["id"]),
                        store_name=m.get("name", ""),
                        available=qty > 0,
                        quantity=qty,
                        distance_km=round(dist, 1),
                        city=a.get("city", ""),
                        url=self.product_url(pkey),
                    )
                )
        return results
