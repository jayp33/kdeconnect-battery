# KDE-Connect-Akku überwachen

`kdeconnect-battery.sh` liest den gemeldeten Akkustand eines gekoppelten Geräts über die D-Bus-Schnittstelle von KDE Connect. `kdeconnect-cli` selbst bietet dafür keine Battery-Option. Das Skript verwendet bewusst die ältere, breit kompatible Eigenschaft `charge`; die Eigenschaft `hasBattery` ist erst in neueren KDE-Connect-Versionen vorhanden.

## Voraussetzungen

- KDE Connect läuft auf dem Rechner und das Zielgerät ist gekoppelt.
- Das **Battery monitor**-Plugin auf dem Zielgerät ist aktiviert.
- `gdbus` ist installiert. Auf Debian/Ubuntu genügt dafür normalerweise `libglib2.0-bin`.
- Für TTS wird optional `spd-say`, `espeak-ng` oder `espeak` benötigt.
- Das Skript wird im Benutzerkontext ausgeführt, in dem auch `kdeconnectd` läuft.

## Geräte-ID ermitteln

Die ID wird mit folgendem Befehl angezeigt:

```bash
kdeconnect-cli -l --id-name-only
```

Der erste Teil jeder Zeile ist die ID, die das Skript benötigt. Bei mehreren Geräten sollte die ID ausdrücklich angegeben werden.

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

Die Meldung wird nur einmal ausgelöst, solange der Akkustand unterhalb der Schwelle bleibt. Nach dem Laden über der Schwelle oder während des Ladens wird sie wieder zurückgesetzt.

## Sprachansage (TTS)

TTS ist standardmäßig deaktiviert. Mit `--tts` wird der Status beim Start und bei jeder Änderung von Ladestand oder Ladezustand standardmäßig auf Englisch vorgelesen:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts
```

Bei einem niedrigen Akkustand lautet die englische Ansage beispielsweise:

```text
Warning. The battery level is only 15 percent.
```

Für eine einmalige Testansage:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --once --tts
```

Die Standardsprache ist Englisch. Eine britische Stimme oder Deutsch kann mit `--tts-language` ausgewählt werden:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --tts-language en-GB
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts --tts-language de
```

Mit `--tts-every` wird bei jedem Abfrageintervall gesprochen. Das ist bei kurzen Intervallen entsprechend aufdringlich:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --tts-every --interval 60
```

Das Skript sucht automatisch nach `spd-say`, `espeak-ng` und `espeak` und verwendet dabei die gewählte Sprache. Ein eigenes Kommando kann mit `--tts-command` angegeben werden. Dabei steht der vorbereitete Text in `$BATTERY_TEXT`:

```bash
./kdeconnect-battery.sh \
    --device <GERÄTE-ID> \
    --tts-command 'espeak-ng -v en-us "$BATTERY_TEXT"'
```

Das TTS-Kommando erhält außerdem `DEVICE_ID`, `BATTERY_LEVEL`, `BATTERY_CHARGING`, `BATTERY_LANGUAGE` und `BATTERY_CHARGE_LIMIT`. Es wird über `bash -c` ausgeführt; nur vertrauenswürdige Befehle verwenden.

## Warnung beim Erreichen eines Ladelimits

Mit `--charge-limit` kann eine Ladewarnung aktiviert werden. Die Warnung erscheint, wenn das Gerät noch lädt und der Ladestand den angegebenen Wert erreicht oder überschreitet:

```bash
./kdeconnect-battery.sh --device <GERÄTE-ID> --charge-limit 80
```

`--charge-limit` aktiviert die TTS-Ausgabe automatisch. Die englische Ansage lautet beispielsweise:

```text
Warning. The battery is at 80 percent or higher and is still charging. You can stop charging now.
```

Die Warnung wird pro Episode nur einmal ausgegeben. Sie wird zurückgesetzt, wenn das Gerät vom Ladegerät getrennt wird oder der Ladestand wieder unterhalb des Limits liegt. Mit `--tts-every` wird sie bei jedem Abfrageintervall wiederholt. Das Skript beendet das Laden nicht selbst, sondern informiert lediglich über den erreichten Grenzwert.

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

## Hilfe anzeigen

```bash
./kdeconnect-battery.sh --help
```

## Fehlerbehebung

Wenn das Skript `No such object`, `charge=-1` oder ein anderes D-Bus-Fehler meldet:

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
