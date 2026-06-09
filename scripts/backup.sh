#!/bin/bash
# Daily backup: pg_dump both databases + Odoo filestore
# Run manually: ./scripts/backup.sh
# Run by cron sidecar: see scripts/backup-cron.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DATE=$(date +%Y%m%d_%H%M%S)
PGUSER="${PGUSER:-odoo}"
PGHOST="${PGHOST:-db}"
DATABASES="${DATABASES:-mnl_db bioleaf_db}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

for DB in $DATABASES; do
    echo "  pg_dump $DB..."
    if docker compose exec -T db pg_dump -U "$PGUSER" -Fc "$DB" > "$BACKUP_DIR/${DB}_${DATE}.dump"; then
        echo "  Saved: $BACKUP_DIR/${DB}_${DATE}.dump"
    else
        echo "  ERROR: pg_dump failed for $DB" >&2
        exit 1
    fi
done

# Backup Odoo filestore (named Docker volume)
FILESTORE_VOLUME=$(docker volume ls --format '{{.Name}}' | grep 'odoo-filestore' | head -1)
if [ -n "$FILESTORE_VOLUME" ]; then
    echo "  Backing up filestore volume: $FILESTORE_VOLUME..."
    docker run --rm \
        -v "${FILESTORE_VOLUME}:/data:ro" \
        -v "$(realpath "$BACKUP_DIR"):/backup" \
        alpine tar czf "/backup/filestore_${DATE}.tar.gz" -C /data .
    echo "  Saved: $BACKUP_DIR/filestore_${DATE}.tar.gz"
else
    echo "  WARNING: odoo-filestore volume not found — skipping filestore backup"
fi

# Prune old backups
find "$BACKUP_DIR" -name "*.dump" -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true

echo "[$(date)] Backup complete. Files:"
ls -lh "$BACKUP_DIR/"*_${DATE}* 2>/dev/null || true
