.DEFAULT_GOAL := help
SHELL := /bin/bash

# Database names (must match dbfilter pattern: %d_db where %d = subdomain)
MNL_DB    := mnl_db
BIOLEAF_DB := bioleaf_db

.PHONY: help up down restart logs logs-db pull shell-mnl shell-bioleaf \
        create-dbs init-mnl init-bioleaf update-mnl update-bioleaf \
        backup restore ps

help:
	@echo ""
	@echo "  Odoo — Available commands"
	@echo "  ──────────────────────────────────────────────────────"
	@echo "  make up              Start all services"
	@echo "  make down            Stop all services"
	@echo "  make restart         Restart Odoo (not DB)"
	@echo "  make logs            Tail Odoo logs"
	@echo "  make logs-db         Tail PostgreSQL logs"
	@echo "  make ps              Show running containers"
	@echo "  make pull            Pull latest images"
	@echo ""
	@echo "  make create-dbs      Create mnl_db and bioleaf_db (run once)"
	@echo "  make init-mnl        Install base modules in mnl_db"
	@echo "  make init-bioleaf    Install base modules in bioleaf_db"
	@echo "  make update-mnl      Update all modules in mnl_db (set MODULES=name)"
	@echo "  make update-bioleaf  Update all modules in bioleaf_db"
	@echo ""
	@echo "  make shell-mnl       Open Odoo Python shell for mnl_db"
	@echo "  make shell-bioleaf   Open Odoo Python shell for bioleaf_db"
	@echo "  make backup          Run manual backup"
	@echo ""

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart odoo

logs:
	docker compose logs -f odoo

logs-db:
	docker compose logs -f db

ps:
	docker compose ps

pull:
	docker compose pull

# Enable DB manager temporarily, then create databases, then lock it down again
create-dbs:
	@echo "NOTE: Temporarily enabling list_db — access /web/database/manager now"
	@echo "Create databases: $(MNL_DB) and $(BIOLEAF_DB) — Polish language, Poland country"
	@echo "Then run: make lock-db"

lock-db:
	@echo "After creating databases, ensure list_db = False in odoo.conf and restart"
	docker compose restart odoo

shell-mnl:
	docker compose exec odoo odoo shell -d $(MNL_DB)

shell-bioleaf:
	docker compose exec odoo odoo shell -d $(BIOLEAF_DB)

# Install Polish localization + custom modules
# Run after creating databases via /web/database/manager
# Sensible minimum for full Polish bookkeeping.
# Add point_of_sale, website, fleet etc. later per company need — they pull in
# significant configuration that should not auto-install on first init.
BASE_MODULES := l10n_pl,l10n_pl_edi,l10n_pl_taxable_supply_date,l10n_pl_bank_verification,\
account,account_asset_management,account_financial_report,account_tax_balance,\
sale_management,purchase,stock,\
hr,hr_payroll,l10n_pl_payroll,\
crm,project,maintenance,\
mail,calendar,contacts,\
l10n_pl_edi_fixes,l10n_pl_jpk_v7,l10n_pl_jpk_kr_pd,l10n_pl_nbp_rates

init-mnl:
	docker compose exec odoo odoo \
	  -d $(MNL_DB) \
	  -i $(BASE_MODULES) \
	  --stop-after-init \
	  --without-demo=all

init-bioleaf:
	docker compose exec odoo odoo \
	  -d $(BIOLEAF_DB) \
	  -i $(BASE_MODULES) \
	  --stop-after-init \
	  --without-demo=all

# Update modules (MODULES=all or MODULES=module_name)
MODULES ?= all
update-mnl:
	docker compose exec odoo odoo -d $(MNL_DB) -u $(MODULES) --stop-after-init

update-bioleaf:
	docker compose exec odoo odoo -d $(BIOLEAF_DB) -u $(MODULES) --stop-after-init

backup:
	./scripts/backup.sh

restore:
	@echo "Usage: DB=mnl_db FILE=backups/mnl_db_20260101_120000.sql.gz ./scripts/restore.sh"
