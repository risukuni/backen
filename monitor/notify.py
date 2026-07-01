"""Discord-Benachrichtigung via Webhook."""
from __future__ import annotations

import requests

from .models import StoreAvailability

GREEN = 0x2ECC71
BLUE = 0x3498DB


def _post(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=20)
    resp.raise_for_status()


def send_restock(webhook_url: str, events: list[StoreAvailability], mention: str = "") -> None:
    """Eine Nachricht pro Restock-Welle, ein Embed pro verfuegbarem Treffer."""
    if not events:
        return
    embeds = []
    for e in events:
        fields = [{"name": "Wo", "value": e.location_label(), "inline": False}]
        if e.quantity is not None:
            fields.append({"name": "Menge", "value": f"{e.quantity} Stk.", "inline": True})
        if e.price is not None:
            fields.append({"name": "Preis", "value": f"{e.price:.2f} €", "inline": True})
        embeds.append(
            {
                "title": f"🟢 Wieder verfügbar: {e.product_label}",
                "url": e.url or None,
                "color": GREEN,
                "fields": fields,
            }
        )

    # Discord erlaubt max. 10 Embeds pro Nachricht
    for i in range(0, len(embeds), 10):
        payload: dict = {"embeds": embeds[i : i + 10]}
        if i == 0 and mention:
            payload["content"] = mention
        _post(webhook_url, payload)


def send_text(webhook_url: str, text: str, *, color: int = BLUE, title: str = "") -> None:
    if title:
        _post(webhook_url, {"embeds": [{"title": title, "description": text, "color": color}]})
    else:
        _post(webhook_url, {"content": text})
