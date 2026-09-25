"""Regressionstests: Fehler, die in kdeconnect-battery.sh und
kdeconnect-battery-desktops.sh schon einmal aufgetreten sind. Der Kommentar
über jedem Test nennt den Fehler, der vermieden werden soll.
"""

from __future__ import annotations

import pytest

from harness import erfundene_id, erfundene_id_mit_unterstrichen

DEVICE = "test-device-0001"
# Erfundene Geräte-IDs, keine echten (siehe harness.erfundene_id).
ID1 = erfundene_id("POCO F1")
ID2 = erfundene_id_mit_unterstrichen("Redmi Pad SE")

pytestmark = pytest.mark.usefixtures("sandbox")


# ======================================================================
# kdeconnect-battery.sh
# ======================================================================


def test_ergebnis_aus_funktion_bleibt_erhalten(sandbox):
    """Fehler: Das Ergebnis von gdbus wurde in einer Befehlsersetzung
    ausgewertet, wodurch die Zuweisung in einer Subshell verschwand und der
    Wert leer blieb."""
    sandbox.set_status("77 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert any("77%, charging=false" in line for line in result.status_lines), result.describe()


@pytest.mark.parametrize("plain", [True, False], ids=["ohne-klammern", "mit-klammern"])
def test_beide_variantenformate(sandbox, plain):
    """Fehler: gdbus liefert je nach Version "(77,)" oder "(<77>,)". Beide
    Formen müssen entpackt werden."""
    sandbox.set_status("33 true")
    if plain:
        sandbox.plain_gdbus_answers()

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert any("33%, charging=true" in line for line in result.status_lines), result.describe()


def test_charge_minus_eins(sandbox):
    """Fehler: charge=-1 wurde als Ladestand behandelt und ergab "-1%"."""
    sandbox.set_status("-1 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert "noch kein gültiger Akkustand gemeldet (charge=-1)" in result.stdout, result.describe()
    assert "-1%" not in result.stdout, result.describe()


def test_has_battery_wird_nicht_abgefragt(sandbox):
    """Fehler: hasBattery wurde abgefragt. Die Eigenschaft fehlt in älteren
    KDE-Connect-Versionen, wodurch die Abfrage fehlschlug."""
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert sandbox.gdbus_properties() == ["charge", "isCharging"]
    assert "hasBattery" not in sandbox.gdbus_log.read_text()


@pytest.mark.loop
def test_null_als_ausschaltwert(sandbox):
    """Fehler: 0 wurde als "sofort unterhalb" gelesen, wodurch jedes Gerät
    dauerhaft warnte. 0 muss die Warnung abschalten."""
    sandbox.set_status("5 true", "99 true")

    sandbox.start_battery(
        "-d", DEVICE, "--interval", "1",
        "--threshold", "0", "--charge-limit", "0",
        "--tts-command", str(sandbox.bin / "fake-tts"),
    )
    result = sandbox.wait_battery()

    assert "Akkustand niedrig" not in result.stdout, result.describe()
    assert "Ladewarnung" not in result.stdout, result.describe()
    assert sandbox.tts_count() == 0


def test_geraete_id_wird_nicht_ausgewertet(sandbox):
    """Fehler: Die Geräte-ID wurde ungeprüft in eine Subshell eingesetzt,
    wodurch Sonderzeichen ausgeführt wurden."""
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", "x; echo HACKED; y")

    assert result.status == 0, result.describe()
    assert "HACKED" not in result.output, result.describe()
    assert f"/modules/kdeconnect/devices/x; echo HACKED; y/battery" in sandbox.gdbus_paths()


@pytest.mark.loop
def test_zaehler_wird_nach_verbindungsverlust_zurueckgesetzt(sandbox):
    """Fehler: Nach einem Verbindungsverlust blieb der Warnzähler stehen,
    sodass die Warnung nach der Rückkehr des Geräts ausblieb."""
    sandbox.set_status("10 false", "FAIL false", "10 false")

    sandbox.start_battery("-d", DEVICE, "--interval", "1")
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig: 10%.") == 2, result.describe()
    assert result.stdout.count("nicht erreichbar") == 1, result.describe()
    assert "Verbindung zum Gerät wiederhergestellt." in result.stdout, result.describe()


def test_ladewarnung_nennt_stand_und_limit(sandbox):
    """Fehler: Die Überladewarnung nannte nur den Ladestand, nicht das Limit.
    Ohne Limit war nicht erkennbar, wann geladen werden soll."""
    sandbox.set_status("83 true")

    result = sandbox.run_battery(
        "--once", "-d", DEVICE,
        "--charge-limit", "80",
        "--tts-language", "de",
        "--tts-command", str(sandbox.bin / "fake-tts"),
    )

    assert result.status == 0, result.describe()
    assert (
        "Ladewarnung: Der Akku ist bei 83% (Ladelimit: 80%) und lädt noch."
        in result.stdout
    ), result.describe()
    assert any(
        "Der Akku ist bei 83 Prozent, über dem Ladelimit von 80 Prozent" in text
        for text in sandbox.tts_texts()
    ), sandbox.tts_texts()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--once"], 0),
        (["--once", "--threshold", "200"], 2),
        (["--once", "--quatsch"], 2),
    ],
)
def test_exit_codes(sandbox, args, expected):
    """Fehler: Die Exit-Codes waren nicht festgelegt. 0 = Erfolg,
    2 = Aufruffehler. Ein Gerät, das nicht antwortet, ergibt 1."""
    sandbox.set_status("50 false")
    result = sandbox.run_battery(*args, "-d", DEVICE)
    assert result.status == expected, result.describe()

    sandbox.set_status("FAIL false")
    result = sandbox.run_battery(*args, "-d", DEVICE)
    assert result.status == (1 if expected == 0 else expected), result.describe()


@pytest.mark.loop
def test_deutsche_texte_nennen_den_akku(sandbox):
    """Fehler: Die deutschen Texte enthielten "Batteriestatus" statt "Akku"."""
    sandbox.set_status("50 true", "85 true")

    sandbox.start_battery(
        "-d", DEVICE, "--interval", "1",
        "--tts-every", "--tts-language", "de",
        "--tts-command", str(sandbox.bin / "fake-tts"),
    )
    sandbox.wait_battery()

    spoken = "\n".join(sandbox.tts_texts())
    assert "Der Akku wird geladen. Akkustand 50 Prozent." in spoken, spoken
    assert "Achtung. Der Akku ist bei 85 Prozent" in spoken, spoken
    assert "Batterie" not in spoken, spoken


def test_kein_festes_sprachprogramm(sandbox):
    """Fehler: Ein fest verdrahtetes Sprachprogramm (spd-say) brach auf
    Systemen ohne speech-dispatcher ab. Die Wahl muss der Installation folgen."""
    sandbox.add_engine("spd-say")
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every")
    assert result.status == 0, result.describe()
    assert "-l en-us" in sandbox.engine_log.read_text(), "spd-say wird zuerst verwendet"

    # Ohne spd-say muss das nächste Programm in der Kette genommen werden.
    (sandbox.bin / "spd-say").unlink()
    sandbox.set_status("50 false")
    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every")
    assert result.status == 0, result.describe()
    assert "-v en-us" in sandbox.engine_log.read_text(), "espeak-ng wird danach verwendet"


# ======================================================================
# kdeconnect-battery-desktops.sh
# ======================================================================


def test_exec_ohne_prozentzeichen(sandbox):
    """Fehler: Ein "%" in der Exec-Zeile gilt in Desktop-Dateien als Feldcode
    (%f, %u). Der Ladestand gehört nicht in die Exec-Zeile, ein Prozentzeichen
    dort bricht den Starter."""
    sandbox.set_devices(f"{ID1} POCO F1", f"{ID2} Redmi Pad SE")

    result = sandbox.run_desktops("-o", str(sandbox.data / "applications"))
    assert result.status == 0, result.describe()

    files = sandbox.desktop_files(sandbox.data / "applications")
    assert len(files) == 2
    for path in files:
        assert "%" not in path.read_text(encoding="utf-8"), f"{path.name} enthält ein %"


def test_tabelle_aendert_nur_werte(sandbox):
    """Fehler: Ein Tabelleneintrag ohne passendes Gerät legte einen leeren
    Starter an. Die Tabelle ändert nur Werte, nicht die Anzahl der Starter."""
    sandbox.set_devices(f"{ID1} POCO F1")

    result = sandbox.run_desktops("-o", str(sandbox.data / "applications"))
    assert result.status == 0, result.describe()

    files = sandbox.desktop_files(sandbox.data / "applications")
    assert [path.name for path in files] == ["kdeconnect-akku-poco-f1.desktop"]


def test_gleichnamige_geraete_ueberschreiben_nicht(sandbox):
    """Fehler: Zwei gleichnamige Geräte erzeugten denselben Dateinamen; der
    zweite überschrieb den ersten."""
    sandbox.set_devices("aaaa1111 Smartphone", "bbbb2222 Smartphone")

    result = sandbox.run_desktops("-o", str(sandbox.data / "applications"))
    assert result.status == 0, result.describe()

    out = sandbox.data / "applications"
    files = sandbox.desktop_files(out)
    assert len(files) == 2, [path.name for path in files]
    assert "--device aaaa1111" in (out / "kdeconnect-akku-smartphone-aaaa11.desktop").read_text()
    assert "--device bbbb2222" in (out / "kdeconnect-akku-smartphone-bbbb22.desktop").read_text()


def test_dateiname_ohne_fuehrenden_bindestrich(sandbox):
    """Fehler: Ein führendes Sonderzeichen im Gerätenamen blieb als Bindestrich
    im Dateinamen stehen ("kdeconnect-akku--name.desktop")."""
    sandbox.set_devices(f"{ID1} (2024) Tablet")

    result = sandbox.run_desktops("-o", str(sandbox.data / "applications"))
    assert result.status == 0, result.describe()

    names = [path.name for path in sandbox.desktop_files(sandbox.data / "applications")]
    assert names == ["kdeconnect-akku-2024-tablet.desktop"]


def test_generator_endet_auch_bei_kurzen_ids(sandbox):
    """Fehler: Bei gleichem Namen und gleichem ID-Anfang suchte der Generator
    unendlich nach einem längeren ID-Kürzel und blieb hängen."""
    sandbox.set_devices("ab Smartphone", "ab Smartphone")

    result = sandbox.run_desktops("-o", str(sandbox.data / "applications"))
    assert result.status == 0, result.describe()

    files = sandbox.desktop_files(sandbox.data / "applications")
    assert len(files) == 2, [path.name for path in files]
