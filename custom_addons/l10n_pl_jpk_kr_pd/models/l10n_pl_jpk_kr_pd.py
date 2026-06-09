"""
JPK_KR_PD(1) generator — Polish CIT SAF-T monthly/annual file.

Authoritative schema:
  /Users/admin/Source/private/odoo/schemas/jpk_kr_pd.xsd
  Target namespace: http://jpk.mf.gov.pl/wzor/2024/09/04/09041/
  wersjaSchemy:     "1-1"  (XSD fixed; brochure misquotes as "1-0")
  kodSystemowy:     "JPK_KR_PD (1)"

XSD-strict root sequence:
  <JPK>
    <Naglowek>
    <Podmiot1>
    <Kontrahent>*       (0..unbounded, one per counterparty appearing in period)
    <ZOiS>              (1, contains choice ZOiS1..ZOiS8 each 1..unbounded)
    <Dziennik>+         (1..unbounded — but each is one account.move)
    <Ctrl>              (1)
    <RPD>               (1 — income-tax reconciliation, 8 K_* fields)

Variant choice — this implementation emits ZOiS8 (IFRS) by default because:
  • ZOiS8 makes the statutory-balance-sheet markers (S_12_1, S_12_2) OPTIONAL
  • Variants 1-7 require ~600 enumeration values pre-mapped per account
  • A small sp. z o.o. with AI-assisted books can satisfy KAS audit via ZOiS8
    if also reporting under MSSF/IFRS or using simplified accounting

To switch to ZOiS7 (typical Polish CoA), set company.l10n_pl_jpk_zois_variant.

Deadline: 2027-07-31 for typical sp. z o.o. (fiscal year 2026).
Submission: https://www.podatki.gov.pl/e-deklaracje/
"""
import base64
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_NS_JPK_KR_PD = 'http://jpk.mf.gov.pl/wzor/2024/09/04/09041/'
_NS_ETD = 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/'
_NS_KUS = 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/KodyUrzedowSkarbowych/'

_WERSJA_SCHEMY = '1-1'   # XSD fixed value

_POSTAL_RE = re.compile(r'^\d{2}-\d{3}$')

# Map Odoo move_type → Polish D_5 document-type marker
_MOVE_TYPE_TO_D5 = {
    'out_invoice': 'FS',
    'out_refund':  'KFS',
    'in_invoice':  'FZ',
    'in_refund':   'KFZ',
    'entry':       'PK',
}


class L10nPlJpkKrPd(models.Model):
    _name = 'l10n_pl.jpk.kr.pd'
    _description = 'JPK_KR_PD (JPK_CIT) Report'
    _order = 'date_from desc'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string='Period From', required=True)
    date_to = fields.Date(string='Period To', required=True)
    fiscal_year_from = fields.Date(
        string='Fiscal Year From',
        help='Start of the fiscal year covering this period. '
             'Auto-computed from date_to if empty.',
    )
    fiscal_year_to = fields.Date(string='Fiscal Year To')
    cel_zlozenia = fields.Selection([
        ('1', '1 — Initial submission'),
        ('2', '2 — Correction'),
    ], string='Purpose of Filing', default='1', required=True)
    kod_urzedu = fields.Char(
        string='Kod Urzędu Skarbowego',
        help='4-digit tax office code. Falls back to company tax office if blank.',
    )

    # ── ZOiS variant ──────────────────────────────────────────────────────────
    zois_variant = fields.Selection([
        ('ZOiS7', 'ZOiS7 — Standard Polish entities (requires markers per account)'),
        ('ZOiS8', 'ZOiS8 — IFRS / simplified (markers optional, RECOMMENDED)'),
    ], string='ZOiS Variant', default='ZOiS8', required=True,
       help='ZOiS8 makes statutory-balance-sheet markers optional. Use ZOiS7 only '
            'if you have pre-mapped every account.account.l10n_pl_zois_marker.')

    # ── Manual RPD inputs (cannot be derived from accounting) ────────────────
    rpd_k_3 = fields.Float(string='RPD K_3 — Revenue taxable this year, booked prior',
                           help='Manual input — accounts tagged PD3 in TMapKontaPD use only the _PB variant.')
    rpd_k_6 = fields.Float(string='RPD K_6 — Costs recognised this year, booked prior')
    rpd_k_7 = fields.Float(string='RPD K_7 — Taxable revenue not booked')
    rpd_k_8 = fields.Float(string='RPD K_8 — Deductible costs not booked')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('submitted', 'Submitted to MF'),
    ], default='draft', string='Status')
    xml_file = fields.Binary(string='JPK_KR_PD XML', attachment=True)
    xml_filename = fields.Char(string='Filename')
    move_count = fields.Integer(string='Moves Included', readonly=True)
    move_line_count = fields.Integer(string='Postings Included', readonly=True)
    account_count = fields.Integer(string='Accounts Included', readonly=True)
    notes = fields.Text(string='Notes')

    @api.depends('company_id', 'date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.company_id:
                rec.name = f'JPK_KR_PD_{rec.date_from.strftime("%Y%m")}-{rec.date_to.strftime("%Y%m")}_{rec.company_id.name}'
            else:
                rec.name = 'JPK_KR_PD (draft)'

    @api.onchange('date_to', 'company_id')
    def _onchange_fiscal_year(self):
        """Auto-fill fiscal-year fields from the company calendar."""
        if not self.date_to or not self.company_id:
            return
        try:
            fy = self.company_id.compute_fiscalyear_dates(self.date_to)
            self.fiscal_year_from = fy.get('date_from')
            self.fiscal_year_to = fy.get('date_to')
        except Exception:
            pass

    # ── Generation ────────────────────────────────────────────────────────────

    def action_generate(self):
        self.ensure_one()
        company = self.company_id
        vat = (company.vat or '').upper().replace('PL', '').replace(' ', '')
        if not vat or len(vat) != 10 or not vat.isdigit():
            raise UserError(_('Invalid company NIP (need 10 digits).'))
        if not self.fiscal_year_from or not self.fiscal_year_to:
            # Auto-compute
            try:
                fy = company.compute_fiscalyear_dates(self.date_to)
                self.fiscal_year_from = fy['date_from']
                self.fiscal_year_to = fy['date_to']
            except Exception as exc:
                raise UserError(_('Cannot determine fiscal year: %s') % exc)

        kod_urzedu = self._get_kod_urzedu()
        if not kod_urzedu or len(kod_urzedu) != 4:
            raise UserError(_(
                'Tax office code (Kod Urzędu Skarbowego) missing/invalid. '
                'Set on report or in company tax office configuration.'
            ))

        xml_bytes = self._generate_xml(company, vat, kod_urzedu)
        filename = f'JPK_KR_PD_{self.date_from.strftime("%Y%m%d")}-{self.date_to.strftime("%Y%m%d")}_{vat}.xml'

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(xml_bytes),
            'res_model': self._name,
            'res_id': self.id,
        })
        self.write({
            'xml_file': base64.b64encode(xml_bytes),
            'xml_filename': filename,
            'state': 'generated',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def _get_kod_urzedu(self):
        if self.kod_urzedu:
            return self.kod_urzedu.strip()
        for field in ('l10n_pl_tax_office_id', 'l10n_pl_tax_office'):
            office = getattr(self.company_id, field, None)
            if office and getattr(office, 'code', None):
                return office.code.strip()
        return None

    def _generate_xml(self, company, nip, kod_urzedu):
        # Fetch all data
        moves = self._get_moves()
        lines = self._get_lines(moves)
        accounts = self._get_active_accounts(moves)
        partners = self._get_partners(moves)

        self.move_count = len(moves)
        self.move_line_count = len(lines)
        self.account_count = len(accounts)

        # Build XML
        root = self._build_root()
        self._build_naglowek(root, kod_urzedu)
        self._build_podmiot(root, company, nip)
        self._build_kontrahenci(root, partners)
        self._build_zois(root, accounts, moves)
        self._build_dziennik(root, moves, lines)
        self._build_ctrl(root, moves, lines)
        self._build_rpd(root, moves)

        return etree.tostring(
            root, xml_declaration=True, encoding='UTF-8', pretty_print=True
        )

    def _get_moves(self):
        return self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ], order='journal_id,date,name,id')

    def _get_lines(self, moves):
        return moves.line_ids.sorted(lambda l: (l.move_id.id, l.id))

    def _get_active_accounts(self, moves):
        """Active = referenced in any move within the fiscal year (cumulative)."""
        fy_moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('date', '>=', self.fiscal_year_from),
            ('date', '<=', self.fiscal_year_to),
        ])
        accounts = fy_moves.line_ids.account_id
        return accounts.sorted('code')

    def _get_partners(self, moves):
        partners = moves.line_ids.mapped('partner_id').filtered(lambda p: p and p.ref)
        return partners.sorted('ref')

    # ── XML builders ──────────────────────────────────────────────────────────

    def _build_root(self):
        nsmap = {None: _NS_JPK_KR_PD, 'etd': _NS_ETD, 'kus': _NS_KUS}
        return etree.Element(f'{{{_NS_JPK_KR_PD}}}JPK', nsmap=nsmap)

    def _sub(self, parent, tag, text=None, ns=None, attrib=None):
        if ns is None:
            ns = _NS_JPK_KR_PD
        el = etree.SubElement(parent, f'{{{ns}}}{tag}', attrib=attrib or {})
        if text is not None:
            el.text = str(text)
        return el

    @staticmethod
    def _fmt(amount):
        return f'{round(float(amount or 0.0), 2):.2f}'

    def _build_naglowek(self, root, kod_urzedu):
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        nag = self._sub(root, 'Naglowek')
        self._sub(nag, 'KodFormularza', 'JPK_KR_PD', attrib={
            'kodSystemowy': 'JPK_KR_PD (1)',
            'wersjaSchemy': _WERSJA_SCHEMY,
        })
        self._sub(nag, 'WariantFormularza', '1')
        self._sub(nag, 'CelZlozenia', self.cel_zlozenia)
        self._sub(nag, 'DataWytworzeniaJPK', now_utc)
        self._sub(nag, 'DataOd', str(self.date_from))
        self._sub(nag, 'DataDo', str(self.date_to))
        self._sub(nag, 'RokDataOd', str(self.fiscal_year_from))
        self._sub(nag, 'RokDataDo', str(self.fiscal_year_to))
        # Tax year — if different from fiscal year, set on company
        # (optional pair: emit both or neither)
        self._sub(nag, 'DomyslnyKodWaluty', self.company_id.currency_id.name or 'PLN')
        self._sub(nag, 'KodUrzedu', kod_urzedu)

    def _build_podmiot(self, root, company, nip):
        podmiot = self._sub(root, 'Podmiot1')
        ident = self._sub(podmiot, 'IdentyfikatorPodmiotu')
        self._sub(ident, 'NIP', nip, ns=_NS_ETD)
        self._sub(ident, 'PelnaNazwa', (company.name or '')[:240], ns=_NS_ETD)
        regon = getattr(company, 'company_registry', None) or getattr(company, 'l10n_pl_regon', None)
        if regon:
            self._sub(ident, 'REGON', regon, ns=_NS_ETD)

        partner = company.partner_id
        country = partner.country_id.code if partner.country_id else 'PL'

        # XSD requires <Adres> wrapper containing the AdresPol|AdresZagr choice.
        # AdresPol/AdresZagr is a child of <Adres>, NOT a sibling.
        adres = self._sub(podmiot, 'Adres')
        inner_tag = 'AdresPol' if country == 'PL' else 'AdresZagr'
        inner = self._sub(adres, inner_tag)

        # XSD length constraints (etd v10):
        #   TJednAdmin maxLength=36 (Wojewodztwo, Powiat, Gmina)
        #   TMiejscowosc maxLength=56
        #   TUlica maxLength=65
        #   TNrBudynku maxLength=9, TNrLokalu maxLength=10
        #   TKodPocztowy NN-NNN (8 chars) for PL
        street_number = getattr(partner, 'street_number', None)
        street_number2 = getattr(partner, 'street_number2', None)
        street_name = getattr(partner, 'street_name', None)

        if country == 'PL':
            self._sub(inner, 'KodKraju', 'PL', ns=_NS_ETD)
            woj = getattr(partner, 'state_id', None)
            self._sub(inner, 'Wojewodztwo',
                      ((woj.name if woj else '') or 'BRAK')[:36], ns=_NS_ETD)
            self._sub(inner, 'Powiat',
                      (getattr(partner, 'l10n_pl_powiat', None) or 'BRAK')[:36], ns=_NS_ETD)
            self._sub(inner, 'Gmina',
                      (getattr(partner, 'l10n_pl_gmina', None) or 'BRAK')[:36], ns=_NS_ETD)
            ulica = (street_name or partner.street or '').strip()
            if ulica:
                self._sub(inner, 'Ulica', ulica[:65], ns=_NS_ETD)
            self._sub(inner, 'NrDomu', (street_number or '1')[:9], ns=_NS_ETD)
            if street_number2:
                self._sub(inner, 'NrLokalu', street_number2[:10], ns=_NS_ETD)
            self._sub(inner, 'Miejscowosc', (partner.city or 'BRAK')[:56], ns=_NS_ETD)
            zip_code = partner.zip or ''
            if not _POSTAL_RE.match(zip_code):
                zip_code = '00-000'  # placeholder; KAS may reject
            self._sub(inner, 'KodPocztowy', zip_code[:8], ns=_NS_ETD)
        else:
            self._sub(inner, 'KodKraju', country, ns=_NS_ETD)
            self._sub(inner, 'KodPocztowy', (partner.zip or '00000')[:8], ns=_NS_ETD)
            self._sub(inner, 'Miejscowosc', (partner.city or 'BRAK')[:56], ns=_NS_ETD)
            if partner.street:
                self._sub(inner, 'Ulica', partner.street[:65], ns=_NS_ETD)

    def _build_kontrahenci(self, root, partners):
        """
        XSD: T_1/T_2/T_3 are declared inline in JPK_KR_PD with elementFormDefault=
        qualified, so they live in the JPK_KR_PD target namespace (tns), NOT etd.
        Their *types* reference etd, but the element names are in tns.
        """
        for partner in partners:
            kont = self._sub(root, 'Kontrahent')
            self._sub(kont, 'T_1', (partner.ref or '')[:256])
            vat = (partner.vat or '').replace(' ', '').upper()
            if vat:
                country_prefix = vat[:2] if vat[:2].isalpha() else None
                tin = vat[2:] if country_prefix else vat
                if country_prefix:
                    self._sub(kont, 'T_2', country_prefix)  # tns (default), NOT etd
                self._sub(kont, 'T_3', tin)  # tns (default), NOT etd

    def _build_zois(self, root, accounts, period_moves):
        """Build ZOiS section with one ZOiS<n> per account.

        Uses ZOiS8 (IFRS) by default — S_12_1/S_12_2 optional.
        """
        zois = self._sub(root, 'ZOiS')
        period_account_balances = self._compute_period_balances(period_moves)
        fy_account_balances = self._compute_fy_balances()
        opening_balances = self._compute_opening_balances()

        variant_tag = self.zois_variant  # 'ZOiS7' or 'ZOiS8'

        for account in accounts:
            row = self._sub(zois, variant_tag)
            parent_code = self._derive_parent_code(account.code)
            opening_dr, opening_cr = opening_balances.get(account.id, (0.0, 0.0))
            period_dr, period_cr = period_account_balances.get(account.id, (0.0, 0.0))
            fy_dr, fy_cr = fy_account_balances.get(account.id, (0.0, 0.0))
            closing_balance = (opening_dr + fy_dr) - (opening_cr + fy_cr)
            closing_dr = max(closing_balance, 0.0)
            closing_cr = max(-closing_balance, 0.0)

            self._sub(row, 'S_1', account.code)
            self._sub(row, 'S_2', (account.name or '')[:256])
            self._sub(row, 'S_3', parent_code or '0')
            self._sub(row, 'S_4', self._fmt(opening_dr))
            self._sub(row, 'S_5', self._fmt(opening_cr))
            self._sub(row, 'S_6', self._fmt(period_dr))
            self._sub(row, 'S_7', self._fmt(period_cr))
            self._sub(row, 'S_8', self._fmt(fy_dr))
            self._sub(row, 'S_9', self._fmt(fy_cr))
            self._sub(row, 'S_10', self._fmt(closing_dr))
            self._sub(row, 'S_11', self._fmt(closing_cr))

            # Markers — only emit if set on account.account (optional in ZOiS8)
            marker_1 = getattr(account, 'l10n_pl_zois_marker_1', None)
            marker_2 = getattr(account, 'l10n_pl_zois_marker_2', None)
            marker_pd = getattr(account, 'l10n_pl_pd_marker', None)
            if marker_1:
                self._sub(row, 'S_12_1', marker_1)
            if marker_2:
                self._sub(row, 'S_12_2', marker_2)
            if marker_pd:
                self._sub(row, 'S_12_3', marker_pd)

    @staticmethod
    def _derive_parent_code(code):
        """Derive parent account code by stripping the last '-' segment."""
        if not code:
            return None
        for sep in ('-', '.'):
            if sep in code:
                return code.rsplit(sep, 1)[0]
        # Numeric CoA: 401 → 40 → 4 → '0'
        if code.isdigit() and len(code) > 1:
            return code[:-1]
        return '0'

    def _compute_period_balances(self, moves):
        """Sum debit/credit per account for the reporting period."""
        result = defaultdict(lambda: [0.0, 0.0])
        for line in moves.line_ids:
            result[line.account_id.id][0] += line.debit
            result[line.account_id.id][1] += line.credit
        return {k: tuple(v) for k, v in result.items()}

    def _compute_fy_balances(self):
        """YTD debit/credit from fiscal_year_from to date_to."""
        fy_moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('date', '>=', self.fiscal_year_from),
            ('date', '<=', self.date_to),
        ])
        result = defaultdict(lambda: [0.0, 0.0])
        for line in fy_moves.line_ids:
            result[line.account_id.id][0] += line.debit
            result[line.account_id.id][1] += line.credit
        return {k: tuple(v) for k, v in result.items()}

    def _compute_opening_balances(self):
        """Opening balances from start of FY (cumulative from books open)."""
        opening_moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('date', '<', self.fiscal_year_from),
        ])
        result = defaultdict(lambda: [0.0, 0.0])
        for line in opening_moves.line_ids:
            result[line.account_id.id][0] += line.debit
            result[line.account_id.id][1] += line.credit
        return {k: tuple(v) for k, v in result.items()}

    def _build_dziennik(self, root, moves, lines):
        """One <Dziennik> element per account.move; KontoZapis* per line."""
        per_journal_seq = defaultdict(int)
        for move in moves:
            per_journal_seq[move.journal_id.id] += 1
            seq = per_journal_seq[move.journal_id.id]
            d1 = f"{seq}/{move.journal_id.code or move.journal_id.name[:3]}/{move.date.strftime('%m/%Y')}"

            dz = self._sub(root, 'Dziennik')
            self._sub(dz, 'D_1', d1[:256])
            self._sub(dz, 'D_2', (move.journal_id.name or '')[:256])

            partner_ref = getattr(move.partner_id, 'ref', None)
            if partner_ref:
                self._sub(dz, 'D_3', partner_ref[:256])

            ref = (move.ref or move.name or '')[:256]
            self._sub(dz, 'D_4', ref)

            d5 = _MOVE_TYPE_TO_D5.get(move.move_type, 'PK')
            self._sub(dz, 'D_5', d5)

            event_date = move.invoice_date or move.date
            self._sub(dz, 'D_6', str(event_date))
            self._sub(dz, 'D_7', str(move.invoice_date or move.date))
            self._sub(dz, 'D_8', str(move.date))

            user = move.create_uid or move.invoice_user_id
            self._sub(dz, 'D_9', (user.name if user else 'system')[:256])

            narration = self._strip_html(move.narration or '')
            if not narration:
                narration = (move.line_ids[:1].name if move.line_ids else '') or move.ref or 'BRAK'
            self._sub(dz, 'D_10', narration[:512])

            amount = abs(move.amount_total_signed or sum(l.balance for l in move.line_ids if l.debit))
            self._sub(dz, 'D_11', self._fmt(amount))

            ksef_num = getattr(move, 'l10n_pl_edi_number', None)
            if ksef_num:
                self._sub(dz, 'D_12', ksef_num)

            # KontoZapis per line
            line_idx = 0
            for line in move.line_ids.sorted('id'):
                if not line.debit and not line.credit:
                    continue
                line_idx += 1
                kz = self._sub(dz, 'KontoZapis')
                self._sub(kz, 'Z_1', str(line_idx))
                self._sub(kz, 'Z_2', (line.name or '/')[:512])
                self._sub(kz, 'Z_3', (line.account_id.code or 'null')[:256])
                if line.debit > 0:
                    self._sub(kz, 'Z_4', self._fmt(line.debit))
                    if line.currency_id and line.currency_id != self.company_id.currency_id:
                        self._sub(kz, 'Z_5', self._fmt(abs(line.amount_currency)))
                        self._sub(kz, 'Z_6', line.currency_id.name)
                else:
                    self._sub(kz, 'Z_7', self._fmt(line.credit))
                    if line.currency_id and line.currency_id != self.company_id.currency_id:
                        self._sub(kz, 'Z_8', self._fmt(abs(line.amount_currency)))
                        self._sub(kz, 'Z_9', line.currency_id.name)

    @staticmethod
    def _strip_html(text):
        return re.sub(r'<[^>]+>', '', text or '').strip()

    def _build_ctrl(self, root, moves, lines):
        """
        Build Ctrl section.

        XSD: C_1 and C_3 are tns:TNaturalnyJPK with minExclusive=0 — they MUST
        be > 0. A period with no moves cannot be filed; caller must skip
        generation or filing is structurally invalid.
        """
        active_lines = [line for line in lines if line.debit or line.credit]
        if not moves or not active_lines:
            raise UserError(_(
                'Cannot generate JPK_KR_PD for a period with no posted moves. '
                'XSD requires C_1 (move count) and C_3 (line count) > 0. '
                'Period: %s — %s, posted moves found: %d, active lines: %d.'
            ) % (self.date_from, self.date_to, len(moves), len(active_lines)))

        ctrl = self._sub(root, 'Ctrl')
        self._sub(ctrl, 'C_1', str(len(moves)))
        c2 = sum(abs(m.amount_total_signed or 0.0) for m in moves)
        self._sub(ctrl, 'C_2', self._fmt(c2))
        self._sub(ctrl, 'C_3', str(len(active_lines)))
        self._sub(ctrl, 'C_4', self._fmt(sum(line.debit for line in active_lines)))
        self._sub(ctrl, 'C_5', self._fmt(sum(line.credit for line in active_lines)))

    def _build_rpd(self, root, moves):
        """RPD section — 8 K_* income-tax reconciliation fields."""
        # K_1, K_2, K_4, K_5 — from accounts tagged with l10n_pl_pd_marker
        # K_3, K_6, K_7, K_8 — from wizard manual input
        k1 = k2 = k4 = k5 = 0.0
        for line in moves.line_ids:
            marker = getattr(line.account_id, 'l10n_pl_pd_marker', None)
            if not marker:
                continue
            balance = line.balance
            if marker.startswith('PD1'):
                k1 += -balance  # revenue side, negate
            elif marker.startswith('PD2'):
                k2 += -balance
            elif marker.startswith('PD4'):
                k4 += balance
            elif marker.startswith('PD5'):
                k5 += balance

        rpd = self._sub(root, 'RPD')
        self._sub(rpd, 'K_1', self._fmt(k1))
        self._sub(rpd, 'K_2', self._fmt(k2))
        self._sub(rpd, 'K_3', self._fmt(self.rpd_k_3))
        self._sub(rpd, 'K_4', self._fmt(k4))
        self._sub(rpd, 'K_5', self._fmt(k5))
        self._sub(rpd, 'K_6', self._fmt(self.rpd_k_6))
        self._sub(rpd, 'K_7', self._fmt(self.rpd_k_7))
        self._sub(rpd, 'K_8', self._fmt(self.rpd_k_8))
