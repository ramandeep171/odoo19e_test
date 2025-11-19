# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class RmcBreakdownEvent(models.Model):
    _name = 'rmc.breakdown.event'
    _description = 'RMC Breakdown Event (Clause 9)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_time desc'

    name = fields.Char(string='Event Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', required=True, ondelete='restrict', tracking=True)
    contractor_id = fields.Many2one(related='agreement_id.contractor_id', string='Contractor', store=True)
    
    event_type = fields.Selection([
        ('emergency', 'Emergency Breakdown'),
        ('loto', 'LOTO (Lock-Out Tag-Out)'),
        ('scheduled', 'Scheduled Maintenance'),
        ('ngt', 'NGT/Govt Shutdown'),
        ('force_majeure', 'Force Majeure')
    ], string='Event Type', required=True, tracking=True)
    
    start_time = fields.Datetime(string='Start Time', required=True, tracking=True)
    end_time = fields.Datetime(string='End Time', tracking=True)
    downtime_hr = fields.Float(string='Downtime (Hours)', compute='_compute_downtime', store=True, digits=(5, 2))
    
    responsibility = fields.Selection([
        ('contractor', 'Contractor Fault'),
        ('client', 'Client Responsibility'),
        ('third_party', 'Third Party'),
        ('govt', 'Government/NGT')
    ], string='Responsibility', required=True, default='contractor', tracking=True)
    
    # Clause 9 specifics
    standby_staff = fields.Integer(string='Standby Staff Count', default=0, help='Essential staff retained during shutdown')
    standby_allowance = fields.Monetary(string='Standby Allowance', currency_field='currency_id', help='Special allowance for standby staff')
    is_mgq_achieved = fields.Boolean(string='MGQ Achieved Despite Shutdown', default=False, help='If MGQ met even with shutdown, no deduction applies')
    deduction_amount = fields.Monetary(string='Part-B Deduction', compute='_compute_deduction', store=True, currency_field='currency_id')
    
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    description = fields.Text(string='Description')
    corrective_action = fields.Text(string='Corrective Action Taken')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('closed', 'Closed')], default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    settlement_included = fields.Boolean(string='Included in Settlement', default=False, copy=False)
    settlement_reference = fields.Char(string='Settlement Reference', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            agreement_id = vals.get('agreement_id')
            if agreement_id:
                self.env['rmc.contract.agreement'].browse(agreement_id)._check_closure_operation_allowed(_('create breakdown events'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.breakdown.event') or _('New')
        return super(RmcBreakdownEvent, self).create(vals_list)

    def write(self, vals):
        if self:
            agreements = self.mapped('agreement_id')
            if agreements:
                agreements._check_closure_operation_allowed(_('update breakdown events'))
        return super(RmcBreakdownEvent, self).write(vals)

    @api.depends('start_time', 'end_time')
    def _compute_downtime(self):
        for record in self:
            if record.start_time and record.end_time:
                delta = record.end_time - record.start_time
                record.downtime_hr = delta.total_seconds() / 3600.0
            else:
                record.downtime_hr = 0.0

    @api.depends('responsibility', 'event_type', 'downtime_hr', 'is_mgq_achieved', 'agreement_id.part_b_variable')
    def _compute_deduction(self):
        """
        Clause 9 Deduction Logic:
        - If contractor_fault → Part-B deduction proportional to downtime
        - If NGT/govt shutdown → 50:50 salary share rule (no full deduction if standby staff retained)
        - If MGQ achieved despite shutdown → no deduction
        """
        for record in self:
            if record.is_mgq_achieved:
                record.deduction_amount = 0.0
                continue
            
            if record.responsibility == 'contractor' and record.event_type in ('emergency', 'loto'):
                # Contractor fault: deduct Part-B proportionally
                # Assume 720 hours/month, deduct proportional Part-B
                if record.downtime_hr > 0 and record.agreement_id.part_b_variable > 0:
                    deduction_pct = min(record.downtime_hr / 720.0, 1.0)
                    record.deduction_amount = record.agreement_id.part_b_variable * deduction_pct
                else:
                    record.deduction_amount = 0.0
            elif record.event_type == 'ngt' and record.responsibility == 'govt':
                # NGT/Govt: 50:50 share if standby staff retained; otherwise full deduction
                if record.standby_staff > 0:
                    record.deduction_amount = record.agreement_id.part_b_variable * 0.5
                else:
                    record.deduction_amount = record.agreement_id.part_b_variable
            else:
                record.deduction_amount = 0.0

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for record in self:
            if record.end_time and record.start_time and record.end_time < record.start_time:
                raise ValidationError(_('End time must be after start time.'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        self.message_post(body=_('Breakdown event confirmed'))

    def action_close(self):
        self.write({'state': 'closed'})
        self.message_post(body=_('Breakdown event closed'))
