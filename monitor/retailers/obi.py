"""OBI: Online-Signal + echte Markt-Verfuegbarkeit pro Filiale im Umkreis.

Datenquellen (oeffentlich, reverse-engineered von obi.de):
  * Produkt-API:  GET https://www.obi.de/api/pdp/v1/products/{sku}
                  -> buyboxStates.homeDeliveryAvailable / reserveAndCollectAvailable
  * Pro Markt:    GET .../products/{sku}?storeId={storeId}
                  -> buyboxStates.roPo.available  (True == im Markt abholbar)
  * Markt-IDs:    data/obi_stores.json (einmalig via tools/build_obi_stores.py).

Die Markt-Abfragen laufen PARALLEL (ThreadPool), damit ein Check schnell ist.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..geo import geocode_plz, haversine_km
from ..models import Product, StoreAvailability
from ..web import make_session
from .base import Retailer

PRODUCT_API = "https://www.obi.de/api/pdp/v1/products/{sku}"
STORE_CACHE = Path("data/obi_stores.json")
MAX_WORKERS = 8


class Obi(Retailer):
    name = "obi"

    @staticmethod
    def _sku(url: str) -> str:
        m = re.search(r"/p/(\d+)", url)
        return m.group(1) if m else ""

    def _stores_in_radius(self) -> list[tuple[float, dict]]:
        if not STORE_CACHE.exists():
            print("[obi] data/obi_stores.json fehlt -> tools/build_obi_stores.py ausfuehren")
            return []
        try:
            stores = json.loads(STORE_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        coords = geocode_plz(self.plz, self.session)
        if not coords:
            return []
        lat0, lon0 = coords
        out = []
        for st in stores:
            try:
                d = haversine_km(lat0, lon0, float(st["lat"]), float(st["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
            if d <= self.radius_km:
                out.append((round(d, 1), st))
        out.sort(key=lambda x: x[0])
        return out

    def _product_json(self, session, sku: str, store_id: str | None = None):
        params = {"storeId": store_id} if store_id else None
        try:
            r = session.get(
                PRODUCT_API.format(sku=sku),
                params=params,
                headers={"Accept": "application/json"},
                timeout=20,
            )
            if r.status_code != 200:
                return None
            return r.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[obi] API {sku} store={store_id}: {exc}")
            return None

    @staticmethod
    def _store_available(data) -> bool | None:
        ropo = ((data or {}).get("buyboxStates", {}) or {}).get("roPo", {}) or {}
        if ropo.get("showAvailability"):
            return bool(ropo.get("available"))
        return None

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        results: list[StoreAvailability] = []
        stores = self._stores_in_radius()
        if stores:
            print(f"[obi] {len(stores)} Maerkte im {self.radius_km:.0f}-km-Umkreis")
        for p in products:
            url = self.product_url(p.key)
            sku = self._sku(url)
            if not sku:
                continue
            base = self._product_json(self.session, sku)
            if base is None:
                print(f"[obi] {p.key}: Produkt-API nicht erreichbar")
                continue
            bb = base.get("buyboxStates", {}) or {}
            results.append(
                StoreAvailability(
                    retailer=self.name,
                    product_key=p.key,
                    product_label=p.label,
                    store_id="online",
                    store_name="OBI Online",
                    available=bool(bb.get("homeDeliveryAvailable")),
                    url=url,
                )
            )
            if not stores:
                continue

            def worker(item, sku=sku):
                dist, st = item
                session = make_session()  # eigene Session je Thread
                data = self._product_json(session, sku, st["storeId"])
                return dist, st, data

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                rows = list(ex.map(worker, stores))

            for dist, st, data in rows:
                results.append(
                    StoreAvailability(
                        retailer=self.name,
                        product_key=p.key,
                        product_label=p.label,
                        store_id=st["storeId"],
                        store_name=st.get("name", ""),
                        available=self._store_available(data),
                        distance_km=dist,
                        url=url,
                    )
                )
        return results
