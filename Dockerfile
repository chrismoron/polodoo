FROM odoo:19.0

# Install Python packages required by OCA modules:
#   xlsxwriter — OCA report_xlsx (required for Excel exports in account_financial_report)
#   xlrd       — reading Excel files (required by report_xlsx)
#   requests   — explicit declaration (used by l10n_pl_nbp_rates; likely already present
#                as Odoo transitive dep, but declaring ensures availability)
USER root
RUN pip3 install --no-cache-dir xlsxwriter xlrd
USER odoo
