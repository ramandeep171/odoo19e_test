# -*- coding: utf-8 -*-
"""Agreement term change log model."""

from odoo import api, fields, models, _


class RmcAgreementChangeLog(models.Model):
    """Stores JSON deltas for agreement renewal changes."""

    _name = 'rmc.agreement.change.log'
    _description = 'Agreement Change Log'
    _order = 'changed_on desc, id desc'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade',
    )
    changed_by_id = fields.Many2one(
        'res.users',
        string='Changed By',
        ondelete='set null',
        default=lambda self: self.env.user,
    )
    changed_on = fields.Datetime(
        string='Changed On',
        required=True,
        default=fields.Datetime.now,
    )
    delta_json = fields.Json(string='Delta JSON', readonly=True)
    name = fields.Char(string='Description', compute='_compute_name')

    @api.depends('agreement_id', 'changed_on')
    def _compute_name(self):
        for record in self:
            if record.changed_on:
                timestamp = fields.Datetime.to_string(record.changed_on)
                record.name = _('Change on %s') % timestamp
            else:
                record.name = _('Change Log Entry')
