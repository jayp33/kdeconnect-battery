"""Tests für kdeconnect-battery-desktops.sh: Hilfe, Argumentprüfung,
Geräteliste, erzeugte Dateien, Zuordnung der Wertetabelle, Dateinamen und ein
Testlauf mit dem erzeugten Befehl.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import BATTERY_SCRIPT, erfundene_id, erfundene_id_mit_unterstrichen

# Erfundene Geräte-IDs, keine echten. Die IDs werden im Generator nur für den
# Dateinamen und die Zuordnung per ID gebraucht; die Wertetabelle selbst wird
# über den Gerätenamen zugeordnet, deshalb dürfen hier beliebige Werte stehen.
ID1 = erfundene_id("POCO F1")
ID2 = erfundene_id_mit_unterstrichen("Redmi Pad SE")
ID3 = erfundene_id("POCO X3 Pro")

# Die drei Geräte, für die der Generator eine Tabelle mitführt. Die Namen
# müssen zur Tabelle im Skript passen, die IDs sind frei erfunden.
THREE_DEVICES = (f"{ID1} POCO F1", f"{ID2} Redmi Pad SE", f"{ID3} POCO X3 Pro")

pytestmark = pytest.mark.usefixtures("sandbox")


@pytest.fixture
def out(sandbox):
    """Zielverzeichnis der erzeugten Starter."""
    return sandbox.data / "applications"


@pytest.fixture
def three(sandbox):
    """Attrappe meldet die drei Geräte aus der Wertetabelle."""
    sandbox.set_devices(*THREE_DEVICES)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ======================================================================
# Hilfe und Argumentprüfung
# ======================================================================


def test_hilfe_enthaelt_alle_optionen(sandbox, three):
    result = sandbox.run_desktops("--help")

    assert result.status == 0, result.describe()
    for option in ("--output-dir", "--script", "--list", "--dry-run", "device_table"):
        assert option in result.output, result.describe()


def test_unbekannte_option(sandbox, three):
    result = sandbox.run_desktops("--quatsch")

    assert result.status == 1, result.describe()
    assert "Unbekannte Option: --quatsch" in result.stderr, result.describe()
    assert "siehe --help" in result.stderr, result.describe()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--output-dir"], "benötigt ein Verzeichnis"),
        (["--script"], "benötigt einen Pfad"),
    ],
)
def test_fehlender_parameterwert(sandbox, three, args, message):
    result = sandbox.run_desktops(*args)

    assert result.status == 1, result.describe()
    assert message in result.stderr, result.describe()


# ======================================================================
# Geräteliste
# ======================================================================


def test_liste_zeigt_geraete_und_optionen(sandbox, three):
    # Eigene Tabelle: Geprüft wird die Formatierung der Liste, nicht der Inhalt
    # der Tabelle im Skript. Die dort eingetragenen Geräte und Optionen sind
    # Konfiguration und ändern sich; die Liste selbst nicht.
    variant = sandbox.generator_variant(
        '"POCO F1|"',
        '"Redmi Pad SE|--charge-limit 70"',
        '"POCO X3 Pro|--charge-limit 70 --tts-command /pfad/kdeconnect-speak"',
    )
    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "--list")

    assert result.status == 0, result.describe()
    assert f"POCO F1 ({ID1})  Standardwerte" in result.stdout, result.describe()
    assert f"Redmi Pad SE ({ID2})  Optionen: --charge-limit 70" in result.stdout, result.describe()
    assert (
        f"POCO X3 Pro ({ID3})  Optionen: --charge-limit 70 --tts-command /pfad/kdeconnect-speak"
        in result.stdout
    ), result.describe()


def test_liste_schreibt_keine_dateien(sandbox, three, out):
    result = sandbox.run_desktops("--list", "-o", str(out))

    assert result.status == 0, result.describe()
    assert not out.exists(), "--list legt kein Verzeichnis an"


def test_kdeconnect_cli_nicht_installiert(sandbox, out):
    sandbox.use_minimal_path()
    (sandbox.bin / "kdeconnect-cli").unlink()

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 1, result.describe()
    assert "kdeconnect-cli wurde nicht gefunden." in result.stderr, result.describe()


def test_keine_geraete_erreichbar(sandbox, out):
    sandbox.set_devices()

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 1, result.describe()
    assert "Keine erreichbaren KDE-Connect-Geräte gefunden." in result.stderr, result.describe()


def test_kdeconnect_cli_fehler_wird_als_leere_liste_gemeldet(sandbox, out):
    sandbox.fail_kdeconnect_cli()

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 1, result.describe()
    assert "Keine erreichbaren KDE-Connect-Geräte gefunden." in result.stderr, result.describe()


def test_akku_skript_fehlt(sandbox, three, out):
    result = sandbox.run_desktops("--script", str(sandbox.root / "gibt-es-nicht.sh"), "-o", str(out))

    assert result.status == 1, result.describe()
    assert "kdeconnect-battery.sh wurde nicht gefunden" in result.stderr, result.describe()


# ======================================================================
# Erzeugte Dateien
# ======================================================================


def test_erzeugt_eine_datei_je_geraet(sandbox, three, out):
    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    assert [path.name for path in sandbox.desktop_files(out)] == [
        "kdeconnect-akku-poco-f1.desktop",
        "kdeconnect-akku-poco-x3-pro.desktop",
        "kdeconnect-akku-redmi-pad-se.desktop",
    ], result.describe()
    assert "3 Starter erzeugt" in result.stdout, result.describe()
    assert f"Geschrieben: {out}/kdeconnect-akku-poco-f1.desktop" in result.stdout, result.describe()


def test_dateiinhalt_ist_vollstaendig(sandbox, three, out):
    variant = sandbox.generator_variant(
        '"POCO F1|"',
        '"Redmi Pad SE|--charge-limit 70"',
        '"POCO X3 Pro|--charge-limit 70"',
    )
    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))
    assert result.status == 0, result.describe()

    file = out / "kdeconnect-akku-redmi-pad-se.desktop"
    content = read(file)
    for expected in [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=KDE-Connect-Akku: Redmi Pad SE",
        "Comment=Überwacht den Akkustand von Redmi Pad SE",
        " (Optionen: --charge-limit 70)",  # die Beschreibung nennt die Optionen
        f"Exec={BATTERY_SCRIPT} --device {ID2} --tts --tts-language de --charge-limit 70",
        "Icon=battery-good",
        "Terminal=true",
        "Categories=System;",
        "Keywords=Akku;Batterie;KDE Connect;Redmi Pad SE;",
    ]:
        assert expected in content, f"{expected!r} fehlt in {file.name}"

    assert os.access(file, os.X_OK), f"{file.name} ist nicht ausführbar"


def test_exec_zeile_ohne_prozentzeichen(sandbox, three, out):
    result = sandbox.run_desktops("-o", str(out))
    assert result.status == 0, result.describe()

    for file in sandbox.desktop_files(out):
        assert "%" not in read(file), f"Prozentzeichen in {file.name}"


def test_tts_befehl_bleibt_ein_argument(sandbox, three, out):
    """Ein TTS-Skript muss als einzelnes Argument ankommen.

    Die Exec-Zeile wird nicht von einer Shell interpretiert, sondern an
    Leerzeichen getrennt. Ein Pfad darf deshalb nicht in Anführungszeichen
    gesetzt werden; ein ausgeschriebener curl-Aufruf mit Leerzeichen käme
    hier gar nicht erst an.
    """
    variant = sandbox.generator_variant('"POCO F1|--tts-command /opt/tts/kdeconnect-speak"')
    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))
    assert result.status == 0, result.describe()

    content = read(out / "kdeconnect-akku-poco-f1.desktop")
    exec_line = next(line for line in content.splitlines() if line.startswith("Exec="))
    argv = exec_line[len("Exec="):].split()

    assert argv[argv.index("--tts-command") + 1] == "/opt/tts/kdeconnect-speak"
    assert "'" not in exec_line, "Hochkomma in der Exec-Zeile"
    assert '"' not in exec_line, "Anführungszeichen in der Exec-Zeile"


def test_standardwerte_ohne_optionshinweis(sandbox, three, out):
    variant = sandbox.generator_variant(
        '"POCO F1|"',
        '"Redmi Pad SE|--charge-limit 70"',
        '"POCO X3 Pro|--charge-limit 70"',
    )
    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))
    assert result.status == 0, result.describe()

    content = read(out / "kdeconnect-akku-poco-f1.desktop")
    assert f"Exec={BATTERY_SCRIPT} --device {ID1} --tts --tts-language de" in content
    assert "Optionen:" not in content


def test_ausgabe_ohne_kategorien_zusaetzlich(sandbox, three, out):
    result = sandbox.run_desktops("-o", str(out))
    assert result.status == 0, result.describe()

    content = read(out / "kdeconnect-akku-poco-f1.desktop")
    assert "Categories=System;" in content
    assert content.count("Categories=") == 1


def test_dateien_werden_ueberschrieben(sandbox, three, out):
    assert sandbox.run_desktops("-o", str(out)).status == 0
    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    assert len(sandbox.desktop_files(out)) == 3, "Keine zusätzlichen Dateien"


def test_trockenlauf_schreibt_nichts(sandbox, three, out):
    result = sandbox.run_desktops("--dry-run", "-o", str(out))

    assert result.status == 0, result.describe()
    assert not out.exists(), "Kein Verzeichnis angelegt"
    assert f"Würde schreiben: {out}/kdeconnect-akku-poco-f1.desktop" in result.stdout, result.describe()
    assert "    [Desktop Entry]" in result.stdout, "Inhalt eingerückt"
    assert f"    Exec={BATTERY_SCRIPT} --device {ID1}" in result.stdout, "Inhalt vollständig"


def test_verzeichnis_wird_angelegt(sandbox, three):
    deep = sandbox.root / "a" / "b" / "c"

    result = sandbox.run_desktops("-o", str(deep))

    assert result.status == 0, result.describe()
    assert (deep / "kdeconnect-akku-poco-f1.desktop").exists()


def test_standardverzeichnis_aus_xdg_data_home(sandbox, three):
    result = sandbox.run_desktops()

    assert result.status == 0, result.describe()
    assert (sandbox.data / "applications" / "kdeconnect-akku-poco-f1.desktop").exists()


def test_standardverzeichnis_aus_home(sandbox, three):
    del sandbox.env["XDG_DATA_HOME"]

    result = sandbox.run_desktops()

    assert result.status == 0, result.describe()
    assert (sandbox.home / ".local/share/applications/kdeconnect-akku-poco-f1.desktop").exists()


# ======================================================================
# Wertetabelle
# ======================================================================


def test_tabelleneintrag_ohne_geraet_wird_gemeldet(sandbox, three, out):
    variant = sandbox.generator_variant(
        '"POCO F1|"',
        '"Redmi Pad SE|--charge-limit 70"',
        '"Galaxy S99|--charge-limit 50"',
    )

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, "Ein fehlendes Gerät ist kein Fehler"
    assert (
        'Der Tabelleneintrag "Galaxy S99" passt zu keinem erreichbaren Gerät.'
        in result.stderr
    ), result.describe()
    assert '"POCO F1"' not in result.stderr, "Genutzte Einträge werden nicht gemeldet"


def test_geraet_ohne_eintrag_bekommt_standardwerte(sandbox, out):
    sandbox.set_devices(f"{ID1} Fremdes Geraet")

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    file = out / "kdeconnect-akku-fremdes-geraet.desktop"
    assert file.exists(), result.describe()
    assert f"Exec={BATTERY_SCRIPT} --device {ID1} --tts --tts-language de" in read(file)
    assert '"POCO F1"' in result.stderr, "Nicht passende Einträge werden gemeldet"


def test_zuordnung_ueber_gerate_id(sandbox, out):
    sandbox.set_devices(f"{ID1} Tablet Eins", f"{ID2} Tablet Zwei")
    variant = sandbox.generator_variant(f'"{ID1}|--charge-limit 60"')

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, result.describe()
    assert (
        f"--device {ID1} --tts --tts-language de --charge-limit 60"
        in read(out / "kdeconnect-akku-tablet-eins.desktop")
    )
    assert (
        f"--device {ID2} --tts --tts-language de"
        in read(out / "kdeconnect-akku-tablet-zwei.desktop")
    )


def test_zuordnung_ueber_name_ignoriert_gross_kleinschreibung(sandbox, out):
    sandbox.set_devices(f"{ID1} POCO F1")
    variant = sandbox.generator_variant('"poco f1|--charge-limit 65"')

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, result.describe()
    assert "--charge-limit 65" in read(out / "kdeconnect-akku-poco-f1.desktop")
    assert "passt zu keinem" not in result.stderr, "Der Eintrag wurde benutzt"


def test_id_hat_vorrang_vor_name(sandbox, out):
    sandbox.set_devices(f"{ID1} POCO F1")
    # Beide Einträge passen auf dasselbe Gerät; die ID muss gewinnen.
    variant = sandbox.generator_variant(
        '"POCO F1|--threshold 33"', f'"{ID1}|--threshold 44"'
    )

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, result.describe()
    content = read(out / "kdeconnect-akku-poco-f1.desktop")
    assert "--threshold 44" in content
    assert "--threshold 33" not in content, "Der Eintrag des Namens wird nicht zusätzlich verwendet"


# ======================================================================
# Dateinamen
# ======================================================================


def test_dateiname_aus_geraetename(sandbox, out):
    sandbox.set_devices(f"{ID1} Redmi Pad SE")

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    assert (out / "kdeconnect-akku-redmi-pad-se.desktop").exists(), "Leerzeichen werden zu Bindestrichen"


def test_dateiname_bei_sonderzeichen(sandbox, out):
    sandbox.set_devices(
        f"{ID1} Phone #1 (2024)", f"{ID2} Laptop Ü", f"{ID3} --  Doppel  Bindestrich --"
    )

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    for expected in [
        "kdeconnect-akku-phone-1-2024.desktop",  # Sonderzeichen entfallen
        "kdeconnect-akku-laptop.desktop",  # Umlaut entfällt ohne Reststrich
        "kdeconnect-akku-doppel-bindestrich.desktop",  # Mehrfachbindestriche werden zusammengezogen
    ]:
        assert (out / expected).exists(), f"{expected} fehlt: {result.describe()}"


def test_gleichnamige_geraete_bekommen_eigene_dateien(sandbox, out):
    sandbox.set_devices("aaaa1111 Smartphone", "bbbb2222 Smartphone", "cccc3333 Tablet")
    variant = sandbox.generator_variant('"Smartphone|--charge-limit 66"')

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, result.describe()
    assert len(sandbox.desktop_files(out)) == 3, "Jedes Gerät hat eine eigene Datei"
    assert (out / "kdeconnect-akku-smartphone-aaaa11.desktop").exists()
    assert (out / "kdeconnect-akku-smartphone-bbbb22.desktop").exists()
    assert (out / "kdeconnect-akku-tablet.desktop").exists(), "Eindeutiger Name bleibt kurz"
    assert 'Der Name "Smartphone" passt auf 2 Geräte' in result.stderr, result.describe()
    assert "Zuordnung per Geräte-ID ist eindeutiger" in result.stderr, "Empfehlung"
    assert "--device aaaa1111" in read(out / "kdeconnect-akku-smartphone-aaaa11.desktop")
    assert "--device bbbb2222" in read(out / "kdeconnect-akku-smartphone-bbbb22.desktop")


def test_gleichnamige_geraete_werden_richtig_zugeordnet(sandbox, out):
    sandbox.set_devices("aaaa1111 Smartphone", "bbbb2222 Smartphone")
    variant = sandbox.generator_variant('"aaaa1111|--charge-limit 66"')

    result = sandbox.run(variant, "--script", str(BATTERY_SCRIPT), "-o", str(out))

    assert result.status == 0, result.describe()
    assert "--charge-limit 66" in read(out / "kdeconnect-akku-smartphone-aaaa11.desktop")
    assert "--device bbbb2222 --tts --tts-language de" in read(
        out / "kdeconnect-akku-smartphone-bbbb22.desktop"
    )


def test_kurze_ids_bekommen_zusaetzliches_kuerzel(sandbox, out):
    # Gleicher Name und gleiche (zu kurze) ID: Der Generator darf nicht endlos
    # nach einem längeren Kürzel suchen, sondern muss eindeutige Namen finden.
    sandbox.set_devices("ab Smartphone", "ab Smartphone")

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    assert len(sandbox.desktop_files(out)) == 2, "Zwei verschiedene Dateien"
    assert (out / "kdeconnect-akku-smartphone-ab.desktop").exists()
    assert (out / "kdeconnect-akku-smartphone-ab-1.desktop").exists()


# ======================================================================
# Prüfungen und Integration
# ======================================================================


def test_skriptpfad_wird_uebernommen(sandbox, three, out):
    elsewhere = sandbox.root / "andere-stelle" / "kdeconnect-battery.sh"
    elsewhere.parent.mkdir()
    shutil.copy(BATTERY_SCRIPT, elsewhere)

    result = sandbox.run_desktops("--script", str(elsewhere), "-o", str(out))

    assert result.status == 0, result.describe()
    assert f"Exec={elsewhere} --device {ID1}" in read(out / "kdeconnect-akku-poco-f1.desktop")


def test_systembereich_wird_aktualisiert(sandbox, three, out):
    sandbox.add_engine("kbuildsycoca6")
    sandbox.add_engine("kbuildsycoca5")

    result = sandbox.run_desktops("-o", str(out))

    assert result.status == 0, result.describe()
    log = sandbox.engine_log.read_text(encoding="utf-8")
    assert "--noincremental" in log, "kbuildsycoca6 wird benutzt"
    assert "kbuildsycoca5" not in log, "Die veraltete Version bleibt unbenutzt"


def test_erzeugter_befehl_laueuft(sandbox, three, out):
    result = sandbox.run_desktops("-o", str(out))
    assert result.status == 0, result.describe()

    for file in sandbox.desktop_files(out):
        sandbox.set_status("10 false")

        run = sandbox.run_generated_entry(file)

        assert run.status == 0, f"{file.name}: {run.describe()}"
        assert any(
            " 10%, charging=false" in line for line in run.status_lines
        ), f"{file.name} liest den Akkustand nicht: {run.describe()}"
        assert "Akkustand niedrig: 10%." in run.stdout, f"{file.name} warnt nicht"
        assert sandbox.tts_count() == 1, f"{file.name} spricht {sandbox.tts_count()}mal"
        assert any(
            "10 Prozent" in text for text in sandbox.tts_texts()
        ), f"{file.name} spricht nicht auf Deutsch"


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate fehlt.",
)
def test_generierte_datei_ist_gueltig(sandbox, three, out):
    result = sandbox.run_desktops("-o", str(out))
    assert result.status == 0, result.describe()

    for file in sandbox.desktop_files(out):
        check = subprocess.run(
            ["desktop-file-validate", str(file)],
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0, f"{file.name} ist ungültig: {check.stdout}{check.stderr}"
