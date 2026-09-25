#!/usr/bin/env bash
#
# Liest den Akkustand eines über KDE Connect gekoppelten Geräts über D-Bus.
#
# Ohne --command wird bei jedem Unterschreiten des Schwellenwerts nur eine
# Meldung ausgegeben. Mit --command kann ein beliebiger Shell-Befehl ausgeführt
# werden. Der Befehl erhält DEVICE_ID, BATTERY_LEVEL und BATTERY_CHARGING als
# Umgebungsvariablen. Mit --tts kann der Status zusätzlich vorgelesen werden;
# das TTS-Kommando erhält zusätzlich BATTERY_TEXT.

set -Eeuo pipefail

readonly DBUS_SERVICE="org.kde.kdeconnect"
readonly DBUS_INTERFACE="org.kde.kdeconnect.device.battery"

usage() {
    cat <<'EOF'
Verwendung:
  kdeconnect-battery.sh [OPTIONEN] [GERÄTE-ID]

Optionen:
  -d, --device ID          KDE-Connect-Geräte-ID (alternativ positional)
  -t, --threshold PROZENT  Meldung/Aktion unterhalb dieses Wertes (Standard: 20)
  -i, --interval SEKUNDEN  Abfrageintervall (Standard: 60)
  -c, --command BEFEHL    Shell-Befehl bei niedrigem Akkustand ausführen
      --tts               Sprachansage bei Statusänderung aktivieren
      --tts-every         Sprachansage bei jedem Abfrageintervall aktivieren
      --tts-language SPRACHE  Sprache für Ansage und Stimme (Standard: en)
      --tts-command BEFEHL  Eigenes TTS-Kommando; erhält $BATTERY_TEXT
      --charge-limit PROZENT  Warnung beim Laden ab diesem Stand (Standard: aus)
  -1, --once              Nur einmal auslesen und beenden
  -h, --help              Diese Hilfe anzeigen

Beispiele:
  ./kdeconnect-battery.sh -d 0123456789abcdef
  ./kdeconnect-battery.sh -d 0123456789abcdef --once --tts
  ./kdeconnect-battery.sh -d 0123456789abcdef --tts --tts-language en-GB
  ./kdeconnect-battery.sh -d 0123456789abcdef --tts --charge-limit 80
  ./kdeconnect-battery.sh -d 0123456789abcdef -t 25 -i 30 --tts-every
  ./kdeconnect-battery.sh -d 0123456789abcdef -t 20 \
      -c 'notify-send "KDE Connect" "Akku nur noch $BATTERY_LEVEL%"'
EOF
}

device_id=""
threshold=20
interval=60
once=0
command=""
tts_enabled=0
tts_every=0
tts_language="en"
tts_command=""
charge_limit=0

if (($# == 0)); then
    usage >&2
    exit 2
fi

while (($# > 0)); do
    case "$1" in
        -d|--device)
            (($# >= 2)) || { echo "Fehler: $1 benötigt eine Geräte-ID." >&2; exit 2; }
            device_id=$2
            shift 2
            ;;
        -t|--threshold)
            (($# >= 2)) || { echo "Fehler: $1 benötigt einen Prozentwert." >&2; exit 2; }
            threshold=$2
            shift 2
            ;;
        -i|--interval)
            (($# >= 2)) || { echo "Fehler: $1 benötigt eine Anzahl Sekunden." >&2; exit 2; }
            interval=$2
            shift 2
            ;;
        -c|--command)
            (($# >= 2)) || { echo "Fehler: $1 benötigt einen Befehl." >&2; exit 2; }
            command=$2
            shift 2
            ;;
        --tts)
            tts_enabled=1
            shift
            ;;
        --tts-every)
            tts_enabled=1
            tts_every=1
            shift
            ;;
        --tts-language)
            (($# >= 2)) || { echo "Fehler: $1 benötigt eine Sprache." >&2; exit 2; }
            tts_language=$2
            tts_enabled=1
            shift 2
            ;;
        --tts-command)
            (($# >= 2)) || { echo "Fehler: $1 benötigt ein TTS-Kommando." >&2; exit 2; }
            tts_command=$2
            tts_enabled=1
            shift 2
            ;;
        --charge-limit)
            (($# >= 2)) || { echo "Fehler: $1 benötigt einen Prozentwert." >&2; exit 2; }
            charge_limit=$2
            if [[ "$charge_limit" != "0" ]]; then
                tts_enabled=1
            fi
            shift 2
            ;;
        -1|--once)
            once=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unbekannte Option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -n "$device_id" ]]; then
                echo "Fehler: Mehrere Geräte-IDs angegeben." >&2
                exit 2
            fi
            device_id=$1
            shift
            ;;
    esac
done

# Optionale positional arguments nach "--" als Geräte-ID zulassen.
if (($# > 0)); then
    if [[ -n "$device_id" || $# -ne 1 ]]; then
        echo "Fehler: Ungültige Geräte-ID." >&2
        exit 2
    fi
    device_id=$1
    shift
fi

if [[ -z "$device_id" ]]; then
    echo "Es wurde keine Geräte-ID angegeben." >&2
    usage >&2
    exit 2
fi

if ! [[ "$threshold" =~ ^[0-9]+$ ]] || ((threshold < 0 || threshold > 100)); then
    echo "Fehler: --threshold muss eine Zahl zwischen 0 und 100 sein." >&2
    exit 2
fi

if ! [[ "$interval" =~ ^[1-9][0-9]*$ ]]; then
    echo "Fehler: --interval muss eine positive ganze Zahl sein." >&2
    exit 2
fi

if ! [[ "${tts_language,,}" =~ ^(en|de)([-_][A-Za-z0-9]+)?$ ]]; then
    echo "Fehler: --tts-language unterstützt z. B. en, en-GB, de oder de-DE." >&2
    exit 2
fi

if ! [[ "$charge_limit" =~ ^(0|[1-9][0-9]*)$ ]] || ((charge_limit > 100)); then
    echo "Fehler: --charge-limit muss 0 (aus) oder eine Zahl von 1 bis 100 sein." >&2
    exit 2
fi

if ! command -v gdbus >/dev/null 2>&1; then
    echo "Fehler: gdbus wurde nicht gefunden." >&2
    echo "Installiere auf Debian/Ubuntu z. B. das Paket libglib2.0-bin." >&2
    exit 1
fi

if ((tts_enabled)); then
    tts_voice=${tts_language,,}
    tts_voice=${tts_voice//_/-}
    case "$tts_voice" in
        en)
            tts_voice="en-us"
            ;;
        de|de-*)
            tts_voice="de"
            ;;
    esac

    if [[ -z "$tts_command" ]]; then
        if command -v spd-say >/dev/null 2>&1; then
            tts_command="spd-say -l $tts_voice \"\$BATTERY_TEXT\""
        elif command -v espeak-ng >/dev/null 2>&1; then
            tts_command="espeak-ng -v $tts_voice \"\$BATTERY_TEXT\""
        elif command -v espeak >/dev/null 2>&1; then
            tts_command="espeak -v $tts_voice \"\$BATTERY_TEXT\""
        else
            echo "Fehler: Kein TTS-Programm gefunden." >&2
            echo "Installiere z. B. espeak-ng oder verwende --tts-command." >&2
            exit 1
        fi
    fi
fi

readonly object_path="/modules/kdeconnect/devices/${device_id}/battery"

# gdbus gibt skalare Varianten je nach Version als "(87,)" oder
# "(<87>,)" aus. Die folgende Funktion entfernt diese GVariant-Verpackung.
get_property() {
    local property=$1
    local response value

    if ! response=$(gdbus call --session \
        --dest "$DBUS_SERVICE" \
        --object-path "$object_path" \
        --method org.freedesktop.DBus.Properties.Get \
        "$DBUS_INTERFACE" "$property" 2>&1); then
        echo "D-Bus-Abfrage von '$property' fehlgeschlagen: $response" >&2
        return 1
    fi

    if [[ ! "$response" =~ ^\((.*)\)$ ]]; then
        echo "Unerwartete Antwort von gdbus für $property: $response" >&2
        return 1
    fi

    value=${BASH_REMATCH[1]}
    value=${value%,}
    if [[ ${value:0:1} == "<" && ${value: -1} == ">" ]]; then
        value=${value:1:${#value}-2}
    fi
    printf '%s\n' "$value"
}

make_status_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        if [[ "$is_charging" == "true" ]]; then
            printf 'Der Akku wird geladen. Akkustand %s Prozent.' "$charge"
        elif ((charge <= threshold)); then
            printf 'Achtung. Der Akkustand beträgt nur noch %s Prozent.' "$charge"
        else
            printf 'Akkustand %s Prozent.' "$charge"
        fi
    else
        if [[ "$is_charging" == "true" ]]; then
            printf 'The battery is charging. The battery level is %s percent.' "$charge"
        elif ((charge <= threshold)); then
            printf 'Warning. The battery level is only %s percent.' "$charge"
        else
            printf 'The battery level is %s percent.' "$charge"
        fi
    fi
}

make_charge_warning_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        printf 'Achtung. Der Akku ist zu %s Prozent oder mehr geladen und lädt noch. Du kannst das Laden jetzt beenden.' "$charge_limit"
    else
        printf 'Warning. The battery is at %s percent or higher and is still charging. You can stop charging now.' "$charge_limit"
    fi
}

speak_text() {
    local text=$1

    if ! DEVICE_ID="$device_id" \
        BATTERY_LEVEL="$charge" \
        BATTERY_CHARGING="$is_charging" \
        BATTERY_LANGUAGE="$tts_language" \
        BATTERY_CHARGE_LIMIT="$charge_limit" \
        BATTERY_TEXT="$text" \
        bash -c "$tts_command"; then
        echo "TTS-Befehl ist mit einem Fehler beendet: $tts_command" >&2
    fi
}

speak_status() {
    speak_text "$(make_status_text)"
}

read_status() {
    # Die Eigenschaft "charge" ist die in allen KDE-Connect-Versionen
    # vorhandene und maßgebliche Eigenschaft. "hasBattery" ist erst in
    # neueren Versionen vorhanden und darf hier nicht vorausgesetzt werden.
    charge=$(get_property charge) || return 1
    is_charging=$(get_property isCharging) || return 1

    if [[ "$charge" == "-1" ]]; then
        echo "Für dieses Gerät wurde noch kein gültiger Akkustand gemeldet (charge=-1)." >&2
        return 1
    fi
    if ! [[ "$charge" =~ ^[0-9]+$ ]] || ((charge > 100)); then
        echo "Ungültiger Akkustand: $charge" >&2
        return 1
    fi
    if [[ "$is_charging" != "true" && "$is_charging" != "false" ]]; then
        echo "Ungültiger Ladezustand: $is_charging" >&2
        return 1
    fi
}

low=0
charge_warning_active=0
last_tts_key=""

while true; do
    if ! read_status; then
        echo "KDE-Connect-Akkuinformationen konnten nicht gelesen werden." >&2
        if ((once)); then
            exit 1
        fi
        sleep "$interval"
        continue
    fi

    printf '%(%F %T)T  %s%%, charging=%s\n' -1 "$charge" "$is_charging"

    tts_key="${charge}:${is_charging}"
    charge_warning_now=0
    if ((charge_limit > 0)) && [[ "$is_charging" == "true" ]] && ((charge >= charge_limit)); then
        charge_warning_now=1
    fi

    if ((charge_warning_now)); then
        if ((charge_warning_active == 0)); then
            charge_warning_active=1
            printf 'Ladewarnung: Das Akku ist bei %s%% oder höher und lädt noch.\n' "$charge"
            if ((tts_enabled)); then
                speak_text "$(make_charge_warning_text)"
                last_tts_key=$tts_key
            fi
        elif ((tts_enabled == 1 && tts_every == 1)); then
            speak_text "$(make_charge_warning_text)"
        fi
    else
        charge_warning_active=0
    fi

    should_speak=0
    if ((tts_enabled == 1 && charge_warning_now == 0)); then
        if ((tts_every)) || [[ "$tts_key" != "$last_tts_key" ]]; then
            should_speak=1
        fi
    fi
    if ((should_speak)); then
        speak_status
        last_tts_key=$tts_key
    fi

    if [[ "$is_charging" == "false" ]] && ((charge <= threshold)); then
        if ((low == 0)); then
            low=1
            printf 'Akkustand niedrig: %s%%.\n' "$charge"
            if [[ -n "$command" ]]; then
                if ! DEVICE_ID="$device_id" BATTERY_LEVEL="$charge" BATTERY_CHARGING="$is_charging" \
                    bash -c "$command"; then
                    echo "Der konfigurierte Befehl ist mit einem Fehler beendet." >&2
                fi
            fi
        fi
    else
        low=0
    fi

    if ((once)); then
        exit 0
    fi
    sleep "$interval"
done
