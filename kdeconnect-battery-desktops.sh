#!/usr/bin/env bash
#
# Erzeugt .desktop-Starter für kdeconnect-battery.sh – einen Eintrag je Gerät.
#
# Jede Instanz überwacht genau ein Gerät, also braucht es weiterhin einen Starter je
# Gerät. Solange es die Konfigurationsdatei aus Issue #2 nicht gibt, stehen die
# gerätespezifischen Werte in der Tabelle unten im Skript; danach übernimmt die
# Konfiguration diese Werte und die Tabelle entfällt.

set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# --- Einstellungen, die für alle Geräte gelten -------------------------------

battery_script="$script_dir/kdeconnect-battery.sh"
output_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icon="battery-good"
base_args=(--tts --tts-language de)

# Gerät (Name oder Geräte-ID) | zusätzliche Optionen für kdeconnect-battery.sh
#
# Ohne eigenen Eintrag bekommt ein Gerät die Standardwerte. Die Zuordnung erfolgt
# zuerst über die Geräte-ID, danach über den Namen (beides ohne Beachtung der
# Groß-/Kleinschreibung). Beispiel: "Redmi Pad SE|--charge-limit 70"
#
# $tts_befehl verweist auf das Sprachskript aus tts/kdeconnect-speak. Der
# curl-Aufruf selbst kann nicht in einer Exec-Zeile stehen, weil die nicht von
# einer Shell interpretiert wird. Siehe tts/README.md.
tts_befehl="--tts-command $HOME/.local/bin/kdeconnect-speak"
device_table=(
    "POCO F1|$tts_befehl"
    "Redmi Pad SE|--charge-limit 70 $tts_befehl"
    "POCO X3 Pro|--charge-limit 70 $tts_befehl"
)

# --- Hilfsfunktionen ---------------------------------------------------------

die() {
    printf 'Fehler: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Verwendung:
  kdeconnect-battery-desktops.sh [OPTIONEN]

Erzeugt für jedes erreichbare KDE-Connect-Gerät einen .desktop-Starter, über den
der Akkuvergleich mit Sprachwarnungen gestartet werden kann. Die gerätespezifischen
Werte stehen in der Tabelle device_table im Skript.

Optionen:
  -o, --output-dir VERZEICHNIS  Zielverzeichnis für die .desktop-Dateien
      --script PFAD             Pfad zu kdeconnect-battery.sh
      --list                    Nur verfügbare Geräte und ihre Optionen zeigen
  -n, --dry-run                Nichts schreiben, nur anzeigen
  -h, --help                   Diese Hilfe anzeigen
EOF
}

slugify() {
    local text=$1
    text=${text,,}
    text=${text//[^a-z0-9]/-}
    while [[ $text == *--* ]]; do
        text=${text//--/-}
    done
    text=${text#-}
    text=${text%-}
    printf '%s' "$text"
}

# Eindeutigen Dateinamen vergeben. Namen sind nicht eindeutig, deshalb wird bei
# mehreren Geräten mit gleichem Namen ein Kürzel der Geräte-ID angehängt.
declare -A used_slugs=()
declare -a slugs=()
assign_slugs() {
    declare -A counts=()
    local index slug compact length candidate suffix
    for index in "${!device_names[@]}"; do
        slug=$(slugify "${device_names[$index]}")
        counts[$slug]=$(( ${counts[$slug]:-0} + 1 ))
    done
    for index in "${!device_names[@]}"; do
        slug=$(slugify "${device_names[$index]}")
        compact=${device_ids[$index]//_/}
        compact=${compact,,}
        length=6
        candidate=$slug
        if (( ${counts[$slug]} > 1 )); then
            candidate="$slug-${compact:0:$length}"
        fi
        # Bei einem Namenskonflikt wird das Kürzel der ID verlängert. Ist die
        # ID ausgeschöpft oder beginnen zwei IDs gleich, wird eine laufende
        # Nummer angehängt, damit die Suche immer endet.
        suffix=1
        while [[ -n ${used_slugs[$candidate]:-} ]]; do
            if ((length < ${#compact})); then
                length=$((length + 2))
                candidate="$slug-${compact:0:$length}"
            else
                candidate="$slug-$compact-$suffix"
                ((suffix += 1))
            fi
        done
        used_slugs[$candidate]=1
        slugs+=("$candidate")
    done
}

# Argumente der Tabelle für ein Gerät: zuerst über die ID, dann über den Namen.
# Setzt MATCH_INDEX (Tabellenindex oder -1) und MATCH_ARGS. Bewusst ohne
# Command-Substitution, damit die Zuordnung im aufrufenden Prozess sichtbar ist.
MATCH_INDEX=-1
MATCH_ARGS=""
table_args_for() {
    local id=$1 name=$2 index=0 entry key
    MATCH_INDEX=-1
    MATCH_ARGS=""
    for entry in "${device_table[@]}"; do
        key=${entry%%|*}
        if [[ ${key,,} == ${id,,} ]]; then
            MATCH_INDEX=$index
            MATCH_ARGS=${entry#*|}
            return 0
        fi
        index=$((index + 1))
    done
    index=0
    for entry in "${device_table[@]}"; do
        key=${entry%%|*}
        if [[ ${key,,} == ${name,,} ]]; then
            MATCH_INDEX=$index
            MATCH_ARGS=${entry#*|}
            return 0
        fi
        index=$((index + 1))
    done
}

desktop_file_content() {
    local id=$1 name=$2 extra=$3 comment_suffix=''
    if [[ -n $extra ]]; then
        comment_suffix=" (Optionen: $extra)"
    fi
    cat <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=KDE-Connect-Akku: $name
Comment=Überwacht den Akkustand von $name mit Sprachwarnungen$comment_suffix
Exec=$battery_script --device $id ${base_args[*]}${extra:+ $extra}
Icon=$icon
Terminal=true
Categories=System;
Keywords=Akku;Batterie;KDE Connect;$name;
EOF
}

# --- Optionen einlesen -------------------------------------------------------

list_only=0
dry_run=0
while (($# > 0)); do
    case "$1" in
        -o|--output-dir)
            (($# >= 2)) || die "$1 benötigt ein Verzeichnis."
            output_dir=$2
            shift 2
            ;;
        --script)
            (($# >= 2)) || die "$1 benötigt einen Pfad."
            battery_script=$2
            shift 2
            ;;
        --list)
            list_only=1
            shift
            ;;
        -n|--dry-run)
            dry_run=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unbekannte Option: $1 (siehe --help)"
            ;;
    esac
done

command -v kdeconnect-cli >/dev/null || die "kdeconnect-cli wurde nicht gefunden."
[[ -x $battery_script ]] || die "kdeconnect-battery.sh wurde nicht gefunden oder ist nicht ausführbar: $battery_script"

# --- Geräte ermitteln --------------------------------------------------------

declare -a device_ids=() device_names=()
while read -r id name; do
    [[ -n $id ]] || continue
    device_ids+=("$id")
    device_names+=("$name")
done < <(kdeconnect-cli --list-available --id-name-only 2>/dev/null)

((${#device_ids[@]} > 0)) || die "Keine erreichbaren KDE-Connect-Geräte gefunden."

# --- Modus: nur anzeigen -----------------------------------------------------

if ((list_only)); then
    printf 'Verfügbare Geräte:\n'
    for index in "${!device_ids[@]}"; do
        table_args_for "${device_ids[$index]}" "${device_names[$index]}"
        extra=$MATCH_ARGS
        if [[ -n $extra ]]; then
            printf '  %s (%s)  Optionen: %s\n' "${device_names[$index]}" "${device_ids[$index]}" "$extra"
        else
            printf '  %s (%s)  Standardwerte\n' "${device_names[$index]}" "${device_ids[$index]}"
        fi
    done
    exit 0
fi

# --- Starter schreiben -------------------------------------------------------

assign_slugs

declare -A used_entries=()
written=0

for index in "${!device_ids[@]}"; do
    id=${device_ids[$index]}
    name=${device_names[$index]}
    table_args_for "$id" "$name"
    extra=$MATCH_ARGS
    if ((MATCH_INDEX >= 0)); then
        used_entries[$MATCH_INDEX]=1
    fi

    matches=0
    for other in "${!device_names[@]}"; do
        if [[ ${device_names[$other],,} == ${name,,} ]]; then
            matches=$((matches + 1))
        fi
    done
    if ((matches > 1)); then
        printf 'Warnung: Der Name "%s" passt auf %s Geräte; die Zuordnung per Geräte-ID ist eindeutiger. Datei: kdeconnect-akku-%s.desktop\n' \
            "$name" "$matches" "${slugs[$index]}" >&2
    fi

    file="$output_dir/kdeconnect-akku-${slugs[$index]}.desktop"
    if ((dry_run)); then
        printf 'Würde schreiben: %s\n' "$file"
        desktop_file_content "$id" "$name" "$extra" | sed 's/^/    /'
        continue
    fi

    mkdir -p "$output_dir"
    desktop_file_content "$id" "$name" "$extra" > "$file"
    chmod +x "$file"
    printf 'Geschrieben: %s\n' "$file"
    ((written += 1))
done

# --- Hinweise und Prüfungen --------------------------------------------------

for index in "${!device_table[@]}"; do
    if [[ -z ${used_entries[$index]:-} ]]; then
        printf 'Hinweis: Der Tabelleneintrag "%s" passt zu keinem erreichbaren Gerät.\n' "${device_table[$index]%%|*}" >&2
    fi
done

if ((dry_run)); then
    exit 0
fi

if command -v desktop-file-validate >/dev/null; then
    while IFS= read -r file; do
        if ! desktop-file-validate "$file" >&2; then
            die "$file ist kein gültiger .desktop-Eintrag."
        fi
    done < <(find "$output_dir" -maxdepth 1 -name 'kdeconnect-akku-*.desktop' -print)
fi

for cache in kbuildsycoca6 kbuildsycoca5; do
    if command -v "$cache" >/dev/null; then
        "$cache" --noincremental >/dev/null 2>&1 || true
        break
    fi
done

printf '\n%d Starter erzeugt in %s\n' "$written" "$output_dir"
