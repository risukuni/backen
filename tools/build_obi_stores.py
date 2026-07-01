#!/usr/bin/env python3
"""Einmal-Builder: erzeugt data/obi_stores.json (storeId + Koordinaten je OBI-Markt
im Umkreis der konfigurierten PLZ).

OBI identifiziert Maerkte per storeId, die nur auf der jeweiligen Marktseite steht.
Dieser Builder holt die Marktuebersicht, filtert auf PLZ-Umkreis (+ Puffer) und
liest je Markt die storeId aus. Einmal laufen lassen; bei PLZ-Wechsel erneut.

Aufruf:  python tools/build_obi_stores.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor import config as config_mod  # noqa: E402
from monitor.geo import geocode_plz, haversine_km  # noqa: E402
from monitor.web import make_session  # noqa: E402

OVERVIEW = "https://www.obi.de/markt"
BUFFER_KM = 25  # etwas groesser als der Radius, damit kleine PLZ-Aenderungen passen


def _devalue(html: str):
    m = re.search(r'id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.S)
    return json.loads(m.group(1)) if m else None


def _resolve(arr, i, depth=0):
    if not isinstance(i, int) or i < 0 or i >= len(arr) or depth > 6:
        return i
    v = arr[i]
    if isinstance(v, dict):
        return {k: _resolve(arr, x, depth + 1) for k, x in v.items()}
    if isinstance(v, list):
        return [_resolve(arr, x, depth + 1) for x in v]
    return v


def main() -> int:
    cfg = config_mod.load()
    session = make_session()
    coords = geocode_plz(cfg.plz, session)
    if not coords:
        print("Geocoding fehlgeschlagen")
        return 1
    lat0, lon0 = coords
    max_km = cfg.radius_km + BUFFER_KM

    arr = _devalue(session.get(OVERVIEW, timeout=40).text)
    if not arr:
        print("OBI-Uebersicht: __NUXT_DATA__ nicht gefunden")
        return 1

    stores = []
    for i, v in enumerate(arr):
        if not (isinstance(v, dict) and "storeName" in v and "geo" in v and "cta" in v):
            continue
        node = _resolve(arr, i)
        try:
            name = node["storeName"]["content"]["text"]
            geo = node["geo"]["content"]
            lat, lon = float(geo["latitude"]), float(geo["longitude"])
            href = node["cta"]["content"]["href"]
            addr = node["address"]["content"]["text"]
        except (KeyError, TypeError, ValueError):
            continue
        d = haversine_km(lat0, lon0, lat, lon)
        if d <= max_km:
            slug = href.rstrip("/").split("/")[-1]
            city = addr.split("\n")[-1].strip() if "\n" in addr else name
            stores.append({"slug": slug, "name": name, "city": city, "lat": lat, "lon": lon})

    print(f"{len(stores)} OBI-Maerkte im Umkreis (<= {max_km:.0f} km). Hole storeIds ...")
    out = []
    for st in sorted(stores, key=lambda s: haversine_km(lat0, lon0, s["lat"], s["lon"])):
        try:
            pg = session.get(f"https://www.obi.de/markt/{st['slug']}", timeout=30).text
            arr2 = _devalue(pg)
            m = re.search(r'"storeId":(\d+)', pg)
            store_id = None
            if m and arr2:
                ref = int(m.group(1))
                store_id = arr2[ref] if 0 <= ref < len(arr2) else None
            if store_id is None:
                print(f"  ! {st['name']}: keine storeId")
                continue
            st["storeId"] = str(store_id)
            out.append(st)
            print(f"  {st['name']:28} storeId={store_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {st['name']}: {exc}")

    path = Path("data/obi_stores.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(out)} Maerkte -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
