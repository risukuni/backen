"""Registry aller Baumarkt-Module."""
from __future__ import annotations

from .bauhaus import Bauhaus
from .globus import Globus
from .hornbach import Hornbach
from .obi import Obi
from .toom import Toom

REGISTRY = {
    cls.name: cls
    for cls in (Bauhaus, Obi, Toom, Hornbach, Globus)
}


def build(name: str, cfg: dict, plz: str, radius_km: float):
    cls = REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unbekannter Baumarkt: {name}")
    return cls(cfg, plz, radius_km)
