#!/usr/bin/env python3
"""Restock-Monitor fuer die Midea PortaSplit (8.000 / 12.000 BTU).

Prueft konfigurierte Baumaerkte und meldet per Discord, wenn ein Produkt von
'nicht verfuegbar' auf 'verfuegbar' wechselt.

Aufruf:
    python run.py                 # einmal pruefen (mit Discord-Meldung bei Restock)
    python run.py --dry-run       # einmal pruefen + Tabelle, KEINE Discord-Meldung
    python run.py --loop          # Dauerschleife (fuer GitHub Actions):
                                  #   schnelle Ketten jede Runde, Browser-Ketten
                                  #   (Globus) nur jede N-te Runde; endet nach
                                  #   --max-runtime und wird per Zeitplan neu gestartet.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from monitor import config as config_mod
from monitor import notify, state
from monitor import retailers as retailers_mod
from monitor.models import StoreAvailability


def collect(cfg: config_mod.Config, *, skip_browser: bool = False):
    """Fuehrt die (ausgewaehlten) Ketten aus. Gibt (results, ran_names) zurueck."""
    results: list[StoreAvailability] = []
    ran: list[str] = []
    for name in cfg.enabled_retailers():
        rcfg = cfg.retailers[name]
        if skip_browser and rcfg.get("engine") == "browser":
            continue
        try:
            retailer = retailers_mod.build(name, rcfg, cfg.plz, cfg.radius_km)
            results.extend(retailer.check(cfg.products))
            ran.append(name)
        except Exception as exc:  # noqa: BLE001 - eine Kette darf den Lauf nicht killen
            print(f"[{name}] Fehler: {exc}")
    return results, ran


def process(cfg: config_mod.Config, prev: dict, results: list[StoreAvailability]):
    """Diff bilden und ggf. Discord-Meldung senden. Gibt (events, new_state, first) zurueck."""
    events, new_state, first = state.diff_and_update(prev, results)
    if not cfg.discord_webhook_url:
        return events, new_state, first
    if first:
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
    elif events:
        notify.send_restock(cfg.discord_webhook_url, events, cfg.mention)
    return events, new_state, first


def fmt(av: StoreAvailability) -> str:
    sym = {True: "JA ", False: "nein", None: "?  "}[av.available]
    price = f"  {av.price:.2f} EUR" if av.price else ""
    return f"  [{sym}] {av.product_key:>5} BTU  {av.location_label()}{price}"


def run_single(cfg: config_mod.Config, dry_run: bool) -> int:
    results, _ = collect(cfg)
    print("\nErgebnisse:")
    for av in sorted(results, key=lambda a: (a.retailer, a.product_key)):
        print(fmt(av))
    known = [a for a in results if a.available is not None]
    print(f"\n{len(results)} Treffer gesamt, {len(known)} mit verwertbarem Signal.")
    if dry_run:
        return 0
    if not cfg.discord_webhook_url:
        print("Kein Discord-Webhook gesetzt (DISCORD_WEBHOOK_URL) -> keine Meldung.")
    prev = state.load()
    events, new_state, first = process(cfg, prev, results)
    if first:
        print("Erstlauf: Basis gespeichert, Start-Meldung gesendet.")
    elif events:
        print(f"{len(events)} Restock-Meldung(en) gesendet.")
    else:
        print("Keine Aenderung seit letztem Lauf.")
    state.save(new_state)
    return 0


def run_loop(cfg: config_mod.Config, args) -> int:
    prev = state.load()
    start = time.time()
    cycle = 0
    print(
        f"Loop: alle {args.interval}s pruefen, Browser-Ketten jede {args.browser_every}. Runde, "
        f"max {args.max_runtime}s Laufzeit."
    )
    while time.time() - start < args.max_runtime:
        cycle += 1
        run_browser = (cycle == 1) or (cycle % args.browser_every == 0)
        results, ran = collect(cfg, skip_browser=not run_browser)
        events, new_state, first = process(cfg, prev, results)
        prev = new_state
        state.save(new_state)

        ts = datetime.now().strftime("%H:%M:%S")
        tag = "START-Meldung" if first else (f"🟢 {len(events)} RESTOCK!" if events else "keine Aenderung")
        print(f"[{ts}] Zyklus {cycle} ({', '.join(ran)}): {tag}")
        for e in events:
            print(f"    -> {e.product_label} @ {e.location_label()}")

        if args.max_runtime - (time.time() - start) <= args.interval:
            break
        time.sleep(args.interval)

    print(f"Loop-Ende: {cycle} Zyklen in {int(time.time() - start)}s.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="Nur pruefen, nichts senden.")
    ap.add_argument("--loop", action="store_true", help="Dauerschleife (GitHub Actions).")
    ap.add_argument("--interval", type=int, default=70, help="Sekunden zwischen Checks im Loop.")
    ap.add_argument("--max-runtime", type=int, default=270, help="Loop-Laufzeit in Sekunden, dann Exit.")
    ap.add_argument("--browser-every", type=int, default=5, help="Browser-Ketten (Globus) jede N-te Runde.")
    args = ap.parse_args()

    cfg = config_mod.load(args.config)
    problems = cfg.validate()
    if problems and not args.dry_run:
        for p in problems:
            print("KONFIG-PROBLEM:", p)
        return 2

    print(f"PLZ {cfg.plz} | Umkreis {cfg.radius_km:.0f} km | Ketten: {', '.join(cfg.enabled_retailers())}")
    if args.loop:
        return run_loop(cfg, args)
    return run_single(cfg, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
