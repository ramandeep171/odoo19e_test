from odoo import models
from odoo.tools.misc import format_date


class AgreementPerformanceReport(models.AbstractModel):
    _name = 'report.rmc_mpc.report_agreement_performance'
    _description = 'Agreement Performance Summary Report Helper'

    def _get_report_values(self, docids, data=None):
        docs = self.env['rmc.contract.agreement'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'rmc.contract.agreement',
            'docs': docs,
            'format_date': format_date,
        }
