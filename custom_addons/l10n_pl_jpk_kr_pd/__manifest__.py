{
    'name': 'Poland - JPK_KR_PD (JPK_CIT) Generator',
    'version': '19.0.1.0.0',
    'summary': 'JPK_KR_PD(1) and JPK_ST_KR(1) XML for Polish CIT SAF-T',
    'description': """
        JPK_KR_PD (Jednolity Plik Kontrolny Ksiąg Rachunkowych — Podatki Dochodowe)
        is the annual Corporate Income Tax SAF-T file required from:

          • 2026-07-31 — large CIT taxpayers (revenue > EUR 50M) for tax year 2024
          • 2027-07-31 — other CIT taxpayers also submitting JPK_V7M (typical sp. z o.o.)
          • 2028-07-31 — remaining CIT taxpayers

        Companion: JPK_ST_KR(1) — fixed assets register.

        Schema (verified 2026-06-09 against MF XSD):
          JPK_KR_PD(1)  namespace: http://jpk.mf.gov.pl/wzor/2024/09/04/09041/
          JPK_ST_KR(1)  namespace: http://jpk.mf.gov.pl/wzor/2024/04/24/04242/
          Version:      wersjaSchemy "1-1" (XSD fixed)
          kodSystemowy: "JPK_KR_PD (1)"
          Embedded:     schemas/jpk_kr_pd.xsd, schemas/jpk_st_kr.xsd

        IMPLEMENTED — Full XML generation:
          • Naglowek with kodSystemowy + wersjaSchemy 1-1
          • Podmiot1 with NIP + REGON + IdentyfikatorPodmiotu + Address
            (AdresPol with KodKraju/Wojewodztwo/Powiat/Gmina/Miejscowosc/KodPocztowy NN-NNN,
             or AdresZagr for foreign companies)
          • Kontrahent×N for partners appearing in the period (T_1=ref, T_2=country, T_3=TIN)
          • ZOiS — one ZOiS<n> per active account.account, with:
              - S_1=code, S_2=name, S_3=parent
              - S_4/S_5 opening Dr/Cr from fiscal-year-start
              - S_6/S_7 period Dr/Cr
              - S_8/S_9 YTD Dr/Cr
              - S_10/S_11 closing Dr/Cr (auto-computed)
              - S_12_1/S_12_2/S_12_3 markers (optional in ZOiS8, required in ZOiS7)
          • Dziennik — one element per account.move (D_1..D_12 + KontoZapis*)
          • KontoZapis — one element per account.move.line (Z_1..Z_9 choice Dr/Cr)
          • Ctrl — C_1 (move count), C_2 (move total), C_3 (line count), C_4 (Σdebit), C_5 (Σcredit)
          • RPD — 8 K_* income-tax reconciliation fields:
              - K_1/K_2/K_4/K_5 auto-computed from account.account.l10n_pl_pd_marker
              - K_3/K_6/K_7/K_8 from wizard manual inputs

        Defaults to ZOiS8 (IFRS variant) where statutory balance-sheet markers
        S_12_1/S_12_2 are OPTIONAL — this lets the file validate without
        pre-mapping ~600 statutory markers per account. Switch to ZOiS7 and
        populate l10n_pl_zois_marker_1 on each account when ready.

        Reference: https://www.gov.pl/web/kas/struktury-jpk-w-podatkach-dochodowych
    """,
    'category': 'Accounting/Localizations',
    'author': 'Polish sp. z o.o. Odoo Project',
    'license': 'LGPL-3',
    'depends': ['l10n_pl', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/l10n_pl_jpk_kr_pd_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
