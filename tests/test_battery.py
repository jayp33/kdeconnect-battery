"""Tests für kdeconnect-battery.sh: Hilfe, Argumentprüfung, D-Bus-Auslese,
Verbindungsfehler, Unterlade- und Ladewarnung, TTS-Modi, Sprachen und die
interaktive Geräteauswahl.
"""

from __future__ import annotations

import re
import time

import pytest

DEVICE = "test-device-0001"

# Die Statuszeile des Skripts, Beispiel:
# 2026-09-25 18:04:11  42%, charging=false
STATUS_LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+(\d+)%, charging=(true|false)$", re.MULTILINE
)

pytestmark = pytest.mark.usefixtures("sandbox")


def polls(result):
    """(Ladestand, laedt) je Abfrage in der Reihenfolge der Ausgabe."""
    return [(int(level), charging == "true") for level, charging in STATUS_LINE.findall(result.stdout)]


def tts(sandbox):
    """Das TTS-Kommando der Sandbox als Argumentliste."""
    return ["--tts-command", str(sandbox.bin / "fake-tts")]


def command(sandbox):
    """Ein protokollierender Befehl als Argumentliste."""
    return ["--command", str(sandbox.bin / "fake-command")]


def ladewarnung(level: int, limit: int, sprache: str = "en") -> str:
    """Der erwartete Wortlaut der Überladewarnung."""
    if sprache == "de":
        return (
            f"Achtung. Der Akku ist bei {level} Prozent, über dem Ladelimit von "
            f"{limit} Prozent, und lädt noch. Du kannst das Laden jetzt beenden."
        )
    return (
        f"Warning. The battery is at {level} percent, above the {limit} percent limit, "
        "and is still charging. You can stop charging now."
    )


# ======================================================================
# Hilfe und Argumentprüfung
# ======================================================================


def test_hilfe_enthaelt_alle_optionen(sandbox):
    result = sandbox.run_battery("--help")

    assert result.status == 0, result.describe()
    for option in [
        "--device", "--threshold", "--interval", "--command", "--tts",
        "--tts-every-percent", "--tts-every", "--tts-language", "--tts-command",
        "--charge-limit", "--once",
    ]:
        assert option in result.output, f"{option} fehlt in der Hilfe"


def test_hilfe_nennt_standardwerte(sandbox):
    result = sandbox.run_battery("--help")

    for expected in ["Standard: 20", "Standard: 80", "Standard: 60", "Standard: en"]:
        assert expected in result.output, f"{expected!r} fehlt in der Hilfe"


def test_unbekannte_option(sandbox):
    result = sandbox.run_battery("--quatsch", "-d", DEVICE)

    assert result.status == 2, result.describe()
    assert "Unbekannte Option: --quatsch" in result.stderr, result.describe()
    assert "Verwendung" in result.stderr, "Die Hilfe wird mit ausgegeben"


@pytest.mark.parametrize(
    "option",
    ["--device", "--threshold", "--interval", "--command", "--tts-language",
     "--tts-command", "--charge-limit"],
)
def test_fehlender_parameterwert(sandbox, option):
    result = sandbox.run_battery(option)

    assert result.status == 2, result.describe()
    assert "benötigt" in result.stderr, result.describe()


@pytest.mark.parametrize("value", ["abc", "-5", "101", "20.5", ""])
def test_threshold_ungueltig(sandbox, value):
    result = sandbox.run_battery("-d", DEVICE, "--threshold", value)

    assert result.status == 2, result.describe()
    assert "--threshold muss eine Zahl zwischen 0 und 100 sein." in result.stderr, result.describe()


@pytest.mark.parametrize("value", ["abc", "0", "-1", "1.5", ""])
def test_interval_ungueltig(sandbox, value):
    result = sandbox.run_battery("-d", DEVICE, "--interval", value)

    assert result.status == 2, result.describe()
    assert "--interval muss eine positive ganze Zahl sein." in result.stderr, result.describe()


@pytest.mark.parametrize("value", ["abc", "-3", "101", "70.5", ""])
def test_charge_limit_ungueltig(sandbox, value):
    result = sandbox.run_battery("-d", DEVICE, "--charge-limit", value)

    assert result.status == 2, result.describe()
    assert (
        "--charge-limit muss 0 (aus) oder eine Zahl von 1 bis 100 sein." in result.stderr
    ), result.describe()


@pytest.mark.parametrize("value", ["xx", "e", "de-", "e n", "1234"])
def test_tts_language_ungueltig(sandbox, value):
    result = sandbox.run_battery("-d", DEVICE, "--tts-language", value)

    assert result.status == 2, result.describe()
    assert "--tts-language" in result.stderr, result.describe()


@pytest.mark.parametrize("value", ["en", "de", "en-GB", "de-DE", "de_DE", "en-AU"])
def test_tts_language_gueltig(sandbox, value):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-language", value, *tts(sandbox))

    assert result.status == 0, result.describe()


def test_zwei_gerate_ids(sandbox):
    result = sandbox.run_battery("-d", DEVICE, "--device", "zweitgerat")

    assert result.status == 2, result.describe()
    assert "Mehrere Geräte-IDs angegeben." in result.stderr, result.describe()


def test_id_als_positionales_argument(sandbox):
    sandbox.set_status("42 false")

    result = sandbox.run_battery("--once", DEVICE)

    assert result.status == 0, result.describe()
    assert polls(result) == [(42, False)], result.describe()


def test_id_und_positionales_argument(sandbox):
    result = sandbox.run_battery("-d", DEVICE, "--", DEVICE)

    assert result.status == 2, result.describe()
    assert "Ungültige Geräte-ID." in result.stderr, result.describe()


def test_id_nach_doppelter_strich(sandbox):
    sandbox.set_status("42 false")

    result = sandbox.run_battery("--once", "--", DEVICE)

    assert result.status == 0, result.describe()
    assert polls(result) == [(42, False)], result.describe()


def test_zwei_positionale_argumente(sandbox):
    result = sandbox.run_battery("--once", "--", "erste-id", "zweite-id")

    assert result.status == 2, result.describe()
    assert "Ungültige Geräte-ID." in result.stderr, result.describe()


# ======================================================================
# D-Bus-Auslese
# ======================================================================


def test_statuszeile_format(sandbox):
    sandbox.set_status("42 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert STATUS_LINE.findall(result.stdout), f"Keine Statuszeile: {result.describe()}"


def test_gdbus_antwort_ohne_variantenwrapper(sandbox):
    sandbox.plain_gdbus_answers()
    sandbox.set_status("42 false")
    erst = sandbox.run_battery("--once", "-d", DEVICE)
    sandbox.set_status("77 true")
    zweit = sandbox.run_battery("--once", "-d", DEVICE)

    assert polls(erst) == [(42, False)], erst.describe()
    assert polls(zweit) == [(77, True)], zweit.describe()


def test_abgefragte_eigenschaften(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert sandbox.gdbus_properties() == ["charge", "isCharging"]
    assert "hasBattery" not in sandbox.gdbus_log.read_text(encoding="utf-8")


def test_objektpfad_enthaelt_gerate_id(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", "abc123")

    assert result.status == 0, result.describe()
    assert "/modules/kdeconnect/devices/abc123/battery" in sandbox.gdbus_paths()


def test_gdbus_fehler_beendet_once_mit_fehler(sandbox):
    sandbox.set_status("FAIL false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert "KDE-Connect-Gerät ist nicht erreichbar" in result.stdout, result.describe()
    assert "Der nächste Versuch erfolgt in 60 Sekunden." in result.stdout, result.describe()


def test_gdbus_fehler_in_der_ladezustandsabfrage(sandbox):
    sandbox.set_status("50 FAIL")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert "nicht erreichbar" in result.stdout, "Wird als Verbindungsfehler behandelt"


def test_gdbus_nicht_installiert(sandbox):
    sandbox.use_minimal_path()
    (sandbox.bin / "gdbus").unlink()

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert "gdbus wurde nicht gefunden." in result.stderr, result.describe()
    assert "libglib2.0-bin" in result.stderr, "Installationshinweis"


def test_ladestand_minus_eins(sandbox):
    sandbox.set_status("-1 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert (
        "Für dieses Gerät wurde noch kein gültiger Akkustand gemeldet (charge=-1)."
        in result.stdout
    ), result.describe()
    assert "nicht erreichbar" not in result.stdout, "Ist kein Verbindungsfehler"


def test_ladestand_ungueltig(sandbox):
    sandbox.set_status("abc false")

    erst = sandbox.run_battery("--once", "-d", DEVICE)
    sandbox.set_status("101 false")
    zweit = sandbox.run_battery("--once", "-d", DEVICE)

    assert erst.status == 1, erst.describe()
    assert "KDE-Connect hat einen ungültigen Akkustand gemeldet: abc" in erst.stdout, erst.describe()
    assert zweit.status == 1, zweit.describe()
    assert "ungültigen Akkustand gemeldet: 101" in zweit.stdout, zweit.describe()


def test_ladezustand_ungueltig(sandbox):
    sandbox.set_status("50 maybe")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert (
        "KDE-Connect hat einen ungültigen Ladezustand gemeldet: maybe" in result.stdout
    ), result.describe()


def test_unerwartete_gdbus_antwort(sandbox):
    sandbox.set_status("GARBAGE false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 1, result.describe()
    assert "Unerwartete Antwort von gdbus für charge" in result.stdout, result.describe()


def test_ladestand_null_ist_gueltig(sandbox):
    sandbox.set_status("0 false")

    result = sandbox.run_battery("--once", "-d", DEVICE)

    assert result.status == 0, result.describe()
    assert polls(result) == [(0, False)], result.describe()


# ======================================================================
# Verbindungsverlust
# ======================================================================


@pytest.mark.loop
def test_verbindungsverlust_wird_nur_einmal_gemeldet(sandbox):
    sandbox.set_status("50 false", "FAIL", "FAIL", "50 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("nicht erreichbar") == 1, result.describe()
    assert result.stdout.count("Verbindung zum Gerät wiederhergestellt.") == 1, result.describe()
    assert "nicht erreichbar. Der nächste Versuch erfolgt in 1 Sekunden." in result.stdout
    assert polls(result) == [(50, False), (50, False)], result.describe()
    assert sandbox.tts_texts() == [
        "The connection to the device was lost. I will try again.",
        "The connection to the device has been restored.",
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_verbindungsverlust_ohne_tts(sandbox):
    sandbox.set_status("FAIL", "FAIL", "50 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE)
    result = sandbox.wait_battery()

    assert result.stdout.count("nicht erreichbar") == 1, result.describe()
    assert sandbox.tts_count() == 0, "Ohne TTS wird nichts gesprochen"


@pytest.mark.loop
def test_verbindungsstatus_in_umgebungsvariablen(sandbox):
    sandbox.set_status("FAIL", "50 false")

    sandbox.start_battery(
        "--interval", "1", "--tts-every-percent", "-d", DEVICE, *tts(sandbox)
    )
    sandbox.wait_battery()

    assert sandbox.tts_fields(6) == ["disconnected", "connected"], sandbox.tts_texts()


@pytest.mark.loop
def test_verbindungsverlust_setzt_warnzustaende_zurueck(sandbox):
    # Niedriger Akkustand mit Warnung, dann Ausfall, dann Erholung: die
    # Unterladewarnung darf beim zweiten Mal nicht unterdrückt werden.
    sandbox.set_status("10 false", "FAIL", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig: 10%.") == 2, result.describe()


# ======================================================================
# Unterladewarnung
# ======================================================================


@pytest.mark.loop
def test_unterladewarnung_einmal(sandbox):
    sandbox.set_status("10 false", "10 false", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig: 10%.") == 1, result.describe()
    assert sandbox.tts_texts() == [
        "Warning. The battery level is only 10 percent."
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_unterladewarnung_wieder_nach_erholung(sandbox):
    sandbox.set_status("10 false", "50 false", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig") == 2, result.describe()
    assert sandbox.tts_count() == 2, "Zwei Sprachwarnungen"


@pytest.mark.loop
def test_unterladewarnung_beim_laden_nicht(sandbox):
    sandbox.set_status("10 true", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig") == 1, result.describe()
    assert sandbox.tts_count() == 1, "Nur die zweite Abfrage warnt"


def test_schwelle_grenzfall(sandbox):
    sandbox.set_status("20 false")
    am_limit = sandbox.run_battery("--once", "-d", DEVICE, *tts(sandbox))
    sandbox.set_status("21 false")
    darueber = sandbox.run_battery("--once", "-d", DEVICE)

    assert "Akkustand niedrig: 20%." in am_limit.stdout, am_limit.describe()
    assert "Akkustand niedrig" not in darueber.stdout, darueber.describe()


@pytest.mark.loop
def test_schwelle_null_schaltet_warnung_ab(sandbox):
    sandbox.set_status("5 false", "5 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, "--threshold", "0", *tts(sandbox))
    result = sandbox.wait_battery()

    assert "Akkustand niedrig" not in result.stdout, result.describe()
    assert sandbox.tts_count() == 0


def test_schwelle_eigen(sandbox):
    sandbox.set_status("30 false")
    passend = sandbox.run_battery("--once", "--threshold", "30", "-d", DEVICE, *tts(sandbox))
    sandbox.set_status("30 false")
    zu_niedrig = sandbox.run_battery("--once", "--threshold", "29", "-d", DEVICE)

    assert "Akkustand niedrig: 30%." in passend.stdout, passend.describe()
    assert "Akkustand niedrig" not in zu_niedrig.stdout, zu_niedrig.describe()


def test_befehl_wird_bei_warnung_ausgefuehrt(sandbox):
    sandbox.set_status("10 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, *command(sandbox))

    assert result.status == 0, result.describe()
    assert sandbox.command_rows() == [[DEVICE, "10", "false"]], sandbox.command_rows()


@pytest.mark.loop
def test_befehl_nur_beim_warnwechsel(sandbox):
    sandbox.set_status("10 false", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *command(sandbox))
    sandbox.wait_battery()

    assert len(sandbox.command_rows()) == 1, "Der Befehl läuft nur einmal"


def test_befehlsfehler_wird_gemeldet(sandbox):
    sandbox.set_status("10 false")

    result = sandbox.run_battery(
        "--once", "-d", DEVICE, "--command", str(sandbox.bin / "fake-command-fail")
    )

    assert result.status == 0, "Die Überwachung läuft weiter"
    assert "Der konfigurierte Befehl ist mit einem Fehler beendet." in result.stderr, result.describe()


def test_befehl_nur_bei_warnung(sandbox):
    sandbox.set_status("50 false")
    sandbox.run_battery("--once", "-d", DEVICE, *command(sandbox))
    assert sandbox.command_rows() == [], "Kein Befehl ohne Warnung"

    sandbox.set_status("10 true")
    sandbox.run_battery("--once", "-d", DEVICE, *command(sandbox))
    assert sandbox.command_rows() == [], "Kein Befehl beim Laden"

    sandbox.set_status("90 true")
    sandbox.run_battery("--once", "-d", DEVICE, *command(sandbox))
    assert sandbox.command_rows() == [], "Kein Befehl bei der Ladewarnung"


# ======================================================================
# Ladewarnung
# ======================================================================


@pytest.mark.loop
def test_ladewarnung_ab_standardlimit(sandbox):
    sandbox.set_status("85 true", "85 true", "85 true")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Ladewarnung") == 1, result.describe()
    assert (
        "Ladewarnung: Der Akku ist bei 85% (Ladelimit: 80%) und lädt noch." in result.stdout
    ), result.describe()
    assert sandbox.tts_texts() == [ladewarnung(85, 80)], sandbox.tts_texts()


@pytest.mark.loop
def test_ladewarnung_unter_standardlimit(sandbox):
    sandbox.set_status("79 true", "79 true")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert "Ladewarnung" not in result.stdout, "79 Prozent liegen unter dem Standardlimit"
    assert sandbox.tts_count() == 0


def test_ladewarnung_genau_am_limit(sandbox):
    sandbox.set_status("80 true")

    result = sandbox.run_battery("--once", "-d", DEVICE, *tts(sandbox))

    assert "Ladewarnung" in result.stdout, "Genau am Limit wird gewarnt"


def test_ladewarnung_mit_eigenem_limit(sandbox):
    sandbox.set_status("75 true")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--charge-limit", "70", *tts(sandbox))

    assert (
        "Ladewarnung: Der Akku ist bei 75% (Ladelimit: 70%) und lädt noch." in result.stdout
    ), result.describe()
    assert any("above the 70 percent limit" in text for text in sandbox.tts_texts())


@pytest.mark.loop
def test_ladewarnung_verschwindet_und_kommt_wieder(sandbox):
    sandbox.set_status("85 true", "60 false", "85 true")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Ladewarnung") == 2, "Warnung nach jedem neuen Eintritt"
    assert sandbox.tts_count() == 2


def test_ladewarnung_nur_beim_laden(sandbox):
    sandbox.set_status("95 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, *tts(sandbox))

    assert "Ladewarnung" not in result.stdout, "Ohne Laden keine Ladewarnung"


@pytest.mark.loop
def test_ladewarnung_null_schaltet_ab(sandbox):
    sandbox.set_status("100 true", "100 true")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, "--charge-limit", "0")
    result = sandbox.wait_battery()

    assert "Ladewarnung" not in result.stdout, result.describe()
    assert sandbox.tts_count() == 0


def test_charge_limit_null_aktiviert_kein_tts(sandbox):
    # Der eingeschränkte Pfad sorgt dafür, dass auch ein auf dem Rechner
    # installiertes Sprachprogramm nicht gefunden wird.
    sandbox.use_minimal_path()
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--charge-limit", "0")

    assert result.status == 0, result.describe()
    assert "Kein TTS-Programm" not in result.output, "TTS wird nicht unbeabsichtigt aktiviert"


def test_charge_limit_aktiviert_tts(sandbox):
    sandbox.use_minimal_path()
    sandbox.remove_engines()
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--charge-limit", "85")

    assert result.status == 1, "Ohne Sprachprogramm bricht --charge-limit ab"
    assert "Kein TTS-Programm gefunden." in result.stderr, result.describe()


@pytest.mark.loop
def test_ladewarnung_wiederholt_bei_tts_every(sandbox):
    sandbox.set_status("85 true", "86 true", "87 true")

    sandbox.start_battery("--interval", "1", "--tts-every", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert result.stdout.count("Ladewarnung") == 1, "Die Konsolenausgabe bleibt einmal"
    assert sandbox.tts_texts() == [
        ladewarnung(85, 80), ladewarnung(86, 80), ladewarnung(87, 80)
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_ladewarnung_wiederholt_nur_bei_prozentwechsel(sandbox):
    sandbox.set_status("85 true", "86 true", "86 true")

    sandbox.start_battery("--interval", "1", "--tts-every-percent", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_count() == 2, "Ansage nur bei geändertem Ladestand"


# ======================================================================
# TTS-Modi
# ======================================================================


@pytest.mark.loop
def test_tts_standardmaessig_aus(sandbox):
    sandbox.set_status("50 false", "10 false", "10 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE)
    result = sandbox.wait_battery()

    assert result.stdout.count("Akkustand niedrig") == 1, "Die Warnung erscheint trotzdem"
    assert sandbox.tts_count() == 0, "Ohne TTS-Option wird nichts gesprochen"


@pytest.mark.loop
def test_tts_nur_warnungen(sandbox):
    sandbox.set_status("50 false", "51 false", "10 false", "10 false")

    sandbox.start_battery("--interval", "1", "--tts", "-d", DEVICE, *tts(sandbox))
    result = sandbox.wait_battery()

    assert len(polls(result)) == 4, "Alle Abfragen erscheinen auf der Konsole"
    assert sandbox.tts_texts() == [
        "Warning. The battery level is only 10 percent."
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_tts_bei_prozentwechsel(sandbox):
    sandbox.set_status("50 false", "50 true", "50 false", "51 false")

    sandbox.start_battery("--interval", "1", "--tts-every-percent", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_texts() == [
        "The battery level is 50 percent.",
        "The battery level is 51 percent.",
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_tts_bei_jedem_intervall(sandbox):
    sandbox.set_status("50 false", "50 false")

    sandbox.start_battery("--interval", "1", "--tts-every", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_texts() == [
        "The battery level is 50 percent.",
        "The battery level is 50 percent.",
    ], sandbox.tts_texts()


@pytest.mark.loop
def test_tts_every_gewinnt_gegen_every_percent(sandbox):
    sandbox.set_status("50 false", "50 false")

    sandbox.start_battery(
        "--interval", "1", "--tts-every", "--tts-every-percent", "-d", DEVICE, *tts(sandbox)
    )
    sandbox.wait_battery()

    assert sandbox.tts_count() == 2, "Ohne Prozentwechsel wird trotzdem gesprochen"


@pytest.mark.loop
def test_tts_ersetzt_statusansage_durch_warnung(sandbox):
    sandbox.set_status("50 false", "10 false", "10 false")

    sandbox.start_battery("--interval", "1", "--tts-every-percent", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_count() == 2
    assert not any("The battery level is 10 percent." in text for text in sandbox.tts_texts())
    assert "Warning. The battery level is only 10 percent." in sandbox.tts_texts()


@pytest.mark.loop
def test_tts_ersetzt_statusansage_durch_ladewarnung(sandbox):
    sandbox.set_status("90 true", "91 true")

    sandbox.start_battery("--interval", "1", "--tts-every-percent", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_count() == 2, "Zwei Ladewarnungen"
    assert not any("The battery level is 90 percent." in text for text in sandbox.tts_texts())


def test_kein_tts_programm(sandbox):
    sandbox.use_minimal_path()
    sandbox.remove_engines()
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts")

    assert result.status == 1, result.describe()
    for expected in ["Kein TTS-Programm gefunden.", "espeak-ng", "--tts-command"]:
        assert expected in result.stderr, f"{expected!r} fehlt: {result.describe()}"


def test_tts_befehl_erhaelt_umgebungsvariablen(sandbox):
    sandbox.set_status("90 true")

    result = sandbox.run_battery(
        "--once", "--tts-language", "de", "--charge-limit", "85", "-d", DEVICE, *tts(sandbox)
    )

    assert result.status == 0, result.describe()
    assert sandbox.tts_texts() == [ladewarnung(90, 85, "de")], sandbox.tts_texts()
    assert sandbox.tts_fields(2) == ["90"], "BATTERY_LEVEL"
    assert sandbox.tts_fields(3) == ["true"], "BATTERY_CHARGING"
    assert sandbox.tts_fields(4) == ["de"], "BATTERY_LANGUAGE"
    assert sandbox.tts_fields(5) == ["85"], "BATTERY_CHARGE_LIMIT"
    assert sandbox.tts_fields(6) == ["connected"], "BATTERY_CONNECTION"
    assert sandbox.tts_fields(7) == [DEVICE], "DEVICE_ID"


def test_tts_befehlsfehler_wird_gemeldet(sandbox):
    sandbox.set_status("10 false")

    result = sandbox.run_battery(
        "--once", "--tts", "-d", DEVICE,
        "--tts-command", str(sandbox.bin / "fake-tts-fail"),
    )

    assert result.status == 0, "Die Überwachung läuft weiter"
    assert "TTS-Befehl ist mit einem Fehler beendet" in result.stderr, result.describe()


@pytest.mark.loop
def test_tts_befehl_schaltet_tts_ein(sandbox):
    sandbox.set_status("50 false", "51 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE, *tts(sandbox))
    sandbox.wait_battery()

    assert sandbox.tts_count() == 0, "--tts-command allein aktiviert nur die Warnansagen"


def test_tts_programm_waehlt_eng_passend(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every")

    assert result.status == 0, result.describe()
    assert "-v en-us The battery level is 50 percent." in sandbox.engine_log.read_text(
        encoding="utf-8"
    )


def test_tts_programm_waehlt_eng_passend_mit_spdsay(sandbox):
    sandbox.add_engine("spd-say")
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every")

    assert result.status == 0, result.describe()
    log = sandbox.engine_log.read_text(encoding="utf-8")
    assert "-l en-us The battery level is 50 percent." in log, "spd-say wird bevorzugt"
    assert "-v en-us" not in log, "espeak-ng wird nicht zusätzlich benutzt"


def test_tts_programm_waehlt_eng_passend_ohne_espeak_ng(sandbox):
    # Der eingeschränkte Pfad sorgt dafür, dass auch ein auf dem Rechner
    # installiertes espeak-ng nicht gefunden wird und wirklich kein Ton entsteht.
    sandbox.use_minimal_path()
    (sandbox.bin / "espeak-ng").unlink()
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every")

    assert result.status == 0, result.describe()
    assert "-v en-us The battery level is 50 percent." in sandbox.engine_log.read_text(
        encoding="utf-8"
    )


# ======================================================================
# Sprachen
# ======================================================================


@pytest.mark.loop
def test_sprache_deutsch(sandbox):
    sandbox.set_status("50 false", "50 true", "10 false", "90 true")

    sandbox.start_battery(
        "--interval", "1", "--tts-every", "--tts-language", "de", "-d", DEVICE, *tts(sandbox)
    )
    sandbox.wait_battery()

    gesprochen = sandbox.tts_texts()
    for expected in [
        "Der Akku wird geladen. Akkustand 50 Prozent.",
        "Achtung. Der Akkustand beträgt nur noch 10 Prozent.",
        "Achtung. Der Akku ist bei 90 Prozent, über dem Ladelimit von 80 Prozent",
    ]:
        assert any(expected in text for text in gesprochen), f"{expected!r} fehlt: {gesprochen}"
    assert not any("percent" in text for text in gesprochen), "Keine englischen Reste"


@pytest.mark.loop
def test_sprache_deutsch_verbindungsverlust(sandbox):
    sandbox.set_status("FAIL", "50 false")

    sandbox.start_battery(
        "--interval", "1", "--tts-language", "de", "-d", DEVICE, *tts(sandbox)
    )
    sandbox.wait_battery()

    assert sandbox.tts_texts() == [
        "Die Verbindung zum Gerät wurde unterbrochen. Ich versuche es erneut.",
        "Die Verbindung zum Gerät ist wiederhergestellt.",
    ], sandbox.tts_texts()


def test_sprache_standard_englisch(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "--tts-every", "-d", DEVICE, *tts(sandbox))

    assert result.status == 0, result.describe()
    assert sandbox.tts_texts() == ["The battery level is 50 percent."]
    assert sandbox.tts_fields(4) == ["en"]


def test_sprache_en_gb_stellt_stimme_ein(sandbox):
    sandbox.set_status("50 false")

    result = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every", "--tts-language", "en-GB")

    assert result.status == 0, result.describe()
    assert "-v en-gb The battery level is 50 percent." in sandbox.engine_log.read_text(
        encoding="utf-8"
    )


def test_sprache_de_mit_stimme(sandbox):
    sandbox.set_status("50 false")
    erste = sandbox.run_battery("--once", "-d", DEVICE, "--tts-every", "--tts-language", "de")
    assert erste.status == 0, erste.describe()
    assert "-v de Akkustand 50 Prozent." in sandbox.engine_log.read_text(encoding="utf-8")

    sandbox.set_status("50 false")
    zweit = sandbox.run_battery(
        "--once", "-d", DEVICE, "--tts-every", "--tts-language", "de_DE", *tts(sandbox)
    )
    assert zweit.status == 0, zweit.describe()
    assert sandbox.tts_fields(4) == ["de_DE"], "de_DE wird unverändert weitergereicht"
    assert sandbox.tts_texts() == ["Akkustand 50 Prozent."], sandbox.tts_texts()


# ======================================================================
# Geräteauswahl
# ======================================================================


def test_ohne_gerate_id_und_ohne_interaktion(sandbox):
    sandbox.set_devices(f"{DEVICE} Testgerät")

    result = sandbox.run_battery("--once")

    assert result.status == 1, result.describe()
    assert "Verfügbare KDE-Connect-Geräte:" in result.stdout, result.describe()
    assert f"1) Testgerät (ID: {DEVICE})" in result.stdout, result.describe()
    assert "Keine interaktive Auswahl möglich." in result.stderr, result.describe()
    assert "--device" in result.stderr, "Hinweis auf --device"


def test_interaktive_auswahl(sandbox):
    sandbox.set_status("50 false")
    sandbox.set_devices(f"{DEVICE} Testgerät", "zweites Tablet B")

    result = sandbox.run_pty(["--once"], b"2\n")

    assert result.status == 0, result.describe()
    assert "Ausgewähltes Gerät: Tablet B (zweites)" in result.stdout, result.describe()
    assert "/modules/kdeconnect/devices/zweites/battery" in sandbox.gdbus_paths()


def test_interaktive_auswahl_mit_enter(sandbox):
    sandbox.set_status("50 false")
    sandbox.set_devices(f"{DEVICE} Testgerät", "zweites Tablet B")

    result = sandbox.run_pty(["--once"], b"\n")

    assert result.status == 0, result.describe()
    assert f"Ausgewähltes Gerät: Testgerät ({DEVICE})" in result.stdout, result.describe()


@pytest.mark.parametrize("eingabe", ["9\n", "abc\n"], ids=["ausserhalb", "buchstaben"])
def test_interaktive_auswahl_ungueltig(sandbox, eingabe):
    sandbox.set_devices(f"{DEVICE} Testgerät")

    result = sandbox.run_pty(["--once"], eingabe.encode())

    assert result.status == 1, result.describe()
    assert f"Ungültige Auswahl: {eingabe.strip()}" in result.stdout, result.describe()


def test_interaktive_auswahl_abgebrochen(sandbox):
    sandbox.set_devices(f"{DEVICE} Testgerät")

    # Strg-D beendet die Eingabe, wie ein leeres Terminal.
    result = sandbox.run_pty(["--once"], b"\x04")

    assert result.status == 1, result.describe()
    assert "Auswahl abgebrochen." in result.output, result.describe()


def test_kdeconnect_cli_fehler(sandbox):
    sandbox.fail_kdeconnect_cli()

    result = sandbox.run_battery("--once")

    assert result.status == 1, result.describe()
    assert "Die Liste der KDE-Connect-Geräte konnte nicht abgerufen werden." in result.stderr
    assert "KDE Connect laeuft nicht" in result.stderr, "Die Ausgabe von kdeconnect-cli wird gezeigt"


def test_kdeconnect_cli_nicht_installiert(sandbox):
    sandbox.use_minimal_path()
    (sandbox.bin / "kdeconnect-cli").unlink()

    result = sandbox.run_battery("--once")

    assert result.status == 1, result.describe()
    assert "kdeconnect-cli wurde nicht gefunden." in result.stderr, result.describe()
    assert "Ohne --device" in result.stderr


def test_keine_geraete_erreichbar(sandbox):
    sandbox.set_devices()

    result = sandbox.run_battery("--once")

    assert result.status == 1, result.describe()
    assert "Keine erreichbaren KDE-Connect-Geräte gefunden." in result.stderr, result.describe()
    assert "kdeconnect-cli --list-available" in result.stderr, "Prüfhinweis"


def test_geraeteliste_ausgabe_format(sandbox):
    sandbox.set_status("50 false")
    sandbox.set_devices(
        "id_eins Name ohne Leerzeichen Problem",
        "id_zwei",  # ohne Namen
        "",  # Leerzeile wird übersprungen
        "id_drei   Name  mit   Leerzeichen",
    )

    result = sandbox.run_pty(["--once"], b"3\n")

    assert result.status == 0, result.describe()
    assert "Ausgewähltes Gerät: Name  mit   Leerzeichen (id_drei)" in result.stdout, result.describe()
    assert "2) (ohne Namen) (ID: id_zwei)" in result.stdout, "Gerät ohne Namen"
    assert "/modules/kdeconnect/devices/id_drei/battery" in sandbox.gdbus_paths()


# ======================================================================
# Schleife
# ======================================================================


def test_once_beendet_sich_sofort(sandbox):
    sandbox.set_status("50 false")

    start = time.monotonic()
    result = sandbox.run_battery("--once", "-d", DEVICE)
    dauer = time.monotonic() - start

    assert result.status == 0, result.describe()
    assert dauer < 10, f"--once hat {dauer:.1f}s gedauert statt sofort zu enden"


@pytest.mark.loop
def test_intervall_wird_eingehalten(sandbox):
    sandbox.set_status("50 false", "50 false", "50 false")

    start = time.monotonic()
    sandbox.start_battery("--interval", "2", "-d", DEVICE)
    result = sandbox.wait_battery()
    dauer = time.monotonic() - start

    assert len(polls(result)) == 3, "Drei Abfragen"
    assert dauer >= 4, f"Zwei Wartezeiten von je zwei Sekunden fehlen ({dauer:.1f}s)"


@pytest.mark.loop
def test_statuszeile_pro_abfrage(sandbox):
    sandbox.set_status("50 false", "51 true", "52 false")

    sandbox.start_battery("--interval", "1", "-d", DEVICE)
    result = sandbox.wait_battery()

    assert polls(result) == [(50, False), (51, True), (52, False)], result.describe()
    assert len(sandbox.gdbus_properties()) == 6, "Zwei D-Bus-Abfragen je Abfrage"
