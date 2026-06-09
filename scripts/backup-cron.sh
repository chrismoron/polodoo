#!/bin/bash
# Cron-driven backup: pg_dump both databases + tar the Odoo filestore.
# Mounted at /backup-cron.sh in the db-backup sidecar.
#
# Failure semantics:
#   - Each pg_dump runs into a temp file; on failure the temp file is removed.
#   - If ANY backup fails, the script exits non-zero AND the retention prune is skipped
#     to avoid silently deleting old known-good dumps while new ones are missing.
#   - Filestore is tar'd via a side-channel (read-only volume mount in sidecar).
#
# Optional off-host upload: set BACKUP_S3_BUCKET to enable.
set -euo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
PGUSER="${PGUSER:-odoo}"
PGHOST="${PGHOST:-db}"
DATABASES="${DATABASES:-mnl_db bioleaf_db}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
FILESTORE_MNT="${FILESTORE_MNT:-/filestore}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

echo "[$(date)] Backup started"
FAILED=0

for DB in $DATABASES; do
    DUMP="$BACKUP_DIR/${DB}_${DATE}.dump"
    DUMP_TMP="${DUMP}.partial"
    echo "  Dumping $DB → $(basename "$DUMP")"
    if pg_dump -h "$PGHOST" -U "$PGUSER" -Fc -f "$DUMP_TMP" "$DB"; then
        chmod 600 "$DUMP_TMP"
        mv "$DUMP_TMP" "$DUMP"
        echo "  OK: $(du -sh "$DUMP" | cut -f1)"
    else
        echo "  FAILED: $DB" >&2
        rm -f "$DUMP_TMP"
        FAILED=1
    fi
done

# Filestore backup (if the volume is mounted into the sidecar)
if [ -d "$FILESTORE_MNT" ]; then
    FS_TAR="$BACKUP_DIR/filestore_${DATE}.tar.gz"
    FS_TMP="${FS_TAR}.partial"
    echo "  Tarring filestore..."
    if tar czf "$FS_TMP" -C "$FILESTORE_MNT" . 2>/dev/null; then
        chmod 600 "$FS_TMP"
        mv "$FS_TMP" "$FS_TAR"
        echo "  OK: $(du -sh "$FS_TAR" | cut -f1)"
    else
        echo "  FAILED: filestore tar" >&2
        rm -f "$FS_TMP"
        FAILED=1
    fi
else
    echo "  SKIP: filestore (not mounted at $FILESTORE_MNT)" >&2
fi

# Off-host upload (optional)
if [ "$FAILED" -eq 0 ] && [ -n "${BACKUP_S3_BUCKET:-}" ] && command -v aws >/dev/null 2>&1; then
    echo "  Uploading to s3://$BACKUP_S3_BUCKET/..."
    aws s3 sync "$BACKUP_DIR" "s3://$BACKUP_S3_BUCKET/$(hostname)/$(date +%Y-%m)/" \
        --exclude '*.partial' \
        ${BACKUP_S3_ENDPOINT:+--endpoint-url "$BACKUP_S3_ENDPOINT"} \
        --sse AES256 \
        || { echo "  WARN: S3 upload failed" >&2; FAILED=1; }
fi

# Retention: only prune if all backups succeeded — never delete good ones to make
# room for broken ones.
if [ "$FAILED" -eq 0 ]; then
    find "$BACKUP_DIR" -name "*.dump" -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "*.tar.gz" -mtime +"$RETAIN_DAYS" -delete 2>/dev/null || true
    echo "[$(date)] Backup complete — pruned files older than ${RETAIN_DAYS}d"
else
    echo "[$(date)] Backup FAILED — retention pruning SKIPPED to protect good archives" >&2
fi

exit "$FAILED"
