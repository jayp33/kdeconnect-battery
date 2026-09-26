# Testsuite

Tests für `kdeconnect-battery.sh` und `kdeconnect-battery-desktops.sh`.
167 Tests in drei Dateien, ein Lauf dauert etwa anderthalb Minuten.

## Ausführen

```bash
python3 -m venv .venv                              # einmalig
.venv/bin/pip install -r tests/requirements.txt     # einmalig
.venv/bin/pytest                                   # alles
.venv/bin/pytest tests/test_battery.py             # eine Datei
.venv/bin/pytest -k ladewarnung                    # Tests nach Namen
.venv/bin/pytest -m loop                           # nur die Tests mit Schleife
```

`pyproject.toml` setzt `timeout = 120` je Test. Ein Skript, das sich nicht
beendet, lässt den Test also scheitern statt den ganzen Lauf aufzuhängen. Wer
einen Test einzeln laufen lässt und mehr Zeit braucht, erhöht das mit
`--timeout 300`.

Ohne installiertes `desktop-file-validate` wird die Prüfung der erzeugten
Desktop-Dateien übersprungen; die Tests laufen trotzdem durch.

## Aufbau

| Datei | Inhalt |
| --- | --- |
| `harness.py` | Die Klasse `Sandbox`: Verzeichnisse, Umgebung, Attrappen, Skriptaufrufe |
| `conftest.py` | Die Fixture `sandbox` |
| `fakes/bin/` | Attrappen als ausführbare Shell-Skripte |
| `test_battery.py` | Optionen, D-Bus-Auslese, Warnungen, TTS, Sprachen, Geräteauswahl, Schleife |
| `test_desktops.py` | Der Generator für die Starter im Anwendungsmenü |
| `test_regressions.py` | Fehler, die schon einmal aufgetreten sind, mit der Begründung |

`Sandbox` legt pro Test ein temporäres Verzeichnis an (pytest liefert es als
`tmp_path`) und setzt darin `HOME`, `XDG_DATA_HOME` und `XDG_CONFIG_HOME` auf
eigene Pfade. Damit erreicht kein Test die echten Geräte und keiner die
Konfiguration des Benutzers. Am Ende räumt die Fixture auf.

## Erfundene Geräte-IDs

Die Tests kommen ohne die Geräte-IDs des Benutzers aus. `erfundene_id("POCO F1")`
und `erfundene_id_mit_unterstrichen("Redmi Pad SE")` in `harness.py` erzeugen aus
einem lesbaren Namen eine ID in der Form, die KDE-Connect vergibt: 32
Hexadezimalzeichen, teils in der älteren Schreibweise mit Unterstrichen. Aus dem
Keim statt aus `random`, damit derselbe Wert in jedem Lauf und in jedem Protokoll
steht und ein Fehlschlag nachvollziehbar bleibt.

Die Namen der echten Geräte stehen nur in der Wertetabelle von
`kdeconnect-battery-desktops.sh`, weil die Tabelle im Betrieb genau diese Namen
zuordnen muss. Die Tests prüfen diese Tabelle an den Namen.

## PATH und fehlende Programme

Der `PATH` ist `<sandbox>/bin:<Systempfad>`. Die Attrappen liegen also vorn und
werden immer benutzt.

Für Tests, in denen ein Programm **fehlen** soll, genügt es nicht, die Attrappe
zu löschen: Ein auf dem Rechner installiertes `espeak-ng` wäre weiterhin sichtbar
und würde tatsächlich sprechen. Solche Tests rufen `sandbox.use_minimal_path()` auf,
das einen `PATH` nur aus wenigen Grundprogrammen zusammensetzt.

## Die gdbus-Attrappe

`set_status()` schreibt eine Zeile je Abfragepaar in das Format
`<charge> <isCharging>`. Statt einer Zahl stehen dort auch die Schlüsselwörter
`FAIL` (gdbus meldet einen Fehler) und `GARBAGE` (unerwartete Antwort). Die
Antwort wird wahlweise als `(77,)` oder `(<77>,)` ausgegeben, weil gdbus je nach
Version beides liefert; `sandbox.plain_gdbus_answers()` wählt die erste Variante.

Jeder Skriptstart beginnt wieder bei der ersten Zeile und leert die Protokolle
(`reset_fakes`), damit ein Test dasselbe Skript mehrfach starten kann.

Sind alle Zeilen verbraucht, beendet die Attrappe das Überwachungsskript. Sie
bekommt dessen PID über die Datei `stop.pid`, die die Sandbox unmittelbar nach
dem Start befüllt, und wartet dann, bis der Prozess wirklich beendet ist. So
kann ein Test mit Endlosschleife nicht hängen bleiben, auch wenn er `--once`
vergisst, und die erwartete Ausgabe lässt sich genau festlegen, statt mit
Wartezeiten zu arbeiten.

## Tests schreiben

Ein Test ohne Schleife:

```python
def test_lesen_des_akkustands(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", "test-device-0001")

    assert result.status == 0, result.describe()
    assert polls(result) == [(50, False)], result.describe()
```

`polls()` in `test_battery.py` liefert je Abfrage das Paar aus Ladestand und
Ladezustand, `result.describe()` hängt bei einem Fehlschlag Exit-Code, stdout
und stderr an die Meldung.

Ein Test mit Schleife. `--interval 1` verkürzt die Wartezeit auf eine Sekunde je
Abfrage, und die `@pytest.mark.loop`-Markierung grenzt diese Tests ab:

```python
@pytest.mark.loop
def test_warnung_beim_eintritt(sandbox):
    sandbox.set_status("10 false", "10 false", "10 false")

    sandbox.start_battery("--interval", "1", "-d", "test-device-0001", *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig: 10%.") == 1, result.describe()
```

Die interaktive Geräteauswahl braucht ein Terminal, sonst lehnt das Skript sie ab.
`run_pty` öffnet dafür ein Pseudoterminal; `b"\x04"` beendet die Eingabe wie ein
leeres Terminal:

```python
result = sandbox.run_pty(["--once"], b"2\n")
assert "Ausgewähltes Gerät: Tablet B" in result.stdout, result.describe()
```

Bei Argumentprüfungen ist `-d <ID>` wichtig: Ohne `--device` läuft zuerst die
Geräteauswahl, und die Prüfung der Option kommt erst danach.
