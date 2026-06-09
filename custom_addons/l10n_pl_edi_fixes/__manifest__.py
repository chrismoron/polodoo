{
    'name': 'Poland - KSeF / l10n_pl_edi Compliance Fixes',
    'version': '19.0.1.0.0',
    'summary': 'Patches missing compliance fields in the official l10n_pl_edi module',
    'description': """
        Fills gaps in Odoo 19 CE l10n_pl_edi that prevent full KSeF FA(3) compliance:

        1. GTU commodity codes in FA(3) invoice line XML (P_106)
           l10n_pl stores GTU on the product but l10n_pl_edi never outputs P_106 in FaWiersz.

        2. MPP (Mechanizm Podzielonej Płatności / Split Payment) flag
           P_18A is hardcoded to 2 (No) in l10n_pl_edi.
           This module adds a per-invoice boolean and wires it into FA(3) XML.

        3. VAT exemption legal basis (P_19a / P_19b / P_19c)
           Hardcoded as "no exempt items" in l10n_pl_edi.
           This module adds a selection field for the legal basis of VAT exemption.

        4. KSeF production API URL fix (GitHub issue #247360)
           The decommissioned URL https://ksef.mf.gov.pl/api/v2 is replaced with
           the correct https://api.ksef.mf.gov.pl/v2 via system parameter at install.

        Note: Items 1-3 require the FA(3) XML template to be extended.
        See models/account_move.py for the override method.
        The FA(3) template override uses _l10n_pl_edi_get_invoice_vals() if available,
        otherwise falls back to setting values via field only (UI visible, XML pending).
    """,
    'category': 'Accounting/Localizations',
    'author': 'Polish sp. z o.o. Odoo Project',
    'license': 'LGPL-3',
    'depends': ['l10n_pl_edi'],
    'data': [
        'data/ksef_config.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'post_init_hook': 'fix_ksef_api_url',
}
