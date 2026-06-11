#!/usr/bin/env python3
"""
onboard.py — Polish sp. z o.o. onboarding for Odoo 19.

Asks an interactive set of questions (in Polish), validates inputs
(NIP/REGON checksums, NN-NNN ZIP, mod-97 IBAN), then pipes the answers
into `docker compose run odoo shell -d <db>` as a single idempotent
Python script that writes them to res.company / res.partner /
res.partner.bank / ir.config_parameter.

Usage:
    ./scripts/onboard.py --db mnl_db
    ./scripts/onboard.py --db bioleaf_db --from-json configs/bioleaf.json
    ./scripts/onboard.py --db mnl_db --save configs/mnl.json
    ./scripts/onboard.py --list-tax-offices | grep WOŁOMIN

Re-running is safe: nothing is duplicated, existing records get updated
in place. Bank accounts are matched by acc_number.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────────

NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7]
REGON_9_WEIGHTS = [8, 9, 2, 3, 4, 5, 6, 7]
REGON_14_WEIGHTS = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]


def validate_nip(s: str) -> str:
    """Strip 'PL' prefix; validate 10-digit Polish NIP via weighted checksum."""
    digits = re.sub(r"[^0-9]", "", s.upper().replace("PL", ""))
    if len(digits) != 10:
        raise ValueError("NIP musi mieć dokładnie 10 cyfr")
    chk = sum(int(d) * w for d, w in zip(digits[:9], NIP_WEIGHTS)) % 11
    if chk == 10:
        raise ValueError("Suma kontrolna NIP = 10 (niedopuszczalne)")
    if chk != int(digits[9]):
        raise ValueError(f"NIP ma niepoprawną sumę kontrolną (oczekiwana {chk})")
    return digits


def validate_regon(s: str) -> str:
    digits = re.sub(r"[^0-9]", "", s)
    if len(digits) == 9:
        chk = sum(int(d) * w for d, w in zip(digits[:8], REGON_9_WEIGHTS)) % 11 % 10
        if chk != int(digits[8]):
            raise ValueError(f"REGON-9 niepoprawna suma kontrolna (oczekiwana {chk})")
        return digits
    if len(digits) == 14:
        validate_regon(digits[:9])
        chk = sum(int(d) * w for d, w in zip(digits[:13], REGON_14_WEIGHTS)) % 11 % 10
        if chk != int(digits[13]):
            raise ValueError(f"REGON-14 niepoprawna suma kontrolna (oczekiwana {chk})")
        return digits
    raise ValueError("REGON musi mieć 9 lub 14 cyfr")


def validate_krs(s: str) -> str:
    digits = re.sub(r"[^0-9]", "", s)
    if not digits or len(digits) > 10:
        raise ValueError("KRS musi mieć do 10 cyfr (zostaną dopełnione zerami)")
    return digits.zfill(10)


def validate_zip(s: str) -> str:
    s = s.strip()
    if not re.fullmatch(r"\d{2}-\d{3}", s):
        raise ValueError("Kod pocztowy musi mieć format NN-NNN (np. 05-250)")
    return s


def validate_iban_pl(s: str) -> str:
    s = re.sub(r"[\s-]", "", s.upper())
    if not s.startswith("PL"):
        s = "PL" + s
    if not re.fullmatch(r"PL\d{26}", s):
        raise ValueError("Polski IBAN: PL + 26 cyfr (z lub bez spacji)")
    # IBAN mod-97 check: move first 4 chars to end, replace letters with numbers, mod 97 == 1
    rearranged = s[4:] + str(ord("P") - 55) + str(ord("L") - 55) + s[2:4]
    if int(rearranged) % 97 != 1:
        raise ValueError("IBAN ma niepoprawną sumę kontrolną (mod-97)")
    return s


def validate_email(s: str) -> str:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", s):
        raise ValueError("Niepoprawny format adresu email")
    return s


def validate_tax_office_code(s: str) -> str:
    if not re.fullmatch(r"\d{4}", s):
        raise ValueError("Kod Urzędu Skarbowego to 4 cyfry (np. 1442 = Wołomin)")
    return s


def validate_share_capital(s: str) -> str:
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        raise ValueError("Kapitał zakładowy musi być liczbą (PLN)")
    return digits


# ─────────────────────────────────────────────────────────────────────────────
# CLI prompts
# ─────────────────────────────────────────────────────────────────────────────

WOJEWODZTWA = [
    ("DS", "dolnośląskie"),
    ("KP", "kujawsko-pomorskie"),
    ("LU", "lubelskie"),
    ("LB", "lubuskie"),
    ("LD", "łódzkie"),
    ("MA", "małopolskie"),
    ("MZ", "mazowieckie"),
    ("OP", "opolskie"),
    ("PK", "podkarpackie"),
    ("PD", "podlaskie"),
    ("PM", "pomorskie"),
    ("SL", "śląskie"),
    ("SK", "świętokrzyskie"),
    ("WN", "warmińsko-mazurskie"),
    ("WP", "wielkopolskie"),
    ("ZP", "zachodniopomorskie"),
]


def ask(label, *, default=None, validator=None, required=True):
    while True:
        prompt = f"  {label}"
        if default:
            prompt += f" [{default}]"
        prompt += ": "
        try:
            v = input(prompt).strip()
        except EOFError:
            print()
            sys.exit(1)
        if not v:
            if default is not None:
                v = str(default)
            elif not required:
                return ""
            else:
                print("    ⚠  pole wymagane")
                continue
        if validator:
            try:
                v = validator(v)
            except ValueError as e:
                print(f"    ⚠  {e}")
                continue
        return v


def ask_yes(label, *, default=True):
    suffix = " [T/n]" if default else " [t/N]"
    while True:
        v = input(f"  {label}{suffix}: ").strip().lower()
        if not v:
            return default
        if v in ("t", "tak", "y", "yes"):
            return True
        if v in ("n", "nie", "no"):
            return False
        print("    ⚠  odpowiedz t/n")


def ask_state():
    print("    Województwa:")
    for i, (code, name) in enumerate(WOJEWODZTWA, 1):
        print(f"      {i:>2}. {code} — {name}")
    while True:
        v = input("    Wybór (1-16 lub kod 2-literowy, np. MZ): ").strip().upper()
        if not v:
            continue
        for code, name in WOJEWODZTWA:
            if v == code:
                return code
        try:
            idx = int(v) - 1
            if 0 <= idx < len(WOJEWODZTWA):
                return WOJEWODZTWA[idx][0]
        except ValueError:
            pass
        print("    ⚠  niepoprawny wybór")


def ask_ksef_mode():
    print("    Tryb KSeF:")
    print("      1. test  — api-test.ksef.mf.gov.pl/v2 (zalecane na start)")
    print("      2. prod  — api.ksef.mf.gov.pl/v2 (wymaga prawdziwego tokena!)")
    while True:
        v = input("    Wybór [1]: ").strip()
        if v in ("", "1"):
            return "test"
        if v == "2":
            return "prod"
        print("    ⚠  niepoprawny wybór")


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Q&A
# ─────────────────────────────────────────────────────────────────────────────

def gather_answers(db_name: str, prefill: dict | None = None) -> dict:
    p = prefill or {}
    print(f"\n╭─ Onboarding firmy w bazie '{db_name}' ─╮")
    print("│ Enter = wartość domyślna · Ctrl-C = przerwij           │")
    print("╰────────────────────────────────────────────────────────╯\n")

    print("┌── 1. Identyfikacja prawna ─────────────────────────")
    name = ask("Nazwa firmy (np. 'Bioleaf Pharma sp. z o.o.')", default=p.get("name"))
    nip = ask("NIP (10 cyfr lub z prefixem PL)", default=p.get("nip"), validator=validate_nip)
    krs = ask("KRS (10 cyfr)", default=p.get("krs"), validator=validate_krs)
    regon = ask("REGON (9 lub 14 cyfr)", default=p.get("regon"),
                validator=validate_regon, required=False)
    share_capital = ask("Kapitał zakładowy w PLN (cyfry, np. 550000)",
                        default=p.get("share_capital"),
                        validator=validate_share_capital, required=False)

    print("\n┌── 2. Adres rejestrowy ─────────────────────────────")
    street = ask("Ulica i numer (np. 'ul. Wiejska 5')", default=p.get("street"))
    zip_code = ask("Kod pocztowy (NN-NNN)", default=p.get("zip"), validator=validate_zip)
    city = ask("Miejscowość", default=p.get("city"))
    if p.get("state_code"):
        state_code = p["state_code"]
        print(f"    Województwo: {state_code} (z konfiguracji)")
    else:
        state_code = ask_state()

    print("\n┌── 3. Urząd Skarbowy ───────────────────────────────")
    print("    Lista wszystkich kodów: ./scripts/onboard.py --list-tax-offices --db",
          db_name)
    tax_office_code = ask("Kod US (4 cyfry, np. 1442 = Wołomin)",
                          default=p.get("tax_office_code"),
                          validator=validate_tax_office_code)

    print("\n┌── 4. Kontakt ──────────────────────────────────────")
    email = ask("E-mail firmowy (WYMAGANY w nagłówku JPK)",
                default=p.get("email"), validator=validate_email)
    phone = ask("Telefon", default=p.get("phone"), required=False)
    website = ask("Strona WWW", default=p.get("website"), required=False)

    print("\n┌── 5. Konto bankowe ────────────────────────────────")
    iban, iban_vat = "", ""
    if ask_yes("Dodać konto bankowe teraz?", default=True):
        iban = ask("IBAN główny (PL + 26 cyfr)",
                   default=p.get("iban"), validator=validate_iban_pl)
        iban_vat = ask("Rachunek VAT do MPP (opcjonalnie)",
                       default=p.get("iban_vat"), validator=validate_iban_pl,
                       required=False)

    print("\n┌── 6. KSeF ─────────────────────────────────────────")
    if p.get("ksef_mode"):
        ksef_mode = p["ksef_mode"]
        print(f"    Tryb: {ksef_mode} (z konfiguracji)")
    else:
        ksef_mode = ask_ksef_mode()

    return {
        "db": db_name,
        "name": name,
        "nip": nip,
        "krs": krs,
        "regon": regon,
        "share_capital": share_capital,
        "street": street,
        "zip": zip_code,
        "city": city,
        "state_code": state_code,
        "tax_office_code": tax_office_code,
        "email": email,
        "phone": phone,
        "website": website,
        "iban": iban,
        "iban_vat": iban_vat,
        "ksef_mode": ksef_mode,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Apply to Odoo via shell
# ─────────────────────────────────────────────────────────────────────────────

ODOO_SHELL_SCRIPT = r"""
# Auto-generated by onboard.py — applies sp. z o.o. config to Odoo
import json

A = json.loads(__ANSWERS_JSON__)

company = env['res.company'].browse(1)
print("[onboard] Company before: {!r}  currency={}  country={}"
      .format(company.name, company.currency_id.name,
              company.partner_id.country_id.code or '-'))

# Polish country and chosen state
country_pl = env['res.country'].search([('code', '=', 'PL')], limit=1)
state = env['res.country.state'].search(
    [('country_id', '=', country_pl.id), ('code', '=', A['state_code'])], limit=1)

# Build partner notes (KRS/REGON/kapitał/PKD)
notes_lines = ['<p><strong>Dane rejestrowe:</strong><br/>']
notes_lines.append('NIP: %s<br/>' % A['nip'])
notes_lines.append('KRS: %s<br/>' % A['krs'])
if A.get('regon'):
    notes_lines.append('REGON: %s<br/>' % A['regon'])
if A.get('share_capital'):
    cap_s = '{:,}'.format(int(A['share_capital'])).replace(',', ' ')
    notes_lines.append('Kapitał zakładowy: %s PLN<br/>' % cap_s)
notes_lines.append('US: kod %s</p>' % A['tax_office_code'])
notes_html = ''.join(notes_lines)

# Update company name
company.write({'name': A['name']})

# Update company partner
partner_vals = {
    'name': A['name'],
    'vat': 'PL' + A['nip'],
    'company_registry': A['krs'],
    'street': A['street'],
    'zip': A['zip'],
    'city': A['city'],
    'state_id': state.id if state else False,
    'country_id': country_pl.id,
    'email': A['email'],
    'comment': notes_html,
}
if A.get('phone'):
    partner_vals['phone'] = A['phone']
if A.get('website'):
    partner_vals['website'] = A['website']
company.partner_id.write(partner_vals)
print("[onboard] Partner updated: %s · NIP %s · KRS %s · %s, %s %s · %s"
      % (A['name'], A['nip'], A['krs'], A['street'], A['zip'], A['city'], A['email']))

# Tax office (Urząd Skarbowy)
tax_office = env['l10n_pl.l10n_pl_tax_office'].search(
    [('code', '=', A['tax_office_code'])], limit=1)
if tax_office:
    company.l10n_pl_reports_tax_office_id = tax_office.id
    print("[onboard] US: %s %s" % (tax_office.code, tax_office.name))
else:
    print("[onboard] WARN: brak Urzędu Skarbowego o kodzie %s — pominięto"
          % A['tax_office_code'])

# Bank accounts
def upsert_bank(acc_number, label):
    if not acc_number:
        return
    Bank = env['res.partner.bank']
    existing = Bank.search(
        [('partner_id', '=', company.partner_id.id),
         ('acc_number', '=', acc_number)], limit=1)
    if existing:
        print("[onboard] %s już istnieje: %s" % (label, acc_number))
        return
    Bank.create({
        'partner_id': company.partner_id.id,
        'acc_number': acc_number,
        'company_id': company.id,
    })
    print("[onboard] %s dodany: %s" % (label, acc_number))

upsert_bank(A.get('iban'), 'IBAN główny')
upsert_bank(A.get('iban_vat'), 'Rachunek VAT (MPP)')

# KSeF mode
icp = env['ir.config_parameter'].sudo()
icp.set_param('l10n_pl_edi_ksef.mode', A['ksef_mode'])
print("[onboard] KSeF mode: %s" % A['ksef_mode'])

env.cr.commit()

# Final summary
print()
print("=" * 60)
print("[onboard] DONE — bazę %s zaktualizowano." % env.cr.dbname)
print("=" * 60)
print("  Nazwa:     %s" % company.name)
print("  NIP:       %s" % company.partner_id.vat)
print("  KRS:       %s" % company.partner_id.company_registry)
print("  Adres:     %s, %s %s, %s" % (
    company.partner_id.street, company.partner_id.zip,
    company.partner_id.city,
    company.partner_id.state_id.name if company.partner_id.state_id else '-'))
print("  Email:     %s" % company.partner_id.email)
print("  US:        %s" % (
    company.l10n_pl_reports_tax_office_id.code
    if company.l10n_pl_reports_tax_office_id else '-'))
print("  Waluta:    %s" % company.currency_id.name)
print("  KSeF mode: %s" % icp.get_param('l10n_pl_edi_ksef.mode'))
print()
"""


def apply_to_odoo(db_name: str, answers: dict) -> int:
    payload = json.dumps(answers, ensure_ascii=False)
    # Inject as a Python string literal so odoo shell can json.loads it
    script = ODOO_SHELL_SCRIPT.replace("__ANSWERS_JSON__", json.dumps(payload))
    repo_root = Path(__file__).resolve().parent.parent
    cmd = [
        "docker", "compose", "--env-file", ".env",
        "run", "--rm", "--no-deps", "-T", "odoo",
        "odoo", "shell", "-d", db_name, "--no-http",
    ]
    print(f"\n→ uruchamiam: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, input=script, text=True, cwd=repo_root)
    return result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Tax office lookup mode
# ─────────────────────────────────────────────────────────────────────────────

LIST_TAX_OFFICES_SCRIPT = """
# List all tax offices
offices = env['l10n_pl.l10n_pl_tax_office'].search([], order='code')
for o in offices:
    print('%s\\t%s' % (o.code, o.name))
"""


def list_tax_offices(db_name: str) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    cmd = [
        "docker", "compose", "--env-file", ".env",
        "run", "--rm", "--no-deps", "-T", "odoo",
        "odoo", "shell", "-d", db_name, "--no-http",
    ]
    result = subprocess.run(cmd, input=LIST_TAX_OFFICES_SCRIPT, text=True, cwd=repo_root)
    return result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Onboarding firmy sp. z o.o. w Odoo 19 (PL)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", required=True, help="Nazwa bazy Odoo (np. mnl_db)")
    parser.add_argument("--from-json", metavar="PATH",
                        help="Wczytaj odpowiedzi z pliku JSON (przed pytaniami; brakujące pola dopytane)")
    parser.add_argument("--save", metavar="PATH",
                        help="Zapisz odpowiedzi do pliku JSON dla powtarzalności")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Nie pytaj — użyj tylko --from-json (wymagane)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tylko pokaż odpowiedzi, nie zapisuj do bazy")
    parser.add_argument("--list-tax-offices", action="store_true",
                        help="Wypisz wszystkie kody Urzędów Skarbowych i wyjdź")
    args = parser.parse_args()

    if args.list_tax_offices:
        sys.exit(list_tax_offices(args.db))

    prefill = {}
    if args.from_json:
        prefill = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        print(f"  ✓  Wczytano konfigurację z {args.from_json}\n")

    if args.non_interactive:
        if not args.from_json:
            parser.error("--non-interactive wymaga --from-json")
        answers = prefill
    else:
        try:
            answers = gather_answers(args.db, prefill=prefill)
        except KeyboardInterrupt:
            print("\n\n  ✗  Przerwano przez użytkownika.")
            sys.exit(130)

    print("\n┌── Podsumowanie odpowiedzi ─────────────────────────")
    for key in ("name", "nip", "krs", "regon", "share_capital", "street",
                "zip", "city", "state_code", "tax_office_code",
                "email", "phone", "website", "iban", "iban_vat", "ksef_mode"):
        val = answers.get(key) or "—"
        print(f"  {key:<16} {val}")
    print("└" + "─" * 53)

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  ✓  zapisano odpowiedzi → {out}")

    if args.dry_run:
        print("\n  (dry-run — nic nie zapisano do bazy)")
        return

    if not args.non_interactive:
        if not ask_yes("\nAplikować te ustawienia do bazy?", default=True):
            print("  Anulowano.")
            return

    rc = apply_to_odoo(args.db, answers)
    sys.exit(rc)


if __name__ == "__main__":
    main()
