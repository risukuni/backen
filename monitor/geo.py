"""Geo-Helfer: PLZ -> Koordinaten und Distanzberechnung (Umkreis-Filter)."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

from .web import get


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def geocode_plz(plz: str, session) -> Optional[tuple[float, float]]:
    """Deutsche PLZ -> (lat, lon) ueber api.zippopotam.us (kostenlos, ohne Key)."""
    try:
        r = get(session, f"https://api.zippopotam.us/DE/{plz}", timeout=20)
        if r.status_code == 200:
            place = r.json()["places"][0]
            return float(place["latitude"]), float(place["longitude"])
    except Exception as exc:  # noqa: BLE001
        print(f"[geo] Geocoding {plz} fehlgeschlagen: {exc}")
    return None
