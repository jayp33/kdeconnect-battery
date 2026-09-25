#!/usr/bin/env bash
#
# Liest den Akkustand eines über KDE Connect gekoppelten Geräts über D-Bus.
# Ohne --device wird eine Geräteliste angezeigt und interaktiv ausgewählt.
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

Ohne --device wird eine Liste der verfügbaren Geräte angezeigt und es kann
eines interaktiv ausgewählt werden.

Optionen:
  -d, --device ID          KDE-Connect-Geräte-ID (alternativ positional)
  -t, --threshold PROZENT  Meldung/Aktion unterhalb dieses Wertes (0 = aus, Standard: 20)
  -i, --interval SEKUNDEN  Abfrageintervall (Standard: 60)
  -c, --command BEFEHL    Shell-Befehl bei niedrigem Akkustand ausführen
      --tts               Sprachausgabe nur für Warnungen aktivieren
      --tts-every-percent Statusansage bei jeder Prozentänderung aktivieren
      --tts-every         Sprachansage bei jedem Abfrageintervall aktivieren
      --tts-language SPRACHE  Sprache für Ansage und Stimme (Standard: en)
      --tts-command BEFEHL  Eigenes TTS-Kommando; erhält $BATTERY_TEXT
      --charge-limit PROZENT  Warnung beim Laden ab diesem Stand (Standard: 80)
  -1, --once              Nur einmal auslesen und beenden
  -h, --help              Diese Hilfe anzeigen

Beispiele:
  ./kdeconnect-battery.sh
  ./kdeconnect-battery.sh --once
  ./kdeconnect-battery.sh -d 0123456789abcdef
  ./kdeconnect-battery.sh -d 0123456789abcdef --once --tts
  ./kdeconnect-battery.sh -d 0123456789abcdef --tts --tts-every-percent
  ./kdeconnect-battery.sh -d 0123456789abcdef --tts --tts-language en-GB
  ./kdeconnect-battery.sh -d 0123456789abcdef --tts --charge-limit 90
  ./kdeconnect-battery.sh -d 0123456789abcdef -t 25 -i 30 --tts-every
  ./kdeconnect-battery.sh -d 0123456789abcdef -t 20 \
      -c 'notify-send "KDE Connect" "Akku nur noch $BATTERY_LEVEL%"'
EOF
}

select_device() {
    local output line id name selection count index
    local -a device_ids=()
    local -a device_names=()

    if ! command -v kdeconnect-cli >/dev/null 2>&1; then
        echo "Fehler: kdeconnect-cli wurde nicht gefunden." >&2
        echo "Ohne --device wird es für die Geräteauswahl benötigt." >&2
        return 1
    fi

    if ! output=$(kdeconnect-cli --list-available --id-name-only 2>&1); then
        echo "Fehler: Die Liste der KDE-Connect-Geräte konnte nicht abgerufen werden." >&2
        [[ -n "$output" ]] && printf '%s\n' "$output" >&2
        return 1
    fi

    while IFS= read -r line; do
        line=${line%$'\r'}
        [[ -n "$line" ]] || continue
        if [[ "$line" =~ ^([^[:space:]]+)[[:space:]]*(.*)$ ]]; then
            id=${BASH_REMATCH[1]}
            name=${BASH_REMATCH[2]}
            [[ -n "$name" ]] || name="(ohne Namen)"
            device_ids+=("$id")
            device_names+=("$name")
        fi
    done <<< "$output"

    count=${#device_ids[@]}
    if ((count == 0)); then
        echo "Keine erreichbaren KDE-Connect-Geräte gefunden." >&2
        echo "Prüfe die Kopplung mit kdeconnect-cli --list-available." >&2
        return 1
    fi

    echo "Verfügbare KDE-Connect-Geräte:"
    for ((index = 0; index < count; index++)); do
        printf '  %d) %s (ID: %s)\n' \
            "$((index + 1))" "${device_names[index]}" "${device_ids[index]}"
    done

    if [[ ! -t 0 ]]; then
        echo "Keine interaktive Auswahl möglich. Bitte --device <GERÄTE-ID> angeben." >&2
        return 1
    fi

    if ! read -r -p "Gerät auswählen [1-$count, Enter = 1]: " selection; then
        echo "Auswahl abgebrochen." >&2
        return 1
    fi
    [[ -n "$selection" ]] || selection=1

    if ! [[ "$selection" =~ ^[1-9][0-9]*$ ]] || ((selection > count)); then
        echo "Ungültige Auswahl: $selection" >&2
        return 1
    fi

    index=$((selection - 1))
    device_id=${device_ids[index]}
    printf 'Ausgewähltes Gerät: %s (%s)\n' "${device_names[index]}" "$device_id"
}

device_id=""
threshold=20
interval=60
once=0
command=""
tts_enabled=0
tts_every=0
tts_every_percent=0
tts_language="en"
tts_command=""
charge_limit=80

while (($# > 0)); do
    case "$1" in
        -d|--device)
            (($# >= 2)) || { echo "Fehler: $1 benötigt eine Geräte-ID." >&2; exit 2; }
            if [[ -n "$device_id" ]]; then
                echo "Fehler: Mehrere Geräte-IDs angegeben." >&2
                exit 2
            fi
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
        --tts-every-percent)
            tts_enabled=1
            tts_every_percent=1
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
    select_device || exit $?
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
# Sie unterscheidet zwei Fehlerarten: Wenn die Abfrage selbst scheitert, ist das
# Gerät nicht erreichbar (last_error_is_connection=1). Antwortet gdbus, ist die
# Antwort aber unlesbar, dann wird diese mit der Originalantwort gemeldet, weil
# das sonst wie ein Verbindungsproblem aussieht und die Ursache verbirgt.
get_property() {
    local property=$1
    local response value

    last_error=""
    last_error_is_connection=0
    if ! response=$(gdbus call --session \
        --dest "$DBUS_SERVICE" \
        --object-path "$object_path" \
        --method org.freedesktop.DBus.Properties.Get \
        "$DBUS_INTERFACE" "$property" 2>&1); then
        last_error="D-Bus-Abfrage von '$property' fehlgeschlagen: $response"
        last_error_is_connection=1
        return 1
    fi

    if [[ ! "$response" =~ ^\((.*)\)$ ]]; then
        last_error="Unerwartete Antwort von gdbus für $property: $response"
        return 1
    fi

    value=${BASH_REMATCH[1]}
    value=${value%,}
    if [[ ${value:0:1} == "<" && ${value: -1} == ">" ]]; then
        value=${value:1:${#value}-2}
    fi
    GET_PROPERTY_VALUE=$value
}

make_low_warning_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        printf 'Achtung. Der Akkustand beträgt nur noch %s Prozent.' "$charge"
    else
        printf 'Warning. The battery level is only %s percent.' "$charge"
    fi
}

make_status_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        if [[ "$is_charging" == "true" ]]; then
            printf 'Der Akku wird geladen. Akkustand %s Prozent.' "$charge"
        elif ((threshold > 0 && charge <= threshold)); then
            make_low_warning_text
        else
            printf 'Akkustand %s Prozent.' "$charge"
        fi
    else
        if [[ "$is_charging" == "true" ]]; then
            printf 'The battery is charging. The battery level is %s percent.' "$charge"
        elif ((threshold > 0 && charge <= threshold)); then
            make_low_warning_text
        else
            printf 'The battery level is %s percent.' "$charge"
        fi
    fi
}

make_charge_warning_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        printf 'Achtung. Der Akku ist bei %s Prozent, über dem Ladelimit von %s Prozent, und lädt noch. Du kannst das Laden jetzt beenden.' "$charge" "$charge_limit"
    else
        printf 'Warning. The battery is at %s percent, above the %s percent limit, and is still charging. You can stop charging now.' "$charge" "$charge_limit"
    fi
}

make_connection_lost_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        printf 'Die Verbindung zum Gerät wurde unterbrochen. Ich versuche es erneut.'
    else
        printf 'The connection to the device was lost. I will try again.'
    fi
}

make_connection_restored_text() {
    if [[ "${tts_language,,}" == de* ]]; then
        printf 'Die Verbindung zum Gerät ist wiederhergestellt.'
    else
        printf 'The connection to the device has been restored.'
    fi
}

speak_text() {
    local text=$1

    if ! DEVICE_ID="$device_id" \
        BATTERY_LEVEL="${charge:-}" \
        BATTERY_CHARGING="${is_charging:-}" \
        BATTERY_LANGUAGE="$tts_language" \
        BATTERY_CHARGE_LIMIT="$charge_limit" \
        BATTERY_CONNECTION="$connection_state" \
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
    read_error=""
    read_error_is_connection=0

    if ! get_property charge; then
        read_error=$last_error
        read_error_is_connection=$last_error_is_connection
        return 1
    fi
    charge=$GET_PROPERTY_VALUE

    if ! get_property isCharging; then
        read_error=$last_error
        read_error_is_connection=$last_error_is_connection
        return 1
    fi
    is_charging=$GET_PROPERTY_VALUE

    if [[ "$charge" == "-1" ]]; then
        read_error="Für dieses Gerät wurde noch kein gültiger Akkustand gemeldet (charge=-1)."
        return 1
    fi
    if ! [[ "$charge" =~ ^[0-9]+$ ]] || ((charge > 100)); then
        read_error="KDE-Connect hat einen ungültigen Akkustand gemeldet: $charge"
        return 1
    fi
    if [[ "$is_charging" != "true" && "$is_charging" != "false" ]]; then
        read_error="KDE-Connect hat einen ungültigen Ladezustand gemeldet: $is_charging"
        return 1
    fi
}

low=0
charge_warning_active=0
last_charge_warning_charge=""
last_tts_charge=""
charge=""
is_charging=""
GET_PROPERTY_VALUE=""
last_error=""
last_error_is_connection=0
read_error=""
read_error_is_connection=0
connection_state="unknown"

while true; do
    if ! read_status; then
        if ((read_error_is_connection)); then
            if [[ "$connection_state" != "disconnected" ]]; then
                connection_state="disconnected"
                low=0
                charge_warning_active=0
                printf '%(%F %T)T  KDE-Connect-Gerät ist nicht erreichbar. Der nächste Versuch erfolgt in %s Sekunden.\n' -1 "$interval"
                if ((tts_enabled)); then
                    speak_text "$(make_connection_lost_text)"
                fi
            fi
        else
            printf '%(%F %T)T  %s\n' -1 "${read_error:-KDE-Connect-Akkuinformationen konnten nicht gelesen werden.}"
        fi
        if ((once)); then
            exit 1
        fi
        sleep "$interval"
        continue
    fi

    if [[ "$connection_state" == "disconnected" ]]; then
        connection_state="connected"
        last_tts_charge=$charge
        printf '%(%F %T)T  Verbindung zum Gerät wiederhergestellt.\n' -1
        if ((tts_enabled)); then
            speak_text "$(make_connection_restored_text)"
        fi
    elif [[ "$connection_state" == "unknown" ]]; then
        connection_state="connected"
    fi

    printf '%(%F %T)T  %s%%, charging=%s\n' -1 "$charge" "$is_charging"

    # Die Unterladewarnung wird nur beim Eintritt in den Warnzustand gesprochen.
    low_warning_now=0
    if [[ "$is_charging" == "false" ]] && ((threshold > 0 && charge <= threshold)); then
        if ((low == 0)); then
            low=1
            low_warning_now=1
            printf 'Akkustand niedrig: %s%%.\n' "$charge"
            if ((tts_enabled)); then
                speak_text "$(make_low_warning_text)"
                last_tts_charge=$charge
            fi
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

    charge_warning_now=0
    if ((charge_limit > 0)) && [[ "$is_charging" == "true" ]] && ((charge >= charge_limit)); then
        charge_warning_now=1
    fi

    if ((charge_warning_now)); then
        if ((charge_warning_active == 0)); then
            charge_warning_active=1
            printf 'Ladewarnung: Der Akku ist bei %s%% (Ladelimit: %s%%) und lädt noch.\n' "$charge" "$charge_limit"
            if ((tts_enabled)); then
                speak_text "$(make_charge_warning_text)"
                last_tts_charge=$charge
                last_charge_warning_charge=$charge
            fi
        elif ((tts_enabled == 1 && tts_every == 1)); then
            speak_text "$(make_charge_warning_text)"
            last_tts_charge=$charge
            last_charge_warning_charge=$charge
        elif ((tts_enabled == 1 && tts_every_percent == 1)) &&
            [[ -z "$last_charge_warning_charge" || "$charge" != "$last_charge_warning_charge" ]]; then
            speak_text "$(make_charge_warning_text)"
            last_tts_charge=$charge
            last_charge_warning_charge=$charge
        fi
    else
        charge_warning_active=0
        last_charge_warning_charge=""
    fi

    should_speak=0
    if ((tts_enabled == 1 && charge_warning_now == 0 && low_warning_now == 0)); then
        if ((tts_every)); then
            should_speak=1
        elif ((tts_every_percent)) && [[ -z "$last_tts_charge" || "$charge" != "$last_tts_charge" ]]; then
            should_speak=1
        fi
    fi
    if ((should_speak)); then
        speak_status
        last_tts_charge=$charge
    fi

    if ((once)); then
        exit 0
    fi
    sleep "$interval"
done
