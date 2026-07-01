"""Globus Baumarkt: Browser-basierter Checker (laeuft NUR in GitHub Actions).

Globus liefert Produktdaten nur ueber FACT-Finder mit client-seitigem
Request-Signing (siehe README) -> echter (headless) Browser noetig.

Signal: taucht die PortaSplit (per Artikelnummer / Deeplink) in den
FACT-Finder-PRODUKT-Treffern (Channel GlobusBaumarktLive) auf, gilt sie als
verfuegbar. Ausverkaufte Artikel filtert Globus aus den Ergebnissen -> tauchen
sie NICHT auf, obwohl die Produkt-Suche Treffer lieferte, gilt das als nicht
verfuegbar. Feuerte gar keine Produkt-Suche -> None (kein Alarm).

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

                # 1) Suche ueber das Suchfeld + Enter
                found = page.evaluate(FOCUS_SEARCH)
                diag.append(f"suchfeld={found}")
                if found:
                    page.keyboard.type(query, delay=90)
                    page.wait_for_timeout(3000)
                    try:
                        page.keyboard.press("Enter")
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:  # noqa: BLE001
                        pass
                    diag.append(f"url={page.url.split('://')[-1][:45]}")
                    self._scroll(page)

                # 2) Direkter Aufruf der Suchergebnis-Seite (loest Produkt-Suche aus)
                try:
                    page.goto(
                        HOME + "search?search=" + query.replace(" ", "%20"),
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    try:
                        page.wait_for_selector("ff-record-list", timeout=8000)
                    except Exception:  # noqa: BLE001
                        pass
                    self._scroll(page)
                except Exception as exc:  # noqa: BLE001
                    diag.append(f"nav2={str(exc)[:40]}")

                browser.close()
        except Exception as exc:  # noqa: BLE001
            diag.append(f"fehler={str(exc)[:80]}")

        # ---- Diagnose ins Log ----
        print(f"[globus] Diagnose: {'; '.join(diag)}")
        print(f"[globus] FF-Antworten: {len(ff)}")
        product_search_hits = 0
        seen = set()
        for url, body in ff:
            channel = url.rsplit("/", 1)[-1].split("?", 1)[0]
            kind = "suggest" if "/suggest/" in url else ("search" if "/search/" in url else "other")
            cnt = _count_items(body)
            ac = any(a in json.dumps(body, ensure_ascii=False) for a in wanted)
            if channel == PROD_CHANNEL and kind == "search":
                product_search_hits += cnt
            sig = (channel, kind, cnt, ac)
            if sig not in seen:
                seen.add(sig)
                print(f"[globus]   {kind} {channel}: {cnt} Eintraege, PortaSplit-Treffer={ac}")
        print(f"[globus] Produkt-Suchtreffer gesamt: {product_search_hits}")

        results: list[StoreAvailability] = []
        for art, product in wanted.items():
            rec = None
            for _, body in ff:
                rec = _search_dict_for_article(body, art)
                if rec is not None:
                    break
            if rec is not None:
                fields = list(_flatten(rec).keys())
                print(f"[globus] {product.key}: gefunden. Felder={fields[:25]}")
                avail, price = self._interpret(rec)
                if avail is None:
                    avail = True  # taucht in Treffern auf -> verfuegbar
            elif product_search_hits > 0:
                # Produkt-Suche lieferte Treffer, aber ohne dieses Geraet -> ausverkauft
                print(f"[globus] {product.key}: nicht in Produkt-Treffern -> nicht verfuegbar")
                avail, price = False, None
            else:
                # keine echte Produkt-Suche zustande gekommen -> unbekannt
                print(f"[globus] {product.key}: keine Produkt-Suche -> unbekannt")
                avail, price = None, None
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
    def _scroll(page):
        for _ in range(3):
            try:
                page.mouse.wheel(0, 1600)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2200)

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


def _count_items(body) -> int:
    total = 0
    for key in ("hits", "records", "suggestions"):
        v = body.get(key) if isinstance(body, dict) else None
        if isinstance(v, list):
            total += len(v)
    return total


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


def _has_signal(d) -> bool:
    keys = " ".join(_flatten(d).keys()).lower()
    return any(kw in keys for kw in ("price", "avail", "verfueg", "verfüg", "stock", "bestand", "deeplink"))


def _search_dict_for_article(obj, article: str):
    candidates: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            s = json.dumps(o, ensure_ascii=False)
            if article in s:
                if len(s) < 8000:
                    candidates.append(o)
                for v in o.values():
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    if not candidates:
        return None
    with_signal = [d for d in candidates if _has_signal(d)]
    pool = with_signal or candidates
    return min(pool, key=lambda d: len(json.dumps(d, ensure_ascii=False)))
