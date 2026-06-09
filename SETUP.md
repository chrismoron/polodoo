# Odoo 19 CE — Polish sp. z o.o. Setup Guide

Fully Dockerized, Coolify-ready Odoo for:
- **MNL sp. z o.o.** → `mnl.yourdomain.com` → database `mnl_db`
- **Bioleaf sp. z o.o.** → `bioleaf.yourdomain.com` → database `bioleaf_db`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Module Stack — 100% Free & Open Source](#2-module-stack--100-free--open-source)
3. [Initial Server Setup](#3-initial-server-setup)
4. [Coolify Deployment](#4-coolify-deployment)
5. [Database Initialization](#5-database-initialization)
6. [Polish Compliance Configuration](#6-polish-compliance-configuration)
7. [KSeF e-Invoicing Setup](#7-ksef-e-invoicing-setup)
8. [JPK Reporting Setup](#8-jpk-reporting-setup)
9. [Fixed Assets — Środki Trwałe](#9-fixed-assets--środki-trwałe)
10. [POS & Kasa Fiskalna Setup](#10-pos--kasa-fiskalna-setup)
12. [HR & Payroll Setup](#12-hr--payroll-setup)
13. [Backup & Recovery](#13-backup--recovery)
14. [Compliance Checklist](#14-compliance-checklist)
15. [Known Issues & Gaps](#15-known-issues--gaps)

---

## 1. Architecture Overview

```
Internet
    │
    ▼
Coolify (Traefik) ── SSL/TLS (Let's Encrypt)
    │
    ├── mnl.yourdomain.com ──► Odoo 19 CE (port 8069)
    └── bioleaf.yourdomain.com ─┘
                                 │
                          dbfilter: ^%d_db$
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
                 mnl_db                  bioleaf_db
                    └──────── PostgreSQL 16 ──┘
                                    │
                              Named Volume
                              (pg-data)

Odoo Filestore ── Named Volume (odoo-filestore)
Custom addons  ── Bind mount  (./custom_addons)
Third-party    ── Bind mount  (./addons)
```

**Why two databases, one Odoo process:**
Both companies are legally independent with separate VAT registrations, employees, and accounting. Two databases give database-level isolation while sharing one server cost and one maintenance window. Odoo's `dbfilter` routes each subdomain to its own database automatically.

---

## 2. Module Stack — 100% Free & Open Source

**Total cost for all compliance modules: €0.**

After exhaustive research (5 parallel agents scanning GitHub, OCA, apps.odoo.com, Polish Odoo forums), here is what Odoo 19.0 CE provides free and what we built ourselves.

### Built-in Odoo 19.0 CE (LGPL-3, zero cost)

These are bundled in the `odoo:19.0` Docker image. No downloads needed.

| Module | Purpose | Source |
|---|---|---|
| `l10n_pl` | Polish chart of accounts, VAT rates (23/8/5/0/ZW), GTU codes on products, fiscal positions | [GitHub](https://github.com/odoo/odoo/tree/19.0/addons/l10n_pl) |
| `l10n_pl_edi` | **KSeF FA(3) e-invoicing** — send/receive invoices via KSeF 2.0 API, UPO, offline mode | [GitHub](https://github.com/odoo/odoo/tree/19.0/addons/l10n_pl_edi) |
| `l10n_pl_taxable_supply_date` | Taxable supply date field (P_6 in FA(3), separate from invoice date) | Built-in |
| `l10n_pl_bank_verification` | **Biała lista** — white list verification against gov.pl API before payments >PLN 15k | Built-in |
| `account` | Core double-entry accounting (`account_accountant` is Enterprise-only) | Built-in |
| `sale`, `purchase`, `stock` | Sales, purchasing, inventory | Built-in |
| `point_of_sale` | Point of Sale (optional) | Built-in |
| `website`, `website_sale` | eCommerce / website (optional) | Built-in |
| `hr` | Employee records | Built-in |
| `crm` | Customer relationship management | Built-in |
| `project` | Projects (renovation, construction, etc.) | Built-in |
| `maintenance` | Equipment maintenance | Built-in |
| `fleet` | Company vehicles | Built-in |
| `sale_subscription` | Recurring subscriptions (optional) | Built-in |
| `event`, `event_sale` | Event management (optional) | Built-in |

### Custom modules in this repository (LGPL-3, zero cost)

| Module | Purpose |
|---|---|
| `l10n_pl_edi_fixes` | Patches 4 compliance gaps in `l10n_pl_edi`: GTU in FA(3) XML, MPP field (P_18A), VAT exemption basis (P_19a/b/c), **KSeF API URL fix** (GitHub #247360) |
| `l10n_pl_jpk_v7` | **JPK_V7M(3) / JPK_V7K(3) XML generator** — generates monthly VAT SAF-T files from Odoo accounting data. Custom built since no free module exists anywhere. |
| `l10n_pl_nbp_rates` | Daily PLN exchange rates from Narodowy Bank Polski Table A — standalone, no OCA dependency |
| `l10n_pl_jpk_kr_pd` | **JPK_KR_PD (JPK_CIT) generator** — full Naglowek/Podmiot1/Kontrahenci/ZOiS/Dziennik/Ctrl/RPD implementation. Defaults to ZOiS8 (IFRS variant — markers optional). Deadline 2027-07-31. |

### Third-party open source (LGPL-3, zero cost, add as git submodule)

| Module | Purpose | Source |
|---|---|---|
| `l10n_pl_payroll` (vitalibondar) | Polish payroll: ZUS contributions, PIT advance (12%/32%), PPK, PIT-11/DRA/RCA — LGPL-3, actively maintained | [GitHub](https://github.com/vitalibondar/l10n-pl-payroll) |

To add:
```bash
git submodule add https://github.com/vitalibondar/l10n-pl-payroll custom_addons/l10n_pl_payroll
```

> **Note on payroll maturity:** This is a single-team project built for one 82-employee Polish manufacturer. It has 15+ test files, correct 2025/2026 contribution rates, and ZUS DRA/RCA/PIT-11 generation. It is NOT OCA-vetted. Validate every payslip against Płatnik (free ZUS software) before relying on it.

### OCA modules (free, AGPL-3) — fills operational reporting gap

Add as git submodules (see §3):

| Module | Purpose |
|---|---|
| `account_financial_report` | Trial Balance (ZOiS), General Ledger (Dziennik), Aged Receivable/Payable (Rozrachunki wiekowane), Open Items (Salda otwarte), Journal Ledger |
| `account_tax_balance` | VAT balance verification |

### Remaining gaps (no free solution exists anywhere as of June 2026)

| Gap | Severity | Best free option |
|---|---|---|
| **Bilans statutory format** (Załącznik 1/4/5 UoR) | HIGH — required for KRS annual filing | `om_account_accountant` (LGPL-3, free, Odoo 19 CE) gives generic Balance Sheet — not statutory format. For KRS filing: export Trial Balance from OCA → accountant generates Bilans in Comarch Optima (~€200/yr). See note below. |
| **RZiS statutory format** | HIGH — required alongside Bilans | Same as Bilans |
| **Kasa fiskalna (fiscal printer)** | HIGH for B2C POS | Standalone fiscal printer + daily Z-report → manual journal entry in Odoo. Seek legal exemption for online/card-only sales. |
| **JPK_V7M tag mapping** | MEDIUM | Validate K-field mapping after install. |
| **Przelewy24 / BLIK** | Payment gateway | Use Stripe (free Odoo integration) which supports Przelewy24 as a payment method natively. |

> **Bilans/RZiS note:** Polish Ustawa o rachunkowości requires statutory format reports for KRS filing. The practical zero-cost path: generate a full Trial Balance (ZOiS) from OCA `account_financial_report` → give it to your accountant → they produce the Bilans/RZiS in Comarch Optima or any Polish accounting software. This is normal practice for small companies. The accountant signs the document anyway (Art. 52 UoR).

> **Odoo EE pricing (Poland, 2026):** Standard €24.90/user/month, Custom €37.40/user/month. No à-la-carte module purchasing. Not needed for this deployment — OCA `account_asset_management` replaces `account_asset` for free.

---

## 3. Initial Server Setup

### Prerequisites
- VPS with Docker + Docker Compose installed (Coolify handles this)
- Coolify installed and running
- Two DNS A records pointing to your server IP:
  - `mnl.yourdomain.com` → server IP
  - `bioleaf.yourdomain.com` → server IP
- Ports 80 and 443 open in firewall

### Clone and configure

```bash
git clone <this-repo> odoo
cd odoo

# Configure environment
cp .env.example .env
# Edit .env with real values (local dev only — use Coolify UI for production)
nano .env

# Generate a strong master password and set it in .env / Coolify env var
openssl rand -base64 32
# Then set ODOO_MASTER_PASSWORD=<generated> in your .env (local) or Coolify UI.
# odoo.conf has admin_passwd = REPLACE_AT_BOOT; scripts/odoo-entrypoint.sh
# replaces the sentinel with $ODOO_MASTER_PASSWORD at container start.
```

### Add open-source submodules

Run the canonical setup script. It is idempotent — safe to re-run.

```bash
./scripts/setup-submodules.sh
```

The script adds:
- `OCA/account-financial-tools` (branch `19.0`) → `addons/oca-account-financial-tools`
- `OCA/account-financial-reporting` (branch `19.0`) → `addons/oca-account-financial-reporting`
- `OCA/reporting-engine` (branch `19.0`) → `addons/oca-reporting-engine`
- `OCA/server-ux` (branch `19.0`) → `addons/oca-server-ux`
- `vitalibondar/l10n-pl-payroll` → `addons/l10n-pl-payroll` (auto-patches manifest to v19)

The `addons_path` in `odoo.conf` already lists all four OCA directories.

Key OCA modules to install per database:
- `account_asset_management` — **środki trwałe** (fixed assets, depreciation schedules)
- `account_financial_report` — Trial Balance, General Ledger, Aged Receivable/Payable, Open Items
- `account_tax_balance` — VAT balance verification

---

## 4. Coolify Deployment

### Step 1: Create the application

1. Log into Coolify → **New Resource** → **Docker Compose**
2. Connect your git repository OR paste `docker-compose.yml` directly
3. Coolify will detect the compose file

### Step 2: Set Environment Variables

In Coolify → your application → **Environment Variables** tab, set:

| Variable | Value |
|---|---|
| `POSTGRES_USER` | `odoo` |
| `POSTGRES_PASSWORD` | *(strong random value from `openssl rand -base64 32`)* |
| `ODOO_DOMAIN_MNL` | `mnl.yourdomain.com` |
| `ODOO_DOMAIN_BIOLEAF` | `bioleaf.yourdomain.com` |

### Step 3: Domain assignment

In Coolify → your application → **Domains** tab:
- Add `mnl.yourdomain.com` → service `odoo`, port `8069`
- Add `bioleaf.yourdomain.com` → service `odoo`, port `8069`
- Enable **Force HTTPS** for both

> **Note:** The Traefik labels in `docker-compose.yml` handle multi-domain routing directly. Coolify's domain UI and the manual labels are complementary — both work together.

### Step 4: Deploy

Click **Deploy** in Coolify. Watch logs:

```bash
# Or from terminal:
make logs
```

---

## 5. Database Initialization

### Step 1: Temporarily enable the database manager

In `odoo.conf`, temporarily set:
```ini
list_db = True
```
Restart: `make restart`

### Step 2: Create databases

Navigate to `https://mnl.yourdomain.com/web/database/manager`

Create database:
- **Name:** `mnl_db`
- **Language:** Polish (pl_PL)
- **Country:** Poland
- **Demo data:** OFF (uncheck)
- **Admin password:** strong unique password

Repeat for `bioleaf_db`.

### Step 3: Lock the database manager

In `odoo.conf`, restore:
```ini
list_db = False
```
Restart: `make restart`

### Step 4: Install base modules

```bash
# Install all required modules (adjust BASE_MODULES in Makefile as needed)
make init-mnl
make init-bioleaf
```

---

## 6. Polish Compliance Configuration

### Company Setup (repeat for each database)

1. **Settings → Companies → Your Company**
   - Company name: `MNL sp. z o.o.` (or Bioleaf)
   - Country: Poland
   - Fiscal year: January–December
   - Currency: PLN
   - VAT number: `PL` + 10-digit NIP (e.g. `PL1234567890`)
   - Company registry: KRS number
   - REGON number

2. **Accounting → Configuration → Chart of Accounts**
   - Verify `l10n_pl` chart is loaded (Polish classes 0–8)
   - Install OCA `account_financial_report` → exports Trial Balance (ZOiS) + General Ledger

3. **VAT Taxes**
   `l10n_pl` pre-creates all Polish VAT rates. Verify:
   - 23% (standard)
   - 8% (reduced)
   - 5% (super-reduced)
   - 0% (exports)
   - ZW/NP (exempt)
   - Tax groups for JPK_V7 reporting

4. **Split Payment (MPP) — Mandatory**
   After installing `l10n_pl_edi_fixes` (this repo):
   - Settings → Accounting → Polish → Enable Split Payment
   - Products in Annex 15 of the VAT Act must have the MPP flag set
   - Invoices > PLN 15,000 with Annex 15 items auto-annotate with "mechanizm podzielonej płatności"
   - Verify the `P_18A = 1` KSeF flag is generated correctly

5. **Biała lista (White List) verification**
   `l10n_pl_bank_verification` (built into Odoo 19 CE):
   - Settings → Technical → Polish Partners Sync
   - Enter API key (register at `gov.pl`)
   - Verification triggers automatically before payments > PLN 15,000
   - Store verification timestamp and key for 5-year audit trail

6. **NBP Exchange Rates**
   `l10n_pl_nbp_rates` (this repo):
   - Accounting → Configuration → Currencies → Auto-update
   - Set update frequency: daily

---

## 7. KSeF e-Invoicing Setup

KSeF is mandatory for all VAT-registered Polish companies since **April 1, 2026**.

### Fix the known API URL bug in `l10n_pl_edi`

The production KSeF API URL in `l10n_pl_edi` has a known bug (GitHub issue #247360).
After installing `l10n_pl_edi`, fix it:

1. Settings → Technical → Parameters → **System Parameters**
2. Search for `l10n_pl_edi_ksef`
3. Update the production endpoint parameter to: `https://api.ksef.mf.gov.pl/v2`
   (The old incorrect URL was `https://ksef.mf.gov.pl/api/v2` — decommissioned)

### Configure KSeF credentials

1. Obtain your KSeF authentication credentials from `ksef.podatki.gov.pl`:
   - Token (valid through 2026)
   - OR Qualified electronic signature / seal
   - OR KSeF certificate (available from April 2026)

2. In Odoo: Accounting → Configuration → Settings → **Electronic Invoicing (KSeF)**
   - Mode: **Production** (use Test first)
   - Token / Certificate: enter credentials
   - Company NIP: verify it is set correctly on the company

3. Test with a draft invoice: **Send & Print → Send to KSeF**
   - Verify a KSeF number is returned
   - Check UPO (Urzędowe Poświadczenie Odbioru) is saved

### FA(3) mandatory fields (l10n_pl_edi generates these automatically)

- Seller NIP (validated: must be 10 digits, no `PL` prefix in the XML)
- Line items: GTU codes (via `l10n_pl_edi_fixes` — mandatory)
- VAT breakdown by rate
- Payment method and split payment flag (`P_18A`)
- For corrective invoices: reference to original KSeF number

### KSeF QR codes on printed invoices

When distributing PDF invoices outside KSeF (e.g. to foreign buyers without KSeF), include the KSeF QR code. This is generated automatically by `l10n_pl_edi`.

### Offline mode (Tryb offline / awaryjny)

If KSeF is unavailable:
- Offline 24: issue with 24-hour upload window
- System failure: issue with `OFF` tag; upload within 7 days of restoration
- JPK_V7 must include the `OFF`, `BFK`, or `DI` tag instead of KSeF number

### From August 1, 2026: KSeF ID in bank transfer titles

Payment titles for KSeF invoices must include the KSeF invoice ID.
Configure in Accounting → Payments → Payment reference template.

---

## 8. JPK Reporting Setup

### JPK_V7M — Monthly VAT (mandatory, due 25th of each month)

Module: **`l10n_pl_jpk_v7`** (our custom module, LGPL-3, in `custom_addons/`)

1. Accounting → Reporting → **JPK_V7 Reports** → New
2. Select company, period type (monthly), date range
3. Click **Generate XML**
4. Verify: every invoice line has either a `l10n_pl_edi_number` (KSeF) or `OFF`/`BFK`/`DI` tag
5. Download the XML file → upload manually at `https://www.podatki.gov.pl/e-deklaracje/`

**PLN 500 per error** penalty from March 25, 2026 for missing KSeF/tag fields.

> First run: validate the K-field amounts against your accountant's manual calculation.
> The `_TAG_TO_K_FIELD` mapping in `l10n_pl_jpk_v7/models/l10n_pl_jpk_v7.py` must match
> the actual account tags installed by `l10n_pl`. Run:
> `Settings → Technical → Accounting → Account Tags` (filter: country=Poland) to verify.

### JPK_V7K — Quarterly VAT

Same module, select `period_type = quarterly`.

### JPK_MAG / JPK_FA — On-demand only

Submitted only when requested by tax authority (minimum 3-day notice). No module needed until requested; KSeF gives tax authority direct access to all invoices.

### JPK_KR_PD + JPK_ST_KR — Corporate income tax SAF-T

**No free or paid module exists as of June 2026.**

- Typical sp. z o.o. deadline: **July 31, 2027** (tax year 2026)
- Large taxpayers (revenue > EUR 50M): **July 31, 2026**

Required now:
1. Tag chart of accounts with Ministry of Finance JPK_CIT classification codes
2. Ensure every journal entry links to counterparty NIP and KSeF invoice ID
3. Plan custom development — the XML schema is published at `podatki.gov.pl`

---

## 9. Fixed Assets — Środki Trwałe

Module: OCA `account_asset_management` (AGPL-3, free, Mature status — last commit June 8, 2026)

This replaces Odoo EE's `account_asset` module. **They cannot coexist** — install only `account_asset_management`.

### Asset categories to configure

Go to Accounting → Configuration → Asset Models → New for each.
Statutory CIT depreciation rates per Załącznik 1 do UoCIT:

| Category | KŚT Group | Useful life | CIT rate | Method |
|---|---|---|---|---|
| **Budynki niemieszkalne** | 1 | 40 years | 2.5%/yr | liniowa |
| **Budowle, ogrodzenia** | 2 | 22 years | 4.5%/yr | liniowa |
| **Maszyny i urządzenia ogólne** | 4–5 | 5–10 years | 10–20%/yr | liniowa |
| **Sprzęt IT — komputery** | 4 (487) | 3 years | 30%/yr | liniowa lub degresywna (2×) |
| **Środki transportu — samochody** | 7 | 5 years | 20%/yr | liniowa |
| **Wartości niematerialne** | n/a | 2–5 years | 20–50%/yr | liniowa |

> **Jednorazowa amortyzacja (Art. 16f ust. 3 UoCIT):**
> Assets with initial value ≤ PLN 10,000 may be expensed immediately.
> In OCA: `Number of Depreciations = 1`, `Method = linear`, value = full cost.

### Depreciation accounts

`account_asset_management` posts entries to:
- Dr: `407 Amortyzacja` (cost of nature)
- Cr: `071 Umorzenie środków trwałych` (accumulated depreciation)

Verify these accounts exist in your `l10n_pl` chart after install.

---

## 10. POS & Kasa Fiskalna Setup

### Odoo POS (optional)

1. Point of Sale → Configuration → POS Systems → New:
   - **Gate POS** — for ticket sales
   - **Shop POS** — for gift shop
   - **Café POS** — for refreshments

2. Products:
   - Bilet normalny (Adult ticket) — VAT 8% (cultural events)
   - Bilet ulgowy (Reduced ticket) — VAT 8%
   - Bilet grupowy (Group ticket) — VAT 8%
   - Gift shop products — VAT 23% or 5%/8% as applicable

### Kasa Fiskalna (Fiscal Printer)

Polish law requires fiscal printer for B2C POS sales unless an exemption applies.

**No CE solution.** Trilab's Novitus driver is Enterprise-only. CE deployments use a standalone fiscal printer (Novitus/Posnet/Elzab) with daily Z-report → manual journal entry in Odoo.

**Possible exemptions from kasa fiskalna** (requires legal opinion):
- Online ticket sales paid exclusively by electronic means with full transaction audit trail
- Self-service kiosks where the customer initiates the transaction

**Alternative for CE:** Deploy a separate fiscal printer management system alongside Odoo, reconciling daily Z-reports manually into Odoo accounting.

### Przelewy24 / BLIK for eCommerce

Module: `payment_przelewy24`

1. Website → Configuration → Payment Providers → **Przelewy24**
2. Enter Merchant ID and API key from Przelewy24 dashboard
3. Enable BLIK (included)
4. Test with PLN amounts

---

## 11. HR & Payroll Setup

Module: `vitalibondar/l10n-pl-payroll` (LGPL-3, added via `scripts/setup-submodules.sh`).

The setup script automatically handles the Odoo 18 → 19 migration: it prefers the upstream `task/011-odoo19-migration` branch if it exists on the remote, otherwise patches the manifest version in place. **Validate payslip calculations against ZUS Płatnik** before issuing the first real run — the module is a single-team project and not OCA-vetted.

**Daily workflow:**
1. HR → Employees → Create employee records
2. Payroll → Contracts → set base salary, ZUS contribution class
3. Payroll → Payslips → generate monthly
4. Export ZUS XML from `l10n_pl_payroll` → import to Płatnik desktop → submit to ZUS by 15th
5. Export PIT-4R / PIT-11 at year-end

### ZUS rates reminder (2026)

| Contribution | Employer | Employee |
|---|---|---|
| Pension (emerytalna) | 9.76% | 9.76% |
| Disability (rentowa) | 6.50% | 1.50% |
| Accident (wypadkowa) | 0.67–3.33% | — |
| Labor Fund (Fundusz Pracy) | 2.45% | — |
| FGŚP | 0.10% | — |
| Health (zdrowotna) | — | 9.00% |
| Sickness (chorobowa) | — | 2.45% |

**ZUS DRA/RCA deadline:** 15th of the following month
**PIT advance to tax office:** 20th of the following month
**PIT-11 annual:** end of February to both employee and tax office

---

## 12. Backup & Recovery

### Automated daily backups (backup-cron sidecar)

The `db-backup` container in `docker-compose.yml` runs `pg_dump` for both databases at 02:00 daily.

Backups are stored in `./backups/` on the host.

```bash
# Manual backup at any time:
make backup

# Or directly:
./scripts/backup.sh
```

### Restore a database

```bash
# Restore mnl_db from a specific backup:
DB=mnl_db FILE=backups/mnl_db_20260601_020000.dump ./scripts/restore.sh
```

### Filestore backup (CRITICAL — often overlooked)

`pg_dump` alone is NOT sufficient. The Odoo filestore contains all uploaded documents, invoice PDFs, animal photos, etc.

```bash
# The backup.sh script handles filestore backup automatically
# Filestore is saved as: backups/filestore_YYYYMMDD_HHMMSS.tar.gz

# Manual filestore restore:
FILESTORE_VOLUME=$(docker volume ls --format '{{.Name}}' | grep 'odoo-filestore')
docker run --rm \
    -v ${FILESTORE_VOLUME}:/data \
    -v $(pwd)/backups:/backup \
    alpine tar xzf /backup/filestore_20260601_020000.tar.gz -C /data
```

### Coolify native backups

For additional redundancy, configure Coolify's database backup to S3/Cloudflare R2:
- Coolify → your PostgreSQL resource → Backups tab
- Set S3 endpoint (Cloudflare R2 has zero egress cost)
- Recommended schedule: `0 */4 * * *` (every 4 hours)
- Retention: 14 days local, 90 days S3

---

## 13. Compliance Checklist

### KSeF (Mandatory since April 1, 2026)

- [ ] `l10n_pl_edi` installed
- [ ] KSeF API URL bug fixed (system parameter → `https://api.ksef.mf.gov.pl/v2`)
- [ ] KSeF token / certificate configured
- [ ] Test invoice sent and KSeF number received
- [ ] UPO saved for test invoice
- [ ] `l10n_pl_edi_fixes` installed — GTU codes on products
- [ ] `l10n_pl_edi_fixes` installed — VAT exemption legal bases (P_19A) configured
- [ ] Corrective invoice workflow tested
- [ ] Offline mode (Tryb offline) procedure documented

### JPK_V7M (Monthly, due 25th)

- [ ] `l10n_pl_jpk_v7` installed (this repo)
- [ ] Generated XML signed manually with Profil Zaufany before submission
- [ ] First JPK_V7M generated and verified — all invoices have KSeF numbers or OFF/BFK/DI tags
- [ ] Monthly reminder calendar entry created
- [ ] Procedure for corrective JPK filing documented

### Split Payment (MPP)

- [ ] `l10n_pl_edi_fixes` split payment (l10n_pl_split_payment field) enabled
- [ ] Products in Annex 15 flagged
- [ ] Invoice > PLN 15,000 auto-annotates "mechanizm podzielonej płatności"
- [ ] VAT bank account (rachunek VAT) configured in Accounting → Bank Accounts

### Biała lista

- [ ] `l10n_pl_bank_verification` enabled (Odoo 19 CE built-in)
- [ ] Verification runs before payments > PLN 15,000
- [ ] ZAW-NR procedure documented for non-listed accounts

### CIT

- [ ] Monthly CIT advance calculations scheduled (by 20th)
- [ ] CIT-8 annual filing reminder set (March 31)
- [ ] Minimum CIT assessment (if applicable) noted

### ZUS & Payroll

- [ ] Monthly ZUS DRA/RCA filed by 15th (via Płatnik or payroll module)
- [ ] Monthly PIT advance paid to tax office by 20th
- [ ] Annual PIT-11 issued to employees by end of February
- [ ] Annual PIT-4R filed by January 31

### JPK_KR_PD (JPK_CIT)

- [ ] Assess if company is a "large taxpayer" (revenue > EUR 50M) → deadline July 31, 2026
- [ ] If typical sp. z o.o.: deadline July 31, 2027 (tax year 2026)
- [ ] Chart of accounts tagged with MF JPK_CIT classification codes
- [ ] Journal entries include counterparty NIP and KSeF IDs
- [ ] Partner with Solvti/Trilab for module development

### e-Doręczenia (Electronic Delivery)

- [ ] e-Delivery address (ADE) registered for each sp. z o.o. at `business.gov.pl`
- [ ] Mailbox administrator designated (board member with PESEL)
- [ ] Incoming official correspondence process defined


---

## 14. Known Issues & Gaps

| Issue | Status | Workaround |
|---|---|---|
| `l10n_pl_edi` KSeF API URL bug (GitHub #247360) | Fix via system parameter (see §7) | Update `ir.config_parameter` after install |
| `l10n_pl_edi` corrective invoices (known issue as of early 2026) | Monitor Odoo GitHub | Use Trilab KSeF for corrective invoices if needed |
| Polish ZUS/PIT payroll — no v18 CE module | Gap | Płatnik (free, ZUS) + manual journal entries |
| JPK_KR_PD / JPK_CIT — no vendor module | Gap (deadline Jul 2027) | Custom dev or partner engagement |
| Kasa fiskalna (non-Novitus brands) | Gap | Novitus Deon Online hardware + Trilab, or external fiscal management |
| Timed-entry ticketing with capacity limits | Partial | Odoo Events + POS for basic; dedicated platform for advanced |
| PayU payment gateway | Gap | Use Przelewy24 (which includes most PayU use cases) |
| Polish bank MT940 statement import | Gap | Manual import via OFX/CSV, or contact bank for Odoo format |

---

## Support & Partners

| Partner | Specialty | Contact |
|---|---|---|
| **Solvti** | Gold Odoo Partner Poland — KSeF, JPK, payroll | `solvti.com` |
| **Trilab** | Polish tax modules, JPK suite, KSeF | `trilab.pl` |
| **ERPGO.pl** | Polish accounting modules | `erpgo.pl` |
| **Adapt IT** | Polish Odoo implementations | `adapt-it.pl` |
