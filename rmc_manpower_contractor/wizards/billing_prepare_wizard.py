# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.misc import format_date
from datetime import datetime, time
from collections import defaultdict
import base64
import logging

_logger = logging.getLogger(__name__)

class RmcBillingPrepareWizard(models.Model):
    _name = 'rmc.billing.prepare.wizard'
    _description = 'RMC Monthly Billing Preparation Wizard'
    _order = 'create_date desc'

    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', required=True, readonly=True)
    contractor_id = fields.Many2one(related='agreement_id.contractor_id', string='Contractor', readonly=True)
    period_start = fields.Date(string='Period Start', required=True, default=lambda self: fields.Date.today().replace(day=1))
    period_end = fields.Date(string='Period End', required=True)
    
    # Part-A (Fixed)
    part_a_amount = fields.Monetary(string='Part-A Fixed', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    part_a_raw_total = fields.Monetary(
        string='Part-A Raw Total',
        compute='_compute_billing_amounts',
        store=True,
        currency_field='currency_id',
        help='Straight sum of Part-A manpower line amounts before attendance proration.'
    )
    part_a_attendance_adjusted = fields.Monetary(
        string='Part-A Attendance Adjusted',
        compute='_compute_billing_amounts',
        store=True,
        currency_field='currency_id',
        help='Total Part-A amount after applying attendance proration on each manpower line.'
    )
    
    # Part-B (Variable)
    mgq_achieved = fields.Float(string='MGQ Achieved (m³)', digits='Product Unit of Measure')
    mgq_target = fields.Float(related='agreement_id.mgq_target', string='MGQ Target', readonly=True)
    mgq_achievement_pct = fields.Float(string='MGQ Achievement %', compute='_compute_mgq', store=True, digits=(5, 2))
    part_b_amount = fields.Monetary(string='Part-B Variable', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    prime_output_qty = fields.Float(
        string='Prime Output (m³)',
        digits='Product Unit of Measure',
        help='Prime output booked against this agreement for the billing period.'
    )
    optimized_standby_qty = fields.Float(
        string='Optimized Standby (m³)',
        digits='Product Unit of Measure',
        help='Standby delta corresponding to the billing period.'
    )
    
    # Breakdown deductions (Clause 9)
    breakdown_deduction = fields.Monetary(string='Breakdown Deductions', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Performance bonus/penalty
    performance_score = fields.Float(related='agreement_id.performance_score', string='Performance Score', readonly=True)
    stars = fields.Selection(related='agreement_id.stars', string='Stars', readonly=True)
    bonus_penalty_pct = fields.Float(string='Bonus/Penalty %', compute='_compute_bonus_penalty', store=True, help='Positive = bonus, Negative = penalty')
    bonus_penalty_amount = fields.Monetary(string='Bonus/Penalty Amount', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Inventory variance
    inventory_variance = fields.Monetary(string='Inventory Variance', compute='_compute_billing_amounts', store=True, currency_field='currency_id', help='Material shortage/excess')
    
    # Total
    subtotal = fields.Monetary(string='Subtotal (before TDS)', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    tds_amount = fields.Monetary(string='TDS 194C (2%)', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    total_amount = fields.Monetary(string='Net Payable', compute='_compute_billing_amounts', store=True, currency_field='currency_id')

    currency_id = fields.Many2one(related='agreement_id.currency_id', string='Currency', readonly=True)
    attendance_breakdown_html = fields.Html(
        string='Attendance Breakdown',
        compute='_compute_billing_amounts',
        sanitize=False,
        help='Rendered table summarising attendance proration inputs for each manpower line.'
    )
    
    # Supporting reports
    attach_attendance = fields.Boolean(string='Attach Attendance Report', default=True)
    attach_diesel = fields.Boolean(string='Attach Diesel Report', default=True)
    attach_maintenance = fields.Boolean(string='Attach Maintenance Report', default=True)
    attach_breakdown = fields.Boolean(string='Attach Breakdown Report', default=True)
    
    # Approval state
    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('supervisor', 'Awaiting Supervisor'),
        ('manager', 'Awaiting Manager'),
        ('finance', 'Awaiting Finance'),
        ('accounts', 'Awaiting Accounts'),
        ('approved', 'Approved')
    ], string='Approval Status', default='draft', required=True)
    
    state = fields.Selection([('prepare', 'Prepare'), ('review', 'Review'), ('done', 'Done')], default='prepare', required=True)
    notes = fields.Text(string='Notes')

    @api.depends('mgq_achieved', 'mgq_target')
    def _compute_mgq(self):
        for wizard in self:
            if wizard.mgq_target > 0:
                wizard.mgq_achievement_pct = (wizard.mgq_achieved / wizard.mgq_target) * 100
            else:
                wizard.mgq_achievement_pct = 0.0

    @api.onchange('agreement_id')
    def _onchange_agreement_id(self):
        from_log_id = self.env.context.get('from_log_id')
        for wizard in self:
            if not wizard.agreement_id:
                continue
            if from_log_id:
                continue
            wizard.prime_output_qty = wizard.agreement_id.prime_output_qty or 0.0
            wizard.optimized_standby_qty = wizard.agreement_id.optimized_standby_qty or 0.0
        self._sync_mgq_with_prime_output()

    @api.onchange('prime_output_qty')
    def _onchange_prime_output_qty(self):
        self._sync_mgq_with_prime_output()

    def _sync_mgq_with_prime_output(self):
        for wizard in self:
            prime = wizard.prime_output_qty or 0.0
            standby = wizard.optimized_standby_qty or 0.0
            wizard.mgq_achieved = prime + standby

    @api.depends('performance_score', 'stars')
    def _compute_bonus_penalty(self):
        """
        Star-based bonus/penalty
        5 stars: +10%
        4 stars: +5%
        3 stars: 0%
        2 stars: -5%
        1 star: -10%
        """
        ICP = self.env['ir.config_parameter'].sudo()
        bonus_5 = float(ICP.get_param('rmc_billing.bonus_5_star', 10.0))
        bonus_4 = float(ICP.get_param('rmc_billing.bonus_4_star', 5.0))
        penalty_2 = float(ICP.get_param('rmc_billing.penalty_2_star', -5.0))
        penalty_1 = float(ICP.get_param('rmc_billing.penalty_1_star', -10.0))
        
        for wizard in self:
            if wizard.stars == '5':
                wizard.bonus_penalty_pct = bonus_5
            elif wizard.stars == '4':
                wizard.bonus_penalty_pct = bonus_4
            elif wizard.stars == '3':
                wizard.bonus_penalty_pct = 0.0
            elif wizard.stars == '2':
                wizard.bonus_penalty_pct = penalty_2
            elif wizard.stars == '1':
                wizard.bonus_penalty_pct = penalty_1
            else:
                wizard.bonus_penalty_pct = 0.0

    def _apply_attendance_proration(self):
        """Populate attendance days on manpower lines based on compliance records."""
        self.ensure_one()
        if not self.agreement_id or not self.period_start or not self.period_end:
            return
        part_a_lines = self.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_a')
        if not part_a_lines:
            return
        start_date = fields.Date.to_date(self.period_start)
        end_date = fields.Date.to_date(self.period_end)
        if not start_date or not end_date or end_date < start_date:
            return
        scheduled_days = (end_date - start_date).days + 1
        Attendance = self.env['rmc.attendance.compliance']
        attendance_records = Attendance.search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
        ])
        employee_present_days = defaultdict(float)
        total_man_days = 0.0
        for record in attendance_records:
            if not record.date:
                continue
            total_man_days += record.headcount_present or 0.0
            for employee in record.employee_ids:
                employee_present_days[employee.id] += 1.0
        total_part_a_headcount = sum(part_a_lines.mapped('headcount')) or 0.0
        expected_man_days = total_part_a_headcount * scheduled_days
        if attendance_records and expected_man_days:
            fallback_ratio = total_man_days / expected_man_days
        else:
            fallback_ratio = 1.0
        fallback_ratio = max(0.0, min(fallback_ratio, 1.0))

        for line in part_a_lines:
            total_days = float(scheduled_days) if scheduled_days > 0 else 0.0
            if not total_days:
                present_days = 0.0
            elif line.employee_id:
                present_days = min(employee_present_days.get(line.employee_id.id, 0.0), total_days)
            else:
                present_days = total_days * fallback_ratio
            vals = {
                'attendance_total_days': total_days,
                'attendance_present_days': present_days,
            }
            # Avoid unnecessary writes when values already in sync
            if (
                line.attendance_total_days != vals['attendance_total_days'] or
                line.attendance_present_days != vals['attendance_present_days']
            ):
                line.with_context(rmc_attendance_proration=True).write(vals)

    @api.depends(
        'agreement_id.manpower_matrix_ids.remark',
        'agreement_id.manpower_matrix_ids.total_amount',
        'agreement_id.manpower_matrix_ids.attendance_prorated_amount',
        'agreement_id.manpower_matrix_ids.attendance_present_days',
        'agreement_id.manpower_matrix_ids.attendance_total_days',
        'mgq_achievement_pct',
        'bonus_penalty_pct',
        'period_start',
        'period_end'
    )
    def _compute_billing_amounts(self):
        for wizard in self:
            # Part-A: Sum of all Part-A entries in manpower matrix
            part_a_lines = wizard.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_a')
            raw_part_a = sum(part_a_lines.mapped('total_amount'))
            prorated_part_a = sum(part_a_lines.mapped('attendance_prorated_amount'))
            if not part_a_lines:
                fallback = wizard.agreement_id.part_a_fixed or wizard.agreement_id.manpower_part_a_amount or 0.0
                raw_part_a = fallback
                prorated_part_a = fallback
            wizard.part_a_raw_total = raw_part_a
            wizard.part_a_attendance_adjusted = prorated_part_a
            wizard.part_a_amount = prorated_part_a

            # Part-B: Variable component based on MGQ achievement
            part_b_lines = wizard.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_b')
            part_b_base = sum(part_b_lines.mapped('total_amount'))
            if not part_b_base:
                part_b_base = wizard.agreement_id.part_b_variable or wizard.agreement_id.manpower_part_b_amount or 0.0
            
            # Apply MGQ achievement factor (if MGQ < 100%, reduce Part-B proportionally)
            if wizard.mgq_achievement_pct >= 100:
                wizard.part_b_amount = part_b_base
            else:
                wizard.part_b_amount = part_b_base * (wizard.mgq_achievement_pct / 100.0)
            
            # Breakdown deductions (Clause 9)
            breakdown_events = wizard.env['rmc.breakdown.event'].search([
                ('agreement_id', '=', wizard.agreement_id.id),
                ('start_time', '>=', wizard.period_start),
                ('start_time', '<=', wizard.period_end),
                ('state', 'in', ('confirmed', 'closed'))
            ])
            wizard.breakdown_deduction = sum(breakdown_events.mapped('deduction_amount'))
            
            # Inventory variance
            inventory_items = wizard.env['rmc.inventory.handover'].search([
                ('agreement_id', '=', wizard.agreement_id.id),
                ('date', '>=', wizard.period_start),
                ('date', '<=', wizard.period_end),
                ('state', '!=', 'reconciled')
            ])
            wizard.inventory_variance = sum(inventory_items.mapped('variance_value'))
            
            # Bonus/Penalty
            base_for_bonus = wizard.part_a_amount + wizard.part_b_amount
            wizard.bonus_penalty_amount = base_for_bonus * (wizard.bonus_penalty_pct / 100.0)

            # Subtotal
            wizard.subtotal = (wizard.part_a_amount + wizard.part_b_amount - 
                              wizard.breakdown_deduction + wizard.bonus_penalty_amount + 
                              wizard.inventory_variance)
            
            # TDS 194C @ 2% (Indian tax on contractor payments)
            wizard.tds_amount = wizard.subtotal * 0.02
            
            # Total
            wizard.total_amount = wizard.subtotal - wizard.tds_amount
            wizard.attendance_breakdown_html = wizard._build_attendance_breakdown(part_a_lines, with_summary=True)

    @api.constrains('period_start', 'period_end')
    def _check_periods(self):
        for wizard in self:
            if wizard.period_end < wizard.period_start:
                raise ValidationError(_('Period end must be after period start.'))

    def action_compute(self):
        """Recompute all amounts and reopen wizard in review mode."""
        self.ensure_one()
        self._sync_mgq_with_prime_output()
        self._apply_attendance_proration()
        self._compute_billing_amounts()
        self.state = 'review'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_create_bill(self):
        """
        Create vendor bill with all line items and attachments
        Apply multi-level approval chain
        """
        self.ensure_one()
        self._sync_mgq_with_prime_output()
        self._apply_attendance_proration()
        self._compute_billing_amounts()
        
        # Pre-flight checks
        if self.agreement_id.payment_hold:
            raise ValidationError(
                _('Cannot create bill: Payment on hold.\n\n%s') % 
                self.agreement_id.payment_hold_reason
            )
        
        if not self.agreement_id.is_signed():
            raise ValidationError(_('Cannot create bill: Agreement not signed.'))
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.contractor_id.id,
            'agreement_id': self.agreement_id.id,
            'invoice_date': fields.Date.today(),
            'date': fields.Date.today(),
            'ref': f'{self.agreement_id.name} - {self.period_start.strftime("%B %Y")}',
            'narration': f'Monthly billing for period {self.period_start} to {self.period_end}\n{self.notes or ""}',
        }
        if 'extract_state' in self.env['account.move']._fields:
            bill_vals['extract_state'] = 'done'
        
        bill = self.env['account.move'].create(bill_vals)

        # Collect source records used for both attachments and log summary
        source_records = self._collect_source_records()

        # Create invoice lines
        self._create_invoice_lines(bill)

        # Attach supporting reports
        attachments = self._attach_reports(bill, source_records)

        # Reconcile inventory
        self._reconcile_inventory()

        # Log snapshot
        self._create_billing_log(bill, attachments, source_records)
        
        # Post message
        bill.message_post(
            body=_(
                'Bill prepared by billing wizard.<br/>'
                'Part-A: %s<br/>'
                'Part-B: %s<br/>'
                'Breakdown Deduction: %s<br/>'
                'Bonus/Penalty: %s<br/>'
                'Inventory Variance: %s<br/>'
                'TDS: %s<br/>'
                '<b>Total: %s</b>'
            ) % (
                self.part_a_amount, self.part_b_amount, self.breakdown_deduction,
                self.bonus_penalty_amount, self.inventory_variance,
                self.tds_amount, self.total_amount
            ),
            subject=_('Monthly Bill Created')
        )
        
        # Create approval activities
        self._create_approval_chain(bill)
        
        self.state = 'done'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_billing_log(self, bill, attachments, source_records):
        """Persist a snapshot of the wizard data whenever a bill is created."""
        self.ensure_one()
        diesel_records = source_records.get('diesel') if source_records else self.env['rmc.diesel.log']
        _, total_issued, total_consumption = self._prepare_diesel_rows(diesel_records) if diesel_records else ([], 0.0, 0.0)
        log_vals = {
            'agreement_id': self.agreement_id.id,
            'wizard_id': self.id,
            'bill_id': bill.id if bill else False,
            'period_start': self.period_start,
            'period_end': self.period_end,
            'mgq_target': self.mgq_target,
            'mgq_achieved': self.mgq_achieved,
            'mgq_achievement_pct': self.mgq_achievement_pct,
            'prime_output_qty': self.prime_output_qty,
            'optimized_standby_qty': self.optimized_standby_qty,
            'part_a_raw_total': self.part_a_raw_total,
            'part_a_attendance_adjusted': self.part_a_attendance_adjusted,
            'part_a_amount': self.part_a_amount,
            'part_b_amount': self.part_b_amount,
            'breakdown_deduction': self.breakdown_deduction,
            'bonus_penalty_pct': self.bonus_penalty_pct,
            'bonus_penalty_amount': self.bonus_penalty_amount,
            'inventory_variance': self.inventory_variance,
            'subtotal': self.subtotal,
            'tds_amount': self.tds_amount,
            'total_amount': self.total_amount,
            'currency_id': self.currency_id.id,
            'attach_attendance': self.attach_attendance,
            'attach_diesel': self.attach_diesel,
            'attach_maintenance': self.attach_maintenance,
            'attach_breakdown': self.attach_breakdown,
            'notes': self.notes,
            'diesel_total_issued': total_issued,
            'diesel_total_fuel': total_consumption,
        }
        if not self.env.context.get('rmc_skip_log_autorefresh'):
            log_state = 'draft' if self.state == 'prepare' else self.state
            log_vals['state'] = log_state
        else:
            log_vals.pop('wizard_id', None)
        if source_records:
            log_vals.update({
                'attendance_record_ids': [(6, 0, source_records.get('attendance').ids if source_records.get('attendance') else [])],
                'diesel_record_ids': [(6, 0, source_records.get('diesel').ids if source_records.get('diesel') else [])],
                'maintenance_record_ids': [(6, 0, source_records.get('maintenance').ids if source_records.get('maintenance') else [])],
                'breakdown_record_ids': [(6, 0, source_records.get('breakdown').ids if source_records.get('breakdown') else [])],
                'attendance_preview_html': self._build_attendance_preview(source_records.get('attendance')),
                'attendance_breakdown_html': self.attendance_breakdown_html,
                'diesel_preview_html': self._build_diesel_preview(source_records.get('diesel')),
                'maintenance_preview_html': self._build_maintenance_preview(source_records.get('maintenance')),
                'breakdown_preview_html': self._build_breakdown_preview(source_records.get('breakdown')),
            })
        if attachments:
            log_vals.update({
                'attachment_ids': [(6, 0, attachments.get('all').ids if attachments.get('all') else [])],
                'attendance_attachment_id': attachments.get('attendance').id if attachments.get('attendance') else False,
                'diesel_attachment_id': attachments.get('diesel').id if attachments.get('diesel') else False,
                'maintenance_attachment_id': attachments.get('maintenance').id if attachments.get('maintenance') else False,
                'breakdown_attachment_id': attachments.get('breakdown').id if attachments.get('breakdown') else False,
            })
        from_log_id = self.env.context.get('from_log_id')
        log_model = self.env['rmc.billing.prepare.log']
        log = None
        if from_log_id:
            log = log_model.browse(from_log_id)
            if log and log.exists():
                log.with_context(rmc_skip_log_autorefresh=True).write(log_vals)
        if not log or not log.exists():
            log = log_model.create(log_vals)
        has_bill = bool(bill and bill.exists())
        if not self.env.context.get('rmc_skip_log_autorefresh') and has_bill:
            log.state = 'done'
        if attachments:
            log._sync_supporting_attachments(attachments, source_bill=bill)
        return log

    def _collect_source_records(self):
        """Fetch datasets per type for the selected period."""
        self.ensure_one()
        attendance_data = self.env['rmc.attendance.compliance'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
        ])

        diesel_data = self.env['rmc.diesel.log'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
        ])
        if not diesel_data:
            diesel_data = self._collect_fallback_diesel_logs()

        maintenance_data = self.env['rmc.maintenance.check'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
        ])

        breakdown_data = self.env['rmc.breakdown.event'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('start_time', '>=', self.period_start),
            ('start_time', '<=', self.period_end),
        ])

        return {
            'attendance': attendance_data,
            'diesel': diesel_data,
            'maintenance': maintenance_data,
            'breakdown': breakdown_data,
        }

    def _localize_datetime_to_date(self, dt_value):
        if not dt_value:
            return False
        dt_obj = fields.Datetime.to_datetime(dt_value)
        localized = fields.Datetime.context_timestamp(self, dt_obj)
        return localized.date()

    def _collect_fallback_diesel_logs(self):
        DieselBase = self.env['diesel.log']
        if 'rmc_agreement_id' not in DieselBase._fields:
            return self.env['rmc.diesel.log'].browse()
        start_dt = datetime.combine(self.period_start, time.min)
        end_dt = datetime.combine(self.period_end, time.max)
        domain = [
            ('log_type', '=', 'diesel'),
            ('state', 'in', ('approved', 'done')),
            ('rmc_agreement_id', '=', self.agreement_id.id),
            ('date', '>=', fields.Datetime.to_string(start_dt)),
            ('date', '<=', fields.Datetime.to_string(end_dt)),
        ]
        logs = DieselBase.search(domain, order='date asc')
        rmc_model = self.env['rmc.diesel.log']
        fallback = rmc_model.browse()
        for log in logs:
            opening = log.opening_diesel or 0.0
            issued = (getattr(log, 'issue_diesel', False) or log.quantity or 0.0)
            closing = log.closing_diesel or 0.0
            vals = {
                'agreement_id': self.agreement_id.id,
                'date': self._localize_datetime_to_date(log.date),
                'vehicle_id': log.vehicle_id.id if log.vehicle_id else False,
                'opening_ltr': opening,
                'issued_ltr': issued,
                'closing_ltr': closing,
                'work_done_m3': 0.0,
                'work_done_km': log.odometer_difference or 0.0,
                'diesel_efficiency': log.fuel_efficiency or 0.0,
                'efficiency_unit': log._get_odometer_unit_label() if hasattr(log, '_get_odometer_unit_label') else '',
                'state': log.state,
            }
            fallback |= rmc_model.new(vals)
        return fallback

    @staticmethod
    def _build_table(headers, rows):
        if not rows:
            return ''
        head_html = ''.join(f'<th>{header}</th>' for header in headers)
        body_html = ''.join(
            '<tr>' + ''.join(f'<td>{(value or "")}</td>' for value in row) + '</tr>'
            for row in rows
        )
        return (
            '<table class="table table-condensed o_main_table">'
            f'<thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>'
        )

    def _build_attendance_breakdown(self, lines, with_summary=False):
        if not lines:
            base_html = '<p>No Part-A manpower lines configured.</p>'
            if with_summary:
                summary_headers = [_('Metric'), _('Amount')]
                summary_rows = [
                    (_('Raw Part-A Total'), '0.00'),
                    (_('Attendance Adjusted Part-A'), '0.00'),
                    (_('Attendance Deduction'), '0.00'),
                ]
                summary_table = self._build_table(summary_headers, summary_rows)
                base_html = f"{base_html}<br/>{summary_table}"
            return base_html
        rows = []
        for line in lines:
            ratio_pct = (line.attendance_ratio or 0.0) * 100.0
            label = line.designation or line.job_position_name or line.employee_id.display_name or _('Line')
            present_days = line.attendance_present_days or 0.0
            total_days = line.attendance_total_days or 0.0
            rows.append((
                label,
                f'{present_days:.2f}',
                f'{total_days:.2f}',
                f'{ratio_pct:.1f}%',
                line.total_amount,
                line.attendance_prorated_amount,
                line.attendance_deduction_amount,
            ))
        headers = [
            _('Designation/Employee'),
            _('Present Days'),
            _('Scheduled Days'),
            _('Attendance %'),
            _('Base Part-A'),
            _('Prorated Part-A'),
            _('Deduction'),
        ]
        table_html = self._build_table(headers, rows)
        if with_summary:
            raw_total = self.part_a_raw_total or 0.0
            adjusted_total = self.part_a_attendance_adjusted or 0.0
            deduction_total = raw_total - adjusted_total
            summary_headers = [_('Metric'), _('Amount')]
            summary_rows = [
                (_('Raw Part-A Total'), f'{raw_total:.2f}'),
                (_('Attendance Adjusted Part-A'), f'{adjusted_total:.2f}'),
                (_('Attendance Deduction'), f'{deduction_total:.2f}'),
            ]
            summary_table = self._build_table(summary_headers, summary_rows)
            return f"{table_html}<br/>{summary_table}"
        return table_html

    def _build_attendance_preview(self, records):
        if not records:
            return '<p>No attendance records captured for this period.</p>'
        rows = [
            (rec.date, rec.headcount_present, rec.headcount_expected, f'{rec.compliance_percentage:.1f}%', rec.state)
            for rec in records
        ]
        return self._build_table(['Date', 'Present', 'Expected', 'Compliance %', 'State'], rows)

    def _prepare_diesel_rows(self, records):
        rows = []
        total_issued = 0.0
        total_consumption = 0.0
        for rec in records:
            issued = getattr(rec, 'issued_ltr', None)
            if issued is None:
                issued = getattr(rec, 'issue_diesel', 0.0)
            opening = getattr(rec, 'opening_ltr', 0.0)
            closing = getattr(rec, 'closing_ltr', 0.0)
            fuel_consumption = getattr(rec, 'fuel_consumption', None)
            if fuel_consumption in (None, False):
                fuel_consumption = (opening or 0.0) + (issued or 0.0) - (closing or 0.0)
            total_issued += issued or 0.0
            total_consumption += fuel_consumption or 0.0
            rows.append((
                rec.date,
                rec.vehicle_id.display_name if rec.vehicle_id else '',
                f'{(issued or 0.0):.2f}',
                f'{(fuel_consumption or 0.0):.2f}',
                rec.state,
            ))
        return rows, total_issued, total_consumption

    def _build_diesel_preview(self, records):
        if not records:
            return '<p>No diesel logs captured for this period.</p>'
        rows, total_issued, total_consumption = self._prepare_diesel_rows(records)
        rows.append((
            '<strong>Total</strong>',
            '',
            f'<strong>{total_issued:.2f}</strong>',
            f'<strong>{total_consumption:.2f}</strong>',
            ''
        ))
        return self._build_table([
            'Date',
            'Vehicle',
            'Issued (L)',
            'Fuel Consumption (L)',
            'State'
        ], rows)

    def _build_maintenance_preview(self, records):
        if not records:
            return '<p>No maintenance checks captured for this period.</p>'
        rows = [
            (rec.date, rec.machine_id or '', f'{rec.checklist_ok:.1f}%', 'Yes' if rec.repaired else 'No', rec.state)
            for rec in records
        ]
        return self._build_table(['Date', 'Machine', 'Checklist %', 'Repaired', 'State'], rows)

    def _build_breakdown_preview(self, records):
        if not records:
            return '<p>No breakdown events captured for this period.</p>'
        rows = [
            (rec.name, rec.event_type, rec.start_time, rec.end_time, f'{rec.downtime_hr:.2f}', rec.state)
            for rec in records
        ]
        return self._build_table(['Event', 'Type', 'Start', 'End', 'Downtime (hrs)', 'State'], rows)

    def _create_invoice_lines(self, bill):
        """Create detailed invoice lines"""
        InvoiceLine = self.env['account.move.line']
        
        # Get default expense account
        property_model = self.env.get('ir.property')
        expense_account = property_model._get('property_account_expense_categ_id', 'product.category') if property_model else False
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
            ], limit=1)
        expense_account = expense_account or self.env['account.account'].search([], limit=1)
        if not expense_account:
            raise UserError(_('No expense account could be found to create vendor bill lines.'))
        
        # Part-A (Fixed)
        if self.part_a_attendance_adjusted > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'Part-A Fixed Manpower Cost ({self.period_start.strftime("%B %Y")})',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.part_a_attendance_adjusted,
                'analytic_distribution': {self.agreement_id.analytic_account_id.id: 100} if self.agreement_id.analytic_account_id else False,
            })
        
        # Part-B (Variable)
        if self.part_b_amount > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'Part-B Variable Manpower Cost (MGQ: {self.mgq_achievement_pct:.1f}%)',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.part_b_amount,
                'analytic_distribution': {self.agreement_id.analytic_account_id.id: 100} if self.agreement_id.analytic_account_id else False,
            })
        
        # Breakdown Deduction
        if self.breakdown_deduction > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': 'Clause 9 Breakdown Deduction',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': -self.breakdown_deduction,
            })
        
        # Bonus/Penalty
        if self.bonus_penalty_amount != 0:
            label = 'Performance Bonus' if self.bonus_penalty_amount > 0 else 'Performance Penalty'
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'{label} ({self.stars} stars, {self.bonus_penalty_pct:+.1f}%)',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.bonus_penalty_amount,
            })
        
        # Inventory Variance
        if self.inventory_variance != 0:
            label = 'Material Shortage' if self.inventory_variance > 0 else 'Material Excess Credit'
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': label,
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.inventory_variance,
            })
        
        # TDS 194C
        if self.tds_amount > 0:
            tds_account = self.env['account.account'].search([
                ('code', '=like', '2062%'),  # TDS Payable account
            ], limit=1)
            if not tds_account:
                tds_account = expense_account
            
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': 'TDS 194C @ 2% (Contractor Payment)',
                'account_id': tds_account.id,
                'quantity': 1,
                'price_unit': -self.tds_amount,
            })

    def _attach_reports(self, bill, source_records):
        """Attach supporting PDF reports to the bill and return created attachments."""
        Attachment = self.env['ir.attachment'].with_context(no_document=True)
        attachments = {
            'all': self.env['ir.attachment'],
            'attendance': False,
            'diesel': False,
            'maintenance': False,
            'breakdown': False,
        }
        sections = []
        section_keys = []

        if self.attach_attendance:
            sections.append(self._generate_attendance_section(source_records.get('attendance')))
            section_keys.append('attendance')
        if self.attach_diesel:
            sections.append(self._generate_diesel_section(source_records.get('diesel')))
            section_keys.append('diesel')
        if self.attach_maintenance:
            sections.append(self._generate_maintenance_section(source_records.get('maintenance')))
            section_keys.append('maintenance')
        if self.attach_breakdown:
            sections.append(self._generate_breakdown_section(source_records.get('breakdown')))
            section_keys.append('breakdown')

        if not sections:
            return attachments

        html_content = self._wrap_sections_html(sections, bill=bill)
        pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf([html_content], landscape=False)
        combined_attachment = Attachment.create({
            'name': f'Supporting_Report_{self.period_start.strftime("%Y%m")}.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'account.move',
            'res_id': bill.id,
            'mimetype': 'application/pdf'
        })
        attachments['all'] = combined_attachment
        for key in section_keys:
            attachments[key] = combined_attachment

        return attachments
    def _reconcile_inventory(self):
        """Reconcile all inventory handovers for the period"""
        inventory_items = self.env['rmc.inventory.handover'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
            ('state', '!=', 'reconciled')
        ])
        for item in inventory_items:
            item.monthly_reconcile_inventory()

    def _create_approval_chain(self, bill):
        """Create multi-level approval activities"""
        # Supervisor approval
        supervisor_group = self.env.ref('rmc_manpower_contractor.group_rmc_supervisor', raise_if_not_found=False)
        supervisor_users = getattr(supervisor_group, 'users', self.env['res.users']) if supervisor_group else self.env['res.users']
        if supervisor_group and supervisor_users:
            bill.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=supervisor_users[0].id,
                summary=_('Approve Monthly Bill - Supervisor'),
                note=_('Please review and approve monthly contractor bill for %s') % self.agreement_id.name
            )

    def _format_period_label(self):
        start = format_date(self.env, self.period_start) if self.period_start else ''
        end = format_date(self.env, self.period_end) if self.period_end else ''
        return _('%(start)s to %(end)s') % {'start': start, 'end': end}

    def _format_section(self, title, body):
        return {
            'title': title,
            'agreement_name': self.agreement_id.name,
            'period_label': self._format_period_label(),
            'body_html': body,
        }

    def _generate_attendance_section(self, data):
        part_a_lines = self.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_a')
        if data:
            rows = [
                (
                    rec.date,
                    rec.headcount_expected,
                    rec.headcount_present,
                    f'{rec.compliance_percentage:.1f}%',
                    rec.state,
                )
                for rec in data.sorted('date')
            ]
            table = self._build_table(['Date', 'Expected', 'Present', 'Compliance %', 'State'], rows)
        else:
            table = '<p>No attendance records captured for this period.</p>'
        proration_html = self.attendance_breakdown_html or self._build_attendance_breakdown(part_a_lines, with_summary=True)
        body = (
            '<h4>%s</h4>%s<br/><h4>%s</h4>%s' % (
                _('Daily Attendance Compliance'),
                table,
                _('Part-A Attendance Proration'),
                proration_html,
            )
        )
        return self._format_section('Attendance Report', body)

    def _generate_diesel_section(self, data):
        if data:
            rows = [
                (
                    rec.date,
                    rec.vehicle_id.display_name if rec.vehicle_id else '',
                    f'{(rec.issued_ltr or 0.0):.2f}',
                    f'{(rec.work_done_m3 or rec.work_done_km or 0.0):.2f}',
                    f'{(rec.diesel_efficiency or 0.0):.2f} {rec.efficiency_unit or ""}',
                    rec.state,
                )
                for rec in data.sorted('date')
            ]
            table = self._build_table(['Date', 'Vehicle', 'Issued (L)', 'Work Done', 'Efficiency', 'State'], rows)
        else:
            table = '<p>No diesel logs captured for this period.</p>'
        return self._format_section('Diesel Log Report', table)

    def _generate_maintenance_section(self, data):
        if data:
            rows = []
            for rec in data.sorted('date'):
                machine = rec.machine_id
                machine_label = machine.display_name if machine and hasattr(machine, 'display_name') else (machine or '')
                rows.append((
                    rec.date,
                    machine_label,
                    f'{rec.checklist_ok:.1f}%',
                    'Yes' if rec.repaired else 'No',
                    f'{rec.cost:.2f}',
                ))
            table = self._build_table(['Date', 'Machine', 'Checklist %', 'Repaired', 'Cost'], rows)
        else:
            table = '<p>No maintenance checks captured for this period.</p>'
        return self._format_section('Maintenance Report', table)

    def _generate_breakdown_section(self, data):
        if data:
            rows = [
                (
                    rec.name,
                    rec.event_type,
                    f'{rec.downtime_hr:.2f}',
                    rec.responsibility,
                    f'{rec.deduction_amount:.2f}',
                )
                for rec in data.sorted('start_time')
            ]
            table = self._build_table(['Event', 'Type', 'Downtime (hrs)', 'Responsibility', 'Deduction'], rows)
        else:
            table = '<p>No breakdown events captured for this period.</p>'
        return self._format_section('Breakdown Events Report', table)

    def _wrap_sections_html(self, sections, bill=None):
        company = (bill and bill.company_id) or self.agreement_id.company_id or self.env.company
        doc = bill or self.agreement_id
        values = {
            'doc': doc,
            'o': bill or doc,
            'company': company,
            'wizard': self,
            'sections': sections,
            'support_sections': sections,
            'bill': bill,
            'period_label': self._format_period_label(),
            'generated_on': format_date(self.env, fields.Date.context_today(self)),
            'lang': self.env.context.get('lang') or self.env.user.lang,
            'proforma': False,
        }
        return self.env['ir.ui.view']._render_template(
            'rmc_manpower_contractor.report_billing_support_sections', values
        )
