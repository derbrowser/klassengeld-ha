# Klassengeld für Home Assistant

Zeigt Kontostand und offene Zahlungsaufforderungen von [klassengeld.app](https://klassengeld.app) in Home Assistant an. Pro Kind wird ein Gerät angelegt.

> **Stand:** Der Parser wurde gegen den echten Seitenaufbau des Dashboards geprüft (Betrag vor dem Label "Kontostand", Frist auf mehreren Zeilen) und in einem echten Home Assistant getestet. Siehe "Wenn etwas nicht klappt".

Die Entitäts-IDs richten sich nach der Sprache deiner Home-Assistant-Installation, auf Deutsch z. B. `sensor.max_mustermann_kontostand`.

## Installation

1. Ordner `custom_components/klassengeld` nach `/config/custom_components/klassengeld` kopieren.
2. Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Klassengeld**.
4. Benutzer und Passwort von klassengeld.app eingeben.

Die Daten werden alle 30 Minuten abgerufen. Die Integration liest nur, sie bezahlt oder ändert nichts.

## Entitäten (pro Kind)

| Entität | Inhalt |
|---|---|
| Kontostand | aktueller Kontostand in EUR |
| Offener Betrag | Summe aller Zahlungsaufforderungen mit Status "zu bezahlen" |
| Offene Zahlungen | Anzahl offener Aufforderungen (Attribut `payments` mit Titel, Frist, Betrag) |
| Nächste Frist | früheste Frist einer offenen Aufforderung |
| Projekte | Anzahl aller Projekte; Attribut `projects` mit Titel, Frist, Betrag und Status (`open` / `paid` / `unknown`), dazu die Zähler `open`, `paid`, `open_amount` |
| Transaktionen | Anzahl aller Buchungen aus "Alle Transaktionen anzeigen"; Attribut `transactions` mit Datum, Titel, Betrag, Notiz, dazu die Summen `income` und `expenses` |
| Zahlung offen | Binärsensor, an sobald mindestens eine Zahlung offen ist |

Die langen Listen (`projects`, `transactions`) werden nicht in der Recorder-Datenbank gespeichert, sie sind nur im aktuellen Zustand sichtbar.

## Beispiel: Alle Projekte mit Status

```yaml
type: markdown
title: Projekte
content: >
  {% for p in state_attr('sensor.max_mustermann_projekte', 'projects') or [] %}
  - {{ '✅' if p.status == 'paid' else '⏳' }} **{{ p.title }}** – {{ '%.2f'|format(p.amount or 0) }} € (Frist {{ p.due }})
  {% endfor %}
```

## Beispiel: Letzte 10 Transaktionen

```yaml
type: markdown
title: Transaktionen
content: >
  {% for t in (state_attr('sensor.max_mustermann_transaktionen', 'transactions') or [])[:10] %}
  - {{ t.date }} {{ t.title }}: {{ '%.2f'|format(t.amount or 0) }} €
  {% endfor %}
```

## Beispiel: Dashboard-Karte

```yaml
type: markdown
title: Klassengeld
content: >
  {% set e = 'sensor.max_mustermann_offene_zahlungen' %}
  {% for p in state_attr(e, 'payments') or [] %}
  - **{{ p.title }}** – {{ '%.2f'|format(p.amount) }} € bis {{ p.due }}
  {% else %}
  Keine offenen Zahlungen
  {% endfor %}
```

Die Entitäts-ID an den Namen deines Kindes anpassen.

## Beispiel: Erinnerung 3 Tage vor der Frist

```yaml
alias: Klassengeld Frist naht
triggers:
  - trigger: template
    value_template: >
      {% set d = states('sensor.max_mustermann_nachste_frist') %}
      {{ d not in ['unknown','unavailable'] and
         (as_datetime(d).date() - now().date()).days == 3 }}
actions:
  - action: notify.notify
    data:
      message: "Klassengeld: Zahlung fällig am {{ states('sensor.max_mustermann_nachste_frist') }}"
```

## Wenn etwas nicht klappt

- **"Login-Formular nicht erkannt" / "nicht erreichbar":** Die Integration erwartet ein normales HTML-Formular mit Passwortfeld. Läuft der Login über JavaScript/AJAX, muss `api.py` angepasst werden.
- **"Keine Daten im Dashboard erkannt":** Layout weicht ab. Auf der Integrationsseite → drei Punkte → **Diagnose herunterladen**. Die Datei enthält den erkannten Seitentext (`page_lines`), daran lässt sich der Parser in `parser.py` anpassen. Die Datei enthält Namen, vor dem Weitergeben prüfen.
- Debug-Log: in `configuration.yaml`
  ```yaml
  logger:
    logs:
      custom_components.klassengeld: debug
  ```

## Bekannte Grenzen

- Die Transaktionsseite ("Alle Transaktionen anzeigen") wird über den Link im Dashboard gefunden und mit einem allgemeinen, textbasierten Parser gelesen (Datum, Titel, Betrag). Das Layout dieser Seite ist noch nicht gegen die echte Seite geprüft. Liefert der Sensor "Transaktionen" 0, bitte den Diagnose-Download anhängen, er enthält dann `transaction_page_lines`.
- Das Passwort liegt, wie bei allen Integrationen mit Login, im Klartext in `.storage/core.config_entries`. Am besten ein Passwort verwenden, das du nirgends sonst nutzt.

## Hinweis

Dies ist ein inoffizielles, privates Projekt und steht in keiner Verbindung zu klassengeld.app oder deren Betreibern. Die Integration meldet sich mit deinen eigenen Zugangsdaten an und liest nur die Daten, die du selbst im Dashboard siehst. Bitte beachte die Nutzungsbedingungen von klassengeld.app, die Nutzung erfolgt auf eigene Verantwortung. Das Seitenlayout kann sich jederzeit ändern, dann muss der Parser angepasst werden.

## Lizenz

[MIT](LICENSE)
