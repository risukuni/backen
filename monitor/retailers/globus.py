"""Globus Baumarkt: Browser-basierter Checker (laeuft NUR in GitHub Actions).

Warum Browser: Globus liefert Produktdaten ausschliesslich ueber FACT-Finder,
das mit client-seitigem Request-Signing geschuetzt ist (siehe README). Direkte
HTTP-Abrufe -> 401. Ein echter (headless) Browser fuehrt das FF-SDK aus, damit
die Signaturen stimmen und FF antwortet.

Ansatz:
  1. Browser oeffnet globus-baumarkt.de, Cookie-Consent bestaetigen.
  2. Pro Produkt die Artikelnummer in die FF-Suche tippen (articleNumberSearch).
  3. ALLE fact-finder.de-JSON-Antworten abfangen; den Datensatz mit der
     Artikelnummer suchen und Verfuegbarkeit/Preis heuristisch bestimmen.
  4. Defensiv: kann die Verfuegbarkeit nicht sicher bestimmt werden -> None
     (kein Alarm). Beim ersten Lauf werden die Feldnamen geloggt, damit die
     Heuristik nachgeschaerft werden kann.

Konfiguration (config.json -> retailers.globus):
  "products": { "8000": "0694600251", "12000": "0694600235" }   # Artikelnummern
"""
from __future__ import annotations

import json
import re

from ..models import Product, StoreAvailability
from .base import Retailer

HOME = "https://www.globus-baumarkt.de/"
COOKIE_ACCEPT = "[data-cookiefirst-action='accept']"

# JS: Suchfeld im Shadow DOM finden und fokussieren
FOCUS_SEARCH = (
    "()=>{let f=null;function w(r){const i=r.querySelector&&"
    "r.querySelector(\"input[type=search],input[name=search]\");if(i&&!f)f=i;"
    "r.querySelectorAll&&r.querySelectorAll('*').forEach(el=>{if(el.shadowRoot)w(el.shadowRoot);});}"
    "w(document);if(f){f.focus();f.value='';return true;}return false;}"
)

# Feldnamen, die auf Verfuegbarkeit/Bestand hindeuten
AVAIL_HINTS = ("availab", "verfueg", "verfüg", "bestand", "instock", "stock", "lieferbar")
UNAVAIL_TOKENS = ("nicht verfüg", "nicht verfueg", "ausverkauft", "nicht lieferbar", "0", "false", "nein", "no")


class Globus(Retailer):
    name = "globus"

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:  # noqa: BLE001
            print("[globus] playwright nicht installiert -> uebersprungen")
            return []

        art_by_key = (self.cfg.get("products") or {})
        wanted = {art_by_key.get(p.key): p for p in products if art_by_key.get(p.key)}
        if not wanted:
            print("[globus] keine Artikelnummern konfiguriert")
            return []

        results: list[StoreAvailability] = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                )
                page = browser.new_page()
                ff_bodies: list[dict] = []

                def on_response(resp):
                    if "fact-finder.de" in resp.url:
                        try:
                            ff_bodies.append(resp.json())
                        except Exception:  # noqa: BLE001
                            pass

                page.on("response", on_response)
                page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.click(COOKIE_ACCEPT, timeout=6000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(1500)

                for art, product in wanted.items():
                    ff_bodies.clear()
                    ok = page.evaluate(FOCUS_SEARCH)
                    if not ok:
                        print("[globus] Suchfeld nicht gefunden")
                        continue
                    page.keyboard.type(str(art), delay=90)
                    page.wait_for_timeout(6000)
                    rec = self._find_record(ff_bodies, str(art))
                    avail, price = self._interpret(rec, str(art))
                    if rec is None:
                        print(f"[globus] {product.key}: Artikel {art} nicht in FF-Antworten gefunden")
                    else:
                        print(f"[globus] {product.key}: Feldnamen={list(_flatten(rec).keys())[:25]}")
                    results.append(
                        StoreAvailability(
                            retailer=self.name,
                            product_key=product.key,
                            product_label=product.label,
                            store_id="online",
                            store_name="Globus",
                            available=avail,
                            price=price,
                            url=HOME,
                        )
                    )
                browser.close()
        except Exception as exc:  # noqa: BLE001
            print(f"[globus] Browser-Fehler: {exc}")
        return results

    @staticmethod
    def _find_record(bodies: list[dict], article: str):
        """Sucht in allen FF-Antworten den Datensatz mit der Artikelnummer."""
        for body in bodies:
            hit = _search_dict_for_article(body, article)
            if hit is not None:
                return hit
        return None

    @staticmethod
    def _interpret(rec, article: str):
        """(available, price) heuristisch aus dem Datensatz bestimmen. None = unsicher."""
        if rec is None:
            return None, None
        flat = _flatten(rec)
        price = None
        for k, v in flat.items():
            if "price" in k.lower():
                m = re.search(r"\d+[.,]?\d*", str(v))
                if m:
                    try:
                        price = float(m.group(0).replace(",", "."))
                        break
                    except ValueError:
                        pass
        avail = None
        for k, v in flat.items():
            if any(h in k.lower() for h in AVAIL_HINTS):
                sval = str(v).strip().lower()
                if sval in ("true", "1", "ja", "yes", "verfügbar", "verfuegbar", "lieferbar"):
                    avail = True
                elif sval in UNAVAIL_TOKENS:
                    avail = False
                elif sval.isdigit():
                    avail = int(sval) > 0
        return avail, price


def _flatten(obj, prefix="", out=None):
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}{k}.", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20]):
            _flatten(v, f"{prefix}{i}.", out)
    else:
        out[prefix.rstrip(".")] = obj
    return out


def _search_dict_for_article(obj, article: str):
    """Findet das kleinste dict, das die Artikelnummer enthaelt (der Produkt-Record)."""
    if isinstance(obj, dict):
        s = json.dumps(obj, ensure_ascii=False)
        if article in s:
            # tiefer suchen nach einem spezifischeren Teil-Record
            for v in obj.values():
                deeper = _search_dict_for_article(v, article)
                if deeper is not None:
                    return deeper
            if len(s) < 4000:
                return obj
    elif isinstance(obj, list):
        for v in obj:
            deeper = _search_dict_for_article(v, article)
            if deeper is not None:
                return deeper
    return None
