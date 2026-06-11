"""Load the l10n_pl chart of accounts for the existing company.

Run via:
    docker compose --env-file .env run --rm --no-deps odoo \
        odoo shell -d <db> --no-http < scripts/load_pl_chart.py

What it does:
  1. Activates the PLN currency record.
  2. Sets the only company's currency_id to PLN.
  3. Calls account.chart.template._try_loading('pl', company) which deploys
     the Polish chart of accounts, the 23/8/5/0/ZW VAT rates, fiscal
     positions, and journals — same logic Odoo runs on first-time install
     for a Poland-based company.

Idempotent: safe to re-run.
"""

env_obj = env  # provided by odoo shell

company = env_obj['res.company'].browse(1)
print(f"[load_pl_chart] company: {company.name} (id={company.id})")

pln = env_obj['res.currency'].with_context(active_test=False).search([('name', '=', 'PLN')], limit=1)
if not pln:
    raise RuntimeError("PLN currency record not found in res_currency")
if not pln.active:
    pln.active = True
    print("[load_pl_chart] PLN currency activated")
else:
    print("[load_pl_chart] PLN currency already active")

if company.currency_id != pln:
    company.sudo().write({'currency_id': pln.id})
    print(f"[load_pl_chart] company currency: {company.currency_id.name}")
else:
    print(f"[load_pl_chart] company currency already PLN")

pl_country = env_obj['res.country'].search([('code', '=', 'PL')], limit=1)
if company.partner_id.country_id != pl_country:
    company.partner_id.country_id = pl_country
    print("[load_pl_chart] company partner country: Poland")

# Trigger the l10n_pl chart template install.
template_model = env_obj['account.chart.template']
print("[load_pl_chart] installing 'pl' chart template…")
template_model.with_context(allowed_company_ids=[company.id]).try_loading('pl', company, install_demo=False)
print("[load_pl_chart] chart template loaded")

env_obj.cr.commit()
print("[load_pl_chart] committed")
