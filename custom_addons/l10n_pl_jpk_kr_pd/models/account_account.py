"""
Account.account extensions for JPK_KR_PD markers (Znaczniki księgowe).

Per JPK_KR_PD(1) schema, each ZOiS row may carry up to three markers:
  S_12_1  — primary statutory balance-sheet position tag
  S_12_2  — secondary tag (optional)
  S_12_3  — PD (podatek dochodowy) reconciliation bucket

For ZOiS8 (IFRS / simplified) all three are optional.
For ZOiS7 (standard Polish CoA) S_12_1 is required per account.

The full enumerations (TMapKontaPOZ ~600 values, TMapKontaPD ~24 values)
are not pre-loaded — they are stored as free-form Char fields so the
accountant can populate from the XSD. A future revision can convert to
Selection with full enumerations from data/zois_markers.xml.
"""
from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_pl_zois_marker_1 = fields.Char(
        string='ZOiS Marker (S_12_1)',
        help='Primary balance-sheet position tag. Examples: A_I_1, B_II_2, '
             'P_A_I_1. See XSD tns:TMapKontaPOZ enumeration in '
             'schemas/jpk_kr_pd.xsd lines 5569-6795.',
    )
    l10n_pl_zois_marker_2 = fields.Char(
        string='ZOiS Marker (S_12_2)',
        help='Secondary balance-sheet tag, optional. Same enumeration as S_12_1.',
    )
    l10n_pl_pd_marker = fields.Selection([
        ('PD1', 'PD1 — Revenue exempt from tax (permanent diff)'),
        ('PD1_1', 'PD1_1 — Revenue exempt subtype 1'),
        ('PD1_2', 'PD1_2 — Revenue exempt subtype 2'),
        ('PD1_3', 'PD1_3 — Revenue exempt subtype 3'),
        ('PD2', 'PD2 — Non-taxable revenue in current year'),
        ('PD4', 'PD4 — Non-deductible costs (permanent diff)'),
        ('PD4_1', 'PD4_1 — Non-deductible costs subtype 1'),
        ('PD4_2', 'PD4_2 — Non-deductible costs subtype 2'),
        ('PD4_3', 'PD4_3 — Non-deductible costs subtype 3'),
        ('PD5', 'PD5 — Costs not recognised this year'),
        ('PD7', 'PD7 — Other tax adjustment 7'),
        ('PD8_1', 'PD8_1 — Other tax adjustment 8.1'),
        ('PD8_2', 'PD8_2 — Other tax adjustment 8.2'),
        ('PD1_PB', 'PD1_PB — Off-balance variant of PD1'),
        ('PD2_PB', 'PD2_PB — Off-balance variant of PD2'),
        ('PD3_PB', 'PD3_PB — Off-balance variant of PD3'),
        ('PD4_PB', 'PD4_PB — Off-balance variant of PD4'),
        ('PD5_PB', 'PD5_PB — Off-balance variant of PD5'),
        ('PD6_PB', 'PD6_PB — Off-balance variant of PD6'),
    ], string='PD Marker (S_12_3)',
       help='Income-tax (CIT/PIT) reconciliation bucket. Drives RPD K_1, K_2, K_4, K_5.')
