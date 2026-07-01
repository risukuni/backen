"""Datenmodelle fuer den Restock-Monitor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Product:
    key: str      # "8000" oder "12000"
    label: str    # Anzeigename, z. B. "Midea PortaSplit 8.000 BTU"


@dataclass
class StoreAvailability:
    """Verfuegbarkeit EINES Produkts an EINEM Ort (Markt oder Online-Shop)."""
    retailer: str
    product_key: str
    product_label: str
    store_id: str                       # "online" = Online-/Lieferverfuegbarkeit, sonst Markt-ID
    store_name: str
    available: Optional[bool]           # True/False, None = unbekannt (kein Datensignal -> kein Alarm)
    quantity: Optional[int] = None
    price: Optional[float] = None
    distance_km: Optional[float] = None
    city: str = ""
    url: str = ""

    @property
    def state_key(self) -> str:
        return f"{self.retailer}|{self.product_key}|{self.store_id}"

    def location_label(self) -> str:
        if self.store_id == "online":
            return f"{self.retailer} (Online/Lieferung)"
        name = self.store_name or self.store_id
        if self.city and self.city.lower() not in name.lower():
            name = f"{name} ({self.city})"
        if self.distance_km is not None:
            name += f" – ~{self.distance_km:.0f} km"
        return f"{self.retailer}: {name}"
