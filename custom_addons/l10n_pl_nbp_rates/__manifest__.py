{
    'name': 'Poland - NBP Exchange Rates',
    'version': '19.0.1.0.0',
    'summary': 'Automatic PLN exchange rates from Narodowy Bank Polski (NBP) Table A',
    'description': """
        Fetches mid-rates (Table A) from the National Bank of Poland (NBP) public API
        and updates res.currency.rate records daily.

        Source: https://static.nbp.pl/dane/kursy/xml/LastA.xml
        No API key required — the NBP XML feed is public.

        Ported and standalone-ified from OCA/l10n-poland 16.0 module
        currency_rate_update_nbp (AGPL-3).
        This version has no OCA dependency — uses a simple scheduled action.

        Rates are fetched for all active non-PLN currencies in the system.
        PLN is the base currency assumed (company currency = PLN).
    """,
    'category': 'Accounting/Localizations',
    'author': 'Polish sp. z o.o. Odoo Project',
    'license': 'LGPL-3',
    'depends': ['base', 'account'],
    'data': [
        'data/cron.xml',
    ],
    'external_dependencies': {
        'python': ['requests', 'lxml'],
    },
    'installable': True,
    'auto_install': False,
}
