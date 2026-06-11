# Odoo 19 CE — Polish sp. z o.o. ERP

> Fully Dockerized, Coolify-ready Odoo 19 Community Edition for two Polish
> sp. z o.o. companies: **MNL sp. z o.o.** and **Bioleaf sp. z o.o.**

**100% open source. Zero paid licenses. Pełna księgowość. KSeF + JPK_V7M(3) compliant.**

---

## Quick Links

| Document | Purpose |
|---|---|
| [SETUP.md](./SETUP.md) | Full deployment guide — Coolify, database init, module config |
| [LEGAL.md](./LEGAL.md) | Verified Polish law references — UoR, UoCIT, UoVAT, KSeF |
| [DOWNLOADS.md](./DOWNLOADS.md) | Manual download links (Profil Zaufany, Płatnik, KSeF cert) |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture deep dive + design decisions |
| [schemas/](./schemas/) | Embedded MF XSD schemas (JPK_V7M(3), FA(3), JPK_KR_PD, JPK_ST_KR) |

---

## What This Is

A complete, self-hosted Odoo 19 deployment for Polish private limited companies (sp. z o.o.):

1. **Run full bookkeeping themselves** — board members handle Odoo day-to-day; AI assists.
2. **Sign financial statements alone** — when the Prezes is also the bookkeeper (Art. 4 ust. 5 UoR + Art. 52 ust. 2 UoR + 2014 deregulation), no external accountant signature is required.
3. **Stay compliant with all 2026 Polish obligations** — KSeF e-invoicing, JPK_V7M monthly VAT, biała lista, MPP split payment, ZUS payroll.
4. **Cost €0/month in software licenses** — everything is built-in to Odoo CE, OCA AGPL-3, or custom LGPL-3 modules in this repo.

Auditors / tax advisors can verify the data through read-only Odoo access — they do not need to sign anything in this signing model.

---

## Architecture at a Glance

```
                            Internet
                                │
                  ┌─────────────┴──────────────┐
                  │  Coolify (Docker)          │
                  │  + Traefik (Let's Encrypt) │
                  └─────────────┬──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                                   ▼
    mnl.yourdomain.com                  bioleaf.yourdomain.com
              │                                   │
              └────────────────┬──────────────────┘
                               │  dbfilter = ^%d_db$
                               ▼
                  ┌────────────────────────────┐
                  │   Odoo 19.0 CE             │
                  │   (single container)       │
                  │   + custom Dockerfile      │
                  │   (adds xlsxwriter, xlrd)  │
                  └────────────┬───────────────┘
                               │
                  ┌────────────┴─────────────┐
                  ▼                          ▼
              mnl_db                    bioleaf_db
                  └──── PostgreSQL 16 ───────┘
                         (named volume pg-data)

External APIs:
  • KSeF 2.0          → api.ksef.mf.gov.pl/v2 (FA(3) e-invoices)
  • Biała Lista       → wl-api.mf.gov.pl
  • NBP Table A       → static.nbp.pl/dane/kursy/xml/LastA.xml
```

**Why two databases, one Odoo process?**
Both companies are legally independent (separate VAT registrations, KRS numbers, ZUS accounts). Two databases give full data isolation. One Odoo process = one server, one upgrade window, one maintenance task.

---

## Module Stack

### Built-in Odoo 19 CE — `LGPL-3` (zero downloads)

| Module | Coverage |
|---|---|
| `l10n_pl` | Polish chart of accounts (plan kont), VAT rates 23/8/5/0/ZW, GTU codes on products |
| `l10n_pl_edi` | **KSeF FA(3) e-invoicing** via api.ksef.mf.gov.pl/v2 |
| `l10n_pl_taxable_supply_date` | Taxable supply date (P_6 in FA(3)) |
| `l10n_pl_bank_verification` | **Biała Lista** — automatic check for payments > PLN 15,000 |
| `account` | Double-entry bookkeeping (pełna księgowość). `account_accountant` is Enterprise-only; OCA `account_financial_report` covers reports. |
| `sale`, `purchase`, `stock` | Sales, procurement, inventory (inwentaryzacja) |
| `hr`, `hr_payroll` | Employee records, payroll engine |
| `crm`, `project`, `maintenance` | Customer relationships, projects, equipment |

### Custom modules in this repo — `LGPL-3`

| Module | Purpose |
|---|---|
| `l10n_pl_edi_fixes` | Patches gaps in `l10n_pl_edi`: GTU codes in FA(3) XML (<GTU>), MPP split payment (P_18A), VAT exemption legal basis (P_19A), KSeF API URL safety net |
| `l10n_pl_jpk_v7` | **JPK_V7M(3) and JPK_V7K(3) XML generator** — schema namespace `http://crd.gov.pl/wzor/2025/12/19/14090/`, includes NrKSeF + OFF/BFK/DI tags. Has built-in K-field mapping verification button. |
| `l10n_pl_jpk_kr_pd` | **JPK_KR_PD (JPK_CIT) generator** — full XML implementation (Naglowek, Podmiot1, Kontrahenci, ZOiS, Dziennik+KontoZapis, Ctrl, RPD). Defaults to ZOiS8 (IFRS variant — markers optional). Deadline 2027-07-31. |
| `l10n_pl_nbp_rates` | Daily PLN exchange rates from NBP Table A (no API key, no OCA dependency) |

### OCA submodules (free, AGPL-3) — added via `scripts/setup-submodules.sh`

| Repo | Branch | Key Module | Why |
|---|---|---|---|
| `OCA/account-financial-tools` | `19.0` | `account_asset_management` | Środki trwałe (depreciation schedules) — replaces Odoo EE `account_asset` |
| `OCA/account-financial-reporting` | `19.0` | `account_financial_report` | Trial Balance (ZOiS), General Ledger (Dziennik), Aged Receivables/Payables (rozrachunki) |
| `OCA/reporting-engine` | `19.0` | `report_xlsx`, `report_xlsx_helper` | Excel export for the above |
| `OCA/server-ux` | `19.0` | `date_range` | Required by `account_financial_report` |

### External LGPL-3 module — added via `scripts/setup-submodules.sh`

| Repo | Status | Notes |
|---|---|---|
| `vitalibondar/l10n-pl-payroll` | Auto-handled by setup script | Polish ZUS contributions, PIT advance, PPK, PIT-11/DRA generation. Script tracks the Odoo 19 migration branch or auto-bumps the manifest version. |

---

## Coverage Summary

✅ **Covered** by free modules in this repo:

- Pełna księgowość (Plan Kont, podwójny zapis, rozrachunki)
- KSeF FA(3) — wystawianie i odbiór faktur
- JPK_V7M(3) — miesięczna ewidencja VAT (zgodna ze schematem MF z 2025-12-19)
- Biała Lista (weryfikacja przed płatnościami > PLN 15 000)
- MPP — Mechanizm Podzielonej Płatności
- Środki trwałe + amortyzacja (Budynki, Maszyny, Pojazdy, IT)
- ZUS / PIT (po wykonaniu `scripts/setup-submodules.sh`)
- Kursy walut NBP (codzienna aktualizacja Tabela A)
- JPK_KR_PD (zaimplementowany, ZOiS8 domyślnie — deadline 2027-07-31)

⚠️ **Wymaga ręcznej pracy** (i tak prawnie konieczne):

- **Bilans i RZiS** w formacie statutory — wyeksportuj Trial Balance i wypełnij bezpłatną aplikację MF (`e-sprawozdania.mf.gov.pl/ap/`), podpisz Profilem Zaufanym, złóż do RDF.
- **Kasa fiskalna** dla sprzedaży B2C — żaden free module nie obsługuje fiskalnej kasy online. Workaround: zewnętrzna kasa fiskalna + dzienny raport Z → ręczny wpis w Odoo.

---

## Repository Layout

```
/Users/admin/Source/private/odoo/
├── README.md              ← you are here
├── SETUP.md               ← step-by-step deployment guide
├── LEGAL.md               ← verified Polish law references
├── DOWNLOADS.md           ← manual download links (schemas already in schemas/)
├── ARCHITECTURE.md        ← architecture deep dive
│
├── Dockerfile             ← extends odoo:19.0 with xlsxwriter + xlrd
├── docker-compose.yml     ← Coolify-ready stack (Odoo + PG16 + backup sidecar)
├── odoo.conf              ← production Odoo config (workers=2, dbfilter, proxy_mode)
├── .env.example           ← required env vars (set in Coolify UI, not in git)
├── Makefile               ← make up / init-mnl / backup / restore
│
├── custom_addons/         ← our LGPL-3 modules
│   ├── l10n_pl_edi_fixes/
│   ├── l10n_pl_jpk_v7/
│   ├── l10n_pl_jpk_kr_pd/    ← JPK_CIT generator (deadline 2027-07-31)
│   └── l10n_pl_nbp_rates/
│
├── addons/                ← git submodules (OCA + l10n-pl-payroll)
│   ├── oca-account-financial-tools/
│   ├── oca-account-financial-reporting/
│   ├── oca-reporting-engine/
│   ├── oca-server-ux/
│   └── l10n-pl-payroll/
│
├── schemas/               ← embedded official MF XSDs
│   ├── jpk_v7m3.xsd       (69 KB — JPK_V7M version 3)
│   ├── jpk_v7k3.xsd       (69 KB — JPK_V7K version 3)
│   ├── fa3.xsd            (184 KB — KSeF FA(3))
│   ├── jpk_kr_pd.xsd      (359 KB — JPK_CIT, future)
│   └── jpk_st_kr.xsd      (53 KB — fixed assets register, future)
│
├── scripts/
│   ├── setup-submodules.sh    ← run once to add all OCA + payroll submodules
│   ├── backup.sh
│   ├── backup-cron.sh
│   └── restore.sh
│
└── backups/               ← runtime backups (gitignored)
```

---

## Getting Started (5-Minute Version)

```bash
# 1. Clone
git clone <this-repo> odoo
cd odoo

# 2. Add all submodules (handles l10n-pl-payroll version automatically)
./scripts/setup-submodules.sh

# 3. Configure
cp .env.example .env
# Edit .env with real domains and a strong POSTGRES_PASSWORD
# Edit .env: set ODOO_MASTER_PASSWORD (`openssl rand -base64 32`)
# The entrypoint injects it into odoo.conf at start — no manual edit required.

# 4. Deploy
# For Coolify: paste docker-compose.yml as Docker Compose resource, set env vars in UI
# For local testing:
docker network create coolify || true
make up
make logs    # watch startup

# 5. Create databases (one-time)
# Temporarily set list_db = True in odoo.conf, restart
# Visit https://mnl.yourdomain.com/web/database/manager
# Create mnl_db (Polish, country Poland, no demo data)
# Repeat for bioleaf_db
# Set list_db = False, restart

# 6. Install modules
make init-mnl
make init-bioleaf

# 7. Verify K-field mapping for JPK_V7M (one-time, per database)
# Go to Accounting → Reporting → JPK_V7 Reports → New → "Verify K-Field Mapping" button
# Review the notes field — adjust _TAG_TO_K_FIELD if needed
```

See [SETUP.md](./SETUP.md) for the full version including Coolify environment variables, security hardening, post-install module configuration.

---

## Signing Financial Statements (Single-Person Model)

The legal basis for the **prezes-only** signing model:

1. **Art. 4 ust. 5 UoR** — kierownik jednostki (zarząd) ponosi odpowiedzialność za rachunkowość, ale może powierzyć prowadzenie ksiąg sobie samemu.
2. **2014 deregulation** (Dz.U. 2014 poz. 768) — usunięto wszystkie wymogi kwalifikacyjne dla osoby prowadzącej księgi wewnętrznie.
3. **Art. 52 ust. 2 UoR** — sprawozdanie podpisuje *osoba prowadząca księgi i kierownik jednostki*. Gdy są to ta sama osoba — jeden podpis w podwójnej roli.

**Required formal step:**

Pass a board resolution (uchwała zarządu) entrusting bookkeeping to the prezes:

```
UCHWAŁA ZARZĄDU MNL sp. z o.o.

Zarząd, działając na podstawie art. 4 ust. 5 Ustawy o rachunkowości
z dnia 29 września 1994 r., powierza Prezesowi Zarządu Panu/Pani
[imię nazwisko, PESEL] prowadzenie ksiąg rachunkowych Spółki.

Prezes oświadcza, że przyjmuje powierzone obowiązki.

Data: [...]                            Podpis: ______________
```

Keep this resolution in the company's documentation. The same person signs sprawozdanie finansowe (Bilans + RZiS) using Profil Zaufany or qualified electronic signature.

Full reference: [LEGAL.md](./LEGAL.md) — section "Podpisywanie sprawozdań finansowych".

---

## Compliance Calendar — sp. z o.o. (2026/2027)

| Deadline | Obligation | Where |
|---|---|---|
| 25th of each month | **JPK_V7M(3)** for previous month | e-deklaracje.mf.gov.pl |
| 15th of each month | ZUS DRA/RCA + payment | PUE ZUS or Płatnik |
| 20th of each month | PIT advance for employees | Tax office |
| Every B2B invoice | **KSeF FA(3)** real-time | api.ksef.mf.gov.pl/v2 |
| Before each payment > PLN 15k | **Biała Lista** check | Automatic via Odoo |
| End of February 2027 | PIT-11 to employees | PUE ZUS |
| 31 January 2027 | PIT-4R annual | PUE ZUS |
| 31 March 2027 | CIT-8 annual + payment | MF online |
| End of June 2027 | Sprawozdanie finansowe → KRS RDF | ekrs.ms.gov.pl |
| 31 July 2027 | **JPK_KR_PD** (first filing for fiscal year 2026) | e-deklaracje.mf.gov.pl |
| Anytime requested | JPK_MAG, JPK_FA (on demand, 3-day notice) | tax authority request |

---

## License

This project's custom modules are licensed under **LGPL-3** (same as Odoo CE).
OCA submodules are **AGPL-3**. Polish payroll module is **LGPL-3**.

You may use, modify, and redistribute. Compliance with Polish law is the deployer's responsibility — this repo provides tools, not legal advice. Consult a tax advisor (doradca podatkowy) for company-specific situations.
