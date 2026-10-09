#!/bin/sh
# Consistent backup of the database and uploaded files into ~/calibrator-backups
set -e
cd "$(dirname "$0")/.."
DEST="$HOME/calibrator-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
.venv/bin/python -c "import sqlite3; s=sqlite3.connect('data/db.sqlite3'); d=sqlite3.connect('$DEST/db.sqlite3'); s.backup(d)"
tar -czf "$DEST/media.tar.gz" -C data media
ls -1dt "$HOME"/calibrator-backups/* | tail -n +31 | xargs -r rm -rf   # keep 30
echo "Backup written to $DEST"
