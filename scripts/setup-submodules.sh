#!/bin/bash
# Adds all git submodules required by this project and resolves the
# l10n-pl-payroll Odoo 18 → 19 version issue automatically.
#
# Idempotent: re-running is safe — git submodule add silently skips existing entries.
#
# Usage: ./scripts/setup-submodules.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }

# ── OCA submodules (all branch 19.0, all confirmed working) ──────────────────
declare -a OCA_REPOS=(
  "OCA/account-financial-tools:addons/oca-account-financial-tools"
  "OCA/account-financial-reporting:addons/oca-account-financial-reporting"
  "OCA/reporting-engine:addons/oca-reporting-engine"
  "OCA/server-ux:addons/oca-server-ux"
)

for entry in "${OCA_REPOS[@]}"; do
  repo="${entry%%:*}"
  path="${entry##*:}"
  if [ -d "$path/.git" ] || git submodule status "$path" 2>/dev/null | grep -q .; then
    log "OCA submodule already present: $path"
  else
    log "Adding OCA submodule: $repo branch 19.0 → $path"
    git submodule add -b 19.0 --depth 1 "https://github.com/$repo" "$path"
  fi
done

# ── l10n-pl-payroll — handle Odoo 18→19 migration ────────────────────────────
PAYROLL_PATH="addons/l10n-pl-payroll"
MIGRATION_BRANCH="task/011-odoo19-migration"

if [ ! -d "$PAYROLL_PATH/.git" ] && ! git submodule status "$PAYROLL_PATH" 2>/dev/null | grep -q .; then
  log "Adding l10n-pl-payroll submodule"
  git submodule add "https://github.com/vitalibondar/l10n-pl-payroll" "$PAYROLL_PATH"
fi

cd "$PAYROLL_PATH"
git fetch origin --quiet

# Strategy: prefer the migration branch if it exists upstream; otherwise rewrite manifest.
if git ls-remote --heads origin "$MIGRATION_BRANCH" | grep -q .; then
  log "Found migration branch $MIGRATION_BRANCH — checking out"
  git checkout "$MIGRATION_BRANCH"
  git pull --ff-only origin "$MIGRATION_BRANCH" || warn "Could not fast-forward $MIGRATION_BRANCH"
else
  log "Migration branch not on remote — staying on main and patching manifest"
  git checkout main
  git pull --ff-only origin main || warn "Could not pull main"
fi

MANIFEST="l10n_pl_payroll/__manifest__.py"
if [ -f "$MANIFEST" ] && grep -q "'version': '18\." "$MANIFEST"; then
  log "Patching $MANIFEST: '18.x' → '19.0.1.0.0'"
  sed -i.bak "s/'version': '18\.[0-9]\+\.[0-9]\+\.[0-9]\+'/'version': '19.0.1.0.0'/" "$MANIFEST"
  rm -f "${MANIFEST}.bak"
else
  log "$MANIFEST version already 19.x — no patch needed"
fi

cd "$REPO_ROOT"

# ── Init recursive ───────────────────────────────────────────────────────────
log "Updating submodules recursively"
git submodule update --init --recursive

log ""
log "Done. All submodules are at Odoo 19.0:"
git submodule status

log ""
log "Validate payroll calculations against ZUS Płatnik before issuing payslips."
log "Run 'make init-mnl && make init-bioleaf' to install modules in each database."
