"""Gemeinsame HTTP-Helfer.

Wichtig: Mehrere Baumarkt-Seiten (z. B. Bauhaus) blocken einfache
HTTP-Clients per Bot-/TLS-Fingerprint-Erkennung. Deshalb nutzen wir
curl_cffi mit Browser-Impersonation ("chrome"), das einen echten
Browser-TLS-Fingerprint sendet und damit durchkommt.
"""
from __future__ import annotations

import time

from curl_cffi import requests as crequests

IMPERSONATE = "chrome"


def make_session() -> "crequests.Session":
    s = crequests.Session(impersonate=IMPERSONATE)
    s.headers.update({"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    return s


def get(session, url: str, *, timeout: int = 25, retries: int = 2, **kw):
    """GET mit einfachem Retry. Gibt die Response zurueck (auch bei 4xx/5xx)."""
    last = None
    for attempt in range(retries + 1):
        try:
            return session.get(url, timeout=timeout, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]
