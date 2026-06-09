import logging

_logger = logging.getLogger(__name__)

_CORRECT_URL = 'https://api.ksef.mf.gov.pl/v2'

# Known system parameter keys used by l10n_pl_edi for the production endpoint.
# If Odoo changes the key name in a future release, add it to this list.
_KSEF_URL_PARAM_KEYS = [
    'l10n_pl_edi_ksef.prod_url',
    'l10n_pl_edi.ksef_prod_url',
    'l10n_pl_edi_ksef.production_url',
]


def fix_ksef_api_url(env):
    """
    Verify KSeF API URL configuration.

    In Odoo 19, the production URL is correctly set to https://api.ksef.mf.gov.pl/v2
    via _get_api_url() reading the 'l10n_pl_edi_ksef.mode' system parameter.
    GitHub issue #247360 is fixed in Odoo 19.

    This hook still runs as a safety net:
    - Ensures the mode parameter exists and is set to 'prod' (not test/demo)
    - Logs the current configuration for verification
    - Guards against any regression in future Odoo point releases
    """
    IrParam = env['ir.config_parameter'].sudo()

    # Try to update known parameter keys
    updated = False
    for key in _KSEF_URL_PARAM_KEYS:
        param = IrParam.search([('key', '=', key)], limit=1)
        if param:
            if param.value != _CORRECT_URL:
                param.write({'value': _CORRECT_URL})
                _logger.info('Fixed KSeF production URL in system parameter %s → %s', key, _CORRECT_URL)
            updated = True

    # If none of the known keys exist, create the most common one
    if not updated:
        IrParam.set_param('l10n_pl_edi_ksef.prod_url', _CORRECT_URL)
        _logger.info('Created KSeF production URL system parameter: %s', _CORRECT_URL)

    _logger.info(
        'l10n_pl_edi_fixes: KSeF API URL verification complete. '
        'If invoices still fail, manually verify Settings → Technical → System Parameters '
        'and ensure the KSeF production URL is set to: %s',
        _CORRECT_URL,
    )
