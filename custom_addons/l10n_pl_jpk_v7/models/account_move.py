from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_pl_jpk_tag = fields.Selection([
        ('ksef', 'NrKSeF — KSeF invoice number (default)'),
        ('OFF',  'OFF — Issued during KSeF system failure'),
        ('BFK',  'BFK — Issued outside KSeF under valid exemption'),
        ('DI',   'DI — Document other than invoice / offline without KSeF'),
    ], string='JPK_V7 Tag',
       default='ksef',
       help=(
           'Determines the KSeF reference field in JPK_V7M(3) Ewidencja. '
           'Required from February 1, 2026. '
           'Use OFF/BFK/DI only when the invoice has no KSeF number.'
       ))
