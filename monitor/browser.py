"""Gemeinsamer Playwright-Helfer.

Manche Seiten (z. B. Bauhaus/Akamai) blocken einfache HTTP-Clients aus
Rechenzentrums-IPs (GitHub Actions) mit 403 - ein echter Browser kommt eher
durch. Wichtig bei Akamai: zuerst die Startseite besuchen, damit die
Challenge-/Sensor-Cookies gesetzt werden, DANN die Zielseiten (Cookies bleiben
im selben Kontext erhalten). Notfalls einmal neu laden.

Laeuft nur, wenn playwright installiert ist (GitHub Actions).
"""
from __future__ import annotations

from urllib.parse import urlparse

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _looks_blocked(html: str) -> bool:
    if not html or len(html) < 2000:
        return True
    low = html.lower()
    return any(t in low for t in ("access denied", "reference #", "wurde blockiert", "pardon our interruption"))


def fetch_html(urls: list[str], *, wait_ms: int = 2500, timeout: int = 45000) -> dict[str, str]:
    out: dict[str, str] = {}
    if not urls:
        return out
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        print("[browser] playwright nicht installiert -> Fallback nicht moeglich")
        return out
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            )
            ctx = browser.new_context(locale="de-DE", user_agent=UA)
            page = ctx.new_page()

            # Akamai-Warmup: Startseite der ersten URL besuchen (setzt Challenge-Cookies)
            try:
                p0 = urlparse(urls[0])
                page.goto(f"{p0.scheme}://{p0.netloc}/", wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(3500)
            except Exception as exc:  # noqa: BLE001
                print(f"[browser] Warmup: {exc}")

            for url in urls:
                html = ""
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(wait_ms)
                    html = page.content()
                    if _looks_blocked(html):
                        page.wait_for_timeout(2500)
                        try:
                            page.reload(wait_until="domcontentloaded", timeout=timeout)
                            page.wait_for_timeout(wait_ms)
                            html = page.content()
                        except Exception:  # noqa: BLE001
                            pass
                    if _looks_blocked(html):
                        print(f"[browser] {url[:55]}: sieht weiter geblockt aus ({len(html)} B)")
                except Exception as exc:  # noqa: BLE001
                    print(f"[browser] fetch {url[:55]}: {exc}")
                out[url] = html
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[browser] Fehler: {exc}")
    return out
