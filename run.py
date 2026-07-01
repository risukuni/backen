#!/usr/bin/env python3
"""Restock-Monitor fuer die Midea PortaSplit (8.000 / 12.000 BTU).

Prueft konfigurierte Baumaerkte und meldet per Discord, wenn ein Produkt von
'nicht verfuegbar' auf 'verfuegbar' wechselt.

Aufruf:
    python run.py            # normaler Lauf (mit Discord-Meldung bei Restock)
    python run.py --dry-run  # nur pruefen + Tabelle ausgeben, KEINE Discord-Meldung
"""
from __future__ import annotations

import argparse
import sys

from monitor import config as config_mod
from monitor import notify, state
from monitor import retailers as retailers_mod
from monitor.models import StoreAvailability


def collect(cfg: config_mod.Config) -> list[StoreAvailability]:
    products = cfg.products
    results: list[StoreAvailability] = []
    for name in cfg.enabled_retailers():
        rcfg = cfg.retailers[name]
        try:
            retailer = retailers_mod.build(name, rcfg, cfg.plz, cfg.radius_km)
            res = retailer.check(products)
            results.extend(res)
        except Exception as exc:  # noqa: BLE001 - eine Kette darf den Lauf nicht killen
            print(f"[{name}] Fehler: {exc}")
    return results


def fmt(av: StoreAvailability) -> str:
    sym = {True: "JA ", False: "nein", None: "?  "}[av.available]
    price = f"  {av.price:.2f} EUR" if av.price else ""
    return f"  [{sym}] {av.product_key:>5} BTU  {av.location_label()}{price}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="Nur pruefen, nichts senden.")
    args = ap.parse_args()

    cfg = config_mod.load(args.config)
    problems = cfg.validate()
    if problems and not args.dry_run:
        for p in problems:
            print("KONFIG-PROBLEM:", p)
        return 2

    print(f"PLZ {cfg.plz} | Umkreis {cfg.radius_km:.0f} km | Ketten: {', '.join(cfg.enabled_retailers())}")
    results = collect(cfg)

    print("\nErgebnisse:")
    for av in sorted(results, key=lambda a: (a.retailer, a.product_key)):
        print(fmt(av))
    known = [a for a in results if a.available is not None]
    print(f"\n{len(results)} Treffer gesamt, {len(known)} mit verwertbarem Signal.")

    if args.dry_run:
        return 0

    if not cfg.discord_webhook_url:
        print("Kein Discord-Webhook gesetzt (DISCORD_WEBHOOK_URL) -> keine Meldung.")
        return 0

    prev = state.load()
    events, new_state, first_run = state.diff_and_update(prev, results)

    if first_run:
        avail_now = [a for a in results if a.available]
        summary = (
            "Monitor ist aktiv. Ich melde mich, sobald die PortaSplit irgendwo "
            "wieder verfuegbar ist.\n\nAktueller Stand:\n"
            + (
                "\n".join(f"• {a.product_label} — {a.location_label()}" for a in avail_now)
                if avail_now
                else "• aktuell nirgends als verfuegbar gemeldet."
            )
        )
        notify.send_text(cfg.discord_webhook_url, summary, title="🔔 PortaSplit-Monitor gestartet")
        print("Erstlauf: Basis gespeichert, Start-Meldung gesendet.")
    elif events:
        notify.send_restock(cfg.discord_webhook_url, events, cfg.mention)
        print(f"{len(events)} Restock-Meldung(en) gesendet.")
    else:
        print("Keine Aenderung seit letztem Lauf.")

    state.save(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
