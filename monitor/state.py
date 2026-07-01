"""Persistenter Status, um nur bei *Aenderungen* (nicht-verfuegbar -> verfuegbar)
zu benachrichtigen statt bei jedem Lauf."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import StoreAvailability

STATE_PATH = Path("data/state.json")


def load(path: Path = STATE_PATH) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)


def diff_and_update(
    prev: dict, results: list[StoreAvailability]
) -> tuple[list[StoreAvailability], dict, bool]:
    """Vergleicht aktuelle Ergebnisse mit dem letzten Status.

    Rueckgabe: (restock_events, neuer_status, is_first_run)
    - restock_events: alles, was von 'nicht verfuegbar/unbekannt' auf 'verfuegbar' gewechselt ist.
    - Bei unbekanntem Signal (available=None) bleibt der alte Status erhalten (kein Alarm).
    """
    is_first_run = not prev
    new_state = dict(prev)
    events: list[StoreAvailability] = []

    for r in results:
        if r.available is None:
            continue  # kein verwertbares Signal -> alten Stand behalten
        key = r.state_key
        was_available = bool(prev.get(key, {}).get("available", False))
        new_state[key] = {
            "available": r.available,
            "store_name": r.store_name,
            "city": r.city,
            "quantity": r.quantity,
            "price": r.price,
            "url": r.url,
        }
        if r.available and not was_available and not is_first_run:
            events.append(r)

    return events, new_state, is_first_run
