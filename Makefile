.DEFAULT_GOAL := help
SHELL := /bin/bash

# Database names (must match dbfilter pattern: %d_db where %d = subdomain)
MNL_DB    := mnl_db
BIOLEAF_DB := bioleaf_db

.PHONY: help quickstart up down restart logs logs-db pull shell-mnl shell-bioleaf \
        create-dbs init-mnl init-bioleaf update-mnl update-bioleaf \
        onboard-mnl onboard-bioleaf onboard-mnl-from-json onboard-bioleaf-from-json \
        list-tax-offices preflight \
        backup restore ps

help:
	@echo ""
	@echo "  polodoo — dostępne komendy"
	@echo "  ──────────────────────────────────────────────────────"
	@echo ""
	@echo "  make quickstart      ⚡ Pierwsza instalacja od zera (5 minut)"
	@echo "                       Robi: setup-submodules.sh + docker build + up -d"
	@echo ""
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
	@echo ""
	@echo "  make onboard-mnl     Interactive PL company onboarding (mnl_db)"
	@echo "  make onboard-bioleaf Interactive PL company onboarding (bioleaf_db)"
	@echo "  make onboard-mnl-from-json     Apply configs/mnl.json non-interactive"
	@echo "  make onboard-bioleaf-from-json Apply configs/bioleaf.json non-interactive"
	@echo "  make list-tax-offices DB=mnl_db   List all Urząd Skarbowy codes"
	@echo ""
	@echo "  make backup          Run manual backup"
	@echo ""

quickstart: preflight
	@echo ""
	@echo "🚀 polodoo quickstart"
	@echo "═══════════════════════════════════════════════════════════"
	@echo ""
	@echo "Krok 1/5: Pobieranie submoduli OCA + payroll..."
	@./scripts/setup-submodules.sh
	@echo ""
	@echo "Krok 2/5: Tworzenie sieci 'coolify' (lokalna namiastka)..."
	@docker network inspect coolify >/dev/null 2>&1 || docker network create coolify
	@echo ""
	@echo "Krok 3/5: Budowanie obrazu Odoo z naszym Dockerfile..."
	@docker compose build
	@echo ""
	@echo "Krok 4/5: Start usług..."
	@docker compose up -d
	@echo ""
	@echo "Krok 5/5: Oczekiwanie aż Odoo będzie zdrowe (do 2 minut)..."
	@for i in $$(seq 1 24); do \
		if docker compose ps odoo --format '{{.Health}}' | grep -q healthy; then \
			echo "  ✓ Odoo healthy"; break; \
		fi; \
		echo "  …czekam $$i/24 (5s każdy)"; sleep 5; \
	done
	@echo ""
	@echo "═══════════════════════════════════════════════════════════"
	@echo "✅ Stack stoi. Następne kroki:"
	@echo ""
	@echo "  1. Stwórz bazy mnl_db i bioleaf_db:"
	@echo "     • Tymczasowo: sed -i.bak 's/^list_db = False/list_db = True/' odoo.conf && make restart"
	@echo "     • Otwórz: https://$$ODOO_DOMAIN_MNL/web/database/manager"
	@echo "     • Master password = wartość ODOO_MASTER_PASSWORD z .env"
	@echo "     • Stwórz mnl_db i bioleaf_db (Polish, no demo data)"
	@echo "     • Wróć: sed -i.bak 's/^list_db = True/list_db = False/' odoo.conf && make restart"
	@echo ""
	@echo "  2. Onboarding danych spółki:"
	@echo "     make onboard-mnl"
	@echo "     make onboard-bioleaf"
	@echo ""
	@echo "  3. Instalacja modułów:"
	@echo "     make init-mnl"
	@echo "     make init-bioleaf"
	@echo ""
	@echo "  4. Weryfikacja:"
	@echo "     Otwórz https://$$ODOO_DOMAIN_MNL — powinien wpuścić do Odoo"
	@echo "     Accounting → Reporting → JPK_V7 → kliknij 'Verify K-Field Mapping'"
	@echo ""
	@echo "Pełna instrukcja: SETUP.md"
	@echo ""

preflight:
	@command -v docker >/dev/null 2>&1 || { echo "❌ docker nie zainstalowany"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "❌ docker daemon nie odpowiada"; exit 1; }
	@[ -f .env ] || { echo "❌ Brak .env. Skopiuj .env.example → .env i uzupełnij sekrety"; exit 1; }
	@grep -q "^POSTGRES_PASSWORD=.\+" .env || { echo "❌ POSTGRES_PASSWORD pusty w .env"; exit 1; }
	@grep -q "^ODOO_MASTER_PASSWORD=.\+" .env || { echo "❌ ODOO_MASTER_PASSWORD pusty w .env"; exit 1; }
	@grep -q "^ODOO_DOMAIN_MNL=.\+" .env || { echo "❌ ODOO_DOMAIN_MNL pusty w .env"; exit 1; }
	@grep -q "^ODOO_DOMAIN_BIOLEAF=.\+" .env || { echo "❌ ODOO_DOMAIN_BIOLEAF pusty w .env"; exit 1; }
	@echo "✓ preflight OK"

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
# Notes on what's excluded and why:
#  - hr_payroll, hr_contract, l10n_pl_taxable_supply_date are Enterprise-only
#    in Odoo 19. The vitalibondar/l10n-pl-payroll module depends on hr_contract
#    so it cannot be installed on CE either. Handle payroll externally in
#    Płatnik (free ZUS desktop app) and book journal entries manually.
BASE_MODULES := l10n_pl,l10n_pl_edi,l10n_pl_bank_verification,account,account_asset_management,account_financial_report,account_tax_balance,sale_management,purchase,stock,hr,crm,project,maintenance,mail,calendar,contacts,l10n_pl_edi_fixes,l10n_pl_jpk_v7,l10n_pl_jpk_kr_pd,l10n_pl_nbp_rates

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

# ── Polish sp. z o.o. onboarding ─────────────────────────────────────────────
# Interactive: asks NIP/KRS/REGON/address/US/bank/KSeF and applies via odoo shell.
# JSON variants apply a pre-saved configs/<company>.json non-interactively.
onboard-mnl:
	./scripts/onboard.py --db $(MNL_DB) --save configs/mnl.json

onboard-bioleaf:
	./scripts/onboard.py --db $(BIOLEAF_DB) --save configs/bioleaf.json

onboard-mnl-from-json:
	./scripts/onboard.py --db $(MNL_DB) --from-json configs/mnl.json --non-interactive

onboard-bioleaf-from-json:
	./scripts/onboard.py --db $(BIOLEAF_DB) --from-json configs/bioleaf.json --non-interactive

# Usage: make list-tax-offices DB=mnl_db | grep -i WOLOM
DB ?= $(MNL_DB)
list-tax-offices:
	@./scripts/onboard.py --db $(DB) --list-tax-offices

backup:
	./scripts/backup.sh

restore:
	@echo "Usage: DB=mnl_db FILE=backups/mnl_db_20260101_120000.sql.gz ./scripts/restore.sh"
