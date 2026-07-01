"""Hornbach: Relisting-Watcher.

Die PortaSplit-Klimaanlage ist bei Hornbach derzeit delistet (nur Zubehoer
gelistet) -> es gibt keinen Filial-Bestand zu messen. Sinnvoller Alarm:
"PortaSplit ist bei Hornbach wieder gelistet". Wir prüfen die Midea-Klima-
Kategorie und melden, sobald ein echtes Klimagerät (8.000/12.000 BTU,
kein Zubehoer) auftaucht.

Sobald sie zurueck ist, zeigt Hornbach "Stück im Markt" pro Filiale; die
Filial-Abfrage laesst sich dann mit dem dann gueltigen articleId ergaenzen.
"""
from __future__ import annotations

import re

from ..models import Product, StoreAvailability
from .base import Retailer
from ..web import get

CATEGORY = "https://www.hornbach.de/c/heizen-klima-lueftung/klimageraete/S1030/f/Marke=Midea"
ACCESSORY_WORDS = ("halterung", "abdichtung", "schlauch", "fernbedienung", "ersatz", "filter", "reiniger")
BTU_PATTERNS = {"12000": re.compile(r"12[\-\s]?000"), "8000": re.compile(r"8[\-\s]?000")}


class Hornbach(Retailer):
    name = "hornbach"

    def _listed_ac(self) -> list[tuple[str, str]]:
        try:
            t = get(self.session, CATEGORY).text
        except Exception as exc:  # noqa: BLE001
            print(f"[hornbach] Kategorie nicht erreichbar: {exc}")
            return []
        links = set(re.findall(r"/p/([a-z0-9\-]+)/(\d{6,9})", t))
        ac = []
        for slug, aid in links:
            if "portasplit" not in slug and "porta-split" not in slug:
                continue
            if any(w in slug for w in ACCESSORY_WORDS):
                continue
            ac.append((slug, aid))
        return ac

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        ac = self._listed_ac()
        results = []
        for p in products:
            pat = BTU_PATTERNS.get(p.key)
            match = None
            if pat:
                for slug, aid in ac:
                    if pat.search(slug):
                        match = (slug, aid)
                        break
            if match:
                slug, aid = match
                url = f"https://www.hornbach.de/p/{slug}/{aid}/"
                avail = True
            else:
                url = CATEGORY
                avail = False
            results.append(
                StoreAvailability(
                    retailer=self.name,
                    product_key=p.key,
                    product_label=p.label,
                    store_id="online",
                    store_name="Hornbach (gelistet)",
                    available=avail,
                    url=url,
                )
            )
        return results
