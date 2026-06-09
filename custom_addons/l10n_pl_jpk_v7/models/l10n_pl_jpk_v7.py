"""
JPK_V7M(3) / JPK_V7K(3) XML generator for Odoo 19 CE.

Authoritative schema:
  /Users/admin/Source/private/odoo/schemas/jpk_v7m3.xsd  (1220 lines, fully audited)
  /Users/admin/Source/private/odoo/schemas/jpk_v7k3.xsd

Published 2025-12-19, mandatory from 2026-02-01.

Namespaces (verified from XSD):
  tns (default) = http://crd.gov.pl/wzor/2025/12/19/14090/      (V7M)
                  http://crd.gov.pl/wzor/2025/12/19/14089/      (V7K)
  etd           = http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/
                  ── NOT the 2022/01/05 version. Strict.
  kus           = http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/KodyUrzedowSkarbowych/

Strict XSD-mandated element ORDER (must not be violated):
  <JPK>
    <Naglowek>             ── KodFormularza, WariantFormularza,
                              DataWytworzeniaJPK, NazwaSystemu?, CelZlozenia,
                              KodUrzedu, Rok, Miesiac
    <Podmiot1 rola="Podatnik">
      <OsobaNiefizyczna>   ── NIP, PelnaNazwa, Email, Telefon?
    <Deklaracja>           ── BEFORE Ewidencja, not after
    <Ewidencja>            ── ALL SprzedazWiersz first, then SprzedazCtrl,
                              then ALL ZakupWiersz, then ZakupCtrl
                              (no interleaving)

KSeF/OFF/BFK/DI is an xsd:choice in each row — exactly one must appear,
positioned after DataSprzedazy and before optional TypDokumentu.

Submission: https://www.podatki.gov.pl/e-deklaracje/
"""
import base64
import logging
import re
from datetime import datetime, timezone

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Namespaces ────────────────────────────────────────────────────────────────
_NS_JPK_V7M = 'http://crd.gov.pl/wzor/2025/12/19/14090/'
_NS_JPK_V7K = 'http://crd.gov.pl/wzor/2025/12/19/14089/'
_NS_ETD = 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/09/13/eD/DefinicjeTypy/'
_NS_KUS = 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/KodyUrzedowSkarbowych/'
_NS_XSI = 'http://www.w3.org/2001/XMLSchema-instance'

_WERSJA_SCHEMY = '1-0E'   # JPK_V7M(3) schema file version

# KSeF invoice number pattern per FA(3) schema regex
_KSEF_NUM_PATTERN = re.compile(
    r'^([1-9]\d*|M\d{9}|[A-Z]{3}\d{7})-\d{8}-[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{2}$'
)

# ── K-field XSD-ordered tuples (must emit in this order) ─────────────────────
# Per XSD jpk_v7m3.xsd, SprzedazWiersz K-fields (after KSeF/OFF/BFK/DI choice):
_SALES_K_ORDER = (
    'K_10', 'K_11', 'K_12', 'K_13', 'K_14',
    'K_15', 'K_16', 'K_17', 'K_18', 'K_19', 'K_20',
    'K_21', 'K_22', 'K_23', 'K_24', 'K_25', 'K_26',
    'K_27', 'K_28', 'K_29', 'K_30', 'K_31', 'K_32',
    'K_33', 'K_34', 'K_35', 'K_36', 'K_360',
    'SprzedazVAT_Marza',
)

# Per XSD, ZakupWiersz K-fields:
_PURCHASE_K_ORDER = (
    'K_40', 'K_41', 'K_42', 'K_43',
    'K_44', 'K_45', 'K_46', 'K_47',
    'ZakupVAT_Marza',
)

# Output VAT K-fields added into SprzedazCtrl/PodatekNalezny.
# Per XSD line 1058: PodatekNalezny = (K_16+K_18+K_20+K_24+K_26+K_28+K_30+K_32+K_33+K_34)
#                                     − (K_35 + K_36 + K_360)
_SALES_VAT_K_FIELDS_PLUS = frozenset({
    'K_16', 'K_18', 'K_20', 'K_24', 'K_26', 'K_28', 'K_30', 'K_32', 'K_33', 'K_34',
})
_SALES_VAT_K_FIELDS_MINUS = frozenset({'K_35', 'K_36', 'K_360'})

# Input VAT K-fields summed into ZakupCtrl/PodatekNaliczony
# Per XSD docstring: K_41, K_43, K_44, K_45, K_46, K_47
_PURCHASE_VAT_K_FIELDS = frozenset({
    'K_41', 'K_43', 'K_44', 'K_45', 'K_46', 'K_47',
})

# ── Account tag → K-field mapping ────────────────────────────────────────────
# Maps l10n_pl account.account.tag NAMES to JPK K-field names.
# Sign is taken from account.account.tag.tax_negate (Boolean), NOT from
# the tag name prefix (+/-). This handles refunds and corrections correctly.
# v3 schema bound: sales K_10..K_36 + K_360; purchases K_40..K_47.
_K_FIELDS = [f'K_{n}' for n in (list(range(10, 37)) + [360] + list(range(40, 48)))]
_TAG_TO_K_FIELD = {f: f for f in _K_FIELDS}
_TAG_TO_K_FIELD.update({f'+{f}': f for f in _K_FIELDS})  # also accept '+K_NN' form

_SALES_TYPES = {'out_invoice', 'out_refund'}
_PURCHASE_TYPES = {'in_invoice', 'in_refund'}


class L10nPlJpkV7(models.Model):
    _name = 'l10n_pl.jpk.v7'
    _description = 'JPK_V7M / JPK_V7K Report'
    _order = 'date_from desc'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    period_type = fields.Selection([
        ('monthly', 'Monthly — JPK_V7M'),
        ('quarterly', 'Quarterly — JPK_V7K'),
    ], string='Period Type', required=True, default='monthly')
    date_from = fields.Date(string='Period From', required=True)
    date_to = fields.Date(string='Period To', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('submitted', 'Submitted to MF'),
    ], default='draft', string='Status')
    cel_zlozenia = fields.Selection([
        ('1', '1 — Initial submission'),
        ('2', '2 — Correction'),
    ], string='Purpose of Filing', default='1', required=True)
    kod_urzedu = fields.Char(
        string='Kod Urzędu Skarbowego',
        help='4-digit tax office code (e.g. 1471 for Warszawa Mokotów). '
             'Falls back to company.l10n_pl_tax_office_id.code if blank.',
    )
    xml_file = fields.Binary(string='JPK XML File', attachment=True)
    xml_filename = fields.Char(string='Filename')
    invoice_count = fields.Integer(string='Invoices Included', readonly=True)
    notes = fields.Text(string='Notes')

    # ── K-field verification action (verify tag mapping vs DB) ────────────────
    def action_verify_k_field_mapping(self):
        self.ensure_one()
        AccountTag = self.env['account.account.tag']
        poland = self.env.ref('base.pl', raise_if_not_found=False)
        if poland:
            db_tags = AccountTag.search(
                ['|', ('country_id', '=', poland.id), ('country_id', '=', False)]
            )
        else:
            db_tags = AccountTag.search([])
        k_like = db_tags.filtered(
            lambda t: t.name and t.name.strip().lstrip('+-').startswith('K_')
        )

        mapped, unmapped_db = [], []
        for tag in k_like:
            key = tag.name.strip()
            if key in _TAG_TO_K_FIELD:
                mapped.append(f'  ✓ {key}  →  {_TAG_TO_K_FIELD[key]}')
            else:
                unmapped_db.append(f'  ⚠ {key}')

        db_keys = {t.name.strip() for t in k_like}
        missing = sorted(set(_TAG_TO_K_FIELD.keys()) - db_keys)

        report = (
            f'=== K-Field Tag Mapping Verification ===\n'
            f'DB K-tags: {len(k_like)} | Mapping: {len(_TAG_TO_K_FIELD)}\n\n'
            f'MAPPED ({len(mapped)}):\n' + '\n'.join(mapped[:50])
            + f'\n\nDB tags WITHOUT mapping ({len(unmapped_db)}):\n'
            + '\n'.join(unmapped_db[:30])
            + f'\n\nMapping WITHOUT DB tag ({len(missing)}):\n'
            + '\n'.join(f'  ⚠ {k}' for k in missing[:30])
            + '\n\nVerified: ' + fields.Datetime.to_string(fields.Datetime.now())
        )
        self.notes = report
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'K-Field Mapping Verified',
                'message': f'{len(mapped)} mapped / {len(unmapped_db)} unmapped DB / {len(missing)} missing. See Notes.',
                'type': 'success' if not unmapped_db and not missing else 'warning',
                'sticky': True,
            },
        }

    @api.depends('company_id', 'period_type', 'date_from')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.company_id:
                kind = 'V7M' if rec.period_type == 'monthly' else 'V7K'
                rec.name = f'JPK_{kind}_{rec.date_from.strftime("%Y_%m")}_{rec.company_id.name}'
            else:
                rec.name = 'JPK_V7'

    # ── Generation ────────────────────────────────────────────────────────────

    def action_generate(self):
        self.ensure_one()
        company = self.company_id
        vat = (company.vat or '').upper().replace('PL', '').replace(' ', '')
        if not vat or len(vat) != 10 or not vat.isdigit():
            raise UserError(_(
                'Company NIP is not set or invalid (must be 10 digits, no PL prefix). '
                'Configure in Settings → Companies.'
            ))
        if not company.email:
            raise UserError(_(
                'Company email is required by JPK_V7M(3) Podmiot1.Email. '
                'Set it in Settings → Companies → Email.'
            ))

        kod_urzedu = self._get_kod_urzedu()
        if not kod_urzedu or len(kod_urzedu) != 4:
            raise UserError(_(
                'Tax office code (Kod Urzędu Skarbowego) is missing or invalid. '
                'Either set Kod Urzędu on this report (4 digits), or configure '
                'the company tax office in Settings → Companies → Polish Localization.'
            ))

        xml_bytes = self._generate_jpk_xml(company, vat, kod_urzedu)
        kind = 'V7M' if self.period_type == 'monthly' else 'V7K'
        filename = f'JPK_{kind}_{self.date_from.strftime("%Y%m")}_{vat}.xml'

        # Use ir.attachment.raw to pass raw bytes — Odoo handles base64 for us
        # and stores only ONE copy of the XML (vs. two if we set both raw and datas).
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'raw': xml_bytes,
            'res_model': self._name,
            'res_id': self.id,
        })
        # xml_file Binary field still needs base64 — store once, reference attachment.
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

    def _generate_jpk_xml(self, company, nip, kod_urzedu):
        invoices = self._get_invoices()
        self.invoice_count = len(invoices)

        root = self._build_root()

        # XSD-strict order: Naglowek → Podmiot1 → Deklaracja → Ewidencja
        self._build_naglowek(root, kod_urzedu)
        self._build_podmiot(root, company, nip)
        sales_k_totals, purchase_k_totals = self._compute_k_totals(invoices)
        self._build_deklaracja(root, sales_k_totals, purchase_k_totals)
        self._build_ewidencja(root, invoices, sales_k_totals, purchase_k_totals)

        return etree.tostring(
            root, xml_declaration=True, encoding='UTF-8', pretty_print=True
        )

    def _get_invoices(self):
        return self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', list(_SALES_TYPES | _PURCHASE_TYPES)),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ], order='date, name')

    def _build_root(self):
        ns = self._ns()
        nsmap = {None: ns, 'etd': _NS_ETD, 'kus': _NS_KUS}
        return etree.Element(f'{{{ns}}}JPK', nsmap=nsmap)

    def _ns(self):
        return _NS_JPK_V7M if self.period_type == 'monthly' else _NS_JPK_V7K

    def _sub(self, parent, tag, text=None, ns=None, attrib=None):
        if ns is None:
            ns = self._ns()
        el = etree.SubElement(parent, f'{{{ns}}}{tag}', attrib=attrib or {})
        if text is not None:
            el.text = str(text)
        return el

    @staticmethod
    def _fmt(amount):
        """Format kwota as Polish JPK requires (positive, 2 decimals)."""
        return f'{abs(round(float(amount), 2)):.2f}'

    # ── Naglowek ──────────────────────────────────────────────────────────────
    def _build_naglowek(self, root, kod_urzedu):
        """
        Build outer JPK Naglowek.

        Per XSD:
          • V7M(3) and V7K(3) BOTH end with <Miesiac> (NOT Kwartal!).
          • <Kwartal> only appears inside V7K Deklaracja/Naglowek/Kwartal,
            NOT in the outer JPK Naglowek.
        """
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        kod_systemowy = (
            'JPK_V7M (3)' if self.period_type == 'monthly' else 'JPK_V7K (3)'
        )
        naglowek = self._sub(root, 'Naglowek')
        self._sub(naglowek, 'KodFormularza', 'JPK_VAT', attrib={
            'kodSystemowy': kod_systemowy,
            'wersjaSchemy': _WERSJA_SCHEMY,
        })
        self._sub(naglowek, 'WariantFormularza', '3')
        self._sub(naglowek, 'DataWytworzeniaJPK', now_utc)
        self._sub(naglowek, 'NazwaSystemu', 'Odoo 19 CE l10n_pl_jpk_v7')
        self._sub(naglowek, 'CelZlozenia', self.cel_zlozenia, attrib={'poz': 'P_7'})
        self._sub(naglowek, 'KodUrzedu', kod_urzedu)
        self._sub(naglowek, 'Rok', str(self.date_from.year))
        # Both V7M and V7K main Naglowek end with Miesiac per XSD.
        self._sub(naglowek, 'Miesiac', str(self.date_from.month))

    # ── Podmiot1 (without address per TPodmiotDowolnyBezAdresu) ───────────────
    def _build_podmiot(self, root, company, nip):
        podmiot = self._sub(root, 'Podmiot1', attrib={'rola': 'Podatnik'})
        osoba = self._sub(podmiot, 'OsobaNiefizyczna')
        self._sub(osoba, 'NIP', nip)
        self._sub(osoba, 'PelnaNazwa', (company.name or '')[:240])
        self._sub(osoba, 'Email', company.email or '')
        if company.phone:
            self._sub(osoba, 'Telefon', company.phone[:16])

    # ── Ewidencja (XSD order: sales rows → SprzedazCtrl → purchase rows → ZakupCtrl) ─
    def _compute_k_totals(self, invoices):
        """First pass — extract per-invoice K-amounts; sum into running totals."""
        sales_totals, purchase_totals = {}, {}
        for invoice in invoices:
            k = self._get_k_amounts(invoice)
            target = sales_totals if invoice.move_type in _SALES_TYPES else purchase_totals
            for field, amount in k.items():
                target[field] = round(target.get(field, 0.0) + amount, 2)
        return sales_totals, purchase_totals

    def _build_ewidencja(self, root, invoices, sales_totals, purchase_totals):
        ewidencja = self._sub(root, 'Ewidencja')

        # Separate invoices by type, preserving date order within each
        sales = [i for i in invoices if i.move_type in _SALES_TYPES]
        purchases = [i for i in invoices if i.move_type in _PURCHASE_TYPES]

        # Sales rows (1..N), then SprzedazCtrl
        for lp, invoice in enumerate(sales, start=1):
            self._build_sales_row(ewidencja, invoice, lp)
        sprzedaz_ctrl = self._sub(ewidencja, 'SprzedazCtrl')
        self._sub(sprzedaz_ctrl, 'LiczbaWierszySprzedazy', str(len(sales)))
        # PodatekNalezny per XSD: Σ(K_16,18,20,24,26,28,30,32,33,34) − Σ(K_35,36,360)
        plus = sum(v for k, v in sales_totals.items() if k in _SALES_VAT_K_FIELDS_PLUS)
        minus = sum(v for k, v in sales_totals.items() if k in _SALES_VAT_K_FIELDS_MINUS)
        self._sub(sprzedaz_ctrl, 'PodatekNalezny', self._fmt(plus - minus))

        # Purchase rows (1..M), then ZakupCtrl
        for lp, invoice in enumerate(purchases, start=1):
            self._build_purchase_row(ewidencja, invoice, lp)
        zakup_ctrl = self._sub(ewidencja, 'ZakupCtrl')
        self._sub(zakup_ctrl, 'LiczbaWierszyZakupow', str(len(purchases)))
        total_vat_naliczony = sum(
            v for k, v in purchase_totals.items() if k in _PURCHASE_VAT_K_FIELDS
        )
        self._sub(zakup_ctrl, 'PodatekNaliczony', self._fmt(total_vat_naliczony))

    def _build_sales_row(self, parent, invoice, lp):
        row = self._sub(parent, 'SprzedazWiersz')
        partner = invoice.partner_id
        partner_vat = self._strip_vat_prefix(partner.vat) if partner else ''
        country_code = (
            partner.country_id.code if partner and partner.country_id else None
        )

        # ── XSD-mandated order ─────────────────────────────────────────────
        self._sub(row, 'LpSprzedazy', str(lp))
        if country_code and country_code != 'PL':
            self._sub(row, 'KodKrajuNadaniaTIN', country_code)
        # NrKontrahenta is required (1) — emit BRAK if missing
        self._sub(row, 'NrKontrahenta', partner_vat or 'BRAK')
        self._sub(row, 'NazwaKontrahenta', (partner.name if partner else None) or 'BRAK')
        # DowodSprzedazy required (TZnakowyJPK minLength=1) — fall back to ID
        self._sub(row, 'DowodSprzedazy', invoice.name or f'INV-{invoice.id}')

        # XSD: DataWystawienia BEFORE DataSprzedazy
        invoice_date = invoice.invoice_date or invoice.date
        self._sub(row, 'DataWystawienia', str(invoice_date))

        supply_date = getattr(invoice, 'taxable_supply_date', None) or invoice.invoice_date
        if supply_date and supply_date != invoice_date:
            self._sub(row, 'DataSprzedazy', str(supply_date))

        # xsd:choice — exactly one of NrKSeF / OFF / BFK / DI
        self._emit_ksef_choice(row, invoice)

        # ── K-fields in strict XSD order ───────────────────────────────────
        k_amounts = self._get_k_amounts(invoice)
        for k_field in _SALES_K_ORDER:
            amount = k_amounts.get(k_field)
            if amount is not None and abs(amount) > 0:
                self._sub(row, k_field, self._fmt(amount))

    def _build_purchase_row(self, parent, invoice, lp):
        row = self._sub(parent, 'ZakupWiersz')
        partner = invoice.partner_id
        partner_vat = self._strip_vat_prefix(partner.vat) if partner else ''
        country_code = (
            partner.country_id.code if partner and partner.country_id else None
        )

        self._sub(row, 'LpZakupu', str(lp))
        if country_code and country_code != 'PL':
            self._sub(row, 'KodKrajuNadaniaTIN', country_code)
        self._sub(row, 'NrDostawcy', partner_vat or 'BRAK')
        self._sub(row, 'NazwaDostawcy', (partner.name if partner else None) or 'BRAK')
        # DowodZakupu required (TZnakowyJPK minLength=1) — fall back to ID
        self._sub(row, 'DowodZakupu', invoice.ref or invoice.name or f'INV-{invoice.id}')

        purchase_date = invoice.invoice_date or invoice.date
        self._sub(row, 'DataZakupu', str(purchase_date))
        # DataWplywu only if different from DataZakupu
        if invoice.date and invoice.date != purchase_date:
            self._sub(row, 'DataWplywu', str(invoice.date))

        self._emit_ksef_choice(row, invoice)

        k_amounts = self._get_k_amounts(invoice)
        for k_field in _PURCHASE_K_ORDER:
            amount = k_amounts.get(k_field)
            if amount is not None and abs(amount) > 0:
                self._sub(row, k_field, self._fmt(amount))

    @staticmethod
    def _strip_vat_prefix(vat, country_code=None):
        """
        Return TIN with the 2-letter country prefix stripped.
        KAS validators reject combined values like 'FR12345678901' paired with
        KodKrajuNadaniaTIN=FR.
        """
        cleaned = (vat or '').upper().replace(' ', '').replace('-', '')
        # Strip 2-letter alphabetic prefix if present at the start
        if len(cleaned) >= 2 and cleaned[:2].isalpha():
            cleaned = cleaned[2:]
        return cleaned

    def _emit_ksef_choice(self, row, invoice):
        """
        Emit exactly one of NrKSeF / OFF / BFK / DI per xsd:choice.

        Resolution order:
          1. If invoice has a valid l10n_pl_edi_number → emit <NrKSeF>
          2. Else if user explicitly set l10n_pl_jpk_tag to OFF/BFK/DI → emit that
          3. Else if l10n_pl_jpk_tag is 'ksef' (the default) but no KSeF# →
             log a warning and fall back to BFK (best-effort for legacy/no-KSeF docs)
        """
        ksef_num = getattr(invoice, 'l10n_pl_edi_number', None)
        if ksef_num and _KSEF_NUM_PATTERN.match(ksef_num):
            self._sub(row, 'NrKSeF', ksef_num)
            return

        jpk_tag = getattr(invoice, 'l10n_pl_jpk_tag', None)
        if jpk_tag in ('OFF', 'BFK', 'DI'):
            self._sub(row, jpk_tag, '1')
            return

        # 'ksef' selection or empty — invoice was supposed to have a KSeF# but
        # doesn't. Log so the user can investigate; fall back to BFK to keep
        # the file valid (xsd:choice requires exactly one).
        _logger.warning(
            'JPK_V7: invoice %s (id=%s) has no l10n_pl_edi_number and tag=%r — '
            'defaulted to BFK. Set l10n_pl_jpk_tag explicitly to OFF/BFK/DI '
            'or fix the KSeF submission.',
            invoice.name, invoice.id, jpk_tag,
        )
        self._sub(row, 'BFK', '1')

    def _get_k_amounts(self, invoice):
        """
        Extract K-field amounts from invoice line tax tags.

        Sign comes from `account.account.tag.tax_negate` (Boolean) — this is the
        canonical Odoo signal for "this tag's amount should be subtracted from
        the K-field total". The l10n_pl chart sets tax_negate on the refund/
        correction-side tags. Tag name prefixes (+/-) are tolerated for legacy
        configurations but NOT used as the sign source.
        """
        k = {}
        for line in invoice.line_ids:
            for tag in line.tax_tag_ids:
                key = (tag.name or '').strip()
                field = _TAG_TO_K_FIELD.get(key)
                if not field:
                    continue
                # Sign from account.account.tag.tax_negate, not the name prefix.
                tag_sign = -1.0 if getattr(tag, 'tax_negate', False) else 1.0
                # Sales invoices: positive balance = credit = revenue, so negate
                # raw balance to get a positive sales figure.
                raw = -line.balance if invoice.move_type in _SALES_TYPES else line.balance
                amount = tag_sign * raw
                k[field] = round(k.get(field, 0.0) + amount, 2)
        return k

    # ── Deklaracja ────────────────────────────────────────────────────────────
    def _build_deklaracja(self, root, s, p):
        """
        Build Deklaracja.

        KEY XSD CONSTRAINTS:
          • All P_NN amounts are etd:TKwotaC (xsd:integer) — NO DECIMALS.
            We use _fmt_int (rounds to nearest PLN).
          • P_46 is restricted to maxInclusive=0 — must be ≤ 0.
          • P_38 (output VAT total), P_48 (input VAT total) and P_51 (payable)
            are REQUIRED — always emitted even when zero.
          • V7K uses kodSystemowy="VAT-7K (17)", variant 17, plus Kwartal element.
            V7M uses kodSystemowy="VAT-7 (23)", variant 23.
        """
        decl = self._sub(root, 'Deklaracja')
        naglowek = self._sub(decl, 'Naglowek')

        if self.period_type == 'quarterly':
            self._sub(naglowek, 'KodFormularzaDekl', 'VAT-7K', attrib={
                'kodSystemowy': 'VAT-7K (17)',
                'kodPodatku': 'VAT',
                'rodzajZobowiazania': 'Z',
                'wersjaSchemy': _WERSJA_SCHEMY,
            })
            self._sub(naglowek, 'WariantFormularzaDekl', '17')
            quarter = (self.date_from.month - 1) // 3 + 1
            self._sub(naglowek, 'Kwartal', str(quarter))
        else:
            self._sub(naglowek, 'KodFormularzaDekl', 'VAT-7', attrib={
                'kodSystemowy': 'VAT-7 (23)',
                'kodPodatku': 'VAT',
                'rodzajZobowiazania': 'Z',
                'wersjaSchemy': _WERSJA_SCHEMY,
            })
            self._sub(naglowek, 'WariantFormularzaDekl', '23')

        pozycje = self._sub(decl, 'PozycjeSzczegolowe')

        def _p(tag, val):
            """Optional P_NN — integer, emit only when nonzero."""
            if val is not None and abs(round(val)) > 0:
                self._sub(pozycje, tag, self._fmt_int(val))

        def _p_required(tag, val):
            """Required P_NN — always emit (integer, may be zero)."""
            self._sub(pozycje, tag, self._fmt_int(val or 0))

        # Sales positions
        _p('P_10', s.get('K_10', 0))
        _p('P_11', s.get('K_11', 0))
        _p('P_12', s.get('K_12', 0))
        _p('P_13', s.get('K_13', 0))
        _p('P_14', s.get('K_14', 0))
        _p('P_15', s.get('K_15', 0))
        _p('P_16', s.get('K_16', 0))
        _p('P_17', s.get('K_17', 0))
        _p('P_18', s.get('K_18', 0))
        _p('P_19', s.get('K_19', 0))
        _p('P_20', s.get('K_20', 0))
        _p('P_21', s.get('K_21', 0))
        _p('P_22', s.get('K_22', 0))
        _p('P_23', s.get('K_23', 0))
        _p('P_24', s.get('K_24', 0))
        _p('P_25', s.get('K_25', 0))
        _p('P_26', s.get('K_26', 0))
        _p('P_27', s.get('K_27', 0))
        _p('P_28', s.get('K_28', 0))
        _p('P_29', s.get('K_29', 0))
        _p('P_30', s.get('K_30', 0))
        _p('P_31', s.get('K_31', 0))
        _p('P_32', s.get('K_32', 0))
        _p('P_33', s.get('K_33', 0))
        _p('P_34', s.get('K_34', 0))
        _p('P_35', s.get('K_35', 0))
        _p('P_36', s.get('K_36', 0))
        _p('P_360', s.get('K_360', 0))

        # Total output VAT per XSD: Σ(K_16,18,20,24,26,28,30,32,33,34) − Σ(K_35,36,360)
        plus = sum(s.get(k, 0) for k in _SALES_VAT_K_FIELDS_PLUS)
        minus = sum(s.get(k, 0) for k in _SALES_VAT_K_FIELDS_MINUS)
        total_output = plus - minus
        _p_required('P_38', total_output)  # P_38 REQUIRED

        # Purchase positions
        _p('P_40', p.get('K_40', 0))
        _p('P_41', p.get('K_41', 0))
        _p('P_42', p.get('K_42', 0))
        _p('P_43', p.get('K_43', 0))
        _p('P_44', p.get('K_44', 0))
        _p('P_45', p.get('K_45', 0))
        # P_46 — XSD maxInclusive=0; must be ≤ 0
        k46 = p.get('K_46', 0)
        if k46:
            self._sub(pozycje, 'P_46', str(int(round(-abs(k46)))))
        _p('P_47', p.get('K_47', 0))

        # Total deductible input VAT (required)
        total_input = sum(p.get(k, 0) for k in _PURCHASE_VAT_K_FIELDS)
        _p_required('P_48', total_input)

        # Net VAT — P_51 REQUIRED (payable; 0 if input ≥ output)
        net_vat = round(total_output - total_input, 2)
        _p_required('P_51', max(net_vat, 0))
        if net_vat < 0:
            _p('P_53', abs(net_vat))

        # Last element — REQUIRED Pouczenia=1 (acceptance of legal notice)
        self._sub(decl, 'Pouczenia', '1')
