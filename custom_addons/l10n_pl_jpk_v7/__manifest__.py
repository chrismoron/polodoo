{
    'name': 'Poland - JPK_V7M/V7K Generator',
    'version': '19.0.1.0.0',
    'summary': 'Generate JPK_V7M(3) and JPK_V7K(3) XML files for Polish VAT reporting',
    'description': """
        Generates JPK_V7M(3) (monthly) and JPK_V7K(3) (quarterly) XML files per the
        Ministerstwo Finansów schema effective February 1, 2026.

        The JPK_V7(3) schema requires each invoice record to include either:
          - NrKSeF — the KSeF invoice number (from l10n_pl_edi)
          - OFF tag — invoice issued during KSeF system failure
          - BFK tag — invoice issued outside KSeF under valid exemption
          - DI  tag — documents other than invoices, offline invoices

        What it generates:
          - Nagłówek    (header: period, generation timestamp, system name)
          - Podmiot1    (entity: NIP, name, address)
          - Ewidencja   (VAT register: SprzedazWiersz + ZakupWiersz + controls)
          - Deklaracja  (VAT declaration: P_10 through P_68 summary fields)

        Submissions to the Ministry of Finance via the e-Deklaracje portal
        (https://www.podatki.gov.pl/e-deklaracje/) require a Podpis Zaufany or
        qualified electronic signature. This module generates the XML file only —
        submission via Trilab JPK Transfer or manually via e-Deklaracje portal.

        Tax tag mapping assumes the standard l10n_pl account tags.
        See models/l10n_pl_jpk_v7.py _TAG_TO_K_FIELD for the mapping.
        Verify the mapping after installing l10n_pl by checking:
          Settings → Technical → Accounting → Account Tags (filter: country=Poland)

        LIMITATIONS (known gaps, contributions welcome):
        - JPK_V7K (quarterly): period aggregation is implemented but
          quarterly declaration fields may need additional configuration.
        - Manual OFF/BFK/DI tags on individual invoices require the
          l10n_pl_jpk_v7_tag field to be set on account.move.
        - Complex transactions (OSS, WNT, import) may need manual tag review.
    """,
    'category': 'Accounting/Localizations',
    'author': 'Polish sp. z o.o. Odoo Project',
    'license': 'LGPL-3',
    'depends': ['l10n_pl', 'account', 'l10n_pl_edi_fixes'],
    'data': [
        'security/ir.model.access.csv',
        'views/l10n_pl_jpk_v7_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
