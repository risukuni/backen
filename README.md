# PortaSplit Restock-Monitor

Überwacht die **Midea PortaSplit** (8.000 & 12.000 BTU) bei mehreren Baumärkten und
schickt dir eine **Discord-Nachricht, sobald ein Gerät wieder verfügbar ist**.

Läuft kostenlos und rund um die Uhr über **GitHub Actions** – dein PC muss nicht anbleiben.

---

## Wie es funktioniert

1. Alle 15 Minuten prüft ein kleines Python-Skript die konfigurierten Baumärkte.
2. Ein Statusspeicher (`data/state.json`) merkt sich den letzten Stand.
3. Wechselt ein Produkt von **„nicht verfügbar" → „verfügbar"**, kommt **eine** Discord-Meldung
   (kein Dauer-Spam, nur bei echten Änderungen).

---

## Einrichtung (ca. 15 Min, ohne Programmierkenntnisse)

### 1. Discord-Webhook erstellen
1. In deinem Discord-Server: **Servereinstellungen → Integrationen → Webhooks → Neuer Webhook**.
2. Channel wählen (z. B. `#klima-alarm`), **Webhook-URL kopieren**.
   (Die URL ist dein „Bot" – sie reicht, um Nachrichten zu posten.)

### 2. Repository bei GitHub anlegen
1. Auf [github.com](https://github.com) ein **kostenloses Konto** erstellen.
2. **New repository** → Name z. B. `portasplit-monitor` → **Private** → erstellen.
3. Alle Dateien aus diesem Ordner hochladen (Drag & Drop im Browser unter „uploading an existing file").

### 3. Secrets (Geheimnisse) hinterlegen
Im Repo: **Settings → Secrets and variables → Actions → New repository secret**:
- `DISCORD_WEBHOOK_URL` = deine kopierte Webhook-URL
- `PLZ` = deine Postleitzahl (für den 60-km-Umkreis)

Optional unter **Variables**:
- `RADIUS_KM` = `60` (Umkreis ändern, falls gewünscht)

### 4. Läuft!
Der Zeitplan startet automatisch (alle 15 Min). Du kannst ihn auch sofort manuell testen:
**Actions → „PortaSplit Restock Monitor" → Run workflow**.
Beim allerersten Lauf bekommst du eine **Start-Nachricht** mit dem aktuellen Stand.

---

## Lokal testen (optional, nur wenn Python installiert ist)
```bash
pip install -r requirements.txt
copy config.example.json config.json   # Windows  (Mac/Linux: cp ...)
# in config.json deine PLZ eintragen
python run.py --dry-run                 # nur prüfen, nichts senden
```

---

## Abdeckung pro Baumarkt

| Kette     | Signal                                          | Status |
|-----------|-------------------------------------------------|--------|
| **toom**  | **Bestand pro Markt im Umkreis** (Stückzahl)    | ✅ 23 Märkte um 50181 |
| **OBI**   | **Verfügbarkeit pro Markt im Umkreis** + Online | ✅ 47 Märkte um 50181 |
| Bauhaus   | Online-/Lieferverfügbarkeit (stabil)            | ✅ verifiziert |
| Hornbach  | Relisting-Watcher (Produkt aktuell delistet)    | ✅ meldet, sobald wieder gelistet |
| Globus    | Browser-Checker (FACT-Finder, nur in der Cloud) | 🟡 in GitHub Actions, 1. Lauf validiert |

**toom + OBI** liefern die echte Filial-Abfrage: für jeden Markt im 80-km-Umkreis die
Verfügbarkeit (toom mit Stückzahl). PLZ → Koordinaten → Umkreis → Bestand je Markt.

**Hornbach** führt die PortaSplit-Klimaanlage gerade nicht (nur Zubehör) – der Watcher
meldet, sobald sie wieder gelistet wird.

**Globus** ist stärker bot-geschützt: Produktdaten kommen nur aus FACT-Finder mit
client-seitigem Request-Signing – geht **nur über einen echten Browser**. Der
Globus-Checker nutzt daher **Playwright** und läuft **ausschließlich in GitHub
Actions** (der Workflow installiert den Browser automatisch), nie lokal. Er ist
defensiv: kann er die Verfügbarkeit nicht sicher bestimmen, meldet er nichts
(kein Fehlalarm) und loggt beim ersten Lauf die FF-Feldnamen zur Feinjustierung.
Artikelnummern stehen in `config.json` (`retailers.globus.products`).
Zum Deaktivieren: `"enabled": false` + die beiden Playwright-Schritte im Workflow entfernen.

> **OBI-Märkte aktualisieren:** Die OBI-Markt-IDs liegen in `data/obi_stores.json`
> (für PLZ 50181 erzeugt). Bei PLZ-Wechsel einmal `python tools/build_obi_stores.py`
> laufen lassen.

„Filial-Verfügbarkeit im 60-km-Umkreis" wird pro Kette ergänzt – siehe Kommentare in
`monitor/retailers/*.py`. Bei „unbekanntem" Signal löst der Monitor **keinen** Fehlalarm aus.

---

## Wartung
Ändert eine Kette ihre Website/API, ist nur das jeweilige Modul unter
`monitor/retailers/` betroffen. Produkt-URLs stehen zentral in `config.json`.
