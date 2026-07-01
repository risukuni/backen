"""Konfiguration laden. Umgebungsvariablen haben Vorrang vor der JSON-Datei
(damit Secrets in GitHub Actions nicht im Repo stehen)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import Product

DEFAULT_FILES = ["config.json", "config.local.json", "config.example.json"]


class Config:
    def __init__(self, data: dict[str, Any]):
        self.plz: str = os.environ.get("PLZ") or data.get("plz", "")
        self.radius_km: float = float(os.environ.get("RADIUS_KM") or data.get("radius_km", 60))
        self.discord_webhook_url: str = (
            os.environ.get("DISCORD_WEBHOOK_URL") or data.get("discord_webhook_url", "")
        )
        self.mention: str = os.environ.get("DISCORD_MENTION") or data.get("mention", "")
        self.products: list[Product] = [
            Product(key=str(p["key"]), label=p["label"]) for p in data.get("products", [])
        ]
        self.retailers: dict[str, dict] = data.get("retailers", {})

    def enabled_retailers(self) -> list[str]:
        return [name for name, cfg in self.retailers.items() if cfg.get("enabled")]

    def validate(self) -> list[str]:
        problems = []
        if not self.plz or "EINTRAGEN" in self.plz:
            problems.append("PLZ fehlt (config.json oder Umgebungsvariable PLZ).")
        if not self.products:
            problems.append("Keine Produkte konfiguriert.")
        if not self.enabled_retailers():
            problems.append("Kein Baumarkt aktiviert.")
        return problems


def load(path: str | None = None) -> Config:
    candidates = [path] if path else DEFAULT_FILES
    for cand in candidates:
        if cand and Path(cand).exists():
            with open(cand, encoding="utf-8") as fh:
                return Config(json.load(fh))
    raise FileNotFoundError(
        "Keine Konfigurationsdatei gefunden. Kopiere config.example.json nach config.json."
    )
