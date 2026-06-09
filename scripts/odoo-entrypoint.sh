#!/bin/bash
# Custom Odoo entrypoint: inject ODOO_MASTER_PASSWORD into odoo.conf
# before delegating to the upstream entrypoint.
#
# Mounted at /entrypoint-wrapper.sh in the container.
set -euo pipefail

CONF=/etc/odoo/odoo.conf

if [ -n "${ODOO_MASTER_PASSWORD:-}" ] && [ -w "$CONF" ]; then
    # Replace the REPLACE_AT_BOOT sentinel with the real password.
    # Use a non-shell-interpolated delimiter to handle passwords with /
    sed -i "s|^admin_passwd = REPLACE_AT_BOOT$|admin_passwd = ${ODOO_MASTER_PASSWORD}|" "$CONF"
    echo "[entrypoint] Injected ODOO_MASTER_PASSWORD into odoo.conf"
elif grep -q "^admin_passwd = REPLACE_AT_BOOT$" "$CONF" 2>/dev/null; then
    echo "[entrypoint] WARNING: ODOO_MASTER_PASSWORD not set; database manager will be locked" >&2
fi

# Delegate to the upstream Odoo entrypoint
exec /entrypoint.sh "$@"
