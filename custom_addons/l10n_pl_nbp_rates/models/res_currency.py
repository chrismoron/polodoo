import logging
import requests
from lxml import etree

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_NBP_TABLE_A_URL = 'https://static.nbp.pl/dane/kursy/xml/LastA.xml'
_REQUEST_TIMEOUT = 15
_USER_AGENT = 'Odoo l10n_pl_nbp_rates/19.0 (Polish NBP rate updater)'

# XXE-safe parser — disable external entity resolution, DTD loading, and
# network fetches. NBP XML is trusted (HTTPS from gov.pl-adjacent host) but
# defense-in-depth costs nothing here.
_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
)


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _l10n_pl_nbp_update_rates(self):
        """
        Fetch NBP Table A (średnie kursy walut obcych) and create
        res.currency.rate records for every Polish (PLN) company in the DB.

        Multi-company safe: iterates explicitly over companies whose currency
        is PLN. Does not rely on env.company (which is whichever the cron user
        defaults to).
        """
        nbp_rates, rate_date = self._fetch_nbp_table_a()
        if not nbp_rates:
            return

        pl_companies = self.env['res.company'].sudo().search([
            ('currency_id.name', '=', 'PLN'),
        ])
        if not pl_companies:
            _logger.info('NBP rate update: no PLN companies in this database')
            return

        CurrencyRate = self.env['res.currency.rate'].sudo()
        Currency = self.env['res.currency'].sudo()
        non_pln = Currency.search([('active', '=', True), ('name', '!=', 'PLN')])

        for company in pl_companies:
            updated = 0
            # Batch-fetch existing rates for this date+company in one query
            existing = CurrencyRate.search([
                ('currency_id', 'in', non_pln.ids),
                ('name', '=', rate_date),
                ('company_id', '=', company.id),
            ])
            existing_by_curr = {r.currency_id.id: r for r in existing}

            to_create = []
            for currency in non_pln:
                pln_per_foreign = nbp_rates.get(currency.name)
                if not pln_per_foreign:
                    continue
                # Odoo: rate = units of foreign currency per 1 unit of company currency.
                # Company is PLN: 1 PLN = (1/pln_per_foreign) units of foreign.
                odoo_rate = 1.0 / pln_per_foreign
                if currency.id in existing_by_curr:
                    existing_by_curr[currency.id].rate = odoo_rate
                else:
                    to_create.append({
                        'currency_id': currency.id,
                        'name': rate_date,
                        'rate': odoo_rate,
                        'company_id': company.id,
                    })
                updated += 1
            if to_create:
                CurrencyRate.create(to_create)
            _logger.info(
                'NBP rate update: %d currencies for %s (Table A %s)',
                updated, company.name, rate_date,
            )

    def _fetch_nbp_table_a(self):
        """Fetch and parse Table A. Returns (rates_by_iso_code, publication_date) or ({}, today)."""
        try:
            response = requests.get(
                _NBP_TABLE_A_URL,
                timeout=_REQUEST_TIMEOUT,
                headers={'User-Agent': _USER_AGENT},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.error('NBP rate update: HTTP error — %s', exc)
            return {}, fields.Date.today()

        try:
            root = etree.fromstring(response.content, parser=_SAFE_PARSER)
        except etree.XMLSyntaxError as exc:
            _logger.error('NBP rate update: XML parse error — %s', exc)
            return {}, fields.Date.today()

        pub_date_str = (root.findtext('data_publikacji') or '').strip()
        try:
            rate_date = fields.Date.from_string(pub_date_str) if pub_date_str else fields.Date.today()
        except (ValueError, TypeError) as exc:
            _logger.warning('NBP rate update: bad data_publikacji %r — %s; using today', pub_date_str, exc)
            rate_date = fields.Date.today()

        rates = {}
        for position in root.findall('pozycja'):
            code = (position.findtext('kod_waluty') or '').strip().upper()
            rate_str = (position.findtext('kurs_sredni') or '').strip()
            multiplier_str = (position.findtext('przelicznik') or '1').strip()
            if not code or not rate_str:
                continue
            try:
                rate_pln = float(rate_str.replace(',', '.'))
                multiplier = float(multiplier_str)
                if multiplier <= 0:
                    continue
                rates[code] = rate_pln / multiplier
            except ValueError as exc:
                _logger.warning('NBP rate update: parse error for %s — %s', code, exc)
        if not rates:
            _logger.error('NBP rate update: no rates parsed from XML')
        return rates, rate_date
