# Agent Onboarding Prompt

Copy everything between the `---START---` and `---END---` markers below and paste
it as the first message to a fresh Claude Code (or any LLM) session to onboard
the agent onto this project.

---START---

You are continuing work on a Polish sp. z o.o. ERP project built on Odoo 19 CE.
The codebase is at `/Users/admin/Source/private/odoo/`. Read this entire
briefing before doing anything else.

## 1. What this project is

A self-hosted, Coolify-deployed Odoo 19 Community Edition for **two Polish
private-limited companies (sp. z o.o.)**: MNL sp. z o.o. and Bioleaf sp. z o.o.
Both companies do full accounting (*pełna księgowość*) per Ustawa o rachunkowości.

**Cost target: €0 in software licenses.** Everything is built-in Odoo CE,
AGPL-3 OCA modules, or LGPL-3 custom modules in `custom_addons/`. No paid
modules — we verified the open-source ecosystem exhaustively and built what
was missing ourselves.

**Compliance scope:**
- KSeF (Krajowy System e-Faktur) — mandatory e-invoicing API v2.6.0
- JPK_V7M(3) — monthly VAT SAF-T file (schema effective 2026-02-01)
- JPK_KR_PD — annual CIT SAF-T (deadline 2027-07-31 for typical sp. z o.o.)
- Biała Lista — automatic VAT taxpayer verification
- MPP — split payment mechanism
- ZUS / PIT — payroll declarations

## 2. Critical legal context — single-signature signing model

The Prezes (board chair) signs financial statements ALONE under this legal basis:

- **Art. 4 ust. 5 UoR** + **2014 deregulation** (Dz.U. 2014 poz. 768) — no
  qualifications required to run books internally.
- **Art. 52 ust. 2 UoR** — sprawozdanie finansowe needs signatures from
  (a) osoba prowadząca księgi AND (b) kierownik jednostki. When the Prezes
  fills BOTH roles (via uchwała zarządu under Art. 4 ust. 5), one signature
  suffices.
- AI assists day-to-day. External auditor/accountant can verify via read-only
  Odoo access but does NOT need to sign anything.

This drove every design decision. Do NOT add features assuming an external
bookkeeper will sign — they won't.

## 3. Architecture

```
Coolify host → Traefik (TLS, rate-limit, security headers)
            → Odoo 19 CE container (custom Dockerfile: xlsxwriter + xlrd)
              ├─ dbfilter = ^%d_db$ routes:
              │    mnl.domain.com    → mnl_db
              │    bioleaf.domain.com → bioleaf_db
              └─ PostgreSQL 16-alpine (internal-only network)
            → db-backup sidecar (pg_dump + filestore tar, optional S3 sync)
```

Two databases on ONE Odoo process. Legally independent companies, full data
isolation, single maintenance window.

## 4. Repository layout

```
/Users/admin/Source/private/odoo/
├── README.md, SETUP.md, LEGAL.md, DOWNLOADS.md, ARCHITECTURE.md
├── Dockerfile             extends odoo:19.0 with xlsxwriter, xlrd
├── docker-compose.yml     Coolify-ready, 2 dbs, backup sidecar
├── odoo.conf              workers=2, dbfilter, REPLACE_AT_BOOT sentinel
├── .env.example           required env vars
├── Makefile               make init-mnl, make backup, etc.
│
├── custom_addons/         LGPL-3 modules (THIS REPO)
│   ├── l10n_pl_edi_fixes/   FA(3) patches: GTU, P_18A, P_19A
│   ├── l10n_pl_jpk_v7/      JPK_V7M(3)/V7K(3) generator
│   ├── l10n_pl_jpk_kr_pd/   JPK_KR_PD (JPK_CIT) generator
│   └── l10n_pl_nbp_rates/   NBP Table A daily rates
│
├── addons/                git submodules (run setup-submodules.sh)
│   ├── oca-account-financial-tools/    account_asset_management
│   ├── oca-account-financial-reporting/ account_financial_report
│   ├── oca-reporting-engine/           report_xlsx
│   ├── oca-server-ux/                  date_range
│   └── l10n-pl-payroll/                ZUS/PIT (auto-patched to v19)
│
├── schemas/               EMBEDDED official MF XSDs
│   ├── jpk_v7m3.xsd       namespace http://crd.gov.pl/wzor/2025/12/19/14090/
│   ├── jpk_v7k3.xsd       namespace http://crd.gov.pl/wzor/2025/12/19/14089/
│   ├── fa3.xsd            namespace http://crd.gov.pl/wzor/2025/06/25/13775/
│   ├── jpk_kr_pd.xsd      namespace http://jpk.mf.gov.pl/wzor/2024/09/04/09041/
│   └── jpk_st_kr.xsd      namespace http://jpk.mf.gov.pl/wzor/2024/04/24/04242/
│
└── scripts/
    ├── setup-submodules.sh   idempotent OCA + payroll setup
    ├── odoo-entrypoint.sh    injects ODOO_MASTER_PASSWORD into odoo.conf
    ├── backup-cron.sh        runs in sidecar at 02:00 daily
    ├── backup.sh, restore.sh manual operations
```

## 5. XSD compliance — critical namespaces and rules

These were verified by reading the actual XSD files. Do NOT change without
re-verifying against `schemas/*.xsd`.

### JPK_V7M(3) / JPK_V7K(3)
- ETD namespace is `2022/09/13` (NOT 2022/01/05 — strict)
- Root order: `Naglowek → Podmiot1 → Deklaracja → Ewidencja`
  (Deklaracja BEFORE Ewidencja!)
- `Podmiot1` needs attribute `rola="Podatnik"`
- `Podmiot1` body is `<OsobaNiefizyczna>` wrapper — NO address sub-elements
  (the type is `TPodmiotDowolnyBezAdresu`)
- `OsobaNiefizyczna` needs `Email` (required) — company.email must be set
- `Naglowek` ends with `<Miesiac>` even for V7K (Kwartal only in Deklaracja)
- Deklaracja `P_NN` fields are **xsd:integer**, NOT decimal — use `_fmt_int()`
- `P_46` is `maxInclusive=0` — must be ≤ 0
- `P_38`, `P_48`, `P_51` are REQUIRED (always emit, even if 0)
- `Pouczenia=1` is the LAST child of Deklaracja
- V7M Deklaracja: `kodSystemowy="VAT-7 (23)"`, variant=23
- V7K Deklaracja: `kodSystemowy="VAT-7K (17)"`, variant=17, plus `<Kwartal>` element
- K-fields emitted in strict XSD-sequence order from `_SALES_K_ORDER` /
  `_PURCHASE_K_ORDER` tuples
- Tag sign comes from `account.account.tag.tax_negate` (Boolean), NOT name prefix
- NrKSeF/OFF/BFK/DI is xsd:choice — exactly one per row
- DowodSprzedazy/DowodZakupu need minLength=1 — fall back to `INV-{id}`
- Foreign partner TIN: strip 2-letter country prefix; emit prefix as
  `KodKrajuNadaniaTIN`

### JPK_KR_PD(1)
- wersjaSchemy is `"1-1"` (XSD fixed value; brochure misquotes "1-0")
- kodSystemowy is `"JPK_KR_PD (1)"` (exact spacing)
- Address structure: `<Adres>` wrapper containing `<AdresPol>` or `<AdresZagr>`
  (NOT AdresPol directly under Podmiot1)
- T_2/T_3 in `Kontrahent` are in **tns namespace**, NOT etd
- TJednAdmin maxLength=36, TMiejscowosc=56, TUlica=65, TKodPocztowy NN-NNN
- `C_1` and `C_3` are `minExclusive=0` — empty period CANNOT be filed
  (raise UserError)
- Default ZOiS variant is **ZOiS8** (IFRS) — S_12_1/S_12_2 markers optional.
  Switch to ZOiS7 only when account.account.l10n_pl_zois_marker_1 is populated.
- RPD K_3, K_6, K_7, K_8 are manual wizard inputs (not derivable from books)

### FA(3) — KSeF e-invoicing
- GTU is element `<GTU>` with value `GTU_01..GTU_13` (NOT P_106E_N — that's
  the old JPK_FA naming)
- `<GTU>` lives per FaWiersz, in xsd:sequence position between KwotaAkcyzy and
  Procedura
- `<Zwolnienie>` lives inside `<Adnotacje>`, NOT directly under `<Fa>`
- Zwolnienie is xsd:choice between `(P_19 + P_19A|B|C)` and `P_19N` — must
  remove existing P_19N before adding P_19+P_19A
- `<P_18A>` lives at `/Faktura/Fa/Adnotacje/P_18A`
- Patches applied via lxml post-processing of stock Odoo XML — see
  `l10n_pl_edi_fixes/models/account_move.py::_l10n_pl_edi_postprocess_fa3`

### KSeF API v2.6.0 (production as of 2026-06)
- Production: `https://api.ksef.mf.gov.pl/api/v2`
- Test: `https://api-test.ksef.mf.gov.pl/api/v2`
- Access token TTL ~15 min, refresh up to 7 days
- Offline mode signal = API param `offlineMode: true` (NOT an XML element)
- XAdES: Exclusive C14N + RSA-SHA256 + SHA-256 digest
- KSeF number format: 35 chars `NIP-YYYYMMDD-12hex-2hex`
- From 2026-08-01: KSeF# required in MPP payment titles (Art. 108a §1c)
- From 2027-01-01: KSeF# required in ALL B2B payment titles (Art. 108g)

## 6. Custom module conventions

- All custom modules use `license: LGPL-3` (Odoo CE-compatible)
- Author: `'Polish sp. z o.o. Odoo Project'`
- Version: `'19.0.x.y.z'` (Odoo-style version)
- All XML files validate (`xmllint --noout`) — run before any commit
- Python passes `py_compile` — `python3 -m py_compile path/to/file.py`
- XML parsing uses safe `etree.XMLParser(resolve_entities=False,
  no_network=True, load_dtd=False)` — defense against XXE
- Cron methods use `@api.model`, get `.sudo()` for record-rule bypass
- Use `ir.attachment.raw` for binary bytes (NOT `datas` — that's base64-encoded
  string and causes double-encoding when assigning `b64encode(bytes)`)
- Multi-company: never rely on `env.company` in cron — iterate
  `res.company.search([('currency_id.name', '=', 'PLN')])` explicitly

## 7. Deployment

```bash
# Local test
./scripts/setup-submodules.sh   # one-time submodule init
cp .env.example .env             # set ODOO_MASTER_PASSWORD, POSTGRES_PASSWORD, domains
docker network create coolify    # local stand-in for Coolify's network
docker compose build
docker compose up -d
docker compose logs -f odoo

# First-run DB creation (one time)
# 1. Edit odoo.conf: list_db = True; docker compose restart odoo
# 2. Browser → https://mnl.domain/web/database/manager
# 3. Use ODOO_MASTER_PASSWORD as the master password
# 4. Create mnl_db and bioleaf_db (Polish, country=Poland, no demo data)
# 5. Edit odoo.conf: list_db = False; docker compose restart odoo

# Install modules
make init-mnl
make init-bioleaf

# Production = Coolify UI deploys docker-compose.yml; env vars in Coolify panel
```

## 8. Common operations

```bash
make help              # list all targets
make up                # docker compose up -d
make logs              # tail Odoo logs
make backup            # manual backup (sidecar runs daily at 02:00 anyway)
make restore           # interactive restore from ./backups/
make shell-mnl         # Python shell on mnl_db
make update-mnl MODULES=l10n_pl_jpk_v7   # update a specific module
```

## 9. Documentation index

ALWAYS check these before answering questions about the project:

- `README.md` — quick overview, architecture, signing model, getting started
- `SETUP.md` — full deployment guide, Coolify, KSeF/JPK config, compliance checklist
- `LEGAL.md` — VERIFIED Polish law refs (UoR, UoVAT, UoCIT, KSeF API specs)
- `DOWNLOADS.md` — what to download manually (Profil Zaufany, Płatnik, certs)
- `ARCHITECTURE.md` — architecture deep dive, layer model, KSeF flow

If you make a claim about Polish law, cite the article. Don't make up legal
references. If unsure, search and verify before stating.

## 10. Workflow expectations

1. **Read first, write second.** This project has many subtle XSD constraints.
   Before changing a JPK/KSeF module, read its docstring AND the XSD
   (`schemas/*.xsd`).
2. **Verify schemas:** any change to a generator should be paired with a
   manual XSD validation: `xmllint --schema schemas/jpk_v7m3.xsd
   output.xml --noout`
3. **Polish law changes annually.** If you're acting after early 2027, re-verify
   namespaces, deadlines, and percentages with a web search before relying on
   docs that may be stale.
4. **Multi-company safety:** never `env.company` in cron paths. Use
   `res.company.search([...])` and iterate.
5. **Compile checks:** run `python3 -m py_compile` on every Python file you
   touch; run `xmllint --noout` on every XML file you touch.
6. **The Prezes signs alone.** Do not add features assuming an external
   bookkeeper or accountant.

## 11. Known gaps (still need work)

- Bilans/RZiS in statutory format — generated externally by accountant in
  Comarch Optima or e-Sprawozdania MF app. Trial Balance from OCA export
  is the handoff.
- Kasa fiskalna (fiscal printer) for B2C POS — Trilab driver is EE-only;
  CE deployments use standalone hardware + daily Z-report manual entry.
- ZOiS7 statutory markers (~600 enumeration values) require pre-mapping per
  account; ZOiS8 (IFRS) variant is the default to skip this.

## 12. Things explicitly NOT in scope

- Zoo / animal management — was initially considered but removed; do not add
  zoo modules.
- Paid Odoo modules (Trilab, Baris Genc, etc.) — we deliberately replaced
  them with open-source equivalents.
- Odoo Enterprise license — we use CE only.
- External auditor digital signature on financial statements — not legally
  required in our signing model.

---

**Now: read `README.md`, `SETUP.md`, and `LEGAL.md` in that order.** Then ask
the user what task they want to work on.

---END---

## How to use this prompt

**For a fresh Claude Code session:**
1. Open Claude Code in the project directory
2. Paste the text between `---START---` and `---END---` as your first message
3. The agent will read it, then read the three core docs, then ask you what
   to work on

**For another LLM (ChatGPT, Gemini, etc.):**
1. Same — paste the START/END block as the system or first user message
2. Manually share `README.md`, `SETUP.md`, and `LEGAL.md` contents if the
   agent doesn't have filesystem access
3. Share the relevant XSD or module files as needed for the specific task

**For onboarding a human developer:**
Treat this file as the "first day" reading list. Read it, then read the three
core docs, then look at one custom module (e.g. `l10n_pl_jpk_v7/`) end-to-end
to understand the patterns.

## What to update over time

Re-run this prompt thinking when:
- Polish law changes (annually around tax season)
- KSeF API version bumps (currently v2.6.0)
- New JPK schemas published by MF
- New Odoo version released (currently 19.0; v20 expected Oct 2026)
- Submodule lists change in `scripts/setup-submodules.sh`

Update the `Critical Namespaces` and `Module Stack` sections to match reality.
