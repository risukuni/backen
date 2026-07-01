"""Globus Baumarkt: Browser-basierter Checker (laeuft NUR in GitHub Actions).

Globus liefert Produktdaten nur ueber FACT-Finder mit client-seitigem
Request-Signing (siehe README) -> echter (headless) Browser noetig. Die volle
Ergebnisliste laesst sich nicht zuverlaessig ausloesen, die Autocomplete-
Vorschlaege (suggest, Channel GlobusBaumarktLive) aber schon -- und die
enthalten Produkte inkl. Deeplink (/p/<slug>-<artikelnr>/).

Signal: Erscheint die PortaSplit (Artikelnummer im Deeplink) unter den
Produkt-Vorschlaegen -> verfuegbar. Liefern die Vorschlaege Produkte, aber
nicht die PortaSplit -> ausverkauft. Gar keine Produkt-Vorschlaege -> None.

Konfiguration (config.json -> retailers.globus):
  "products": { "8000": "0694600251", "12000": "0694600235" }   # Artikelnummern
  "query":    "midea portasplit"   # optional
"""
from __future__ import annotations

import json
import re

from ..models import Product, StoreAvailability
from .base import Retailer

HOME = "https://www.globus-baumarkt.de/"
PROD_CHANNEL = "GlobusBaumarktLive"
DEFAULT_QUERY = "midea portasplit"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
COOKIE_SELECTORS = [
    "[data-cookiefirst-action='accept']",
    "button#cookiefirst-accept",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')",
]
FOCUS_SEARCH = (
    "()=>{let f=null;function w(r){const i=r.querySelector&&"
    "r.querySelector(\"input[type=search],input[name=search]\");if(i&&!f)f=i;"
    "r.querySelectorAll&&r.querySelectorAll('*').forEach(el=>{if(el.shadowRoot)w(el.shadowRoot);});}"
    "w(document);if(f){f.focus();try{f.value='';}catch(e){}return true;}return false;}"
)

AVAIL_HINTS = ("availab", "verfueg", "verfüg", "bestand", "instock", "lieferbar", "stock")
AVAIL_TRUE = ("true", "1", "ja", "yes", "verfügbar", "verfuegbar", "lieferbar", "instock")
AVAIL_FALSE = ("false", "0", "nein", "no", "nicht verfügbar", "nicht verfuegbar",
               "ausverkauft", "nicht lieferbar", "soldout", "outofstock")


class Globus(Retailer):
    name = "globus"

    def check(self, products: list[Product]) -> list[StoreAvailability]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:  # noqa: BLE001
            print("[globus] playwright nicht installiert -> uebersprungen")
            return []

        art_by_key = self.cfg.get("products") or {}
        wanted = {str(art_by_key[p.key]): p for p in products if art_by_key.get(p.key)}
        if not wanted:
            print("[globus] keine Artikelnummern konfiguriert")
            return []
        query = self.cfg.get("query") or DEFAULT_QUERY

        ff: list[tuple[str, dict]] = []
        diag: list[str] = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                )
                ctx = browser.new_context(locale="de-DE", user_agent=UA)
                page = ctx.new_page()

                def on_response(resp):
                    if "fact-finder.de" in resp.url:
                        try:
                            ff.append((resp.url, resp.json()))
                        except Exception:  # noqa: BLE001
                            pass

                page.on("response", on_response)
                page.goto(HOME, wait_until="domcontentloaded", timeout=45000)

                clicked = False
                for sel in COOKIE_SELECTORS:
                    try:
                        page.click(sel, timeout=3000)
                        clicked = True
                        break
                    except Exception:  # noqa: BLE001
                        continue
                diag.append(f"cookie={clicked}")
                page.wait_for_timeout(1500)

                found = page.evaluate(FOCUS_SEARCH)
                diag.append(f"suchfeld={found}")
                if found:
                    # langsam tippen -> je Zeichen feuert ein suggest (Produkte sammeln sich)
                    page.keyboard.type(query, delay=140)
                    page.wait_for_timeout(5000)
                browser.close()
        except Exception as exc:  # noqa: BLE001
            diag.append(f"fehler={str(exc)[:80]}")

        print(f"[globus] Diagnose: {'; '.join(diag)} | FF-Antworten={len(ff)}")

        prods = _extract_products(ff)
        print(f"[globus] Produkt-Vorschlaege gefunden: {len(prods)}")
        for p in prods[:10]:
            print(f"[globus]   - {p['name'][:42]:42} {p['deeplink'][-46:]}")

        results: list[StoreAvailability] = []
        for art, product in wanted.items():
            match = next(
                (p for p in prods if art in p["deeplink"] or art in json.dumps(p["rec"], ensure_ascii=False)),
                None,
            )
            if match is not None:
                avail, price = self._interpret(match["rec"])
                if avail is None:
                    avail = True  # erscheint unter Produkten -> verfuegbar
                print(f"[globus] {product.key}: PortaSplit gelistet -> available={avail} price={price}")
            elif prods:
                avail, price = False, None
                print(f"[globus] {product.key}: Produkte da, PortaSplit fehlt -> nicht verfuegbar")
            else:
                avail, price = None, None
                print(f"[globus] {product.key}: keine Produkt-Vorschlaege -> unbekannt")
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
        return results

    @staticmethod
    def _interpret(rec):
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
                if sval in AVAIL_TRUE:
                    avail = True
                elif sval in AVAIL_FALSE:
                    avail = False
                elif sval.isdigit():
                    avail = int(sval) > 0
        return avail, price


def _extract_products(ff) -> list[dict]:
    """Produkt-Vorschlaege (mit Deeplink /p/...) aus allen suggest-Antworten ziehen."""
    by_link: dict[str, dict] = {}
    for url, body in ff:
        if PROD_CHANNEL not in url or not isinstance(body, dict):
            continue
        suggs = body.get("suggestions")
        if not isinstance(suggs, list):
            continue
        for sg in suggs:
            flat = _flatten(sg)
            deeplink = next((str(v) for v in flat.values() if isinstance(v, str) and "/p/" in v), None)
            if not deeplink:
                continue
            name = next(
                (str(v) for k, v in flat.items()
                 if isinstance(v, str) and any(t in k.lower() for t in ("name", "label", "title"))),
                "?",
            )
            by_link[deeplink] = {"name": name, "deeplink": deeplink, "rec": sg}
    return list(by_link.values())


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
