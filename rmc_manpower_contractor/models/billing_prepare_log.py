# -*- coding: utf-8 -*-

from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RmcBillingPrepareLog(models.Model):
    _name = 'rmc.billing.prepare.log'
    _description = 'RMC Monthly Billing Log'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _SUPPORT_ATTACHMENT_DESCRIPTION = 'rmc_billing_support'

    name = fields.Char(string='Description', compute='_compute_name', store=True)
    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        ondelete='cascade'
    )
    contractor_id = fields.Many2one(
        related='agreement_id.contractor_id',
        store=True,
        string='Contractor'
    )
    wizard_id = fields.Many2one(
        'rmc.billing.prepare.wizard',
        string='Source Wizard',
        ondelete='set null'
    )
    category = fields.Selection([
        ('monthly', 'Monthly Billing'),
        ('closure', 'Closure Settlement'),
    ], string='Category', default='monthly', required=True, tracking=True)
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        ondelete='set null'
    )
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    mgq_target = fields.Float(string='MGQ Target (m³)')
    mgq_achieved = fields.Float(string='MGQ Achieved (m³)')
    mgq_achievement_pct = fields.Float(string='MGQ Achievement %', digits=(5, 2))
    prime_output_qty = fields.Float(string='Prime Output (m³)')
    optimized_standby_qty = fields.Float(string='Optimized Standby (m³)')
    part_a_raw_total = fields.Monetary(string='Part-A Raw Total')
    part_a_attendance_adjusted = fields.Monetary(string='Part-A Attendance Adjusted')
    part_a_amount = fields.Monetary(string='Part-A Amount')
    part_b_amount = fields.Monetary(string='Part-B Amount')
    breakdown_deduction = fields.Monetary(string='Breakdown Deduction')
    bonus_penalty_pct = fields.Float(string='Bonus/Penalty %', digits=(5, 2))
    bonus_penalty_amount = fields.Monetary(string='Bonus/Penalty Amount')
    inventory_variance = fields.Monetary(string='Inventory Variance')
    subtotal = fields.Monetary(string='Subtotal')
    tds_amount = fields.Monetary(string='TDS Amount')
    total_amount = fields.Monetary(string='Net Payable')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    attach_attendance = fields.Boolean(string='Attendance Attached')
    attach_diesel = fields.Boolean(string='Diesel Attached')
    attach_maintenance = fields.Boolean(string='Maintenance Attached')
    attach_breakdown = fields.Boolean(string='Breakdown Attached')
    notes = fields.Text(string='Notes snapshot')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Review'),
        ('done', 'Done'),
        ('paid', 'Paid'),
    ], string='Status', default='draft', tracking=True)
    settlement_hold = fields.Boolean(string='Settlement On Hold')
    settlement_hold_reason = fields.Text(string='Settlement Hold Reason')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'rmc_billing_log_attachment_rel',
        'log_id',
        'attachment_id',
        string='Attachments'
    )
    attendance_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attendance Attachment',
        ondelete='set null'
    )
    diesel_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Diesel Attachment',
        ondelete='set null'
    )
    maintenance_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Maintenance Attachment',
        ondelete='set null'
    )
    breakdown_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Breakdown Attachment',
        ondelete='set null'
    )
    attendance_record_ids = fields.Many2many(
        'rmc.attendance.compliance',
        'rmc_billing_log_attendance_rel',
        'log_id',
        'attendance_id',
        string='Attendance Records'
    )
    diesel_record_ids = fields.Many2many(
        'rmc.diesel.log',
        'rmc_billing_log_diesel_rel',
        'log_id',
        'diesel_id',
        string='Diesel Records'
    )
    maintenance_record_ids = fields.Many2many(
        'rmc.maintenance.check',
        'rmc_billing_log_maintenance_rel',
        'log_id',
        'maintenance_id',
        string='Maintenance Records'
    )
    breakdown_record_ids = fields.Many2many(
        'rmc.breakdown.event',
        'rmc_billing_log_breakdown_rel',
        'log_id',
        'breakdown_id',
        string='Breakdown Records'
    )
    attendance_preview_html = fields.Html(string='Attendance Details', sanitize=False)
    diesel_preview_html = fields.Html(string='Diesel Details', sanitize=False)
    maintenance_preview_html = fields.Html(string='Maintenance Details', sanitize=False)
    breakdown_preview_html = fields.Html(string='Breakdown Details', sanitize=False)
    attendance_breakdown_html = fields.Html(string='Attendance Breakdown', sanitize=False)
    diesel_total_issued = fields.Float(string='Diesel Issued (L)', digits=(12, 4), default=0.0)
    diesel_total_fuel = fields.Float(string='Fuel Consumption (L)', digits=(12, 4), default=0.0)
    created_by = fields.Many2one(
        'res.users',
        string='Prepared By',
        default=lambda self: self.env.user,
        readonly=True
    )
    created_on = fields.Datetime(
        string='Prepared On',
        default=fields.Datetime.now,
        readonly=True
    )
    dashboard_diesel_efficiency = fields.Float(
        string='Avg Diesel Efficiency (m³/L)',
        compute='_compute_performance_dashboard',
        digits=(12, 4)
    )
    dashboard_diesel_efficiency_pct = fields.Float(
        string='Diesel Efficiency %',
        compute='_compute_performance_dashboard',
        digits=(6, 2)
    )
    dashboard_diesel_efficiency_bar = fields.Html(
        string='Diesel Efficiency Gauge',
        compute='_compute_performance_dashboard',
        sanitize=False
    )
    dashboard_attendance_compliance = fields.Float(
        string='Attendance Compliance (%)',
        compute='_compute_performance_dashboard',
        digits=(5, 2)
    )
    dashboard_maintenance_compliance = fields.Float(
        string='Maintenance Compliance (%)',
        compute='_compute_performance_dashboard',
        digits=(5, 2)
    )
    dashboard_performance_score = fields.Float(
        string='Performance Score (%)',
        compute='_compute_performance_dashboard',
        digits=(5, 2)
    )
    dashboard_star_rating = fields.Selection([
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐'),
    ], string='Star Rating', compute='_compute_performance_dashboard')

    @api.depends('agreement_id', 'period_start', 'period_end')
    def _compute_name(self):
        for record in self:
            if record.agreement_id and record.period_start and record.period_end:
                record.name = _('%s (%s → %s)') % (
                    record.agreement_id.name,
                    record.period_start,
                    record.period_end,
                )
            elif record.agreement_id:
                record.name = record.agreement_id.name
            else:
                record.name = _('Billing Log')

    @api.depends(
        'attendance_record_ids.compliance_percentage',
        'diesel_record_ids.diesel_efficiency',
        'diesel_record_ids.opening_ltr',
        'diesel_record_ids.issued_ltr',
        'diesel_record_ids.closing_ltr',
        'maintenance_record_ids.checklist_ok',
        'agreement_id.contract_type',
        'prime_output_qty',
    )
    def _compute_performance_dashboard(self):
        ICP = self.env['ir.config_parameter'].sudo()
        weight_diesel = float(ICP.get_param('rmc_score.weight_diesel', 0.5))
        weight_maint = float(ICP.get_param('rmc_score.weight_maintenance', 0.3))
        weight_attend = float(ICP.get_param('rmc_score.weight_attendance', 0.2))
        star_5 = float(ICP.get_param('rmc_score.star_5_threshold', 90))
        star_4 = float(ICP.get_param('rmc_score.star_4_threshold', 75))
        star_3 = float(ICP.get_param('rmc_score.star_3_threshold', 60))
        star_2 = float(ICP.get_param('rmc_score.star_2_threshold', 40))
        prime_per_liter_field = self._fields.get('dashboard_diesel_efficiency')
        alias = prime_per_liter_field and prime_per_liter_field.name or 'dashboard_diesel_efficiency'

        for log in self:
            attendance_records = log.attendance_record_ids.filtered(lambda r: r.state == 'validated') or log.attendance_record_ids
            diesel_records = log.diesel_record_ids.filtered(lambda r: r.state == 'validated') or log.diesel_record_ids
            maintenance_records = log.maintenance_record_ids.filtered(lambda r: r.state == 'validated') or log.maintenance_record_ids

            def _avg(records, field_name):
                values = [getattr(rec, field_name, 0.0) or 0.0 for rec in records if getattr(rec, field_name, False) is not False]
                return sum(values) / len(values) if values else 0.0

            def _consumption(record):
                fuel_consumption = getattr(record, 'fuel_consumption', None)
                if fuel_consumption not in (None, False):
                    return fuel_consumption
                opening = getattr(record, 'opening_ltr', 0.0) or 0.0
                issued = getattr(record, 'issued_ltr', 0.0) or 0.0
                closing = getattr(record, 'closing_ltr', 0.0) or 0.0
                return opening + issued - closing

            attendance_pct = _avg(attendance_records, 'compliance_percentage')
            if not attendance_records:
                attendance_pct = log.agreement_id.attendance_compliance
            total_fuel = log.diesel_total_fuel or 0.0
            if not total_fuel:
                total_fuel = sum(_consumption(rec) for rec in diesel_records) if diesel_records else 0.0
            prime = log.prime_output_qty or 0.0
            prime_per_liter = prime / total_fuel if total_fuel else 0.0
            diesel_eff = prime_per_liter or log.agreement_id.avg_diesel_efficiency
            target_l = float(ICP.get_param('rmc_diesel.target_l_per_m3', 0.7))
            actual_l = (total_fuel / prime) if prime else 0.0
            if target_l > 0 and actual_l > 0:
                efficiency_pct = (target_l / actual_l) * 100.0
            else:
                efficiency_pct = 0.0
            efficiency_pct = max(0.0, min(efficiency_pct, 200.0))
            maintenance_pct = _avg(maintenance_records, 'checklist_ok')
            if not maintenance_records:
                maintenance_pct = log.agreement_id.maintenance_compliance
            setattr(log, alias, prime_per_liter)
            log.dashboard_diesel_efficiency_pct = efficiency_pct
            if efficiency_pct >= 95.0:
                color_class = 'bg-success'
            elif efficiency_pct >= 75.0:
                color_class = 'bg-warning'
            else:
                color_class = 'bg-danger'
            width = min(max(efficiency_pct, 0.0), 130.0)
            bar_html = (
                '<div class="o-diesel-inline">'
                '<span class="o-diesel-inline__label">Diesel Efficiency %</span>'
                '<div class="o-diesel-inline__track">'
                '<div class="progress progress-sm">'
                f'<div class="progress-bar {color_class}" role="progressbar" style="width:{width:.1f}%"></div>'
                '</div>'
                f'<span class="o-diesel-inline__value">{efficiency_pct:.1f}%</span>'
                '</div>'
                '</div>'
            )
            log.dashboard_diesel_efficiency_bar = bar_html

            log.dashboard_attendance_compliance = attendance_pct
            log.dashboard_maintenance_compliance = maintenance_pct

            contract_type = log.agreement_id.contract_type
            score = 0.0
            diesel_norm = min(diesel_eff * 20, 100.0)
            if contract_type == 'driver_transport':
                score = diesel_norm * weight_diesel + maintenance_pct * weight_maint
            elif contract_type == 'pump_ops':
                score = maintenance_pct * weight_maint + diesel_norm * weight_diesel
            elif contract_type == 'accounts_audit':
                score = attendance_pct * weight_attend + maintenance_pct * weight_maint
            else:
                score = (attendance_pct * weight_attend) + (maintenance_pct * weight_maint) + (diesel_norm * weight_diesel)
            score = min(score, 100.0)
            log.dashboard_performance_score = score

            if score >= star_5:
                log.dashboard_star_rating = '5'
            elif score >= star_4:
                log.dashboard_star_rating = '4'
            elif score >= star_3:
                log.dashboard_star_rating = '3'
            elif score >= star_2:
                log.dashboard_star_rating = '2'
            elif score:
                log.dashboard_star_rating = '1'
            else:
                log.dashboard_star_rating = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        eligible = records.filtered(lambda l: l.agreement_id and l.period_start and l.period_end)
        if eligible:
            eligible.with_context(rmc_skip_log_autorefresh=True)._refresh_snapshot_from_wizard()
        return records

    def write(self, vals):
        auto_refresh_fields = ('period_start', 'period_end', 'prime_output_qty', 'optimized_standby_qty')
        snapshot_changed = any(field in vals for field in auto_refresh_fields)
        res = super().write(vals)
        if snapshot_changed and not self.env.context.get('rmc_skip_log_autorefresh'):
            self.filtered(lambda l: l.period_start and l.period_end)._refresh_snapshot_from_wizard()
        return res

    def _refresh_snapshot_from_wizard(self):
        Wizard = self.env['rmc.billing.prepare.wizard']
        for log in self:
            if not log.agreement_id or not log.period_start or not log.period_end:
                continue
            wizard_ctx = dict(self.env.context, from_log_id=log.id, rmc_skip_log_autorefresh=True)
            wizard_vals = {
                'agreement_id': log.agreement_id.id,
                'period_start': log.period_start,
                'period_end': log.period_end,
                'prime_output_qty': log.prime_output_qty,
                'optimized_standby_qty': log.optimized_standby_qty,
                'attach_attendance': log.attach_attendance,
                'attach_diesel': log.attach_diesel,
                'attach_maintenance': log.attach_maintenance,
                'attach_breakdown': log.attach_breakdown,
                'notes': log.notes,
            }
            wizard = Wizard.with_context(wizard_ctx).create(wizard_vals)
            try:
                wizard._sync_mgq_with_prime_output()
                wizard._apply_attendance_proration()
                wizard._compute_billing_amounts()
                source_records = wizard._collect_source_records()
                wizard.with_context(rmc_skip_log_autorefresh=True)._create_billing_log(
                    log.bill_id, attachments=None, source_records=source_records
                )
            finally:
                wizard.unlink()

    def _sync_supporting_attachments(self, attachments=None, source_bill=None):
        """Ensure supporting PDFs live on the log record and chatter."""
        self.ensure_one()
        Attachment = self.env['ir.attachment'].with_context(no_document=True)
        support_domain = [
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('description', '=', self._SUPPORT_ATTACHMENT_DESCRIPTION),
        ]
        existing_support_attachments = Attachment.search(support_domain)
        if existing_support_attachments:
            existing_support_attachments.unlink()

        attachment_values = attachments or {}
        source_records = self.env['ir.attachment']
        for recordset in attachment_values.values():
            if recordset:
                source_records |= recordset
        source_records = source_records.sorted('id')

        clear_vals = {
            'attendance_attachment_id': False,
            'diesel_attachment_id': False,
            'maintenance_attachment_id': False,
            'breakdown_attachment_id': False,
        }
        if not source_records:
            self.write(clear_vals)
            return

        copy_map = {}
        new_attachments = self.env['ir.attachment']
        for record in source_records:
            copied = record.with_context(no_document=True).copy({
                'res_model': self._name,
                'res_id': self.id,
                'description': self._SUPPORT_ATTACHMENT_DESCRIPTION,
            })
            new_attachments |= copied
            copy_map[record.id] = copied

        write_vals = {
            'attachment_ids': [(4, att.id) for att in new_attachments],
            **clear_vals,
        }

        def _mapped_for(key):
            source_recordset = attachment_values.get(key)
            if not source_recordset:
                return False
            source_attachment = source_recordset[:1]
            if not source_attachment:
                return False
            return copy_map.get(source_attachment.id)

        for key in ('attendance', 'diesel', 'maintenance', 'breakdown'):
            mapped = _mapped_for(key)
            if mapped:
                write_vals[f'{key}_attachment_id'] = mapped.id

        self.write(write_vals)

        if new_attachments:
            if source_bill and source_bill.exists():
                body = _('Supporting billing report generated from %s.') % source_bill.display_name
            elif self.bill_id:
                body = _('Supporting billing report generated from %s.') % self.bill_id.display_name
            else:
                body = _('Supporting billing report generated.')
            self.message_post(
                body=body,
                attachment_ids=new_attachments.ids,
                subject=_('Supporting Documents Uploaded'),
            )

    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Ensure newer billing stages are always visible even on stale views."""
        res = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type != 'form' or not res.get('arch'):
            return res
        try:
            doc = etree.fromstring(res['arch'])
        except (etree.XMLSyntaxError, TypeError, ValueError):
            return res
        updated = False
        for node in doc.xpath("//field[@name='state'][@widget='statusbar']"):
            visible = node.get('statusbar_visible')
            if not visible:
                continue
            stages = [stage.strip() for stage in visible.split(',') if stage.strip()]
            if 'paid' not in stages:
                stages.append('paid')
                node.set('statusbar_visible', ','.join(stages))
                updated = True
        if updated:
            res['arch'] = etree.tostring(doc, encoding='unicode')
        return res

    def action_prepare_monthly_bill(self):
        self.ensure_one()
        agreement = self.agreement_id
        if not agreement:
            raise ValidationError(_('No agreement linked to this billing log.'))
        self.state = 'review'
        context = {
            'default_agreement_id': agreement.id,
            'default_period_start': self.period_start,
            'default_period_end': self.period_end,
            'default_mgq_achieved': self.mgq_achieved,
            'default_prime_output_qty': self.prime_output_qty,
            'default_optimized_standby_qty': self.optimized_standby_qty,
            'default_part_a_amount': self.part_a_attendance_adjusted or self.part_a_amount,
            'default_notes': self.notes,
            'from_log_id': self.id,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prepare Monthly Bill'),
            'res_model': 'rmc.billing.prepare.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }

    @api.model
    def _get_current_period(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        return start, today

    @api.model
    def _generate_log_for_period(self, agreement, period_start, period_end):
        Wizard = self.env['rmc.billing.prepare.wizard']
        wizard = Wizard.create({
            'agreement_id': agreement.id,
            'period_start': period_start,
            'period_end': period_end,
        })
        wizard._sync_mgq_with_prime_output()
        wizard._apply_attendance_proration()
        wizard._compute_billing_amounts()
        source_records = wizard._collect_source_records()
        attachments = {
            'all': self.env['ir.attachment'],
            'attendance': False,
            'diesel': False,
            'maintenance': False,
            'breakdown': False,
        }
        log = wizard._create_billing_log(self.env['account.move'], attachments, source_records)
        log.state = 'draft'
        wizard.unlink()
        return log

    @api.model
    def ensure_current_month_log(self, agreement_id):
        agreement = self.env['rmc.contract.agreement'].browse(agreement_id)
        if not agreement:
            raise ValidationError(_('Agreement not found.'))
        period_start, period_end = self._get_current_period()
        log = self.search([
            ('agreement_id', '=', agreement.id),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
            ('category', '=', 'monthly'),
        ], limit=1)
        if not log:
            log = self._generate_log_for_period(agreement, period_start, period_end)
        return log

    @api.model
    def action_create_current_month_log(self):
        agreement_id = self.env.context.get('default_agreement_id') or self.env.context.get('active_agreement_id')
        if not agreement_id:
            raise ValidationError(_('Please open Billing Logs from an agreement to create a monthly log.'))
        log = self.ensure_current_month_log(agreement_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rmc.billing.prepare.log',
            'res_id': log.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_new_log(self):
        self.ensure_one()
        agreement = self.agreement_id
        if not agreement:
            raise ValidationError(_('No agreement linked to this billing log.'))
        log = self.ensure_current_month_log(agreement.id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rmc.billing.prepare.log',
            'res_id': log.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _get_current_period(self):
        today = fields.Date.context_today(self)
        start_date = today.replace(day=1)
        return start_date, today

    @api.model
    def _generate_log_for_period(self, agreement, period_start, period_end):
        Wizard = self.env['rmc.billing.prepare.wizard']
        wizard = Wizard.create({
            'agreement_id': agreement.id,
            'period_start': period_start,
            'period_end': period_end,
        })
        wizard._sync_mgq_with_prime_output()
        wizard._apply_attendance_proration()
        wizard._compute_billing_amounts()
        source_records = wizard._collect_source_records()
        attachments = {
            'all': self.env['ir.attachment'],
            'attendance': False,
            'diesel': False,
            'maintenance': False,
            'breakdown': False,
        }
        log = wizard._create_billing_log(self.env['account.move'], attachments, source_records)
        wizard.unlink()
        return log

    @api.model
    def ensure_current_month_log(self, agreement_id):
        agreement = self.env['rmc.contract.agreement'].browse(agreement_id)
        if not agreement:
            raise ValidationError(_('Agreement not found.'))
        period_start, period_end = self._get_current_period()
        log = self.search([
            ('agreement_id', '=', agreement.id),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
            ('category', '=', 'monthly'),
        ], limit=1)
        if not log:
            log = self._generate_log_for_period(agreement, period_start, period_end)
        return log
