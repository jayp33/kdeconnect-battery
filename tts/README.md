# Neuraler TTS über audio.cpp

Dieses Verzeichnis enthält den Dienst und die Server-Konfiguration für eine
Sprachausgabe mit [audio.cpp](https://github.com/0xShug0/audio.cpp) und dem
Modell **Supertonic 3**. `kdeconnect-battery.sh` bleibt dabei unverändert; die
Anbindung erfolgt vollständig über die Option `--tts-command`.

Ausführliche Messungen und die Begründung der Auswahl stehen in
[Issue #1](https://github.com/jayp33/kdeconnect-battery/issues/1).

## Was installiert wird

| Ort | Inhalt | Größe |
|---|---|---:|
| `~/.local/opt/kdeconnect-battery-tts/` | Binary und Bibliotheken | 130 MB |
| `~/.local/share/kdeconnect-battery-tts/models/` | `supertonic-3-f16.gguf` | 299 MB |
| `~/.config/systemd/user/kdeconnect-tts.service` | Dienst | 1 KB |
| `~/.config/kdeconnect-battery-tts/server.json` | Server-Konfiguration | 374 B |

Zusammen rund 430 MB auf der Platte und 260 MB RAM im Betrieb, solange der
Dienst läuft. Ohne die Sprachausgabe wird davon nichts gebraucht.

## Voraussetzungen

- `curl` und `pw-play`. `pw-play` ist über PipeWire bereits vorhanden, sobald KDE
  läuft.
- `systemd --user` ab Version 240 (wegen `Type=exec`).
- Etwa 430 MB freier Platz in `~/.local`.
- Kein GPU, kein Treiber, kein Python.

## Installation

Die folgenden Befehle gehen vom Repository-Wurzelverzeichnis aus, also dem
Verzeichnis mit `kdeconnect-battery.sh`.

### 1. Binary

Aus dem Release `v0.8.2-audio8-perf-hotfix` von audio.cpp. Es ist das
**cpu-portable**-Paket: statisch gelinkt, `backends: cpu`, keine Vulkan- und
keine CUDA-Abhängigkeit.

```sh
mkdir -p ~/.local/opt/kdeconnect-battery-tts
cd ~/.local/opt/kdeconnect-battery-tts

curl -fLO https://github.com/0xShug0/audio.cpp/releases/download/v0.8.2-audio8-perf-hotfix/audio-v0.8.2-audio8-perf-hotfix-bin-ubuntu-x64-cpu-portable.tar.gz

echo "9df1b9744a2d98f757cd7c4be24a14a8f9e4bcdf66571c0b062e767cbe2020b7  audio-v0.8.2-audio8-perf-hotfix-bin-ubuntu-x64-cpu-portable.tar.gz" \
  | sha256sum -c -

tar xzf audio-v0.8.2-audio8-perf-hotfix-bin-ubuntu-x64-cpu-portable.tar.gz
rm audio-v0.8.2-audio8-perf-hotfix-bin-ubuntu-x64-cpu-portable.tar.gz
chmod +x audiocpp_server audiocpp_cli audiocpp_gguf
```

Das `chmod` ist nicht optional: die ausgelieferten Dateien haben kein
Ausführungsbit, der Dienst startet sonst nicht.

### 2. Modell

Das Modell liegt nicht im Release, sondern auf Hugging Face. Es ist auf einen
Commit gepinnt, nicht auf `main`.

```sh
mkdir -p ~/.local/share/kdeconnect-battery-tts/models

curl -fL -o ~/.local/share/kdeconnect-battery-tts/models/supertonic-3-f16.gguf \
  https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/16c271157d4b55e9cb49eb160efc50455e452631/Supertonic-3-GGUF/supertonic-3-f16.gguf

cd ~/.local/share/kdeconnect-battery-tts/models
echo "b312b57797d40ac5c09d915893dbdbaf6405b7dc043f544776c5c95712dff88c  supertonic-3-f16.gguf" \
  | sha256sum -c -
```

> **Nicht `q8_0` nehmen.** Auf Hugging Face ist `supertonic-3-q8_0.gguf` ein
> Byte-Duplikat von `supertonic-3-orig.gguf` (beide 433 MB, gleiche Prüfsumme
> `af814486a0bc9513fb36afabd9b1155ad14fb2c36a107ac6ffe62ea9adafb662`). Die
> Quantisierung hat offenbar nie stattgefunden. `f16` ist die einzige echte
> Variante und die einzige, die hier gemessen ist.

### 3. Konfiguration und Verknüpfung

```sh
mkdir -p ~/.config/kdeconnect-battery-tts
install -m644 tts/server.json ~/.config/kdeconnect-battery-tts/server.json
ln -sfn ~/.local/share/kdeconnect-battery-tts/models ~/.config/kdeconnect-battery-tts/models
```

**Warum ein Symlink:** `audiocpp_server` löst relative Pfade in der
Konfiguration gegen das Verzeichnis der **Konfigurationsdatei** auf, nicht
gegen das Arbeitsverzeichnis des Prozesses. Ein `WorkingDirectory=` im Dienst
ändert daran nichts. `$HOME` wird im Pfad ebenfalls nicht expandiert. Deshalb
steht in `server.json` nur `models`, und der Symlink legt genau dieses
Verzeichnis neben die Konfigurationsdatei. So bleibt die Datei im Repository
und auf dem Rechner identisch.

### 4. Dienste

```sh
install -m644 tts/kdeconnect-tts.service ~/.config/systemd/user/kdeconnect-tts.service
systemctl --user daemon-reload
systemctl --user enable --now kdeconnect-tts.service
```

### 5. Sprachskript

```sh
install -Dm755 tts/kdeconnect-speak ~/.local/bin/kdeconnect-speak
```

Das Skript ist für den Aufruf als `--tts-command` gedacht, also für alle Fälle,
in denen der Befehl in einer `.desktop`-Zeile steht. Auf der Kommandozeile
genügt auch der direkte curl-Aufruf, siehe unten.

## Verwendung im Skript

### Auf der Kommandozeile

```sh
kdeconnect-battery.sh --tts --tts-language de \
  --tts-command 'curl -sS --retry-connrefused --retry 5 --retry-delay 1 --retry-all-errors -X POST http://127.0.0.1:8099/v1/audio/speech -H "Content-Type: application/json" -d "{\"model\":\"supertonic-3\",\"input\":\"$BATTERY_TEXT\",\"voice\":\"M1\",\"language\":\"$BATTERY_LANGUAGE\",\"response_format\":\"wav\"}" -o "$XDG_RUNTIME_DIR/kdc-tts-$DEVICE_ID.wav" && pw-play "$XDG_RUNTIME_DIR/kdc-tts-$DEVICE_ID.wav"'
```

`kdeconnect-battery-desktops.sh --extra` kann dieselbe Zeile an die erzeugten
Starter weiterreichen.

Zu den vier Bestandteilen:

- **`$BATTERY_TEXT` und `$BATTERY_LANGUAGE`** setzt `speak_text()` bereits. Die
  Sprachkürzel sind genau die, die das Skript gegen `--tts-language` prüft.
- **`$DEVICE_ID` im Dateinamen ist nicht optional.** Es läuft ein Prozess je
  Gerät gleichzeitig, und `curl -o` legt die Datei bei Verbindungsaufbau an und
  füllt sie über die ganze Antwort. Ein fester Name lässt zwei gleichzeitig
  warnende Geräte abgeschnittenes Audio hören. Gemessen: 20 KiB von 100 KiB
  gelesen. `$DEVICE_ID` ist laut `--device` eine KDE-Connect-Geräte-ID und damit
  aus `[A-Za-z0-9_]` aufgebaut.
- **`--retry-connrefused`** ist nötig, weil der Dienst den Port erst nach dem
  Laden des Modells öffnet, gemessen nach 4,77 s. Ohne Wiederholung ginge eine
  Warnung in diesem Fenster still verloren. Im Normalfall kostet die Option
  nichts.
- **Kein `jq`, keine Zeilenumbrüche.** Die Projekttexte enthalten keine
  Anführungszeichen und keine Backslashes, die direkte JSON-Interpolation ist
  deshalb sicher. Umlaute kommen als UTF-8 durch, geprüft.

### In einem .desktop-Starter

Hier ist der direkte curl-Aufruf **nicht** möglich. Die `Exec=`-Zeile wird nicht
von einer Shell interpretiert, sondern nach der Desktop-Entry-Spezifikation
geparst: Leerzeichen trennen Argumente, `"` öffnet einen zitierten Abschnitt,
`\` maskiert das nächste Zeichen, und `%` muss als `%%` geschrieben werden.
Ein für die Shell geschriebener Befehl ist dort eine ungültige Datei.

Nachgemessen mit beiden Varianten, `gio launch` auf eine erzeugte Testdatei:

| Variante | Ergebnis |
|---|---|
| curl-Aufruf in `Exec` | `gio` verweigert die Datei: *„Informationen zur Anwendung können nicht geladen werden“* |
| Pfad zu `kdeconnect-speak` | startet, erzeugt 410.600 B WAV |

`desktop-file-validate` meldet für die erste Variante vier Fehler, darunter
*„reserved character `'` outside of a quote"* und dreimal *„non-escaped
character `$` in a quote, but it should be escaped with two backslashes"*.
Die zweite Variante ist fehlerfrei.

Deshalb gehört in die Starter nur der Pfad:

```bash
# in kdeconnect-battery-desktops.sh, damit nicht jedes Gerät es wiederholen muss
tts_befehl="--tts-command $HOME/.local/bin/kdeconnect-speak"
device_table=(
    "POCO F1|$tts_befehl"
    "Redmi Pad SE|--charge-limit 70 $tts_befehl"
    "POCO X3 Pro|--charge-limit 70 $tts_befehl"
)
```

Die Einträge müssen doppelt in Anführungszeichen stehen, damit die Variable
beim Erzeugen der Starter expandiert wird. Anschließend die Starter neu
erzeugen, sonst behalten die alten Dateien weiterhin nur `--tts --tts-language de`
und damit `espeak-ng`.

**Achtung, nicht erreichbare Geräte:** Der Generator schreibt nur Einträge für
Geräte, die gerade erreichbar sind, und meldet die übrigen Tabellenzeilen als
*Hinweis*. Ein ausgefallenes Gerät behält damit seine alte Datei und deren alte
Argumente. Nach einer Umstellung also jede `.desktop`-Datei prüfen, nicht nur die
neu geschriebenen:

```sh
grep -L tts-command ~/.local/share/applications/kdeconnect-akku-*.desktop
```

Findet die Datei noch einen alten Stand, lässt sie sich von Hand auf denselben
Stand bringen, den der Generator schreiben würde, oder das Gerät später
erreichbar machen und den Generator erneut laufen lassen.

## Verhalten

**Ein Server für alle Geräte.** Der Dienst wird von systemd gestartet, nicht vom
Skript. Die Starter laufen beim Anmelben gleichzeitig; würde jeder davon den
Server hochfahren, gäbe es drei Modelle im Speicher und einen Bind-Konflikt auf
Port 8099.

**Lebensdauer wie `pipewire.service`.** `Slice=session.slice` und
`WantedBy=default.target` sind dem Muster von PipeWire nachempfunden. `Linger`
steht auf `no`, der Dienst endet also mit der Sitzung. Das ist Absicht: nach
dem Abmelden gibt es keinen Aufrufer mehr, und `pw-play` könnte ohnehin nichts
abspielen. **Lingering nicht einschalten.**

**Gleichzeitige Anfragen werden gereiht, nicht parallel ausgeführt.** Drei
gleichzeitige POSTs ergaben HTTP 200 in 5,42 s, 7,24 s und 8,89 s — die
Differenzen sind die Einzelaufträge. Ein zweiter paralleler Durchlauf auf
demselben Modell ist nicht vorgesehen, die Warteschlange ist der Schutz.

**Das Modell bleibt im Speicher.** `lazy_load: false` und
`idle_unload_ms: 0`. Akkuwarnungen entstehen Stunden auseinander; jede
Idle-Abschaltung würde den Kaltstart von 4,8 s erneut auslösen. 260 MB RAM auf
einem Rechner mit 62 GiB sind ein vertretbares Verhältnis.

**Ohne Server läuft es weiter.** Der curl-Aufruf schlägt fehl, `speak_text()`
meldet das auf stderr und der Überwachungsablauf läuft weiter. Nachgewiesen
durch `test_tts_befehlsfehler_wird_gemeldet`.

## Prüfen

```sh
systemctl --user status kdeconnect-tts.service
curl -s http://127.0.0.1:8099/health
journalctl --user -u kdeconnect-tts.service -f
```

`/health` liefert `{"status":"ok","backend":"cpu","models":1,…}`. Das ist die
belastbare Aussage, nicht `systemctl status`: Der Dienst meldet sich bei systemd
nicht mit einer Fertigkeitsmeldung und gilt deshalb rund 4,8 s nach dem Start
als aktiv, bevor der Port offen ist.

## Wenn etwas nicht stimmt

| Symptom | Ursache |
|---|---|
| `model path does not exist: …/models` | Symlink aus Schritt 3 fehlt |
| `Failed with result 'exit-code'`, Port zu | Modell nicht geladen, `journalctl` zeigt den Grund |
| Dienst startet nicht, `Permission denied` | `chmod +x` aus Schritt 1 fehlt |
| Kein Ton, aber Datei wird geschrieben | `pw-play` oder PipeWave, nicht der TTS-Dienst |
| Sehr langsame Aussprache | Backends prüfen: `audiocpp_server --version` muss `backends: cpu` zeigen |

Der Dienst startet nach drei Fehlversuchen in fünf Minuten nicht erneut
(`StartLimitBurst=3`), damit ein fehlendes Modell keine Endlos-Schleife
erzeugt. Nach dem Beheben: `systemctl --user reset-failed kdeconnect-tts.service`.

## Lizenzen

- **audio.cpp: Apache-2.0.** Die vollständige Lizenz liegt nach Schritt 1 als
  `LICENSE` in `~/.local/opt/kdeconnect-battery-tts/`.
- **Supertonic 3: BigScience OpenRAIL-M**, abweichend von Apache-2.0. Das Modell
  bringt eigene Bedingungen mit, die vor einer weitergehenden Verwendung zu
  prüfen sind. Für den privaten Einsatz als Sprachwarnung unproblematisch.

Beide Komponenten werden nicht mit dem Skript ausgeliefert, sondern sind
getrennt herunterzuladen. Das Skript selbst bleibt davon unabhängig.
