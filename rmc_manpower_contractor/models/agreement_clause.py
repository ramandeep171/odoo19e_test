# -*- coding: utf-8 -*-
"""
Agreement clause models
- Templates define the default clause structure per contract type
- Agreement-specific clauses are copied from templates and remain editable
"""

from odoo import fields, models, _


class AgreementClauseTemplate(models.Model):
    _name = 'rmc.agreement.clause.template'
    _description = 'Agreement Clause Template'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    contract_type = fields.Selection(
        selection=[
            ('driver_transport', 'Transport/Driver Contract'),
            ('pump_ops', 'Workforce Supply & Operations Agreement'),
            ('accounts_audit', 'Accounts & Auditor Manpower'),
        ],
        required=True,
        help='Contract type this clause template applies to.'
    )
    sequence = fields.Integer(default=10, help='Display order for clauses.')
    title = fields.Char(required=True, translate=True, default=lambda self: _('New Clause'))
    body_html = fields.Html(
        string='Clause Content',
        translate=True,
        sanitize=False,
        help='Default rich-text content for this clause.'
    )


class AgreementClause(models.Model):
    _name = 'rmc.agreement.clause'
    _description = 'Agreement Clause'
    _order = 'sequence, id'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer(default=10)
    title = fields.Char(required=True, default=lambda self: _('New Clause'))
    body_html = fields.Html(string='Clause Content', sanitize=False)

    contract_type = fields.Selection(
        related='agreement_id.contract_type',
        string='Contract Type',
        store=True
    )
