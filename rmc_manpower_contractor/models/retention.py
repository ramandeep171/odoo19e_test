# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero

from . import retention_common

_logger = logging.getLogger(__name__)


class RmcAgreementRetention(models.Model):
    _name = 'rmc.agreement.retention'
    _description = 'Manpower Agreement Retention Hold'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_release_date ASC, id DESC'

    name = fields.Char(string='Reference', default=lambda self: _('Retention Hold'), tracking=True, required=True)
    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade'
    )
    move_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        required=True,
        ondelete='cascade'
    )
    vendor_id = fields.Many2one(
        related='agreement_id.contractor_id',
        store=True,
        string='Vendor'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    base_amount = fields.Monetary(
        string='Retention Base',
        currency_field='currency_id',
        required=True
    )
    retention_rate = fields.Float(
        string='Retention %',
        digits=(12, 6),
        required=True
    )
    retention_amount = fields.Monetary(
        string='Retention Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    retention_base = fields.Selection(
        retention_common.RETENTION_BASE_SELECTION,
        string='Retention Base Type',
        required=True,
        default='untaxed'
    )
    retention_duration = fields.Selection(
        retention_common.RETENTION_DURATION_SELECTION,
        string='Retention Duration',
        required=True,
        default='90_days'
    )
    scheduled_release_date = fields.Date(
        string='Scheduled Release',
        required=True,
        tracking=True
    )
    released_date = fields.Date(
        string='Released On',
        copy=False
    )
    release_state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('released', 'Released'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='pending',
        tracking=True,
        required=True
    )
    auto_release = fields.Boolean(
        string='Auto Release',
        default=True,
        help='Automatically mark the retention as released on the scheduled date.'
    )
    notes = fields.Text(string='Notes')
    retention_move_line_id = fields.Many2one(
        'account.move.line',
        string='Retention Hold Line',
        copy=False
    )
    release_move_id = fields.Many2one(
        'account.move',
        string='Release Journal Entry',
        copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                agreement = self.env['rmc.contract.agreement'].browse(vals.get('agreement_id'))
                move = self.env['account.move'].browse(vals.get('move_id'))
                agreement_name = agreement.name or _('Agreement') if agreement else _('Agreement')
                bill_label = move.name or move.ref or _('Bill') if move else _('Bill')
                vals['name'] = '%s - %s' % (agreement_name, bill_label)
        return super().create(vals_list)

    @api.constrains('retention_amount')
    def _check_retention_amount(self):
        for record in self:
            if record.retention_amount <= 0.0:
                raise ValidationError(_('Retention amount must be positive.'))

    def action_release(self):
        """Mark retention as released."""
        today = fields.Date.context_today(self)
        for record in self.filtered(lambda r: r.release_state == 'pending'):
            record.write({
                'release_state': 'released',
                'released_date': today,
            })

    def action_cancel(self):
        """Cancel a scheduled retention release."""
        for record in self.filtered(lambda r: r.release_state == 'pending'):
            record.write({
                'release_state': 'cancelled',
                'released_date': False,
            })

    @api.model
    def cron_release_due_entries(self):
        """Cron job to auto release due retentions with accounting moves."""
        today = fields.Date.context_today(self)
        aml = self.env['account.move.line']
        domain = [
            ('rmc_retention_entry_id', '!=', False),
            ('rmc_retention_release_due_date', '!=', False),
            ('rmc_retention_release_due_date', '<=', today),
            ('reconciled', '=', False),
            ('company_id', '!=', False),
            ('parent_state', '=', 'posted'),
        ]
        due_lines = aml.search(domain)
        due_lines = due_lines.filtered(
            lambda line: line.rmc_retention_entry_id
            and line.rmc_retention_entry_id.release_state == 'pending'
            and line.rmc_retention_entry_id.auto_release
        )
        if not due_lines:
            return
        group_by_agreement = self._should_group_release_by_agreement()
        grouped_lines = self._group_lines_for_release(due_lines, group_by_agreement)
        for key, lines in grouped_lines.items():
            try:
                self._process_release_group(lines, today, group_by_agreement)
            except ValidationError:
                # Bubble up so cron logs the configuration issue.
                raise
            except Exception:
                _logger.exception('Failed to auto-release retention group %s', key)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _should_group_release_by_agreement(self):
        param_value = self.env['ir.config_parameter'].sudo().get_param(
            'rmc_manpower_contractor.group_retention_release_by_agreement',
            '0'
        )
        return str(param_value).lower() in ('1', 'true', 'yes')

    def _group_lines_for_release(self, lines, group_by_agreement):
        grouped = {}
        for line in lines:
            company_id = line.company_id.id
            if group_by_agreement:
                agreement = line.rmc_retention_entry_id.agreement_id
                key = (company_id, agreement.id)
            else:
                partner = line.partner_id.commercial_partner_id if line.partner_id else False
                key = (company_id, partner.id if partner else 0)
            if key in grouped:
                grouped[key] = grouped[key] | line
            else:
                grouped[key] = line
        return grouped

    def _process_release_group(self, lines, release_date, group_by_agreement):
        lines = lines.filtered(lambda l: not l.reconciled)
        if not lines:
            return
        company = lines[0].company_id
        retention_account = lines[0].account_id
        general_journal = self._get_general_journal(company)
        bank_account = self._get_bank_account(company)

        agreement = lines[0].rmc_retention_entry_id.agreement_id
        partner = lines[0].partner_id.commercial_partner_id if lines[0].partner_id else False
        if group_by_agreement and agreement:
            partner = agreement.contractor_id or partner
            target_label = agreement.display_name or agreement.name
        else:
            target_label = partner.display_name if partner else _('Vendor')

        total_company_amount = sum(abs(line.amount_residual) for line in lines)
        if float_is_zero(total_company_amount, precision_rounding=company.currency_id.rounding):
            return
        currency, amount_currency = self._compute_currency_components(lines)
        ref = _('Retention Release — %s') % target_label

        debit_vals = {
            'name': ref,
            'partner_id': partner.id if partner else False,
            'account_id': retention_account.id,
            'debit': total_company_amount,
            'credit': 0.0,
        }
        credit_vals = {
            'name': ref,
            'partner_id': partner.id if partner else False,
            'account_id': bank_account.id,
            'debit': 0.0,
            'credit': total_company_amount,
        }
        if currency and not float_is_zero(amount_currency, precision_rounding=currency.rounding):
            debit_vals.update({
                'currency_id': currency.id,
                'amount_currency': amount_currency,
            })
            credit_vals.update({
                'currency_id': currency.id,
                'amount_currency': -amount_currency,
            })

        move_vals = {
            'move_type': 'entry',
            'journal_id': general_journal.id,
            'company_id': company.id,
            'date': release_date,
            'ref': ref,
            'line_ids': [
                (0, 0, debit_vals),
                (0, 0, credit_vals),
            ],
        }
        release_move = self.env['account.move'].create(move_vals)
        release_move.action_post()
        debit_release_line = release_move.line_ids.filtered(
            lambda l: l.account_id == retention_account and l.debit
        )
        (lines | debit_release_line).reconcile()

        entries = lines.mapped('rmc_retention_entry_id')
        entries.write({
            'release_state': 'released',
            'released_date': release_date,
            'release_move_id': release_move.id,
        })
        message = _('Retention released on %s') % release_date
        bills = entries.mapped('move_id')
        for bill in bills:
            bill.message_post(body=message)
            bill.retention_release_date = release_date

    def _compute_currency_components(self, lines):
        currencies = lines.mapped('currency_id').filtered(lambda c: c)
        if not currencies:
            return False, 0.0
        unique = set(currencies.ids)
        if len(unique) > 1:
            return False, 0.0
        currency = currencies[0]
        total = sum(abs(line.amount_residual_currency) for line in lines)
        return currency, total

    def _get_general_journal(self, company):
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            raise ValidationError(
                _('Please configure a General Journal for company %s to process retention releases.') % company.name
            )
        return journal

    def _get_bank_account(self, company):
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
            ('default_account_id', '!=', False),
        ], limit=1)
        if not journal:
            raise ValidationError(
                _('Please configure a Bank journal with a default account for company %s to process retention releases.') % company.name
            )
        if not journal.default_account_id.reconcile:
            journal.default_account_id.reconcile = True
        return journal.default_account_id
