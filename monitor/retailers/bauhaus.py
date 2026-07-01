"""Bauhaus: server-seitige schema.org-Verfuegbarkeit ist verlaesslich.

HTTP zuerst (schnell). Wird geblockt (z. B. HTTP 403 durch Akamai von
GitHub-Actions-IPs), Fallback ueber einen echten Browser (Playwright), der
den Bot-Schutz passiert. Liefert das Online-/Liefersignal (store_id="online").

Status: VERIFIZIERT (Online-/Liefersignal).
TODO: Filial-Verfuegbarkeit pro Fachcentrum im Umkreis ergaenzen.
"""
from __future__ import annotations

from ..browser import fetch_html
from ..models import Product, StoreAvailability
from ..web import get
from .base import SchemaOrgRetailer


class Bauhaus(SchemaOrgRetailer):
    name = "bauhaus"

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        results: list[StoreAvailability] = []
        fallback: list[tuple[Product, str]] = []

        # 1) Schneller Versuch per HTTP
        for p in products:
            url = self.product_url(p.key)
            if not url:
                continue
            avail = price = None
            try:
                r = get(self.session, url)
                if r.status_code == 200:
                    avail = self.parse_availability(r.text)
                    price = self.parse_price(r.text)
                else:
                    print(f"[bauhaus] {p.key}: HTTP {r.status_code} -> Browser-Fallback")
            except Exception as exc:  # noqa: BLE001
                print(f"[bauhaus] {p.key}: {exc} -> Browser-Fallback")
            if avail is None:
                fallback.append((p, url))
            else:
                results.append(self._sa(p, url, avail, price))

        # 2) Fallback ueber Browser fuer geblockte URLs
        if fallback:
            html_by_url = fetch_html([u for _, u in fallback])
            for p, url in fallback:
                html = html_by_url.get(url, "")
                avail = self.parse_availability(html) if html else None
                price = self.parse_price(html) if html else None
                if avail is not None:
                    print(f"[bauhaus] {p.key}: via Browser -> verfuegbar={avail}")
                results.append(self._sa(p, url, avail, price))

        return results

    def _sa(self, p: Product, url: str, avail, price) -> StoreAvailability:
        return StoreAvailability(
            retailer=self.name,
            product_key=p.key,
            product_label=p.label,
            store_id="online",
            store_name="Bauhaus Online",
            available=avail,
            price=price,
            url=url,
        )
