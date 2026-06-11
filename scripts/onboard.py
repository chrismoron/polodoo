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


def validate_pkd(s: str) -> str:
    """PKD 2007 format: NN.NN.X (np. 21.20.Z)."""
    s = s.strip().upper().replace(" ", "")
    if not re.fullmatch(r"\d{2}\.\d{2}\.[A-Z]", s):
        raise ValueError("Kod PKD musi mieć format NN.NN.X (np. 21.20.Z)")
    return s


def validate_journal_code(s: str) -> str:
    s = s.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", s):
        raise ValueError("Kod dziennika: 2-5 znaków, wielkie litery/cyfry (np. FV, FZ, FK)")
    return s


def validate_iso_date(s: str) -> str:
    s = s.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError("Data musi być w formacie RRRR-MM-DD (np. 2026-01-01)")
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Polish bank codes (NRB-4 = first 4 of the 8-digit routing portion of IBAN)
# Source: NBP "Wykaz banków" + KIR clearing system. Only majors covered;
# unknown codes return None (don't block the IBAN — user can still proceed).
# ─────────────────────────────────────────────────────────────────────────────

POLISH_BANKS: dict[str, str] = {
    "1010": "NBP — Narodowy Bank Polski",
    "1020": "PKO Bank Polski",
    "1030": "Citi Handlowy",
    "1050": "ING Bank Śląski",
    "1090": "Santander Bank Polska",
    "1130": "BGK — Bank Gospodarstwa Krajowego",
    "1140": "mBank",
    "1160": "Bank Millennium",
    "1240": "Bank Pekao SA",
    "1320": "Bank Pocztowy",
    "1480": "Deutsche Bank Polska",
    "1540": "BOŚ — Bank Ochrony Środowiska",
    "1560": "Citibank Europe",
    "1610": "SGB-Bank",
    "1680": "Plus Bank",
    "1750": "BNP Paribas Bank Polska",
    "1840": "Krakowski Bank Spółdzielczy",
    "1870": "Nest Bank",
    "1930": "Bank Polskiej Spółdzielczości",
    "2030": "BNP Paribas Bank Polska (ex BGŻ)",
    "2120": "Santander Consumer Bank",
    "2160": "Toyota Bank Polska",
    "2480": "Getin Noble Bank",
    "2490": "Alior Bank",
    "2700": "Volkswagen Bank Polska",
    "2710": "Mercedes-Benz Bank Polska",
    "2790": "Aion Bank",
    "1010": "NBP — Narodowy Bank Polski",  # safety duplicate; no harm
}


def lookup_bank_pl(iban: str) -> tuple[str, str] | None:
    """Return (bank_code_4, bank_name) for a validated Polish IBAN, or None."""
    digits = re.sub(r"\D", "", iban.replace("PL", "", 1))
    if len(digits) < 6:  # 2 check + 4 bank
        return None
    bank_code = digits[2:6]
    name = POLISH_BANKS.get(bank_code)
    return (bank_code, name) if name else None


# ─────────────────────────────────────────────────────────────────────────────
# ZIP prefix → suggested US (Urząd Skarbowy) codes
# First 2 digits of postal code → list of [(US code, US name)] most likely.
# This is a hint table — user can always override or list all via `--list-tax-offices`.
# Coverage: largest cities + Warsaw region (where MNL/Bioleaf are based).
# ─────────────────────────────────────────────────────────────────────────────

ZIP_PREFIX_HINTS: dict[str, list[tuple[str, str]]] = {
    "00": [("1471", "US Warszawa-Śródmieście"), ("1437", "US Warszawa-Mokotów")],
    "01": [("1448", "US Warszawa-Wola"), ("1428", "US Warszawa-Bemowo")],
    "02": [("1437", "US Warszawa-Mokotów"), ("1438", "US Warszawa-Ursynów")],
    "03": [("1419", "US Warszawa-Praga"), ("1437", "US Warszawa-Targówek")],
    "04": [("1429", "US Warszawa-Wawer"), ("1419", "US Warszawa-Praga-Pd.")],
    "05": [("1442", "US Wołomin"), ("1409", "US Legionowo"),
           ("1414", "US Nowy Dwór Mazowiecki"), ("1431", "US Pruszków")],
    "06": [("1403", "US Ciechanów")],
    "07": [("1415", "US Ostrołęka"), ("1411", "US Maków Mazowiecki")],
    "08": [("1432", "US Siedlce"), ("1410", "US Łosice"), ("1412", "US Mińsk Mazowiecki")],
    "09": [("1421", "US Płock"), ("1413", "US Mława")],
    # Łódzkie
    "90": [("1023", "US Łódź-Śródmieście"), ("1024", "US Łódź-Bałuty")],
    "91": [("1024", "US Łódź-Bałuty"), ("1023", "US Łódź-Polesie")],
    "92": [("1025", "US Łódź-Widzew")],
    "93": [("1026", "US Łódź-Górna")],
    "94": [("1023", "US Łódź-Polesie")],
    "95": [("1019", "US Pabianice"), ("1020", "US Zgierz")],
    # Małopolskie
    "30": [("1216", "US Kraków-Stare Miasto"), ("1213", "US Kraków-Krowodrza"),
           ("1214", "US Kraków-Nowa Huta"), ("1215", "US Kraków-Podgórze"),
           ("1217", "US Kraków-Śródmieście"), ("1218", "US Kraków-Prądnik")],
    "31": [("1216", "US Kraków-Stare Miasto")],
    "32": [("1218", "US Kraków-Prądnik"), ("1209", "US Olkusz"),
           ("1211", "US Chrzanów"), ("1210", "US Oświęcim")],
    "33": [("1207", "US Nowy Sącz"), ("1208", "US Nowy Targ"), ("1219", "US Tarnów")],
    "34": [("1207", "US Nowy Sącz"), ("1208", "US Nowy Targ"), ("1212", "US Sucha Beskidzka")],
    # Pomorskie
    "80": [("2202", "US Gdańsk-Wrzeszcz"), ("2204", "US Gdańsk-Oliwa"), ("2203", "US Gdańsk-Śródmieście")],
    "81": [("2205", "US Gdynia")],
    "82": [("2208", "US Kwidzyn"), ("2210", "US Malbork")],
    "83": [("2207", "US Kościerzyna"), ("2211", "US Starogard Gdański")],
    "84": [("2214", "US Wejherowo"), ("2206", "US Kartuzy")],
    # Wielkopolskie
    "60": [("3013", "US Poznań-Grunwald"), ("3014", "US Poznań-Jeżyce"),
           ("3015", "US Poznań-Nowe Miasto"), ("3016", "US Poznań-Stare Miasto"),
           ("3017", "US Poznań-Wilda")],
    "61": [("3013", "US Poznań-Grunwald"), ("3016", "US Poznań-Stare Miasto")],
    "62": [("3018", "US Poznań-Winogrady")],
    # Dolnośląskie
    "50": [("0223", "US Wrocław-Śródmieście"), ("0224", "US Wrocław-Krzyki"),
           ("0225", "US Wrocław-Fabryczna"), ("0226", "US Wrocław-Psie Pole"),
           ("0227", "US Wrocław-Stare Miasto")],
    "51": [("0226", "US Wrocław-Psie Pole")],
    "52": [("0227", "US Wrocław-Stare Miasto")],
    "53": [("0224", "US Wrocław-Krzyki")],
    "54": [("0225", "US Wrocław-Fabryczna")],
    # Śląskie
    "40": [("2425", "US Katowice"), ("2419", "US Chorzów")],
    "41": [("2406", "US Bytom"), ("2426", "US Mysłowice"), ("2435", "US Tychy"),
           ("2429", "US Ruda Śląska"), ("2432", "US Siemianowice Śląskie")],
    "42": [("2421", "US Częstochowa")],
    "43": [("2402", "US Bielsko-Biała"), ("2415", "US Cieszyn")],
    "44": [("2422", "US Gliwice"), ("2436", "US Zabrze"), ("2424", "US Jastrzębie-Zdrój"),
           ("2428", "US Rybnik")],
    # Zachodniopomorskie
    "70": [("3208", "US Szczecin-Centrum"), ("3209", "US Szczecin-Śródmieście"),
           ("3210", "US Szczecin-Zachód"), ("3211", "US Szczecin-Prawobrzeże")],
    "71": [("3208", "US Szczecin-Centrum")],
    "72": [("3205", "US Police"), ("3204", "US Goleniów")],
    # Lubelskie
    "20": [("0617", "US Lublin"), ("0619", "US Lublin Pierwszy")],
    "21": [("0617", "US Lublin")],
    "22": [("0620", "US Łuków"), ("0610", "US Hrubieszów"), ("0625", "US Zamość")],
    "23": [("0616", "US Łęczna"), ("0614", "US Kraśnik")],
    # Podkarpackie
    "35": [("1818", "US Rzeszów")],
    "36": [("1818", "US Rzeszów")],
    "37": [("1819", "US Stalowa Wola"), ("1820", "US Tarnobrzeg")],
    "38": [("1811", "US Krosno"), ("1804", "US Jasło")],
    "39": [("1816", "US Mielec"), ("1814", "US Łańcut")],
    # Świętokrzyskie
    "25": [("2604", "US Kielce")],
    "26": [("2604", "US Kielce")],
    "27": [("2607", "US Ostrowiec Świętokrzyski")],
    "28": [("2608", "US Sandomierz")],
    # Lubuskie
    "65": [("0807", "US Zielona Góra")],
    "66": [("0807", "US Zielona Góra"), ("0802", "US Gorzów Wielkopolski")],
    "67": [("0803", "US Krosno Odrzańskie"), ("0808", "US Żary")],
    "68": [("0805", "US Nowa Sól"), ("0806", "US Świebodzin")],
    # Warmińsko-mazurskie
    "10": [("2802", "US Olsztyn")],
    "11": [("2807", "US Mrągowo"), ("2806", "US Kętrzyn")],
    "12": [("2803", "US Działdowo"), ("2811", "US Nidzica")],
    "13": [("2812", "US Iława"), ("2804", "US Elbląg")],
    "14": [("2804", "US Elbląg"), ("2814", "US Ostróda")],
    "16": [("2805", "US Giżycko"), ("2809", "US Pisz")],
    # Podlaskie
    "15": [("2002", "US Białystok")],
    "16": [("2002", "US Białystok"), ("2007", "US Suwałki")],
    "17": [("2003", "US Bielsk Podlaski"), ("2005", "US Łomża")],
    "18": [("2005", "US Łomża"), ("2008", "US Wysokie Mazowieckie")],
    "19": [("2004", "US Hajnówka"), ("2006", "US Sokółka")],
    # Kujawsko-pomorskie
    "85": [("0412", "US Bydgoszcz"), ("0421", "US Toruń")],
    "86": [("0413", "US Chełmno"), ("0421", "US Toruń")],
    "87": [("0421", "US Toruń"), ("0417", "US Inowrocław")],
    "88": [("0419", "US Mogilno"), ("0420", "US Nakło nad Notecią")],
    "89": [("0412", "US Bydgoszcz")],
    # Opolskie
    "45": [("1610", "US Opole")],
    "46": [("1602", "US Brzeg"), ("1604", "US Kędzierzyn-Koźle")],
    "47": [("1611", "US Prudnik"), ("1605", "US Kluczbork")],
    "48": [("1603", "US Głubczyce"), ("1612", "US Strzelce Opolskie")],
    "49": [("1607", "US Krapkowice"), ("1606", "US Nysa")],
}


def suggest_us_codes(zip_code: str) -> list[tuple[str, str]]:
    """Return list of (us_code, us_name) suggested for the given ZIP NN-NNN."""
    if not zip_code or len(zip_code) < 2:
        return []
    return ZIP_PREFIX_HINTS.get(zip_code[:2], [])


def read_opening_csv(path_str: str) -> list[dict]:
    """Parse a bilans-otwarcia CSV with columns account_code,debit,credit[,name].

    - Header row required (case-insensitive, in any column order)
    - Empty cells treated as 0
    - debit and credit must be numeric; each row must have exactly one non-zero
    - Total debit must equal total credit (tolerance 0.01)
    Returns list of dicts: {account_code, debit, credit, name}.
    """
    import csv
    path = Path(path_str).expanduser()
    if not path.is_file():
        raise SystemExit(f"  ✗  Plik CSV nie istnieje: {path}")
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
        for required in ("account_code", "debit", "credit"):
            if required not in cols:
                raise SystemExit(
                    f"  ✗  Brak kolumny '{required}' w {path}. "
                    f"Wymagane: account_code,debit,credit[,name]"
                )
        name_col = cols.get("name")
        for i, row in enumerate(reader, start=2):  # row 1 is header
            code = (row[cols["account_code"]] or "").strip()
            if not code:
                continue  # skip blank rows
            try:
                debit = float(str(row[cols["debit"]] or "0").replace(",", ".") or 0)
                credit = float(str(row[cols["credit"]] or "0").replace(",", ".") or 0)
            except ValueError:
                raise SystemExit(f"  ✗  Wiersz {i}: debit/credit musi być liczbą")
            if debit and credit:
                raise SystemExit(
                    f"  ✗  Wiersz {i} (konto {code}): tylko jedno z debit/credit "
                    f"może być wypełnione"
                )
            rows.append({
                "account_code": code,
                "debit": round(debit, 2),
                "credit": round(credit, 2),
                "name": (row[name_col].strip() if name_col else "") if name_col else "",
            })
    total_d = sum(r["debit"] for r in rows)
    total_c = sum(r["credit"] for r in rows)
    if abs(total_d - total_c) > 0.01:
        raise SystemExit(
            f"  ✗  Bilans niezbilansowany: Dr={total_d:.2f} ≠ Cr={total_c:.2f} "
            f"(różnica {total_d - total_c:+.2f} PLN)"
        )
    print(f"  ✓  Bilans zbilansowany: Dr=Cr={total_d:.2f} PLN")
    return rows


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


def ask_pkd_list(primary_default=None, secondary_default=None):
    """Ask for primary + optional secondary PKD codes."""
    primary = ask(
        "PKD główne (np. 21.20.Z dla farmaceutyków)",
        default=primary_default, validator=validate_pkd,
    )
    secondary = list(secondary_default or [])
    print(f"    PKD dodatkowe: {len(secondary)} kodów"
          + (f" ({', '.join(secondary)})" if secondary else ""))
    if ask_yes("Dodać/zmienić PKD dodatkowe?", default=False):
        secondary = []
        print("    Wprowadzaj kolejne kody PKD — pusta linia kończy.")
        while True:
            v = input("    PKD dodatkowe: ").strip()
            if not v:
                break
            try:
                secondary.append(validate_pkd(v))
            except ValueError as e:
                print(f"    ⚠  {e}")
    return primary, secondary


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
    hints = suggest_us_codes(zip_code)
    if hints:
        print(f"    Sugestie na podstawie kodu {zip_code[:2]}-XXX:")
        for code, name in hints:
            print(f"      {code}  {name}")
    print("    Pełna lista: ./scripts/onboard.py --list-tax-offices --db", db_name)
    default_us = p.get("tax_office_code") or (hints[0][0] if hints else None)
    tax_office_code = ask("Kod US (4 cyfry, np. 1442 = Wołomin)",
                          default=default_us,
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
        bank_info = lookup_bank_pl(iban)
        if bank_info:
            print(f"    ✓  Bank rozpoznany: {bank_info[0]} → {bank_info[1]}")
        else:
            bank_code = re.sub(r"\D", "", iban.replace("PL", "", 1))[2:6]
            print(f"    ⚠  Bank o kodzie {bank_code} nie ma mapowania w skrypcie "
                  f"(lista NBP banków: nbp.pl/home.aspx?f=/statystyka/bilansowe/bilansowe_n.html)")
        iban_vat = ask("Rachunek VAT do MPP (opcjonalnie)",
                       default=p.get("iban_vat"), validator=validate_iban_pl,
                       required=False)
        if iban_vat:
            vat_bank_info = lookup_bank_pl(iban_vat)
            if vat_bank_info and bank_info and vat_bank_info[0] != bank_info[0]:
                print(f"    ⚠  Rachunek VAT jest w innym banku ({vat_bank_info[1]}) "
                      f"niż główny ({bank_info[1]}) — to nietypowe, sprawdź")

    print("\n┌── 6. KSeF ─────────────────────────────────────────")
    if p.get("ksef_mode"):
        ksef_mode = p["ksef_mode"]
        print(f"    Tryb: {ksef_mode} (z konfiguracji)")
    else:
        ksef_mode = ask_ksef_mode()

    print("\n┌── 7. PKD (klasyfikacja działalności) ──────────────")
    pkd_primary, pkd_secondary = ask_pkd_list(
        primary_default=p.get("pkd_primary"),
        secondary_default=p.get("pkd_secondary"),
    )

    print("\n┌── 8. Numeracja faktur ─────────────────────────────")
    print("    Kody dzienników (prefix przed numerem faktury):")
    print("      Sprzedaż: FV  →  FV/2026/06/0001")
    print("      Zakup:    FZ  →  FZ/2026/06/0001")
    print("      Korekty:  FK  →  FK/2026/06/0001")
    journal_sale_code = ask(
        "Kod dziennika sprzedażowego",
        default=p.get("journal_sale_code") or "FV",
        validator=validate_journal_code,
    )
    journal_purchase_code = ask(
        "Kod dziennika zakupowego",
        default=p.get("journal_purchase_code") or "FZ",
        validator=validate_journal_code,
    )

    print("\n┌── 9. Bilans otwarcia ──────────────────────────────")
    print("    Można zaimportować z CSV (kolumny: account_code,debit,credit[,name])")
    print("    albo zostawić pusty szkielet do uzupełnienia w UI.")
    opening_date = ""
    opening_lines: list[dict] = []
    opening_csv = ""
    if ask_yes("Utworzyć bilans otwarcia?", default=False):
        opening_date = ask(
            "Data otwarcia (RRRR-MM-DD)",
            default=p.get("opening_date") or "2026-01-01",
            validator=validate_iso_date,
        )
        default_csv = p.get("opening_csv") or ""
        opening_csv = ask("Plik CSV (ścieżka, Enter = pusty szkielet)",
                          default=default_csv, required=False)
        if opening_csv:
            opening_lines = read_opening_csv(opening_csv)
            print(f"    ✓  Wczytano {len(opening_lines)} linii z {opening_csv}")

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
        "pkd_primary": pkd_primary,
        "pkd_secondary": pkd_secondary,
        "journal_sale_code": journal_sale_code,
        "journal_purchase_code": journal_purchase_code,
        "opening_date": opening_date,
        "opening_csv": opening_csv,
        "opening_lines": opening_lines,
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
notes_lines.append('US: kod %s' % A['tax_office_code'])
if A.get('pkd_primary'):
    notes_lines.append('<br/>PKD główne: %s' % A['pkd_primary'])
if A.get('pkd_secondary'):
    notes_lines.append('<br/>PKD dodatkowe: %s' % ', '.join(A['pkd_secondary']))
notes_lines.append('</p>')
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

# Section 8: Journal codes for invoice numbering (FV/FZ prefixes)
def set_journal_code(journal_type, new_code, label):
    if not new_code:
        return
    journal = env['account.journal'].search(
        [('type', '=', journal_type), ('company_id', '=', company.id)], limit=1)
    if not journal:
        print("[onboard] WARN: brak dziennika typu %s" % journal_type)
        return
    if journal.code == new_code:
        print("[onboard] Dziennik %s już ma kod %s" % (label, new_code))
        return
    # If posted entries exist with old code, only update the journal label;
    # numeracja faktyczna pójdzie od pierwszej nowej faktury.
    posted = env['account.move'].search_count(
        [('journal_id', '=', journal.id), ('state', '=', 'posted')])
    if posted:
        print("[onboard] WARN: dziennik %s ma %d zaksięgowanych zapisów — zmieniam tylko kod, "
              "stare numery zostaną" % (label, posted))
    journal.write({'code': new_code})
    print("[onboard] Dziennik %s: kod %s (poprzedni → nowy)" % (label, new_code))

set_journal_code('sale', A.get('journal_sale_code'), 'sprzedaży')
set_journal_code('purchase', A.get('journal_purchase_code'), 'zakupu')

# Section 9: Opening balance — scaffold + optional CSV import
opening_date = A.get('opening_date')
opening_lines = A.get('opening_lines') or []
if opening_date:
    bo_year = opening_date[:4]
    bo_name = 'Bilans Otwarcia %s' % bo_year
    misc_journal = env['account.journal'].search(
        [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
    if not misc_journal:
        print("[onboard] WARN: brak dziennika 'general' — bilans otwarcia pominięty")
    else:
        existing = env['account.move'].search([
            ('journal_id', '=', misc_journal.id),
            ('ref', '=', bo_name),
            ('company_id', '=', company.id),
        ], limit=1)

        if existing and existing.state == 'posted':
            print("[onboard] %s już istnieje i jest zaksięgowany (id=%s) — pomijam"
                  % (bo_name, existing.id))
            move = existing
        else:
            if existing:
                # Draft exists — clear its lines so we can re-import idempotently
                if existing.line_ids:
                    print("[onboard] %s istnieje jako draft (id=%s) — czyszczę "
                          "%d istniejących linii dla re-importu"
                          % (bo_name, existing.id, len(existing.line_ids)))
                    existing.line_ids.unlink()
                move = existing
            else:
                move = env['account.move'].create({
                    'journal_id': misc_journal.id,
                    'date': opening_date,
                    'ref': bo_name,
                    'move_type': 'entry',
                    'company_id': company.id,
                })
                print("[onboard] Utworzono: %s (id=%s, journal=%s, date=%s)"
                      % (bo_name, move.id, misc_journal.name, opening_date))

            if opening_lines:
                # Lookup accounts by code
                codes = sorted({ln['account_code'] for ln in opening_lines})
                accounts = env['account.account'].search([
                    ('code', 'in', codes), ('company_ids', 'in', company.id),
                ])
                if not accounts:
                    # Fallback: search without company filter (older API)
                    accounts = env['account.account'].search([('code', 'in', codes)])
                code_map = {a.code: a.id for a in accounts}
                missing = [c for c in codes if c not in code_map]
                if missing:
                    print("[onboard] BŁĄD: brak kont w planie kont: %s"
                          % ', '.join(missing))
                    print("[onboard] Bilans otwarcia NIE został wprowadzony")
                else:
                    line_vals = []
                    for ln in opening_lines:
                        line_vals.append((0, 0, {
                            'account_id': code_map[ln['account_code']],
                            'debit': ln['debit'],
                            'credit': ln['credit'],
                            'name': ln.get('name') or bo_name,
                        }))
                    move.write({'line_ids': line_vals})
                    total_d = sum(ln['debit'] for ln in opening_lines)
                    total_c = sum(ln['credit'] for ln in opening_lines)
                    print("[onboard] Bilans otwarcia: %d linii zapisanych "
                          "(Dr=Cr=%.2f PLN)" % (len(opening_lines), total_d))
            else:
                print("[onboard]   → uzupełnij linie w UI: Księgowość → "
                      "Operacje różne → " + bo_name)

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
sale_j = env['account.journal'].search(
    [('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
purchase_j = env['account.journal'].search(
    [('type', '=', 'purchase'), ('company_id', '=', company.id)], limit=1)
print("  Dz. sprz.: %s" % (sale_j.code if sale_j else '-'))
print("  Dz. zak.:  %s" % (purchase_j.code if purchase_j else '-'))
if A.get('opening_date'):
    print("  Bilans otw.: %s" % A['opening_date'])
if A.get('pkd_primary'):
    print("  PKD:       %s%s" % (
        A['pkd_primary'],
        (' (+ %d dodatkowych)' % len(A['pkd_secondary'])) if A.get('pkd_secondary') else ''))
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
    parser.add_argument("--opening-csv", metavar="PATH",
                        help="Plik CSV bilansu otwarcia (account_code,debit,credit[,name]); "
                             "nadpisuje opening_csv z konfiguracji")
    args = parser.parse_args()

    if args.list_tax_offices:
        sys.exit(list_tax_offices(args.db))

    prefill = {}
    if args.from_json:
        prefill = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        print(f"  ✓  Wczytano konfigurację z {args.from_json}\n")

    if args.opening_csv:
        prefill["opening_csv"] = args.opening_csv

    if args.non_interactive:
        if not args.from_json:
            parser.error("--non-interactive wymaga --from-json")
        answers = prefill
        # Even in non-interactive mode, load CSV from path if provided
        csv_path = answers.get("opening_csv")
        if csv_path and not answers.get("opening_lines"):
            answers["opening_lines"] = read_opening_csv(csv_path)
    else:
        try:
            answers = gather_answers(args.db, prefill=prefill)
        except KeyboardInterrupt:
            print("\n\n  ✗  Przerwano przez użytkownika.")
            sys.exit(130)

    print("\n┌── Podsumowanie odpowiedzi ─────────────────────────")
    for key in ("name", "nip", "krs", "regon", "share_capital", "street",
                "zip", "city", "state_code", "tax_office_code",
                "email", "phone", "website", "iban", "iban_vat", "ksef_mode",
                "pkd_primary", "pkd_secondary",
                "journal_sale_code", "journal_purchase_code",
                "opening_date", "opening_csv"):
        val = answers.get(key)
        if isinstance(val, list):
            val = ", ".join(val) if val else "—"
        elif not val:
            val = "—"
        print(f"  {key:<22} {val}")
    if answers.get("opening_lines"):
        print(f"  {'opening_lines':<22} {len(answers['opening_lines'])} pozycji "
              f"(Dr=Cr={sum(l['debit'] for l in answers['opening_lines']):.2f} PLN)")
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
