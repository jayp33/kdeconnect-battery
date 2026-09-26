# KDE-Connect-Akku überwachen

`kdeconnect-battery.sh` liest den gemeldeten Akkustand eines gekoppelten Geräts über die D-Bus-Schnittstelle von KDE Connect. `kdeconnect-cli` selbst bietet dafür keine Battery-Option. Das Skript verwendet bewusst die ältere, breit kompatible Eigenschaft `charge`; die Eigenschaft `hasBattery` ist erst in neueren KDE-Connect-Versionen vorhanden.

## Voraussetzungen

- KDE Connect läuft auf dem Rechner und das Zielgerät ist gekoppelt.
- Das **Battery monitor**-Plugin auf dem Zielgerät ist aktiviert.
- `gdbus` ist installiert. Auf Debian/Ubuntu genügt dafür normalerweise `libglib2.0-bin`.
- Für die automatische Geräteauswahl ohne `--device` wird zusätzlich `kdeconnect-cli` benötigt.
- Für TTS wird optional `spd-say`, `espeak-ng` oder `espeak` benötigt.
- Für eine neutralere Stimme kann stattdessen der Dienst aus [`tts/`](tts/README.md) verwendet werden. Er bringt zusätzlich `curl`, `pw-play` und rund 430 MB Modelldatei mit.
- Das Skript wird im Benutzerkontext ausgeführt, in dem auch `kdeconnectd` läuft.

## Gerät auswählen

Wird das Skript ohne `--device` gestartet, fragt es automatisch die erreichbaren KDE-Connect-Geräte ab und zeigt eine nummerierte Liste:

```bash
./kdeconnect-battery.sh
```

Beispiel:

```text
Verfügbare KDE-Connect-Geräte:
  1) POCO F1 (ID: ...)
  2) Redmi Pad SE (ID: ...)
  3) POCO X3 Pro (ID: ...)
Gerät auswählen [1-3, Enter = 1]:
```

Die Eingabe `1`, `2` oder `3` wählt das entsprechende Gerät aus. Eine leere Eingabe wählt das erste Gerät. Für nicht-interaktive Aufrufe, Cronjobs oder Skripte sollte weiterhin `--device <GERÄTE-ID>` angegeben werden.

Die Liste lässt sich auch manuell abfragen:

```bash
kdeconnect-cli --list-available --id-name-only
```

## Einmaliger Status

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --once
```

Die Ausgabe sieht beispielsweise so aus:

```text
2026-09-25 14:32:10  87%, charging=false
```

## Dauerhafte Überwachung

Standardmäßig wird alle 60 Sekunden abgefragt. Bei einem Ladestand unter 20 Prozent wird eine Meldung ausgegeben:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID>
```

Schwellenwert und Abfrageintervall ändern:

```bash
./kdeconnect-battery.sh \
    --device <GERÄTE-ID> \
    --threshold 25 \
    --interval 30
```

Die Meldung wird nur einmal ausgelöst, solange der Akkustand unterhalb der Schwelle bleibt. Nach dem Laden über der Schwelle oder während des Ladens wird sie wieder zurückgesetzt. Per Sprachausgabe wird die Warnung dagegen bei jeder Prozentänderung wiederholt, siehe [Sprachansage](#sprachansage-tts).

## Sprachansage (TTS)

TTS ist standardmäßig deaktiviert. Mit `--tts` werden standardmäßig nur Warnungen vorgelesen: Unterladewarnungen, Überladewarnungen und Verbindungsänderungen. Normale Statusansagen werden nicht gesprochen.

Warnungen werden dabei nicht nur beim Eintritt in den Warnzustand gesprochen, sondern bei jeder Änderung des Prozentwerts wiederholt, jeweils mit dem aktuellen Stand. Ohne Prozentänderung bleibt es still, sonst würde alle 60 Sekunden dasselbe gesprochen.

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts
```

Bei einem niedrigen Akkustand lautet die englische Warnansage beispielsweise:

```text
Warning. The battery level is only 15 percent.
```

Die Unterladewarnung wird gesprochen, wenn der Gerätestatus in den Warnbereich wechselt, und bei jeder weiteren Änderung des Prozentwerts wiederholt. Ein kurzer Test funktioniert mit:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --once --tts
```

Mit `--tts-every-percent` werden zusätzlich normale Statusansagen beim ersten Ablesen und bei jeder Änderung des Prozentwerts ausgegeben. Ein Wechsel des Ladezustands allein genügt dabei nicht. An den Warnungen ändert die Option nichts, die wiederholen sich bereits so:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts-every-percent
```

Die Standardsprache ist Englisch. Eine britische Stimme oder Deutsch kann mit `--tts-language` ausgewählt werden:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --tts-language en-GB
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --tts-language de
```

Mit `--tts-every` wird auch ohne Änderung des Prozentwerts bei jedem Abfrageintervall gesprochen, auch von den Warnungen. Das ist bei kurzen Intervallen entsprechend aufdringlich:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts-every --interval 60
```

Das Skript sucht automatisch nach `spd-say`, `espeak-ng` und `espeak` und verwendet dabei die gewählte Sprache. Ein eigenes Kommando kann mit `--tts-command` angegeben werden. Dabei steht der vorbereitete Text in `$BATTERY_TEXT`:

```bash
./kdeconnect-battery.sh \
    --device <GERÄTE-ID> \
    --tts-command 'espeak-ng -v en-us "$BATTERY_TEXT"'
```

Das TTS-Kommando erhält außerdem `DEVICE_ID`, `BATTERY_LEVEL`, `BATTERY_CHARGING`, `BATTERY_LANGUAGE`, `BATTERY_CHARGE_LIMIT` und `BATTERY_CONNECTION` (`connected` oder `disconnected`). Es wird über `bash -c` ausgeführt; nur vertrauenswürdige Befehle verwenden.

### Neutrale Stimme mit audio.cpp

`espeak-ng` klingt synthetisch. Wer eine deutlich natürlichere Stimme möchte,
ohne Python oder eine GPU einzusetzen, kann [audio.cpp](https://github.com/0xShug0/audio.cpp)
mit dem Modell Supertonic 3 als lokalen Dienst betreiben. Das Skript bleibt
dabei unverändert, die Anbindung läuft vollständig über `--tts-command`.

Die vollständige Anleitung mit Installation, Prüfsummen und Diensteinrichtung
steht in [`tts/README.md`](tts/README.md). Kurzfassung:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --tts-language de \
  --tts-command 'curl -sS --retry-connrefused --retry 5 --retry-delay 1 --retry-all-errors -X POST http://127.0.0.1:8099/v1/audio/speech -H "Content-Type: application/json" -d "{\"model\":\"supertonic-3\",\"input\":\"$BATTERY_TEXT\",\"voice\":\"M1\",\"language\":\"$BATTERY_LANGUAGE\",\"response_format\":\"wav\"}" -o "$XDG_RUNTIME_DIR/kdc-tts-$DEVICE_ID.wav" && pw-play "$XDG_RUNTIME_DIR/kdc-tts-$DEVICE_ID.wav"'
```

Beides gleichzeitig geht nicht sinnvoll: ist `--tts-command` gesetzt, wird die
Automatik aus `spd-say`/`espeak-ng`/`espeak` nicht mehr verwendet. Fällt der
Dienst aus, meldet das Skript den Fehler und läuft unter `--tts` ohne Stimme
weiter.

## Warnung beim Erreichen eines Ladelimits

Das Ladelimit ist standardmäßig auf 80 Prozent gesetzt. Die Überladewarnung erscheint, wenn das Gerät noch lädt und der Ladestand 80 Prozent oder mehr beträgt:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts
```

Ein anderes Limit kann mit `--charge-limit` angegeben werden:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --charge-limit 90
```

Mit `--charge-limit 0` wird die Überladewarnung deaktiviert. Ein explizit gesetzter Wert größer als 0 aktiviert die TTS-Ausgabe automatisch.

Die englische Ansage nennt den aktuellen Ladestand und das Limit, zum Beispiel:

```text
Warning. The battery is at 85 percent, above the 80 percent limit, and is still charging. You can stop charging now.
```

Die Terminalmeldung erscheint pro Episode einmal. Gesprochen wird die Warnung dagegen bei jeder Änderung des Prozentwerts, und jede Ansage nennt den dann aktuellen Ladestand; mit `--tts-every` bei jedem Abfrageintervall. Die Warnung wird zurückgesetzt, wenn das Gerät vom Ladegerät getrennt wird oder der Ladestand wieder unterhalb des Limits liegt. Das Skript beendet das Laden nicht selbst, sondern informiert lediglich über den erreichten Grenzwert.

Die Unterladewarnung nutzt dagegen `--threshold` (Standard: 20 Prozent). Mit `--threshold 0` wird sie deaktiviert. So lassen sich beide Warnungen unabhängig kombinieren:

```bash
# Nur Unterladewarnung
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --charge-limit 0 --threshold 15

# Beide Warnungen
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --threshold 15 --charge-limit 80
```

## Verbindungsfehler

Wenn das Gerät während der Überwachung nicht mehr erreichbar ist, wird die technische D-Bus-Fehlermeldung nicht mehr bei jeder Abfrage ausgegeben. Stattdessen erscheint eine kurze Meldung mit dem nächsten Versuchszeitpunkt:

```text
2026-09-25 13:00:23  KDE-Connect-Gerät ist nicht erreichbar. Der nächste Versuch erfolgt in 60 Sekunden.
```

Während TTS aktiviert ist, wird der Verbindungsverlust einmal zusätzlich vorgelesen:

```text
The connection to the device was lost. I will try again.
```

Nach einer erfolgreichen Abfrage erscheint eine Wiederherstellungsmeldung; auch diese wird bei aktivem TTS einmal gesprochen. Wiederholte Fehlversuche bleiben ohne zusätzliche Sprachansage, bis die Verbindung wiederhergestellt ist. Für eine deutsche Sprachausgabe kann `--tts-language de` verwendet werden.

## Eigene Aktion ausführen

Mit `--command` kann bei einem neuen niedrigen Akkustand ein Shell-Befehl ausgeführt werden. Der Befehl sollte in Anführungszeichen gesetzt werden:

```bash
./kdeconnect-battery.sh \
    --device <GERÄTE-ID> \
    --threshold 20 \
    --command 'notify-send "KDE Connect" "Akku nur noch $BATTERY_LEVEL%"'
```

Der Befehl erhält folgende Umgebungsvariablen:

- `DEVICE_ID`: KDE-Connect-Geräte-ID
- `BATTERY_LEVEL`: aktueller Ladestand als Zahl
- `BATTERY_CHARGING`: `true` oder `false`

`--command` führt den angegebenen Text absichtlich als Shell-Befehl aus. Nur Befehle verwenden, denen man vertraut.

## Starter im Anwendungsmenü

`kdeconnect-battery-desktops.sh` erzeugt für jedes erreichbare Gerät einen
`.desktop`-Eintrag, über den die Überwachung per Mausklick startet. Die
gerätespezifischen Werte stehen dabei in der Tabelle `device_table` im Skript:

```bash
device_table=(
    "POCO F1|"
    "Redmi Pad SE|--charge-limit 70"
    "POCO X3 Pro|--charge-limit 70"
)
```

Die Zuordnung erfolgt zuerst über die Geräte-ID, danach über den Namen – beides ohne
Beachtung der Groß-/Kleinschreibung. Was links vom `|` steht, sind beliebige weitere
Optionen für `kdeconnect-battery.sh`; ein Gerät ohne Eintrag erhält die Standardwerte.
Für alle Geräte gilt im Generator `--tts --tts-language de`.

```bash
# Nur ansehen, was passieren würde
./kdeconnect-battery-desktops.sh --dry-run

# Nur Geräte und ihre Optionen auflisten
./kdeconnect-battery-desktops.sh --list

# Starter erzeugen (Standard: ~/.local/share/applications)
./kdeconnect-battery-desktops.sh
```

Weitere Optionen: `--output-dir VERZEICHNIS` für ein anderes Ziel und
`--script PFAD`, falls `kdeconnect-battery.sh` woanders liegt. Die erzeugten Dateien
werden mit `desktop-file-validate` geprüft; danach wird der KDE-Systembereich
aktualisiert, sodass die Einträge im Menü erscheinen. Beenden lässt sich die
Überwachung durch Schließen des Terminalfensters.

Hinweise des Generators:

- Ein Tabelleneintrag, der zu keinem erreichbaren Gerät passt, wird gemeldet.
- Geräte mit gleichem Namen sind nicht eindeutig; die Dateinamen bekommen dann ein
  Kürzel der Geräte-ID angehängt, und es erscheint eine Empfehlung, den
  Tabelleneintrag auf die ID umzustellen.
- Dateien werden überschrieben, aber nie gelöscht. Starter für Geräte, die es nicht
  mehr gibt, bleiben deshalb liegen und müssen bei Bedarf von Hand entfernt werden.

Weil jede Instanz genau ein Gerät überwacht, bleibt es auch mit Konfigurationsdatei
bei einem Starter je Gerät. Was dann entfällt, ist die Tabelle im Generator: Die Werte
stehen dann in der Konfiguration, und die `Exec`-Zeilen enthalten nur noch
`--device <GERÄTE-ID>`.

Wer mehrere Geräte gleichzeitig überwachen will, startet die Starter einfach
mehrfach. Die Instanzen laufen unabhängig; nur bei der Sprachausgabe kann es zu
Überschneidungen kommen, wenn zwei Geräte im selben Moment warnen.

## Hilfe anzeigen

```bash
./kdeconnect-battery.sh --help
```

## Fehlerbehebung

Wenn das Skript `KDE-Connect-Gerät ist nicht erreichbar` meldet, `charge=-1` anzeigt oder eine `Unerwartete Antwort von gdbus für …` schreibt:

1. Mit `kdeconnect-cli -l` prüfen, ob das Gerät noch gekoppelt und erreichbar ist.
2. Auf dem Zielgerät prüfen, ob der Battery monitor aktiviert ist.
3. KDE Connect auf beiden Seiten aktualisieren bzw. das Gerät neu verbinden.
4. Prüfen, ob die verwendete ID wirklich die ID des gewünschten Geräts ist.
5. Die beiden Eigenschaften direkt testen:

```bash
ID=<GERÄTE-ID>
P="/modules/kdeconnect/devices/$ID/battery"

gdbus call --session --dest org.kde.kdeconnect \
  --object-path "$P" \
  --method org.freedesktop.DBus.Properties.Get \
  org.kde.kdeconnect.device.battery charge

gdbus call --session --dest org.kde.kdeconnect \
  --object-path "$P" \
  --method org.freedesktop.DBus.Properties.Get \
  org.kde.kdeconnect.device.battery isCharging
```

Die erste Ausgabe sollte eine Zahl zwischen 0 und 100 sein. Die zweite sollte `true` oder `false` liefern. Das Skript benötigt genau diese beiden älteren Eigenschaften und nicht `hasBattery`, damit es auch mit älteren KDE-Connect-Versionen funktioniert.

Für eine einzelne manuelle D-Bus-Abfrage kann alternätzlich folgender Befehl verwendet werden:

```bash
ID=<GERÄTE-ID>
gdbus call --session \
  --dest org.kde.kdeconnect \
  --object-path "/modules/kdeconnect/devices/$ID/battery" \
  --method org.freedesktop.DBus.Properties.GetAll \
  org.kde.kdeconnect.device.battery
```

## TTS-Fehlerbehebung

Wenn `--tts` mit `Kein TTS-Programm gefunden` abbricht, installiere beispielsweise `espeak-ng` oder verwende ein vorhandenes Kommando:

```bash
sudo apt install espeak-ng
```

Der Audioausgabe muss zusätzlich im Benutzerkonto aktiviert sein. Mit einem eigenen Kommando kann die Ausgabe getestet werden:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --once --tts \
    --tts-command 'espeak-ng -v en-us "$BATTERY_TEXT"'
```

Das Skript liest den Akkustand des **entfernten Geräts**. Für den Akku des lokalen Rechners ist dieser D-Bus-Pfad nicht gedacht.

## Tests

Beide Skripte sind mit einer Testsuite abgesichert. Sie braucht nur Python mit `pytest`; Hilfsprogramme wie `gdbus`, `kdeconnect-cli` oder Sprachausgabe liefert die Suite selbst als Attrappen mit. Jeder Test läuft in einem eigenen temporären Verzeichnis mit eigenem `PATH` und eigenem `HOME`. Weder echte Geräte noch die Benutzerumgebung können ein Testergebnis beeinflussen, und kein Test erzeugt Ton.

```bash
python3 -m venv .venv                          # einmalig
.venv/bin/pip install -r tests/requirements.txt # einmalig
.venv/bin/pytest                               # alle Tests
```

Ein Lauf dauert etwa anderthalb Minuten. Aufbau der Suite, das Auswählen einzelner Tests und Beispiele zum Schreiben neuer Tests stehen in [tests/README.md](tests/README.md).
