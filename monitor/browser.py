"""Gemeinsamer Playwright-Helfer.

Manche Seiten (z. B. Bauhaus/Akamai) blocken einfache HTTP-Clients aus
Rechenzentrums-IPs (GitHub Actions) mit 403 - ein echter Browser kommt durch.
Dieser Helfer laedt eine Liste von URLs in einem headless Chromium und gibt
das gerenderte HTML je URL zurueck. Laeuft nur, wenn playwright installiert ist
(in GitHub Actions via requirements.txt + Workflow).
"""
from __future__ import annotations

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(urls: list[str], *, wait_ms: int = 1500, timeout: int = 45000) -> dict[str, str]:
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
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(wait_ms)
                    out[url] = page.content()
                except Exception as exc:  # noqa: BLE001
                    print(f"[browser] fetch {url[:60]}: {exc}")
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[browser] Fehler: {exc}")
    return out
