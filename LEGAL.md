# Verified Polish Legal References

All citations below were verified by multi-source adversarial research on
**2026-06-08**. Sources are official government texts and reputable Polish
tax/accounting outlets (GoFin, Lex, BDO, TPA Poland, biznes.gov.pl).

> **Disclaimer.** This document summarises law as research understood it at
> a point in time. It is not legal advice. Tax law evolves — verify the
> current text before relying on any article for material decisions, and
> consult a doradca podatkowy or radca prawny for company-specific situations.

---

## 1. Ustawa o rachunkowości (UoR) — Accounting Act

Dz.U. 1994 nr 121 poz. 591 — tekst jednolity Dz.U. 2023 poz. 120.

### Art. 4 ust. 5 — Responsibility for bookkeeping

> *„Kierownik jednostki [...] ponosi odpowiedzialność za wykonywanie obowiązków
> w zakresie rachunkowości określonych ustawą, w tym z tytułu nadzoru,
> również w przypadku, gdy określone obowiązki [...] zostaną powierzone innej
> osobie lub przedsiębiorcy, za ich zgodą. Przyjęcie odpowiedzialności przez
> inną osobę lub przedsiębiorcę powinno być stwierdzone w formie pisemnej."*

✅ **Interpretation:** The management board (kierownik jednostki) bears
inescapable responsibility for accounting. Delegation is allowed but requires
written acceptance from the delegate. Critically — the statute does NOT impose
qualifications on the delegate; that was removed in the 2014 deregulation.

[Source: lexlege.pl/ustawa-o-rachunkowosci/art-4](https://lexlege.pl/ustawa-o-rachunkowosci/art-4/)

### Art. 52 ust. 2 — Signing financial statements

> *„Sprawozdanie finansowe podpisują — podając zarazem datę podpisu —
> osoba, której powierzono prowadzenie ksiąg rachunkowych, i kierownik
> jednostki, a jeżeli jednostką kieruje organ wieloosobowy — wszyscy
> członkowie tego organu albo co najmniej jedna osoba wchodząca w skład tego
> organu, w sposób określony w ust. 2b."*

✅ **Two signing roles required:** (1) osoba prowadząca księgi, (2) kierownik
jednostki. **If one person fills both roles (Prezes who personally keeps the
books per Art. 4 ust. 5), one signature suffices** — that's the legal basis
for the single-signature model in this project.

[Source: lexlege.pl/ustawa-o-rachunkowosci/art-52](https://lexlege.pl/ustawa-o-rachunkowosci/art-52/)

### Art. 52 ust. 2b — 2022 multi-board simplification

In force from **2022-01-01** (added by Dz.U. 2021 poz. 2106).

> *„Jeżeli jednostką kieruje organ wieloosobowy, sprawozdanie finansowe może
> podpisać co najmniej jedna osoba wchodząca w skład tego organu, po
> złożeniu przez pozostałe osoby [...] oświadczeń, że sprawozdanie finansowe
> spełnia wymagania przewidziane w ustawie."*

✅ Multi-member boards: one member signs + written statements from the others.
Not relevant if the company has a single-member board.

### Art. 76a ust. 3 — Post-2014 deregulation

> *„Działalność, o której mowa w ust. 1, mogą wykonywać przedsiębiorcy,
> pod warunkiem że czynności z tego zakresu będą wykonywane przez osoby:
> 1) mające pełną zdolność do czynności prawnych;
> 2) niekarane za przestępstwa [...]."*

✅ **Applies to EXTERNAL bookkeeping services** (biuro rachunkowe). For
INTERNAL bookkeeping (employee, board member), no qualifications are required.
The 2014 deregulation (Dz.U. 2014 poz. 768) removed the previous Ministry of
Finance certification (licencja MF) requirement entirely.

[Source: lexlege.pl/ustawa-o-rachunkowosci/art-76a](https://lexlege.pl/ustawa-o-rachunkowosci/art-76a/)

### Art. 76h — OC insurance for external services

> Mandatory OC (civil liability) insurance for entrepreneurs providing
> bookkeeping services. Minimum guaranteed sum: **10,000 EUR per event**
> (Rozporządzenie MF z 6 listopada 2014 r., Dz.U. 2014 poz. 1616).

✅ Confirmed. Does not apply to internal bookkeeping by the company itself.

### Art. 77 — Criminal liability for unreliable books

> *„Kto wbrew przepisom ustawy dopuszcza do nieprowadzenia ksiąg rachunkowych
> [...] albo do podawania w nich nierzetelnych danych — podlega grzywnie lub
> karze pozbawienia wolności do lat 2, albo obu tym karom łącznie."*

✅ Maximum 2 years imprisonment. Intentional offense (must show willful or
reckless conduct). Drives the importance of having an external audit even
when not legally required for sp. z o.o. of this size.

---

## 2. Podpisywanie e-Sprawozdań Finansowych

Allowed signature types per **Art. 45 ust. 1f UoR**:

| Type | Cost | Who |
|---|---|---|
| **Profil Zaufany** (ePUAP) | FREE | Anyone with PESEL |
| **Podpis kwalifikowany** (e.g. Certum, EuroCert, PWPW) | ~PLN 200/yr | Anyone, required for non-PESEL holders |
| **Podpis osobisty** (e-dowód) | FREE (if you have e-dowód) | Polish citizens with e-ID card |

**Submission destinations:**
- **RDF (Repozytorium Dokumentów Finansowych)** via eKRS — for all KRS entities
  → https://ekrs.ms.gov.pl/rdf/rd/
- Some entities also file with KAS directly via e-Deklaracje

**Tip:** when multiple people sign, do **Profil Zaufany first, qualified signature second** — the reverse order locks the XML.

---

## 3. KSeF — Krajowy System e-Faktur

Legal basis: **Ustawa o VAT, Art. 106na** + Ministry of Finance regulations.

| Date | Who | What |
|---|---|---|
| **2026-02-01** | Large taxpayers (sales > PLN 200M brutto in 2024) | KSeF mandatory for issuing AND receiving |
| **2026-02-01** | All other VAT taxpayers | Must be able to receive via KSeF |
| **2026-04-01** | All other VAT taxpayers | KSeF mandatory for issuing |
| **2027-01-01** | Micro-enterprises (sales ≤ PLN 10k/month brutto) | KSeF mandatory for issuing |

✅ **MNL and Bioleaf fall under 2026-04-01 issuing obligation** (unless > PLN 200M).

**API version (verified 2026-06-09):** **v2.6.0** (deployed PRD 2026-05-26)

**API endpoints:**
- Production: `https://api.ksef.mf.gov.pl/api/v2/...`
- Demo (training): `https://api-demo.ksef.mf.gov.pl/api/v2/...`
- Integration (test): `https://api-test.ksef.mf.gov.pl/api/v2/...`

Authoritative spec: `github.com/CIRFMF/ksef-docs` (open-api.json)

**Schema:** FA(3), namespace `http://crd.gov.pl/wzor/2025/06/25/13775/`,
published 2025-06-25. Stored locally at `schemas/fa3.xsd`.

**Critical operational facts:**
- Access tokens TTL ~15 minutes; refresh tokens up to 7 days
- Offline mode signal is the API parameter `offlineMode: true`, NOT an XML element
- XAdES signing — must use Exclusive C14N + RSA-SHA256 (min 2048-bit) + SHA-256 digest
- AES-256-CBC + RSA-OAEP/SHA-256 encryption mandatory for both online and batch
- Max 1 MB per invoice payload (3 MB with structured attachments)
- Rate limits: ~10/s, 30/min, 120/h on most endpoints
- Token-based auth supported through 2026-12-31; KSeF certificate from 2027-01-01

**KSeF number format** (35 chars): `NNNNNNNNNN-YYYYMMDD-XXXXXXXXXXXX-CC`
where NNNNNNNNNN = issuer NIP, YYYYMMDD = acceptance date,
12 hex chars = uniqueness, 2 chars = checksum.

**KSeF number in payment titles:**
- From **2026-08-01**: required for MPP (split payment) transfers (Art. 108a §1c VAT)
- From **2027-01-01**: required for ALL B2B transfers between active VAT taxpayers (Art. 108g VAT)

[Source: ksef.podatki.gov.pl](https://ksef.podatki.gov.pl/informacje-ogolne-ksef-20/zakres-obowiazkowego-ksef/)

---

## 4. JPK_V7M(3) — Monthly VAT SAF-T

### Legal basis & deadlines

- **Art. 109 ust. 3b VAT** — obligation to submit JPK_V7M monthly.
- **Art. 109 ust. 3f VAT** — penalty up to **PLN 500 per error** if not corrected within 14 days of MF notification. *(This penalty has existed since 2020; it is NOT new in 2026.)*
- **Schema version 3 mandatory from 2026-02-01** — first filing 2026-03-25.

### Schema details (verified 2026-06-09 against XSD)

- **Namespace:** `http://crd.gov.pl/wzor/2025/12/19/14090/`
- **Imported ETD namespace:** `http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/` ⚠️ (2022/09/13, NOT 2022/01/05 — strict)
- **Imported KUS namespace:** `http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/KodyUrzedowSkarbowych/`
- **Schema version:** `wersjaSchemy="1-0E"` (XSD file version)
- **Form variant:** `WariantFormularza="3"` (form version)
- **kodSystemowy:** `"JPK_V7M (3)"` or `"JPK_V7K (3)"` — exact spacing
- **Quarterly equivalent (V7K):** `http://crd.gov.pl/wzor/2025/12/19/14089/`

**Strict XSD root order:** `Naglowek → Podmiot1 → Deklaracja → Ewidencja`
(Deklaracja BEFORE Ewidencja — not the other way around)

**Podmiot1 wrapper:** must be `<OsobaNiefizyczna>` with `rola="Podatnik"` attribute,
no `<AdresPodmiotu>` (the type is `TPodmiotDowolnyBezAdresu`).

**Naglowek required fields** (Email is mandatory):
NIP, PelnaNazwa, Email, Telefon? (in OsobaNiefizyczna). KodUrzedu + Rok + Miesiac (in outer Naglowek).

XSD files: `schemas/jpk_v7m3.xsd` (verified 1220 lines), `schemas/jpk_v7k3.xsd`.

### Required KSeF / tag fields

Every sales and purchase record must contain **exactly one** of:

| Field | Use |
|---|---|
| `<NrKSeF>` | KSeF invoice number from `l10n_pl_edi_number` field |
| `<OFF>1</OFF>` | Issued during confirmed KSeF system failure |
| `<BFK>1</BFK>` | Issued outside KSeF under valid exemption (cash register, B2C) |
| `<DI>1</DI>` | Non-invoice document / offline without KSeF number |

The `l10n_pl_jpk_v7` module in this repo defaults to `NrKSeF` if available and falls back to `BFK` otherwise (with a log warning).

[Source: podatki.gov.pl JPK_VAT downloads](https://www.podatki.gov.pl/podatki-firmowe/jednolity-plik-kontrolny/jpk_vat-z-deklaracja/pliki-do-pobrania/)

---

## 5. JPK_KR_PD — Annual CIT SAF-T (JPK_CIT)

Legal basis: **Art. 9 ust. 1c UoCIT** (added 2024).

### Phased rollout

| Tax year ending after | Filing deadline | Taxpayers |
|---|---|---|
| 2024-12-31 | 2026-07-31 | Large taxpayers (revenue > EUR 50M) and tax capital groups |
| 2025-12-31 | 2027-07-31 | Other CIT taxpayers submitting JPK_V7M (= typical sp. z o.o.) |
| 2026-12-31 | 2028-07-31 | Remaining CIT taxpayers |

✅ **MNL and Bioleaf first JPK_KR_PD: 2027-07-31** (for fiscal year 2026).

### Schema

- **JPK_KR_PD(1):** namespace `http://jpk.mf.gov.pl/wzor/2024/09/04/09041/`, version `wersjaSchemy="1-1"` (XSD fixed; brochure misquotes "1-0" — use **1-1**), `kodSystemowy="JPK_KR_PD (1)"`. Stored at `schemas/jpk_kr_pd.xsd`.
- **JPK_ST_KR(1):** namespace `http://jpk.mf.gov.pl/wzor/2024/04/24/04242/`, `wersjaSchemy="1-0"`, separate companion. Stored at `schemas/jpk_st_kr.xsd`.

**Implementation status:** `l10n_pl_jpk_kr_pd` module (this repo) generates a working JPK_KR_PD using ZOiS8 (IFRS variant — markers optional). Switch to ZOiS7 + populate `account.account.l10n_pl_zois_marker_1` for full traditional Polish CoA mapping.

**Strict XSD root order:** `Naglowek → Podmiot1 → Kontrahent* → ZOiS → Dziennik+ → Ctrl → RPD`

**Mandatory company fields:** NIP, PelnaNazwa, full address (KodKraju, Wojewodztwo, Powiat, Gmina, Ulica, NrDomu, Miejscowosc, KodPocztowy `NN-NNN`). Set them in Company / Partner before generating.

**RPD section** has 8 mandatory K_* fields:
- K_1, K_2, K_4, K_5 — auto-computed from `account.account.l10n_pl_pd_marker`
- K_3, K_6, K_7, K_8 — manual inputs on the report wizard (cannot be derived)

[Source: gov.pl/web/kas/struktury-jpk-w-podatkach-dochodowych](https://www.gov.pl/web/kas/struktury-jpk-w-podatkach-dochodowych)

---

## 6. MPP — Mechanizm Podzielonej Płatności

Legal basis: **Art. 108a Ustawy o VAT**.

✅ **Mandatory when ALL of:**
1. Invoice gross value > **PLN 15,000** (or foreign equivalent)
2. Invoice contains at least one item from **Załącznik 15 UoVAT**
3. Both parties are Polish VAT taxpayers

**Annex 15** covers: steel and metal products, electronics, fuel and lubricants, coal, certain construction services, waste, etc.
For most sp. z o.o. this rarely applies — but if you renovate a building with construction services > PLN 15k, MPP kicks in.

✅ Configured in this repo: `l10n_pl_edi_fixes` adds the `l10n_pl_split_payment` boolean field on invoices, which:
- Sets `P_18A=1` in KSeF FA(3) XML
- Adds the statutory annotation "mechanizm podzielonej płatności" to the printed invoice

---

## 7. Biała Lista — VAT Whitelist

Legal basis: **Art. 96b ust. 1 Ustawy o VAT** + **Art. 15d Ustawy o CIT** + **Art. 22p Ustawy o PIT**.

✅ **Mandatory check when:**
- Payment > **PLN 15,000** (gross transaction value)
- Recipient is a Polish VAT taxpayer
- Payment by bank transfer

**Consequence of failure:**
- Cannot recognize payment as tax-deductible cost
- Joint & several liability for the supplier's unpaid VAT

✅ Built into Odoo 19 CE: `l10n_pl_bank_verification` calls `wl-api.mf.gov.pl/api/search/nips/...` automatically before posting payments > PLN 15k. Verification record is stored with timestamp for the 5-year audit trail.

**Escape valve:** File **ZAW-NR** with the tax office within 7 days of the transfer to remove the sanction.

[Source: ifirma.pl/blog/biala-lista-podatnikow-vat-kompendium-2026](https://www.ifirma.pl/blog/biala-lista-podatnikow-vat-kompendium-2026/)

---

## 8. ZUS / PIT — Płace i wynagrodzenia

### Contribution rates (2026)

| Component | Employer rate | Employee rate |
|---|---|---|
| Pension (emerytalna) | 9.76% | 9.76% |
| Disability (rentowa) | 6.50% | 1.50% |
| Accident (wypadkowa) | 0.67–3.33% (industry-rated) | — |
| Sickness (chorobowa) | — | 2.45% |
| Health (zdrowotna) | — | 9.00% |
| Labor Fund (FP) | 2.45% | — |
| FGŚP | 0.10% | — |

### Deadlines

| Form | Date |
|---|---|
| ZUS DRA / RCA / RSA / RZA | 15th of next month |
| ZUS payment | 15th of next month |
| PIT advance (PIT-4 type) | 20th of next month |
| PIT-4R (annual employer) | 31 January |
| PIT-11 (annual employee) | end of February |

The `l10n-pl-payroll` module handles all of these (after Odoo 19 version bump — see [DOWNLOADS.md](./DOWNLOADS.md)).

---

## Last Updated

**2026-06-08** — by automated multi-agent legal verification swarm.
Re-run that verification before relying on these citations for high-stakes
filings, as Polish tax law can change between dates here and your filing date.
