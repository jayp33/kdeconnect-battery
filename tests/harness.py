"""Testinfrastruktur für die beiden Skripte des Projekts.

Jeder Test bekommt eine Sandbox: ein temporäres Verzeichnis mit eigenem ``PATH``,
``HOME`` und ``XDG_DATA_HOME`` und mit Attrappen für ``gdbus``,
``kdeconnect-cli`` und die Sprachprogramme (tests/fakes/bin). Damit erreicht
kein Test die echten Geräte, und kein Test erzeugt Ton.

Zwei Eigenschaften sind wichtig für die Stabilität der Suite:

* **Harte Zeitbegrenzung.** Jeder Skriptaufruf läuft unter einem Timeout. Ein
  Skript, das sich nicht beendet, lässt den Test scheitern statt den ganzen Lauf
  aufzuhängen.
* **Vorgegebene Antworten.** Die gdbus-Attrappe liest Zeile für Zeile aus
  ``gdbus.script``. Damit lässt sich exakt vorgeben, welche Abfragen das Skript
  in welcher Reihenfolge sieht, statt mit Wartezeiten zu arbeiten. Sind die
  Zeilen aufgebraucht, beendet die Attrappe das Skript.
"""

from __future__ import annotations

import hashlib
import os
import pty
import select
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
BATTERY_SCRIPT = REPO_ROOT / "kdeconnect-battery.sh"
DESKTOPS_SCRIPT = REPO_ROOT / "kdeconnect-battery-desktops.sh"
FAKES_BIN = TESTS_DIR / "fakes" / "bin"


# --------------------------------------------------------------------------
# Erfundene Geräte-IDs
# --------------------------------------------------------------------------


def erfundene_id(keim: str) -> str:
    """Eine erfundene Geräte-ID in der Form, die KDE-Connect verwendet.

    KDE-Connect vergibt 32 Hexadezimalzeichen. Der Wert entsteht aus einem
    lesbaren Keim, damit kein echtes Gerät in den Tests auftaucht, aber
    zwischen zwei Läufen und zwischen Test und Protokoll derselbe steht.
    """
    return hashlib.sha256(keim.encode("utf-8")).hexdigest()[:32]


def erfundene_id_mit_unterstrichen(keim: str) -> str:
    """Dieselbe ID in der älteren Schreibweise mit Unterstrichen."""
    roh = erfundene_id(keim)
    return f"{roh[:8]}_{roh[8:12]}_{roh[12:16]}_{roh[16:20]}_{roh[20:24]}_{roh[24:]}"


# Zeitbegrenzungen in Sekunden. Der Wert für Schleifen muss größer sein als die
# Anzahl der erwarteten Abfragen mal dem Intervall der Tests (1 bis 4 Sekunden).
SCRIPT_TIMEOUT = 30
LOOP_TIMEOUT = 30

# Programme, die der eingeschränkte PATH enthalten muss. Alles andere fehlt dort
# absichtlich, vor allem die Sprachprogramme: Ein auf dem Rechner installiertes
# espeak-ng darf in keinem Test laufen.
MINIMAL_COMMANDS = (
    "bash", "basename", "cat", "chmod", "cut", "date", "dirname", "env",
    "find", "grep", "mkdir", "mv", "rm", "sed", "sleep", "sort", "tr", "wc",
)


@dataclass
class Result:
    """Ergebnis eines Skriptaufrufs."""

    status: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """stdout und stderr zusammen."""
        return self.stdout + self.stderr

    @property
    def status_lines(self) -> list[str]:
        """Die Zeitstempelzeilen, die das Skript je Abfrage ausgibt."""
        return [
            line
            for line in self.stdout.splitlines()
            if "charging=" in line
        ]

    def describe(self) -> str:
        """Lesbare Zusammenfassung für Fehlermeldungen."""
        return (
            f"Exit-Code {self.status}\n"
            f"--- stdout ---\n{self.stdout}"
            f"--- stderr ---\n{self.stderr}"
        )


class Sandbox:
    """Ein Testverzeichnis mit eigenem PATH und Attrappen."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.data = root / "data"
        self.config = root / "config"
        self.bin = root / "bin"
        self.minimal = root / "minimal"
        for path in (self.home, self.data, self.config):
            path.mkdir(parents=True, exist_ok=True)

        # Attrappen kopieren: Ein Test darf einzelne löschen, ohne die anderen zu
        # beeinflussen.
        shutil.copytree(FAKES_BIN, self.bin)

        self.gdbus_script = root / "gdbus.script"
        self.gdbus_log = root / "gdbus.log"
        self.gdbus_count = root / "gdbus.count"
        self.stop_pid = root / "stop.pid"
        self.devices = root / "devices.txt"
        self.tts_log = root / "tts.log"
        self.command_log = root / "command.log"
        self.engine_log = root / "engine.log"
        self.stdout = root / "stdout"
        self.stderr = root / "stderr"
        for path in (self.gdbus_script, self.gdbus_log, self.tts_log,
                     self.command_log, self.engine_log, self.stdout,
                     self.stderr):
            path.write_text("", encoding="utf-8")
        self.gdbus_count.write_text("0", encoding="utf-8")
        self.kde_fail = False
        self.plain_gdbus = False

        self._system_path = os.environ.get("PATH", "")
        self._proc: subprocess.Popen[bytes] | None = None
        self._files: list = []
        self.env = self._environment()

    # ------------------------------------------------------------------
    # Vorbereitung
    # ------------------------------------------------------------------

    def _environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "PATH": f"{self.bin}:{self._system_path}",
                "FAKE_GDBUS_SCRIPT": str(self.gdbus_script),
                "FAKE_GDBUS_LOG": str(self.gdbus_log),
                "FAKE_GDBUS_COUNT": str(self.gdbus_count),
                "FAKE_GDBUS_STOP_PID": str(self.stop_pid),
                "FAKE_KDE_DEVICES": str(self.devices),
                "FAKE_KDE_FAIL": "0",
                "TTS_LOG": str(self.tts_log),
                "COMMAND_LOG": str(self.command_log),
                "ENGINE_LOG": str(self.engine_log),
            }
        )
        return env

    def use_minimal_path(self) -> None:
        """PATH ohne Sprachprogramme und ohne kdeconnect-cli.

        Nötig für Tests, in denen ein Programm *fehlen* soll. Ein bloßes Löschen
        der Attrappe genügt nicht, weil ein auf dem Rechner installiertes
        Programm sonst an ihre Stelle tritt.
        """
        self.minimal.mkdir(parents=True, exist_ok=True)
        for command in MINIMAL_COMMANDS:
            found = shutil.which(command, path=self._system_path)
            if found:
                (self.minimal / command).symlink_to(found)
        self.env["PATH"] = f"{self.bin}:{self.minimal}"

    def reset_fakes(self) -> None:
        """Protokolle leeren, damit sie nur den aktuellen Lauf enthalten."""
        self.gdbus_count.write_text("0", encoding="utf-8")
        self.gdbus_log.write_text("", encoding="utf-8")
        for path in (self.tts_log, self.command_log, self.engine_log,
                     self.stdout, self.stderr):
            path.write_text("", encoding="utf-8")

    def set_status(self, *lines: str) -> None:
        """Eine Zeile je Abfrage: "<Ladestand> <lädt>" (true/false/FAIL/GARBAGE)."""
        self.gdbus_script.write_text(
            "".join(f"{line}\n" for line in lines), encoding="utf-8"
        )

    def set_devices(self, *lines: str) -> None:
        """Eine Zeile je erreichbarem Gerät: "<ID> <Name>"."""
        self.devices.write_text(
            "".join(f"{line}\n" for line in lines), encoding="utf-8"
        )

    def fail_kdeconnect_cli(self) -> None:
        """kdeconnect-cli meldet einen Fehler statt einer Geräteliste."""
        self.env["FAKE_KDE_FAIL"] = "1"

    def plain_gdbus_answers(self) -> None:
        """gdbus antwortet mit "(77,)" statt "(<77>,)"."""
        self.env["FAKE_GDBUS_PLAIN"] = "1"

    def add_fake(self, name: str, body: str) -> Path:
        """Legt eine zusätzliche Attrappe an, die body (bash) ausführt."""
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def add_engine(self, name: str) -> Path:
        """Ein Sprachprogramm, das seine Argumente protokolliert."""
        return self.add_fake(name, 'printf \'%s\\n\' "$*" >> "$ENGINE_LOG"\n')

    def remove_engines(self) -> None:
        for name in ("spd-say", "espeak-ng", "espeak"):
            (self.bin / name).unlink(missing_ok=True)

    def generator_variant(self, *table_entries: str) -> Path:
        """Kopie des Generators mit ausgetauschter device_table.

        So lässt sich prüfen, wie der Generator mit anderen Werten umgeht, ohne
        die Tabelle im echten Skript zu ändern. Die übergebenen Zeilen ersetzen
        den Inhalt zwischen ``device_table=(`` und ``)``.
        """
        body: list[str] = []
        in_table = False
        for line in DESKTOPS_SCRIPT.read_text(encoding="utf-8").splitlines():
            if in_table:
                if line == ")":
                    body.extend(f"    {entry}" for entry in table_entries)
                    body.append(")")
                    in_table = False
                continue
            body.append(line)
            if line == "device_table=(":
                in_table = True
        assert not in_table, "device_table=( nicht gefunden"
        path = self.root / "generator.sh"
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    # ------------------------------------------------------------------
    # Ausführen
    # ------------------------------------------------------------------

    def _spawn(self, argv: list[str], env: dict | None = None, **kwargs) -> subprocess.Popen[bytes]:
        self.reset_fakes()
        out = self.stdout.open("w", encoding="utf-8")
        err = self.stderr.open("w", encoding="utf-8")
        self._files += [out, err]
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            env=env or self.env,
            start_new_session=True,  # eigene Prozessgruppe für das Aufräumen
            **kwargs,
        )
        # Die gdbus-Attrappe braucht die PID des Skripts, um es zu beenden.
        self.stop_pid.write_text(str(proc.pid), encoding="utf-8")
        return proc

    def _close_files(self) -> None:
        for handle in self._files:
            handle.close()
        self._files = []

    def _collect(self, status: int) -> Result:
        self._close_files()
        return Result(
            status=status,
            stdout=self.stdout.read_text(encoding="utf-8"),
            stderr=self.stderr.read_text(encoding="utf-8"),
        )

    def _kill(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
        proc.wait()

    def run(
        self,
        script: Path,
        *args: str,
        env: dict[str, str] | None = None,
        timeout: int = SCRIPT_TIMEOUT,
    ) -> Result:
        """Startet ein Skript im Vordergrund und wartet auf sein Ende."""
        argv = [str(script), *args]
        proc = self._spawn(argv, env=env or self.env)
        try:
            status = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            self._close_files()
            pytest.fail(
                f"{script.name} beendet sich nicht (Timeout nach {timeout}s).\n"
                f"Aufruf: {' '.join(argv)}"
            )
        return self._collect(status)

    def run_battery(self, *args: str, **kwargs) -> Result:
        return self.run(BATTERY_SCRIPT, *args, **kwargs)

    def run_desktops(self, *args: str, **kwargs) -> Result:
        return self.run(DESKTOPS_SCRIPT, *args, **kwargs)

    def run_generated_entry(self, path: Path, *args: str) -> Result:
        """Führt die Exec-Zeile einer erzeugten .desktop-Datei aus.

        Ergänzt werden ``--once`` und das TTS-Kommando der Attrappe, damit der
        Aufruf endet und nichts spricht.
        """
        line = next(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("Exec=")
        )
        argv = line[len("Exec="):].split()
        argv += ["--once", "--tts-command", str(self.bin / "fake-tts"), *args]
        return self.run(Path(argv[0]), *argv[1:])

    def start_battery(self, *args: str) -> subprocess.Popen[bytes]:
        """Startet die Überwachung im Hintergrund (Endlosschleife)."""
        self._proc = self._spawn([str(BATTERY_SCRIPT), *args], env=self.env)
        return self._proc

    def wait_battery(self, timeout: int = LOOP_TIMEOUT) -> Result:
        """Wartet auf das Ende der Überwachung und gibt die Ausgabe zurück."""
        proc = self._proc
        assert proc is not None, "start_battery wurde nicht aufgerufen"
        try:
            status = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            self._close_files()
            pytest.fail(
                "Die Überwachung endete nicht von selbst "
                f"(Timeout nach {timeout}s). Vermutlich zu viele Statuszeilen "
                "in set_status()."
            )
        return self._collect(status)

    def run_pty(
        self, args: list[str], stdin_data: bytes = b"", timeout: int = SCRIPT_TIMEOUT
    ) -> Result:
        """Startet das Skript an einem Pseudoterminal (echte Tastatureingabe).

        Für die interaktive Geräteauswahl: Nur mit einem Terminal liest das
        Skript eine Auswahl ein, und nur dort funktioniert die Ausgabe mit
        Zeilenvorschüben und Echo. ``stdin_data`` geht wie getippt ein;
        ``b"\\x04"`` (Strg-D) beendet die Eingabe wie ein leeres Terminal.
        """
        self.reset_fakes()
        master, slave = pty.openpty()
        argv = [str(BATTERY_SCRIPT), *args]
        proc = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=self.env,
            start_new_session=True,
        )
        self.stop_pid.write_text(str(proc.pid), encoding="utf-8")
        os.close(slave)

        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        try:
            if stdin_data:
                try:
                    os.write(master, stdin_data)
                except OSError:
                    pass  # Das Skript war schon fertig.
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    self._kill(proc)
                    pytest.fail(
                        f"Das Skript endet am Pseudoterminal nicht "
                        f"(Timeout nach {timeout}s)."
                    )
                ready, _, _ = select.select([master], [], [], min(left, 0.5))
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break  # Das Terminal ist geschlossen (EIO unter Linux).
                if not data:
                    break
                chunks.append(data)
            status = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
        finally:
            os.close(master)

        # Am Terminal landen stdout und stderr zusammen.
        return Result(
            status=status, stdout=b"".join(chunks).decode("utf-8", "replace"), stderr=""
        )

    def cleanup(self) -> None:
        self._close_files()
        if self._proc is not None and self._proc.poll() is None:
            self._kill(self._proc)

    # ------------------------------------------------------------------
    # Protokolle lesen
    # ------------------------------------------------------------------

    def tts_fields(self, index: int) -> list[str]:
        """Feld index (1-basiert) aus jeder gesprochenen Zeile."""
        if not self.tts_log.read_text(encoding="utf-8"):
            return []
        rows = [
            row.split("\t")
            for row in self.tts_log.read_text(encoding="utf-8").splitlines()
        ]
        return [row[index - 1] if len(row) >= index else "" for row in rows]

    def tts_texts(self) -> list[str]:
        return self.tts_fields(1)

    def tts_count(self) -> int:
        return len(self.tts_texts())

    def command_rows(self) -> list[list[str]]:
        text = self.command_log.read_text(encoding="utf-8")
        if not text:
            return []
        return [row.split("\t") for row in text.splitlines()]

    def gdbus_properties(self) -> list[str]:
        text = self.gdbus_log.read_text(encoding="utf-8")
        if not text:
            return []
        return [row.split("\t")[1] for row in text.splitlines()]

    def gdbus_paths(self) -> list[str]:
        text = self.gdbus_log.read_text(encoding="utf-8")
        if not text:
            return []
        return [row.split("\t")[0] for row in text.splitlines()]

    def desktop_files(self, directory: Path) -> list[Path]:
        return sorted(directory.glob("*.desktop"))
