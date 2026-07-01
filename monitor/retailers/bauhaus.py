"""Bauhaus: server-seitige schema.org-Verfuegbarkeit ist verlaesslich.

Status: VERIFIZIERT (Online-/Liefersignal).
TODO: Filial-Verfuegbarkeit pro Fachcentrum im Umkreis ergaenzen.
"""
from __future__ import annotations

from .base import SchemaOrgRetailer


class Bauhaus(SchemaOrgRetailer):
    name = "bauhaus"
