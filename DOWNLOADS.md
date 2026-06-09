# Manual Downloads & Configuration

What this project already includes vs. what you need to fetch / configure yourself.

---

## Files Already Embedded

All MF XSD schemas were downloaded automatically and are committed under `schemas/`:

| File | Source | Purpose |
|---|---|---|
| `schemas/jpk_v7m3.xsd` | http://crd.gov.pl/wzor/2025/12/19/14090/schemat.xsd | JPK_V7M(3) monthly VAT — used by `l10n_pl_jpk_v7` module |
| `schemas/jpk_v7k3.xsd` | http://crd.gov.pl/wzor/2025/12/19/14089/schemat.xsd | JPK_V7K(3) quarterly VAT |
| `schemas/fa3.xsd` | http://crd.gov.pl/wzor/2025/06/25/13775/schemat.xsd | KSeF FA(3) e-invoice — reference (Odoo's `l10n_pl_edi` carries its own copy) |
| `schemas/jpk_kr_pd.xsd` | https://www.gov.pl/attachment/4ec8f106-032c-42f2-9fb5-15b5ec5ca670 | JPK_CIT — future module (deadline 2027-07-31) |
| `schemas/jpk_st_kr.xsd` | https://www.gov.pl/attachment/336fb09b-ea93-475d-a895-0ef5b8b72a0b | Fixed assets companion schema for JPK_CIT |

These are the **official, current** versions as of 2026-06-08. Re-download them
once a year (Ministry of Finance occasionally updates schemas — track at
[podatki.gov.pl JPK page](https://www.podatki.gov.pl/podatki-firmowe/jednolity-plik-kontrolny/)).

---

## You Need to Download / Configure Manually

### 1. Profil Zaufany (for signing financial statements)

**Cost:** FREE
**Method:** Online via bank, or in-person at ZUS/Post Office/voivodeship
**URL:** https://pz.gov.pl

For each board member who will sign:
1. Go to https://pz.gov.pl
2. Choose "Załóż profil" → via bank (fastest, same day)
3. Verify via PKO BP, Pekao, ING, mBank, Santander, etc.
4. Set a 6-digit signing PIN

Use this to sign Bilans/RZiS XML when filing to RDF (https://ekrs.ms.gov.pl/rdf/rd/).

### 2. ZUS Płatnik (for ZUS declarations)

**Cost:** FREE (Windows / Wine compatible)
**URL:** https://www.zus.pl/en/firmy/program-platnik/pobierz
**Current version:** 10.02.002 + Fix2 (May 2026)

The `l10n-pl-payroll` module generates ZUS XML files. Import them into Płatnik to submit DRA/RCA/RSA/RZA to ZUS. No direct API exists.

**Alternative:** ePłatnik web app at https://www.zus.pl/portal/pomoc/epl0000.html — for employers ≤ 100 employees, no install needed.

### 3. KSeF Test Credentials (for safe initial testing)

**Cost:** FREE
**Steps:**
1. Visit https://api-test.ksef.mf.gov.pl/docs/v2 → review the API
2. Each company's NIP can be registered for test access
3. Sandbox uses anonymized data — invoices have no legal effect
4. Move to production at `https://api.ksef.mf.gov.pl/v2` once tested

**Authentication:** KSeF 2.0 is certificate-based — you need a qualified electronic signature (e.g. from Certum, EuroCert, PWPW, ~PLN 200/year) for production KSeF.

[Setup guide: ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/wsparcie-dla-integratorow/](https://ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/wsparcie-dla-integratorow/)

### 4. e-Sprawozdania Web App (for Bilans / RZiS XML)

**Cost:** FREE
**URL:** https://e-sprawozdania.mf.gov.pl/ap/
**Requirements:** Modern browser only — no install

Workflow:
1. Export Trial Balance from Odoo (OCA `account_financial_report`)
2. Open e-Sprawozdania web app
3. Manually map your trial-balance figures to Bilans/RZiS positions (Załącznik 1 UoR)
4. Sign with Profil Zaufany
5. File at https://ekrs.ms.gov.pl/rdf/rd/

**AI workflow tip:** Export Trial Balance as XLSX → ask Claude/ChatGPT to map account numbers to Bilans positions per UoR Załącznik 1 → manually verify and enter into the MF app.

### 5. l10n-pl-payroll Module — Version Bump

The `vitalibondar/l10n-pl-payroll` GitHub repository has `'version': '18.0.1.0.0'` in its `main` branch as of 2026-06-08. The author has an unmerged `task/011-odoo19-migration` branch.

**To use on Odoo 19, choose one:**

**Option A — Track the migration branch (preferred when it works):**
```bash
cd addons/l10n-pl-payroll
git fetch origin task/011-odoo19-migration
git checkout task/011-odoo19-migration
```

**Option B — Manual version bump (if migration branch lags):**
```bash
sed -i "s/'version': '18.0/'version': '19.0/" \
  addons/l10n-pl-payroll/l10n_pl_payroll/__manifest__.py
```

**Option C — Run on Odoo 18:** if version 19 has compatibility issues, the safest fallback is to use `odoo:18.0` instead of `odoo:19.0` in `Dockerfile`. All other modules in this repo work on both.

⚠️ Always verify payroll calculations against Płatnik before issuing payslips.

### 6. NBP Currency Rates — No Action Needed

`l10n_pl_nbp_rates` (this repo) fetches https://static.nbp.pl/dane/kursy/xml/LastA.xml daily at 09:00. No API key, no registration.

### 7. Biała Lista — No Action Needed

`l10n_pl_bank_verification` (built into Odoo 19 CE) calls https://wl-api.mf.gov.pl directly. No API key, no registration. Auto-triggers before payments > PLN 15,000.

### 8. KSeF Production Certificate

When you move from KSeF test to production:

1. Buy a qualified electronic signature (~PLN 200/year):
   - Certum: https://sklep.certum.pl/
   - EuroCert: https://eurocert.pl/
   - PWPW Sigillum: https://sigillum.pl/

2. Or use a KSeF certificate (free for KSeF only, from MF):
   - Available from 2026-04-01 — application at ksef.podatki.gov.pl

3. Configure in Odoo: Accounting → Configuration → Settings → KSeF →
   upload certificate and set mode to "Production".

---

## Things You Decide & Configure (Not Downloadable)

### Company information

For each company (MNL, Bioleaf) in Odoo Settings → Companies:

| Field | Source |
|---|---|
| Nazwa | KRS |
| NIP (10 digits, no PL prefix) | NIP/CEIDG |
| REGON | GUS |
| Numer KRS | KRS |
| Kapitał zakładowy | Statutory documents |
| Adres | KRS |

### Bank accounts

For Biała Lista verification + MPP:
1. Settings → Bank Accounts → add each Polish bank account
2. Enable "Use VAT account" checkbox for rachunek VAT (for MPP)
3. Whitelist verification happens automatically when posting payments

### Email server

Configure per-company SMTP:
- Settings → Technical → Email → Outgoing Mail Servers
- Required for KSeF UPO confirmations, ZUS deadline alerts, customer invoice delivery

### Board resolution (for single-person signing)

See [README.md](./README.md) → "Signing Financial Statements" — template uchwała included.
File this in the company's documentation before first sprawozdanie filing.

---

## Quick Reference — All URLs

| Resource | URL |
|---|---|
| Profil Zaufany | https://pz.gov.pl |
| KSeF production | https://api.ksef.mf.gov.pl/v2 |
| KSeF test | https://api-test.ksef.mf.gov.pl/v2 |
| KSeF docs | https://github.com/CIRFMF/ksef-docs |
| JPK_V7 submission | https://www.podatki.gov.pl/e-deklaracje/ |
| e-Sprawozdania app | https://e-sprawozdania.mf.gov.pl/ap/ |
| RDF (financial statements) | https://ekrs.ms.gov.pl/rdf/rd/ |
| PUE ZUS | https://www.zus.pl/ |
| ZUS Płatnik download | https://www.zus.pl/en/firmy/program-platnik/pobierz |
| Biała lista (UI) | https://www.podatki.gov.pl/wykaz-podatnikow-vat-wyszukiwarka/ |
| NBP rates | https://static.nbp.pl/dane/kursy/xml/LastA.xml |

---

## Re-Downloading Embedded Schemas

Once a year, refresh the schemas:

```bash
cd schemas
curl -sLO http://crd.gov.pl/wzor/2025/12/19/14090/schemat.xsd -o jpk_v7m3.xsd
curl -sLO http://crd.gov.pl/wzor/2025/12/19/14089/schemat.xsd -o jpk_v7k3.xsd
curl -sLO http://crd.gov.pl/wzor/2025/06/25/13775/schemat.xsd -o fa3.xsd
curl -sLO https://www.gov.pl/attachment/4ec8f106-032c-42f2-9fb5-15b5ec5ca670 -o jpk_kr_pd.xsd
curl -sLO https://www.gov.pl/attachment/336fb09b-ea93-475d-a895-0ef5b8b72a0b -o jpk_st_kr.xsd

# Verify file sizes haven't dramatically changed (schemas evolve slowly)
ls -la *.xsd
```

If a schema URL 404s, the namespace has likely changed — check the [podatki.gov.pl
JPK page](https://www.podatki.gov.pl/podatki-firmowe/jednolity-plik-kontrolny/) for the new version.
