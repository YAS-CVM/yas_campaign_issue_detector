#!/usr/bin/env bash
# Installe une tâche cron qui lance `cvm-monitor run` tous les jours ouvrés (Linux).
# Usage : scripts/install_cron.sh [HEURE] [MINUTE]     (défaut : 9 h 30)
#         scripts/install_cron.sh --remove
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/.venv/bin/cvm-monitor"
LOG="$ROOT/data/cron.log"
TAG="# yas-cvm-monitor"

if [[ "${1:-}" == "--remove" ]]; then
  crontab -l 2>/dev/null | grep -v "$TAG" | crontab -
  echo "Tâche cron supprimée."
  exit 0
fi

HOUR="${1:-9}"
MINUTE="${2:-30}"
[[ -x "$BIN" ]] || { echo "Introuvable : $BIN. Installer d'abord le projet (voir README)."; exit 1; }

# Toutes les 30 min de HOUR à 18 h, du lundi au samedi : le fichier est traité dès qu'il est déposé.
LINE="$MINUTE $HOUR-18/1 * * 1-6 cd \"$ROOT\" && \"$BIN\" run >> \"$LOG\" 2>&1 $TAG"
( crontab -l 2>/dev/null | grep -v "$TAG"; echo "$LINE" ) | crontab -
echo "Tâche cron installée :"
echo "  $LINE"
echo "Journal : $LOG"
