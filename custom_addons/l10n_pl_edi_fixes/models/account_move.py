"""
KSeF FA(3) compliance patches for Odoo 19 CE l10n_pl_edi.

Fills three gaps left by the stock module:
  1. GTU codes — l10n_pl stores GTU on product but l10n_pl_edi never outputs
     the <GTU> element in FaWiersz.
  2. MPP / Split Payment (P_18A) — stock template hardcodes "2" (No).
  3. VAT exemption legal basis (P_19A/P_19B/P_19C) — stock template emits
     only <P_19N>1</P_19N> ("no exempt items"); replaced when the field is set.

Strategy: post-process the rendered XML string with lxml.

Schema verified against:
  /Users/admin/Source/private/odoo/schemas/fa3.xsd
  Namespace: http://crd.gov.pl/wzor/2025/06/25/13775/
  Root:      <Faktura>

Structural facts confirmed from the XSD:
  • <GTU> is a single element per <FaWiersz>, value must be one of GTU_01..GTU_13.
    It is the 22nd element in the FaWiersz xsd:sequence, between KwotaAkcyzy
    and Procedura. The older "P_106E_N" naming belongs to JPK_FA, not FA(3).
  • <Zwolnienie> lives inside <Adnotacje>, NOT directly under <Fa>.
    Full path: /Faktura/Fa/Adnotacje/Zwolnienie
  • <Zwolnienie> is an xsd:choice between:
        (a) <P_19>1</P_19> + exactly one of <P_19A>/<P_19B>/<P_19C>
        (b) <P_19N>1</P_19N>
    The two branches are mutually exclusive — when setting (a) we MUST remove (b).
  • <P_18A> is the 4th child of <Adnotacje>, type TWybor1_2 (values "1" or "2").

Fields used from Odoo 19 l10n_pl_edi:
  • _l10n_pl_edi_render_xml()   — render method we override
  • l10n_pl_edi_number          — accepted KSeF number (after acceptance)
  • l10n_pl_edi_ref             — temporary reference (during polling)
"""
import logging

from lxml import etree

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_MPP_THRESHOLD_PLN = 15000.0
_FA3_NS = 'http://crd.gov.pl/wzor/2025/06/25/13775/'
_VALID_GTU = {f'GTU_{n:02d}' for n in range(1, 14)}

# Children of <FaWiersz> that must come AFTER <GTU> in the xsd:sequence.
# When inserting GTU, we place it before the first of these that exists,
# or append at the end (safe when all later optional children are absent).
_FAWIERSZ_AFTER_GTU = ('Procedura', 'KursWaluty', 'StanPrzed')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── MPP / Split Payment (P_18A in KSeF FA(3)) ────────────────────────────
    l10n_pl_split_payment = fields.Boolean(
        string='Split Payment — MPP',
        tracking=True,
        help=(
            'Mechanizm Podzielonej Płatności. Mandatory for B2B invoices > PLN 15,000 '
            'containing goods/services in Annex 15 of the VAT Act. '
            'Sets P_18A=1 in KSeF FA(3) XML and adds the statutory annotation '
            '"mechanizm podzielonej płatności" to the invoice.'
        ),
    )

    # ── VAT exemption legal basis (P_19A in KSeF FA(3)) ──────────────────────
    # When set, the stock <Zwolnienie><P_19N>1</P_19N></Zwolnienie> is replaced
    # with <Zwolnienie><P_19>1</P_19><P_19A>...</P_19A></Zwolnienie>.
    l10n_pl_vat_exemption = fields.Selection([
        ('art43_1_2',   'Art. 43 ust. 1 pkt 2 — Używane towary'),
        ('art43_1_9',   'Art. 43 ust. 1 pkt 9 — Tereny niezabudowane'),
        ('art43_1_10',  'Art. 43 ust. 1 pkt 10 — Nieruchomości używane'),
        ('art43_1_10a', 'Art. 43 ust. 1 pkt 10a — Nieruchomości pierwsze zasiedlenie'),
        ('art43_1_18',  'Art. 43 ust. 1 pkt 18 — Usługi medyczne'),
        ('art43_1_19',  'Art. 43 ust. 1 pkt 19 — Usługi medyczne pozostałe'),
        ('art43_1_26',  'Art. 43 ust. 1 pkt 26 — Edukacja'),
        ('art43_1_27',  'Art. 43 ust. 1 pkt 27 — Korepetycje'),
        ('art43_1_29',  'Art. 43 ust. 1 pkt 29 — Kształcenie zawodowe'),
        ('art43_1_33',  'Art. 43 ust. 1 pkt 33 — Usługi kulturalne'),
        ('art43_1_34',  'Art. 43 ust. 1 pkt 34 — Usługi sportowe'),
        ('art43_1_36',  'Art. 43 ust. 1 pkt 36 — Najem mieszkalny'),
        ('art43_1_38',  'Art. 43 ust. 1 pkt 38 — Instrumenty finansowe'),
        ('art43_1_39',  'Art. 43 ust. 1 pkt 39 — Usługi finansowe'),
        ('art43_1_40',  'Art. 43 ust. 1 pkt 40 — Usługi płatnicze'),
        ('art43_1_41',  'Art. 43 ust. 1 pkt 41 — Obrót papierami wart.'),
        ('art113_1',    'Art. 113 ust. 1 — Zwolnienie do PLN 200k'),
        ('art113_9',    'Art. 113 ust. 9 — Zwolnienie w pierwszym roku'),
    ], string='Podstawa zwolnienia VAT', tracking=True,
       help='Podstawa prawna zwolnienia z VAT — wypełnia P_19A w FA(3).')

    # ── Onchange: suggest MPP when total ≥ PLN 15,000 ─────────────────────────
    @api.onchange('amount_total', 'currency_id')
    def _onchange_suggest_mpp(self):
        if self.move_type not in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
            return
        if (
            self.currency_id and self.currency_id.name == 'PLN'
            and self.amount_total >= _MPP_THRESHOLD_PLN
            and not self.l10n_pl_split_payment
        ):
            return {
                'warning': {
                    'title': 'Mechanizm Podzielonej Płatności',
                    'message': (
                        f'Wartość faktury ({self.amount_total:.2f} PLN) przekracza PLN '
                        f'{_MPP_THRESHOLD_PLN:,.0f}. Jeśli zawiera towary z Załącznika 15 '
                        'ustawy o VAT, włącz MPP (Split Payment).'
                    ),
                }
            }

    # ── FA(3) XML render override ────────────────────────────────────────────
    def _l10n_pl_edi_render_xml(self):
        """Render FA(3) XML via super, then post-process for GTU/MPP/VAT exemption fields."""
        xml_str = super()._l10n_pl_edi_render_xml()
        try:
            return self._l10n_pl_edi_postprocess_fa3(xml_str)
        except Exception as exc:
            # Defensive: never break invoice sending. Log and return stock XML.
            _logger.exception('FA(3) post-processing failed for %s: %s — using stock XML', self.name, exc)
            return xml_str

    def _l10n_pl_edi_postprocess_fa3(self, xml_str):
        """Inject GTU codes per FaWiersz, set P_18A flag, swap Zwolnienie branch."""
        # XXE-safe parser — even though the XML comes from our own template,
        # defense-in-depth is cheap and protects against future template changes
        # that might allow user-controlled fields with entity references.
        safe_parser = etree.XMLParser(
            resolve_entities=False, no_network=True,
            load_dtd=False, dtd_validation=False, huge_tree=False,
        )
        try:
            root = etree.fromstring(
                xml_str.encode('utf-8') if isinstance(xml_str, str) else xml_str,
                parser=safe_parser,
            )
        except etree.XMLSyntaxError as exc:
            _logger.warning('FA(3) post-process: XML parse failed — %s', exc)
            return xml_str

        ns = root.nsmap.get(None) or _FA3_NS
        nsmap = {'fa': ns}

        # ── 1. GTU per FaWiersz — element <GTU> with value GTU_01..GTU_13 ──
        gtu_by_line_idx = self._get_gtu_codes_by_line()
        if gtu_by_line_idx:
            wiersze = root.findall('.//fa:Fa/fa:FaWiersz', nsmap)
            for i, wiersz in enumerate(wiersze):
                gtu_code = gtu_by_line_idx.get(i)
                if not gtu_code or gtu_code not in _VALID_GTU:
                    continue
                if wiersz.find('fa:GTU', nsmap) is not None:
                    continue  # already emitted by some other extension
                gtu_el = etree.Element(f'{{{ns}}}GTU')
                gtu_el.text = gtu_code
                # Insert at correct position per xsd:sequence
                insert_at = len(wiersz)
                for idx, child in enumerate(wiersz):
                    local = etree.QName(child).localname
                    if local in _FAWIERSZ_AFTER_GTU:
                        insert_at = idx
                        break
                wiersz.insert(insert_at, gtu_el)

        # ── 2. P_18A — Split Payment flag inside Adnotacje ────────────────
        if self.l10n_pl_split_payment:
            p18a = root.find('.//fa:Fa/fa:Adnotacje/fa:P_18A', nsmap)
            if p18a is not None:
                p18a.text = '1'
            # If absent, do nothing — stock Odoo always emits it.

        # ── 3. Zwolnienie — replace <P_19N>1</P_19N> with <P_19>1</P_19> + <P_19A> ─
        if self.l10n_pl_vat_exemption:
            zwol = root.find('.//fa:Fa/fa:Adnotacje/fa:Zwolnienie', nsmap)
            if zwol is not None:
                # xsd:choice — wipe the existing branch (typically P_19N)
                for child in list(zwol):
                    zwol.remove(child)
                p19 = etree.SubElement(zwol, f'{{{ns}}}P_19')
                p19.text = '1'
                p19a = etree.SubElement(zwol, f'{{{ns}}}P_19A')
                p19a.text = self._format_vat_exemption_text()

        return etree.tostring(root, xml_declaration=True, encoding='UTF-8').decode('utf-8')

    def _get_gtu_codes_by_line(self):
        """Returns {line_index: 'GTU_XX'} for lines whose product carries a GTU code."""
        result = {}
        # Match the same line ordering Odoo's FA(3) template uses for FaWiersz:
        # non-display lines only, default ordering by sequence then id.
        lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
        for i, line in enumerate(lines):
            if not line.product_id:
                continue
            gtu = getattr(line.product_id.product_tmpl_id, 'l10n_pl_vat_gtu', None)
            if gtu:
                result[i] = gtu
        return result

    def _format_vat_exemption_text(self):
        """Human-readable description for P_19A from the selection key."""
        if not self.l10n_pl_vat_exemption:
            return ''
        selection_dict = dict(self._fields['l10n_pl_vat_exemption'].selection)
        return selection_dict.get(self.l10n_pl_vat_exemption, self.l10n_pl_vat_exemption)
