#!/bin/bash
# Restore a single database from a pg_dump custom-format file
# Usage: DB=mnl_db FILE=backups/mnl_db_20260101_120000.dump ./scripts/restore.sh
set -euo pipefail

DB="${DB:?Set DB= to the target database name}"
FILE="${FILE:?Set FILE= to the .dump file path}"
PGUSER="${PGUSER:-odoo}"

if [ ! -f "$FILE" ]; then
    echo "ERROR: File not found: $FILE"
    exit 1
fi

echo "WARNING: This will DROP and recreate the database '$DB'."
echo "Press ENTER to continue, Ctrl+C to abort."
read -r

echo "Dropping $DB..."
docker compose exec -T db dropdb -U "$PGUSER" --if-exists "$DB"

echo "Creating $DB..."
docker compose exec -T db createdb -U "$PGUSER" "$DB"

echo "Restoring from $FILE..."
docker compose exec -T db pg_restore \
    -U "$PGUSER" \
    -d "$DB" \
    --no-owner \
    --role="$PGUSER" < "$FILE"

echo "Restore complete. Restart Odoo: docker compose restart odoo"
