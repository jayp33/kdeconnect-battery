# Issues

Geplante Arbeiten, die bewusst zurückgestellt wurden. Jeder Eintrag enthält den
Umfang, die bereits getroffenen Entscheidungen und die Abnahmekriterien, damit die
Umsetzung ohne erneute Absprache beginnen kann.

## #1 Konfigurationsdatei mit Angaben pro Gerät

Status: offen

### Ziel

Werte, die man nach der Einrichtung nicht bei jedem Aufruf tippen will, in einer
Konfigurationsdatei merken und automatisch verwenden, solange sie nicht durch neue
Parameter überschrieben werden. Die Datei soll die Einstellungen für **beliebig
viele Geräte** enthalten, nicht nur für eines.

### Aufbau der Datei

Abschnitt für die geräteunabhängigen Vorgaben, danach ein Abschnitt pro Gerät,
adressiert über die KDE-Connect-ID. Der Name ist reine Zusatzinformation:

```ini
# ~/.config/kdeconnect-battery.conf
[default]
tts_language=de
interval=60

[device:<device_id>]
name=POCO F1
threshold=15
charge_limit=85

[device:<device_id>]
name=Redmi Pad SE
threshold=25
charge_limit=80
```

- Sektionsschlüssel ist die Geräte-ID, auf Kleinschreibung normalisiert, in der
  Schreibweise `[device:<device_id>]`. Die Doppelpunktschreibweise ist festgelegt,
  weil die ID damit als Rest des Sektionskopfs gelesen werden kann und Leerzeichen
  in IDs kein Problem sind.
- `name` dient nur der Anzeige („Schwelle für POCO F1 (<device_id>)“) und dem Aufräumen per
  Hand. **Niemals** zur Zuordnung verwendet: Namen können sich ändern und
  doppelt vorkommen, IDs nicht.
- Schlüssel, die in `[default]` stehen, gelten als Vorgabe für alle Geräte. Ein
  Schlüssel im Geräteabschnitt überschreibt die Vorgabe.
- Das Skript liest weiterhin **ein Gerät pro Prozess**. Die Datei sammelt einfach
  beliebig viele Geräte-Abschnitte (z. B. ein eigener systemd-User-Service je Gerät).

### Umfang

- `threshold`
- `charge_limit`
- `device_id` inklusive `name` (wird bei interaktiver Auswahl aus
  `kdeconnect-cli --list-available` übernommen)
- `interval` und `tts_language` als erstes Beispiel für die generische Mechanik

Der Mechanismus wird generisch aufgebaut (Schlüssel → Variablen-Mapping), damit
weitere Schlüssel später ohne Umbau dazukommen können. `command` wird bewusst
**nicht** automatisch aus der Config geladen: Das wäre die Ausführung eines
Shell-Befehls ohne expliziten Parameter.

### Entscheidungen

- **Ablage:** `${XDG_CONFIG_HOME:-$HOME/.config}/kdeconnect-battery.conf`, optional
  `--config PFAD` für Tests und portabele setups.
- **Prezedenz:** CLI-Parameter > Geräteabschnitt > `[default]` > eingebauter Standard.
- **„Gesetzt“-Erkennung:** über separate Flags (`threshold_set=0/1`), nicht über
  einen Wertvergleich. Sonst ist ein explizites `--threshold 20` nicht von einem
  nicht gesetzten Parameter zu unterscheiden, und ein gespeichertes 15 gewinnt.
- **Kein `source`:** eigener Parser für Sektionen und `key=value` mit `#`-Kommentaren.
  Nur bekannte Schlüssel, Werte als Ganzzahl validiert, sonst Warnung und Standard
  verwenden. Ein Tippfehler darf keinen Shell-Code ausführen.
- **Nur abweichende Werte speichern** (Datei bleibt minimal, spätere Default-Änderungen
  wirken sofort).
- **Speichern:** automatisch, wenn ein Wert explizit per CLI gesetzt wurde – aber
  **nie bei `--once`**. Bei jeder Speicherung eine Rückmeldung ausgeben.
- **Atomar schreiben** (Temp-Datei + `mv`), damit parallele Instanzen keine halbe
  Datei hinterlassen; nur bei tatsächlicher Änderung schreiben.
- **Nur den betroffenen Abschnitt anfassen:** Kommentare, Reihenfolge und die
  Abschnitte anderer Geräte müssen unangetastet bleiben. Also die Datei in Zeilen
  einlesen und nur die zu ändernden Zeilen ersetzen bzw. den neuen Abschnitt am
  Ende anfügen – nicht die Datei aus dem geparsten Zustand neu serialisieren.
- **Zusammenführen statt duplizieren:** existiert der Abschnitt für eine ID bereits,
  werden nur die betroffenen Schlüssel aktualisiert bzw. fehlende ergänzt. Ein
  doppelt vorhandener Abschnitt ist ein Fehler und wird mit Ort gemeldet, nicht
  stillschweigend gemergt.
- **Aufräumen bleibt manuell:** Das Skript entfernt **nie** einen Geräteabschnitt,
  auch nicht für nicht mehr erreichbare Geräte. Verwaiste Einträge bleiben stehen.
- **Nicht erreichbare Geräte nur melden:** Gibt es zu einem Gerät einen Eintrag, das
  Gerät aber nicht in `kdeconnect-cli --list-available` auftaucht, wird darauf
  hingewiesen (`Eintrag für <name> (<device_id>) vorhanden, Gerät nicht erreichbar`).
  Nichts wird gelöscht oder verändert. Die Prüfung erfolgt nur dort, wo die
  Geräteliste ohnehin abgefragt wird, damit kein zusätzlicher Aufruf entsteht.
- **Zuletzt verwendetes Gerät:** In `[default]` als `last_device=<device_id>` merken
  (`last_device_name` nur zur Anzeige). Aktualisiert bei explizitem `--device` und bei
  interaktiver Auswahl. Ohne `--device` und ohne Positionsargument wird direkt dieses
  Gerät verwendet, **ohne** Auswahlliste.
- **Auswahl erzwingen:** Weil damit das bisherige Verhalten „kein `--device` zeigt die
  Liste“ verschwindet, braucht es einen Ausstieg: Vorschlag `--choose`, das die
  Auswahlliste immer zeigt.
- **Auswahlliste mit Konfigwerten:** Jede Zeile nennt Name, ID und – falls vorhanden –
  die gespeicherten Werte, damit man beim Wechsel zwischen Geräten sieht, was gilt:

  ```text
  1) POCO F1 (<device_id>)       gespeichert: Schwelle 15, Ladelimit 85
  2) Redmi Pad SE (<device_id>)  keine Einstellungen
  3) Galaxy S23 (<device_id>)    Eintrag vorhanden, Gerät nicht erreichbar
  ```

- **Transparenz:** beim Start eine Zeile ausgeben, wenn ein Wert aus der Config kommt
  und vom eingebauten Standard abweicht, z. B. `Schwelle für POCO F1: 15 (Config)`.
  Optional `--print-config` für Debugging.

### Abnahmekriterien

- `--device <ID> --threshold 15` wirkt im Lauf und wird im Abschnitt dieses Geräts
  gemerkt; der nächste Aufruf mit derselben ID nutzt 15 und zeigt den Hinweis, dass
  der Wert aus der Config stammt.
- Ein zweites Gerät mit eigenen Werten (`--device <ID2> --threshold 25`) bekommt
  einen eigenen Abschnitt; beide Werte bleiben beim nächsten Lauf getrennt erhalten.
- Kommentare und die Reihenfolge bestehender Abschnitte bleiben beim Schreiben
  unverändert.
- Beim interaktiven Wählen wird ein neuer Abschnitt mit `name` und ID angelegt.
- `--once --threshold 5` wirkt nur in diesem Lauf und lässt die Datei unverändert.
- Ein ungültiger Wert (`threshold=abc`) oder eine unbekannte Sektion erzeugt eine
  Warnung; das Skript läuft mit dem Standard weiter.
- Fehlt die Konfigurationsdatei, bleibt das bisherige Verhalten unverändert.
- Ohne `--device` und ohne Positionsargument wird das zuletzt verwendete Gerät direkt
  benutzt; mit `--choose` erscheint die Auswahlliste.
- Die Auswahlliste nennt je Gerät Name, ID und gespeicherte Werte.
- Ein Gerät mit Eintrag, das nicht erreichbar ist, erzeugt einen Hinweis; der Eintrag
  bleibt beim nächsten Start unverändert erhalten.
