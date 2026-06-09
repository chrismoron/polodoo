# Architecture Deep Dive

How the pieces fit together and why we chose this design.

---

## 1. Top-Level Topology

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                            INTERNET                                  │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │ TLS 1.3
                                 ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  COOLIFY HOST                                                        │
  │                                                                      │
  │  ┌──────────────┐    ┌─────────────────────────────────────────┐    │
  │  │  Traefik     │───▶│  Odoo container (port 8069 + 8072 WS)   │    │
  │  │  Let's Encrypt│    │  workers=2  max_cron_threads=2          │    │
  │  │  Rate limit  │    │  custom Dockerfile (+ xlsxwriter, xlrd) │    │
  │  └──────────────┘    └────────────────┬────────────────────────┘    │
  │                                       │                              │
  │                                       │ internal network             │
  │                                       ▼                              │
  │                      ┌──────────────────────────────┐                │
  │                      │  PostgreSQL 16 (alpine)      │                │
  │                      │  named volume pg-data        │                │
  │                      └──────────────────────────────┘                │
  │                                       │                              │
  │                                       ▼                              │
  │                      ┌──────────────────────────────┐                │
  │                      │  db-backup sidecar           │                │
  │                      │  daily 02:00 → ./backups/    │                │
  │                      └──────────────────────────────┘                │
  └──────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼ on every page load (dbfilter)
              ┌────────────────────────┴───────────────────────┐
              │                                                │
       Host: mnl.yourdomain.com               Host: bioleaf.yourdomain.com
              │                                                │
              ▼                                                ▼
       Odoo dbfilter pattern  ^%d_db$  matches the first subdomain → db name
              │                                                │
              ▼                                                ▼
          mnl_db                                        bioleaf_db
```

The same Odoo process serves both companies. `dbfilter = ^%d_db$` extracts the first subdomain (`mnl` or `bioleaf`) and routes the request to the matching database. Each database is fully isolated — separate users, separate chart of accounts state, separate invoices, separate everything.

---

## 2. Why Two Databases, One Process?

We considered three architectures.

### Option A — Single database, multi-company
- ❌ Polish VAT compliance is per-NIP; risk of cross-contamination in JPK
- ❌ KSeF integration uses per-company certificates — multi-company adds complexity
- ❌ ZUS payroll requires per-employer settlement — easier in separate DBs
- ❌ Polish auditors expect a 1:1 mapping between database and legal entity

### Option B — Two databases, one Odoo process *(CHOSEN)*
- ✅ Full data isolation per legal entity
- ✅ Single server, single Docker stack, single TLS cert
- ✅ One backup/restore procedure
- ✅ Separate KSeF credentials per database is natural
- ✅ DBFilter routing is battle-tested in Odoo

### Option C — Two Odoo processes, two databases
- ❌ Double the resource footprint
- ❌ Two upgrade windows
- ❌ Operational complexity (which container do I tail logs for?)
- ✅ Total fault isolation — but we get most of that from PG isolation in Option B

---

## 3. Module Layering

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4 — Polish JPK / KSeF custom                         │
│  l10n_pl_edi_fixes, l10n_pl_jpk_v7, l10n_pl_jpk_kr_pd       │
└────────────────┬────────────────────────────────────────────┘
                 │ depends on l10n_pl, l10n_pl_edi
┌────────────────▼────────────────────────────────────────────┐
│  LAYER 3 — OCA financial extensions                         │
│  account_asset_management, account_financial_report,        │
│  account_tax_balance, partner_statement                     │
└────────────────┬────────────────────────────────────────────┘
                 │ depends on account, report_xlsx, date_range
┌────────────────▼────────────────────────────────────────────┐
│  LAYER 2 — Polish localization (built-in Odoo CE)           │
│  l10n_pl, l10n_pl_edi, l10n_pl_taxable_supply_date,         │
│  l10n_pl_bank_verification, l10n_pl_nbp_rates (ours)        │
└────────────────┬────────────────────────────────────────────┘
                 │ depends on account, base
┌────────────────▼────────────────────────────────────────────┐
│  LAYER 1 — Odoo 19 CE core                                  │
│  account, sale, purchase, stock, hr, crm, project, etc.     │
└─────────────────────────────────────────────────────────────┘
```

Each layer depends only on layers below it. The `l10n_pl_edi_fixes` module is intentionally minimal — it patches three specific gaps in the Odoo S.A. KSeF module rather than re-implementing it.

---

## 4. KSeF Flow (Detailed)

```
   ┌─────────────┐
   │  User       │  Send & Print
   │  posts      │──────┐
   │  invoice    │      │
   └─────────────┘      ▼
                ┌───────────────────────────────────┐
                │  account.move._post()             │
                │  → l10n_pl_edi triggers EDI flow  │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  account_move._l10n_pl_edi_       │
                │  render_xml()                     │
                │     │                             │
                │     ├─ super() returns base XML   │
                │     │                             │
                │     ▼                             │
                │  l10n_pl_edi_fixes patches:       │
                │     • GTU codes (<GTU>)        │
                │     • P_18A from split_payment    │
                │     • P_19A VAT exemption basis   │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  XAdES sign (via certificate)     │
                │  → POST to api.ksef.mf.gov.pl/v2  │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  KSeF returns:                    │
                │  • KSeF reference (polling ID)    │
                │     stored in l10n_pl_edi_ref     │
                │  • Status: PROCESSING/ACCEPTED    │
                └────────────────┬──────────────────┘
                                 ▼ scheduled action polls
                ┌───────────────────────────────────┐
                │  ACCEPTED:                        │
                │  • KSeF number stored in          │
                │    l10n_pl_edi_number             │
                │  • UPO downloaded → attached      │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  Month-end JPK_V7M(3):            │
                │  • l10n_pl_jpk_v7 reads           │
                │    l10n_pl_edi_number → NrKSeF    │
                │  • Falls back to BFK/OFF/DI tag   │
                │    if no KSeF number              │
                └───────────────────────────────────┘
```

The `l10n_pl_edi_fixes` module uses lxml post-processing rather than QWeb template inheritance. Reason: the FA(3) template structure has `<P_18A>` inside `<Adnotacje>` and exemption fields inside an optional `<Zwolnienie>` block — XPath inheritance was brittle. Post-processing the rendered XML with lxml is bulletproof.

---

## 5. JPK_V7M(3) Generation

```
   User opens
   Accounting → Reporting → JPK_V7 Reports → New
       │
       ▼
   Choose: period_type (monthly/quarterly), date range, company
       │
       ▼
   Click "Generate XML"
       │
       ▼
   _generate_jpk_xml(company, nip):
       │
       ├──▶ _get_invoices()    # SELECT FROM account_move
       │
       ├──▶ _build_root()       # <JPK xmlns="http://crd.gov.pl/wzor/2025/12/19/14090/">
       │
       ├──▶ _build_naglowek(nip)
       │    • KodFormularza JPK_VAT, wersjaSchemy 1-0E
       │    • WariantFormularza 3
       │    • DataWytworzenia (now UTC)
       │
       ├──▶ _build_podmiot(company, nip)
       │    • NIP, PelnaNazwa, address from res.company
       │
       ├──▶ _build_ewidencja(invoices) → returns (sales_k, purchase_k)
       │    For each invoice:
       │      • Extract K-fields from account tax tags via _TAG_TO_K_FIELD
       │      • SprzedazWiersz / ZakupWiersz with:
       │           - NrKSeF (from l10n_pl_edi_number) OR OFF/BFK/DI tag
       │           - GTU codes from product templates
       │           - MPP marker if l10n_pl_split_payment
       │           - K_10–K_39 (sales) or K_40–K_47 (purchase) amounts
       │      • Increment running totals
       │    SprzedazCtrl, ZakupCtrl with row count + VAT totals
       │
       ├──▶ _build_deklaracja(sales_k, purchase_k)
       │    VAT-7 form embedded:
       │      • P_10 through P_55 declaration positions
       │      • Net VAT calculation
       │
       ▼
   etree.tostring → bytes → ir.attachment → user downloads XML
       │
       ▼
   User uploads at https://www.podatki.gov.pl/e-deklaracje/
   Signs with Profil Zaufany or qualified certificate
   Submits monthly (by 25th)
```

The K-field mapping (`_TAG_TO_K_FIELD`) assumes the standard `l10n_pl` chart of accounts tag names. After installing `l10n_pl`, verify:
- Settings → Technical → Accounting → Account Tags (filter: country=Poland)
- Match the tag names against `_TAG_TO_K_FIELD` keys
- Add aliases if your tag names differ

---

## 6. Single-Person Signing Model

```
┌──────────────────────────────────────────────────────────┐
│  PREZES ZARZĄDU                                          │
│                                                          │
│  Role 1: Kierownik jednostki (Art. 4 ust. 1 UoR)         │
│  Role 2: Osoba prowadząca księgi (Art. 4 ust. 5 UoR)     │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼ uchwała zarządu (written)
                          │
              ┌───────────┴───────────┐
              │ Daily bookkeeping     │
              │ in Odoo (with AI)     │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Monthly JPK_V7M       │
              │ Annual CIT-8          │
              │ Annual Bilans+RZiS    │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Sign with Profil      │
              │ Zaufany (free)        │
              │ — single signature    │
              │   in dual role        │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Submit to MF/RDF/KRS  │
              └───────────────────────┘

OPTIONAL — Auditor / Tax Advisor:
              ┌───────────────────────┐
              │ Read-only Odoo access │
              │ Monthly review        │
              │ Annual audit (NOT     │
              │   legally required    │
              │   for sp. z o.o. of   │
              │   this size)          │
              └───────────────────────┘
```

The auditor doesn't sign anything in this model. They review for *quality assurance*. The legal responsibility rests on the prezes (Art. 4 ust. 5 + Art. 77 UoR).

---

## 7. Data Persistence

| What | Where | Backed up by |
|---|---|---|
| PostgreSQL data | named volume `pg-data` | `db-backup` sidecar (daily 02:00) → `./backups/*.dump` |
| Odoo filestore | named volume `odoo-filestore` | manual `make backup` → `./backups/filestore_*.tar.gz` |
| Custom code | `./custom_addons/` (git tracked) | git remote |
| OCA submodules | `./addons/` (git submodules) | upstream OCA git remote |
| odoo.conf | `./odoo.conf` (git tracked) | git remote |
| MF XSD schemas | `./schemas/` (git tracked) | git remote + MF re-download |
| Secrets | Coolify Environment Variables tab | Coolify's own backup |

**Recovery RTO: ~30 minutes** — provision new VPS, restore Coolify, pull repo, restore `./backups/*.dump`, redeploy.

**Recovery RPO: 24 hours** — daily backup at 02:00. Increase to hourly by setting `0 * * * *` in `scripts/backup-cron.sh` if needed.

---

## 8. Security Posture

| Threat | Mitigation |
|---|---|
| Unauthorized DB Manager access | `list_db = False` + `admin_passwd` (random 32-byte) |
| Login brute force | Traefik rate limit (50/min/IP), Odoo built-in cooldown |
| Cross-company data leak | Separate databases (not just multi-company) |
| Cleartext passwords in code | All secrets via Coolify env vars, none in git |
| Exposed PostgreSQL port | `internal: true` on `odoo-internal` Docker network |
| Backup tampering | Backup files outside git (`.gitignore`) — store off-host |
| Cron job RCE | `_cron_check_expiry` uses `model._cron_check_expiry()` not eval() of input |
| Cross-site request forgery | Odoo core CSRF token — `proxy_mode = True` ensures it works behind Traefik |
| Email injection | Use Odoo SMTP wrapper, never raw `smtplib` |

What we **don't** defend against:
- Compromised host OS (root escalation)
- Coolify itself being breached (use 2FA on Coolify panel)
- Malicious admin user inside Odoo (rely on Polish audit trail + git commit log)

---

## 9. Performance Tuning

`workers = 5` is set in `odoo.conf` based on formula `(vCPU × 2) + 1` for 2 vCPU.

Scaling guidance:
- 2 vCPU / 4 GB RAM → `workers = 5`, `max_cron_threads = 2` *(current default)*
- 4 vCPU / 8 GB RAM → `workers = 9`, `max_cron_threads = 4`
- 8 vCPU / 16 GB RAM → `workers = 17`, `max_cron_threads = 4`

Per-worker memory limits in `odoo.conf`:
- `limit_memory_soft = 671088640` (640 MB) — recycle after current request
- `limit_memory_hard = 1610612736` (1.5 GB) — kill immediately

PostgreSQL connection pool: `db_maxconn = 64` is conservative; raise to 128 if multiple users see "too many connections" errors.

---

## 10. What Could Go Wrong

| Failure mode | Symptom | Recovery |
|---|---|---|
| KSeF rejects FA(3) XML | Invoice EDI status = rejected | Read error in chatter; fix invoice; re-send. Common: NIP missing PL prefix in form, but the XML expects 10 digits only |
| JPK_V7M(3) rejected | XSD validation fails | Schema namespace must match `http://crd.gov.pl/wzor/2025/12/19/14090/`. Module already uses this. |
| Biała Lista check returns "incomplete_partner" | Cannot post payment > PLN 15k | Add NIP to partner record |
| ZUS DRA file rejected | Płatnik error code | Usually means employee contribution rate config is off — verify ZUS rates in payroll module |
| KSeF certificate expired | Invoices fail to send | Renew certificate; upload new one in Odoo settings; re-send queued invoices |
| MF schema updates mid-year | Suddenly fails validation | Re-download XSD per DOWNLOADS.md → adjust module namespace constants |
| Odoo upgrade to 20 (Nov 2026) | Custom modules break | Test in staging DB first; we use stable APIs but a major release can change much |

---

## 11. Why We Built Custom Modules Instead of Paying

Total saved license cost (paid alternatives we replaced):

| Module | Free path | Replaces |
|---|---|---|
| KSeF integration | Built-in `l10n_pl_edi` + `l10n_pl_edi_fixes` | Trilab KSeF €540 |
| JPK_V7M(3) | `l10n_pl_jpk_v7` | Trilab JPK VAT €380 / Baris Genc €187 |
| NBP rates | `l10n_pl_nbp_rates` | Trilab NBP "free but OPL-1" |
| Fixed assets | OCA `account_asset_management` | Odoo EE Custom plan €37.40/user/month |
| Financial reports | OCA `account_financial_report` | Odoo EE `account_reports` |
| Payroll | `vitalibondar/l10n-pl-payroll` | Baris Genc €343 |
| Biała Lista | Built-in `l10n_pl_bank_verification` | Trilab Partners Sync €10 |
| **TOTAL avoided** | **€0** | **~€1,460 one-time + EE subscription** |

The trade-off is operational complexity — custom modules need updates when:
- Polish tax law changes (Ministry of Finance publishes new XSD)
- Odoo S.A. releases version 20+ (typically once a year)
- OCA migration branches lag behind core

If your business cannot afford a half-day of Odoo maintenance per quarter, buy the paid modules instead.
