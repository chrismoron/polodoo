#!/bin/bash
# Custom Odoo entrypoint: inject ODOO_MASTER_PASSWORD into odoo.conf
# before delegating to the upstream entrypoint.
#
# Mounted at /entrypoint-wrapper.sh in the container.
set -euo pipefail

CONF_SRC=/etc/odoo/odoo.conf
CONF=/var/lib/odoo/.odoo.conf

# Copy the bind-mounted conf to a user-writable location, then patch the
# master password sentinel. We can't sed -i in /etc/odoo because the dir
# is root-owned and the file is a read-only bind mount on most setups.
cp "$CONF_SRC" "$CONF"
chmod 600 "$CONF"

if [ -n "${ODOO_MASTER_PASSWORD:-}" ]; then
    sed -i "s|^admin_passwd = REPLACE_AT_BOOT$|admin_passwd = ${ODOO_MASTER_PASSWORD}|" "$CONF"
    echo "[entrypoint] Injected ODOO_MASTER_PASSWORD into $CONF"
elif grep -q "^admin_passwd = REPLACE_AT_BOOT$" "$CONF" 2>/dev/null; then
    echo "[entrypoint] WARNING: ODOO_MASTER_PASSWORD not set; database manager will be locked" >&2
fi

# Tell Odoo (and its entrypoint) to use the writable copy
export ODOO_RC="$CONF"

# Delegate to the upstream Odoo entrypoint
exec /entrypoint.sh "$@"
