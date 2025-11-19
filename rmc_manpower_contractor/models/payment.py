# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero

class AccountMove(models.Model):
    _inherit = 'account.move'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='RMC Agreement',
        help='Link to RMC contractor agreement'
    )
    retention_entry_ids = fields.One2many(
        'rmc.agreement.retention',
        'move_id',
        string='Retention Holds',
        readonly=True
    )
    retention_amount = fields.Monetary(
        string='Retention Amount',
        currency_field='currency_id',
        readonly=True,
        copy=False
    )
    retention_base_amount = fields.Monetary(
        string='Retention Base',
        currency_field='currency_id',
        readonly=True,
        copy=False
    )
    retention_release_date = fields.Date(
        string='Retention Release Date',
        readonly=True,
        copy=False
    )
    retention_move_id = fields.Many2one(
        'account.move',
        string='Retention Journal Entry',
        readonly=True,
        copy=False
    )
    x_retention_booked = fields.Boolean(
        string='Retention Booked',
        readonly=True,
        copy=False
    )
    x_agreement_id = fields.Many2one(
        related='agreement_id',
        string='Retention Agreement',
        store=True,
        readonly=True
    )
    release_due_date = fields.Date(
        string='Retention Release Due',
        readonly=True,
        copy=False
    )

    @api.constrains('agreement_id', 'move_type')
    def _check_payment_hold(self):
        """
        Before creating/validating a vendor bill linked to an agreement,
        check if payment is on hold
        """
        for move in self:
            if move.agreement_id and move.move_type == 'in_invoice':
                if move.agreement_id.payment_hold:
                    reasons = move.agreement_id.payment_hold_reason or 'Unknown reasons'
                    raise ValidationError(
                        _('Payment on hold for agreement %s.\n\nReasons:\n%s') % 
                        (move.agreement_id.name, reasons)
                    )
                
                if not move.agreement_id.is_signed():
                    raise ValidationError(
                        _('Cannot create vendor bill: Agreement %s is not signed yet.') % 
                        move.agreement_id.name
                    )

    def action_post(self):
        """Override to check payment hold before posting"""
        self._rmc_assign_agreements_for_vendor_bills()
        for move in self:
            if move.agreement_id and move.move_type == 'in_invoice':
                if move.agreement_id.payment_hold:
                    raise ValidationError(
                        _('Cannot post bill: Payment on hold for agreement %s.\n\n%s') % 
                        (move.agreement_id.name, move.agreement_id.payment_hold_reason)
                    )
        res = super(AccountMove, self).action_post()
        self._create_retention_entries()
        return res

    def button_draft(self):
        res = super().button_draft()
        for move in self:
            retention_move = move.retention_move_id
            if retention_move:
                if retention_move.state == 'posted':
                    retention_move.button_draft()
                retention_move.unlink()
        pending_entries = self.mapped('retention_entry_ids').filtered(lambda entry: entry.release_state == 'pending')
        if pending_entries:
            pending_entries.unlink()
        self.write({
            'retention_amount': 0.0,
            'retention_base_amount': 0.0,
            'retention_release_date': False,
            'release_due_date': False,
            'retention_move_id': False,
            'x_retention_booked': False,
        })
        return res

    def _create_retention_entries(self):
        for move in self:
            agreement = move.agreement_id
            if not agreement or move.move_type != 'in_invoice':
                continue
            retention_entry = agreement._create_retention_entry_from_bill(move)
            if retention_entry:
                move._rmc_book_retention_with_journal(agreement, retention_entry)

    def _compute_payment_state(self):
        previous_payment_states = {move.id: move.payment_state for move in self}
        previous_invoice_states = {move.id: move.state for move in self}
        super()._compute_payment_state()
        self._rmc_sync_billing_log_payment_state(previous_payment_states, previous_invoice_states)

    # -------------------------------------------------------------------------
    # RMC Agreement auto-linking helpers
    # -------------------------------------------------------------------------
    def _rmc_assign_agreements_for_vendor_bills(self):
        """Attempt to auto-link an active RMC agreement before posting."""
        for move in self:
            if move.move_type != 'in_invoice' or move.agreement_id:
                continue
            agreement = move._rmc_find_matching_agreement()
            if agreement:
                move.agreement_id = agreement.id

    def _rmc_find_matching_agreement(self):
        """Locate the agreement that matches the vendor bill context."""
        self.ensure_one()
        if self.move_type != 'in_invoice':
            return self.env['rmc.contract.agreement'].browse()
        partner = self.partner_id or self.commercial_partner_id
        vendor = partner.commercial_partner_id if partner else False
        if not vendor:
            return self.env['rmc.contract.agreement'].browse()
        company = self.company_id or self.env.company
        bill_date = self.invoice_date or self.date or fields.Date.context_today(self)
        Agreement = self.env['rmc.contract.agreement']
        analytic_id = self._rmc_get_single_analytic_account()

        base_domain = [
            ('state', '=', 'active'),
            ('contractor_id', '=', vendor.id),
            ('company_id', '=', company.id),
            '|', ('validity_start', '=', False), ('validity_start', '<=', bill_date),
            '|', ('validity_end', '=', False), ('validity_end', '>=', bill_date),
        ]
        domain = list(base_domain)
        if analytic_id:
            domain.append(('analytic_account_id', '=', analytic_id))

        agreement = self._rmc_pick_unique_agreement(domain)
        if agreement or not analytic_id:
            return agreement
        # Fallback to vendor-only match when analytic-specific match is missing.
        return self._rmc_pick_unique_agreement(base_domain)

    def _rmc_pick_unique_agreement(self, domain):
        """Search helper ensuring a single agreement is returned."""
        Agreement = self.env['rmc.contract.agreement']
        matches = Agreement.search(domain, limit=2)
        if len(matches) > 1:
            partner = self.partner_id or self.commercial_partner_id
            vendor_name = partner.display_name if partner else _('Unknown Vendor')
            raise ValidationError(
                _('Multiple manpower agreements match vendor bill %(bill)s for %(vendor)s. '
                  'Please set the agreement manually or refine the analytic account.') % {
                      'bill': self.display_name or self.name or self.id,
                      'vendor': vendor_name,
                  }
            )
        return matches

    def _rmc_get_single_analytic_account(self):
        """Extract the analytic account used across invoice lines, if unique."""
        self.ensure_one()
        analytic_ids = set()
        for line in self.invoice_line_ids:
            if line.display_type:
                continue
            distribution = line.analytic_distribution or {}
            if isinstance(distribution, dict):
                for account_key, percentage in distribution.items():
                    if not percentage:
                        continue
                    account_id = self._rmc_normalize_analytic_key(account_key)
                    if account_id:
                        analytic_ids.add(account_id)
            elif hasattr(line, 'analytic_account_id') and line.analytic_account_id:
                analytic_ids.add(line.analytic_account_id.id)
        if len(analytic_ids) > 1:
            raise ValidationError(
                _('Cannot auto-detect an agreement because bill %s uses multiple analytic accounts. '
                  'Please split the bill or assign a single analytic account.') % 
                (self.display_name or self.name or self.id)
            )
        return analytic_ids.pop() if analytic_ids else False

    @staticmethod
    def _rmc_normalize_analytic_key(raw_key):
        """Convert analytic_distribution key to an integer id."""
        if isinstance(raw_key, int):
            return raw_key
        if isinstance(raw_key, str):
            try:
                return int(raw_key)
            except ValueError:
                return False
        if hasattr(raw_key, 'id'):
            return raw_key.id
        return False
    def _rmc_book_retention_with_journal(self, agreement, retention_entry):
        self.ensure_one()
        if not retention_entry:
            return False
        currency = self.currency_id or self.company_currency_id or self.env.company.currency_id
        rounding = currency.rounding if currency else 0.01
        retention_amount = retention_entry.retention_amount or 0.0
        if float_is_zero(retention_amount, precision_rounding=rounding):
            return False
        journal = self._rmc_get_general_journal()
        payable_lines = self._rmc_get_payable_lines()
        payable_account = payable_lines[0].account_id
        payable_partner = payable_lines[0].partner_id or self.partner_id or self.commercial_partner_id
        retention_account = self._rmc_get_retention_payable_account()
        release_due_date = retention_entry.scheduled_release_date
        partner = payable_partner
        rate = retention_entry.retention_rate or agreement.retention_rate or 0.0
        rate_label = ('%.2f' % rate).rstrip('0').rstrip('.') or '0'
        ref = _('Retention %(rate)s%% for %(bill)s [Agreement %(agreement)s]') % {
            'rate': rate_label,
            'bill': self.display_name or self.name or _('Bill'),
            'agreement': agreement.name,
        }
        retention_move_vals = self._rmc_prepare_retention_move_vals(
            journal,
            ref,
            payable_account,
            retention_account,
            retention_amount,
            partner,
        )
        retention_move = self.env['account.move'].create(retention_move_vals)
        retention_move.action_post()
        self._rmc_reconcile_retention_lines(payable_lines, retention_move, payable_account, partner)
        self.write({
            'retention_move_id': retention_move.id,
            'x_retention_booked': True,
        })
        retention_line = retention_move.line_ids.filtered(
            lambda l: l.account_id == retention_account and l.credit
        )
        if retention_line:
            retention_line.write({
                'rmc_retention_entry_id': retention_entry.id,
                'rmc_retention_release_due_date': release_due_date,
            })
            retention_entry.retention_move_line_id = retention_line.id
        return retention_move

    def _rmc_get_general_journal(self):
        company = self.company_id or self.env.company
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            raise ValidationError(
                _('Please configure a General Journal for company %s to book retention holds.') % company.name
            )
        return journal

    def _rmc_get_retention_payable_account(self):
        company = self.company_id or self.env.company
        Account = self.env['account.account']
        domain = [('code', '=', '210950')]
        if 'company_id' in Account._fields:
            domain.append(('company_id', '=', company.id))
        elif 'company_ids' in Account._fields:
            domain.append(('company_ids', 'in', company.id))
        account = Account.search(domain, limit=1)
        if not account:
            raise ValidationError(
                _('Retention Payable account (code 210950) is missing for company %s.') % company.name
            )
        return account

    def _rmc_get_payable_lines(self):
        self.ensure_one()
        partner = self.partner_id or self.commercial_partner_id
        commercial_partner = partner.commercial_partner_id if partner else False

        def _is_payable_account(account):
            if not account:
                return False
            internal_type = getattr(account, 'internal_type', False)
            account_type = getattr(account, 'account_type', False)
            user_type = getattr(account, 'user_type_id', False)
            return (
                internal_type == 'payable'
                or account_type in ('liability_payable', 'payable')
                or (user_type and getattr(user_type, 'type', False) == 'payable')
            )

        lines = self.line_ids.filtered(
            lambda l: not l.display_type
            and _is_payable_account(l.account_id)
            and (
                not commercial_partner
                or not l.partner_id
                or l.partner_id.commercial_partner_id == commercial_partner
            )
        )
        if not lines and commercial_partner:
            lines = self.line_ids.filtered(
                lambda l: not l.display_type
                and l.partner_id
                and l.partner_id.commercial_partner_id == commercial_partner
                and getattr(l.account_id, 'reconcile', False)
            )
        if not lines:
            lines = self.line_ids.filtered(
                lambda l: not l.display_type and getattr(l.account_id, 'reconcile', False)
            )
        if not lines:
            fallback_account = False
            if partner:
                fallback_account = partner.property_account_payable_id
            if not fallback_account and commercial_partner:
                fallback_account = commercial_partner.property_account_payable_id
            if fallback_account:
                lines = self.line_ids.filtered(
                    lambda l: not l.display_type and l.account_id == fallback_account
                )
        if not lines:
            PayableLine = self.env['account.move.line']
            domain = [
                ('move_id', '=', self.id),
                ('account_id.reconcile', '=', True),
                ('display_type', '!=', 'line_note'),
            ]
            fallback_lines = PayableLine.search(domain)
            if commercial_partner:
                fallback_lines = fallback_lines.filtered(
                    lambda l: not l.partner_id
                    or l.partner_id.commercial_partner_id == commercial_partner
                )
            if not fallback_lines:
                fallback_lines = PayableLine.search(
                    domain + [('account_id.internal_type', '=', 'payable')]
                )
            lines = fallback_lines
        if not lines:
            raise ValidationError(
                _('No payable line found on vendor bill %s to book the retention entry.') %
                (self.display_name or self.name or self.id)
            )
        return lines

    def _rmc_prepare_retention_move_vals(self, journal, ref, payable_account, retention_account, retention_amount, partner):
        self.ensure_one()
        company = self.company_id or self.env.company
        currency = self.currency_id or company.currency_id
        company_currency = company.currency_id
        date = self.invoice_date or self.date or fields.Date.context_today(self)
        amount_company = retention_amount
        if currency and company_currency and currency != company_currency:
            amount_company = currency._convert(retention_amount, company_currency, company, date)
        debit_line = {
            'name': ref,
            'partner_id': partner.id if partner else False,
            'account_id': payable_account.id,
            'debit': amount_company,
            'credit': 0.0,
        }
        credit_line = {
            'name': ref,
            'partner_id': partner.id if partner else False,
            'account_id': retention_account.id,
            'debit': 0.0,
            'credit': amount_company,
        }
        if currency and company_currency and currency != company_currency:
            debit_line.update({
                'currency_id': currency.id,
                'amount_currency': retention_amount,
            })
            credit_line.update({
                'currency_id': currency.id,
                'amount_currency': -retention_amount,
            })
        return {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': date,
            'ref': ref,
            'company_id': company.id,
            'line_ids': [
                (0, 0, debit_line),
                (0, 0, credit_line),
            ],
        }

    def _rmc_reconcile_retention_lines(self, bill_payable_lines, retention_move, payable_account, partner):
        if not retention_move:
            return
        retention_lines = retention_move.line_ids.filtered(
            lambda l: l.account_id == payable_account and (not partner or l.partner_id == partner)
        )
        bill_lines = bill_payable_lines.filtered(lambda l: not l.reconciled and l.account_id == payable_account)
        if not bill_lines or not retention_lines:
            return
        (bill_lines | retention_lines).reconcile()

    # -------------------------------------------------------------------------
    # Billing log lifecycle syncing
    # -------------------------------------------------------------------------

    def _rmc_sync_billing_log_payment_state(self, previous_payment_states, previous_invoice_states):
        Log = self.env['rmc.billing.prepare.log']
        for move in self:
            if move.move_type != 'in_invoice':
                continue
            previous_payment = previous_payment_states.get(move.id)
            previous_state = previous_invoice_states.get(move.id)
            payment_changed = move.payment_state != previous_payment
            invoice_state_changed = move.state != previous_state
            if not (payment_changed or invoice_state_changed):
                continue
            logs = Log.search([('bill_id', '=', move.id)])
            if not logs:
                continue
            target_state = move._rmc_target_billing_log_state()
            to_update = logs.filtered(lambda log: log.state != target_state)
            if to_update:
                to_update.write({'state': target_state})

    def _rmc_target_billing_log_state(self):
        self.ensure_one()
        if self.payment_state == 'paid':
            return 'paid'
        if self.state != 'posted':
            return 'review'
        return 'done'


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    rmc_retention_entry_id = fields.Many2one(
        'rmc.agreement.retention',
        string='Retention Entry',
        copy=False,
        index=True
    )
    rmc_retention_release_due_date = fields.Date(
        string='Retention Release Due',
        copy=False
    )
