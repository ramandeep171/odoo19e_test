# -*- coding: utf-8 -*-
"""Renewal wizard for agreements."""

from datetime import timedelta
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import html_escape

try:
    from jsondiff import diff as jsondiff
except ImportError:  # pragma: no cover - dependency should be installed on server
    jsondiff = None


class RmcAgreementRenewalWizard(models.TransientModel):
    _name = 'rmc.agreement.renewal.wizard'
    _description = 'Agreement Renewal Wizard'

    state = fields.Selection(
        selection=[
            ('select', 'Select Agreement'),
            ('edit', 'Edit Terms'),
            ('review', 'Review & Confirm'),
        ],
        default='select',
        string='Wizard Step'
    )
    source_agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Source Agreement',
        required=True,
        domain="[('state', '=', 'active')]"
    )
    contractor_id = fields.Many2one(
        related='source_agreement_id.contractor_id',
        string='Contractor',
        readonly=True
    )
    contract_type = fields.Selection(
        related='source_agreement_id.contract_type',
        string='Contract Type',
        readonly=True
    )
    validity_start = fields.Date(string='New Valid From', required=True)
    validity_end = fields.Date(string='New Valid Until', required=True)
    revision_no = fields.Integer(
        string='Next Revision',
        compute='_compute_revision_no'
    )
    currency_id = fields.Many2one(
        related='source_agreement_id.currency_id',
        string='Currency',
        readonly=True
    )
    matrix_line_ids = fields.One2many(
        'rmc.agreement.renewal.matrix.line',
        'wizard_id',
        string='Manpower Matrix'
    )
    clause_line_ids = fields.One2many(
        'rmc.agreement.renewal.clause.line',
        'wizard_id',
        string='Clauses'
    )
    bonus_rule_line_ids = fields.One2many(
        'rmc.agreement.renewal.rule.line',
        'wizard_id',
        string='Bonus/Penalty Rules'
    )

    def _compute_revision_no(self):
        for wizard in self:
            if wizard.source_agreement_id:
                base = wizard.source_agreement_id.revision_no or 1
            else:
                base = 1
            wizard.revision_no = base + 1

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        source = self._resolve_source_agreement()
        if source:
            res['source_agreement_id'] = source.id
            start, end = self._suggest_validity_window(source)
            res.update({
                'validity_start': start,
                'validity_end': end,
                'matrix_line_ids': self._prepare_matrix_line_defaults(source),
                'clause_line_ids': self._prepare_clause_line_defaults(source),
                'bonus_rule_line_ids': self._prepare_bonus_rule_defaults(source),
                'state': 'edit',
            })
        else:
            today = fields.Date.context_today(self)
            res.setdefault('validity_start', today)
            res.setdefault('validity_end', today)
        return res

    def _resolve_source_agreement(self):
        active_id = self.env.context.get('active_id')
        default_id = self.env.context.get('default_source_agreement_id')
        agreement_id = default_id or active_id
        return self.env['rmc.contract.agreement'].browse(agreement_id) if agreement_id else None

    def _suggest_validity_window(self, source):
        today = fields.Date.context_today(self)
        start = today
        duration = timedelta(days=365)
        if source.validity_start and source.validity_end:
            duration = source.validity_end - source.validity_start or duration
        if source.validity_end:
            start = source.validity_end + timedelta(days=1)
        elif source.validity_start:
            start = source.validity_start + timedelta(days=365)
        start = max(start, today)
        end = start + duration
        return start, end

    def _prepare_matrix_line_defaults(self, source):
        commands = []
        lines = sorted(source.manpower_matrix_ids, key=lambda r: (getattr(r, 'sequence', 0), r.id))
        for line in lines:
            commands.append((0, 0, {
                'designation': line.designation,
                'employee_id': line.employee_id.id,
                'vehicle_id': line.vehicle_id.id,
                'headcount': line.headcount,
                'shift': line.shift,
                'remark': line.remark,
                'base_rate': line.base_rate,
            }))
        return commands

    def _prepare_clause_line_defaults(self, source):
        commands = []
        for clause in sorted(source.clause_ids, key=lambda c: (c.sequence, c.id)):
            commands.append((0, 0, {
                'sequence': clause.sequence,
                'title': clause.title,
                'body_html': clause.body_html,
            }))
        return commands

    def _prepare_bonus_rule_defaults(self, source):
        commands = []
        for rule in sorted(source.bonus_rule_ids, key=lambda r: (r.sequence, r.id)):
            commands.append((0, 0, {
                'sequence': rule.sequence,
                'name': rule.name,
                'rule_type': rule.rule_type,
                'trigger_condition': rule.trigger_condition,
                'percentage': rule.percentage,
                'notes': rule.notes,
            }))
        return commands

    @api.onchange('source_agreement_id')
    def _onchange_source_agreement(self):
        for wizard in self:
            if wizard.source_agreement_id:
                start, end = wizard._suggest_validity_window(wizard.source_agreement_id)
                wizard.validity_start = start
                wizard.validity_end = end
                wizard.matrix_line_ids = [(5, 0, 0)] + wizard._prepare_matrix_line_defaults(wizard.source_agreement_id)
                wizard.clause_line_ids = [(5, 0, 0)] + wizard._prepare_clause_line_defaults(wizard.source_agreement_id)
                wizard.bonus_rule_line_ids = [(5, 0, 0)] + wizard._prepare_bonus_rule_defaults(wizard.source_agreement_id)

    def action_confirm(self):
        self.ensure_one()
        source = self.source_agreement_id
        if not source:
            raise UserError(_('Select an agreement to renew.'))
        if source.state != 'active':
            raise UserError(_('Only active agreements can be renewed.'))
        snapshot_before = source._snapshot_terms()
        vals = self._prepare_new_agreement_vals(source)
        Agreement = self.env['rmc.contract.agreement']
        new_agreement = Agreement.create(vals)
        new_agreement._update_manpower_totals_from_matrix()
        source.with_context({Agreement._LOCK_BYPASS_CONTEXT_KEY: True}).write({'next_agreement_id': new_agreement.id})
        source.message_post(
            body=_('Renewal draft %(name)s (Rev %(rev)s) created.') % {
                'name': new_agreement.display_name,
                'rev': new_agreement.revision_no,
            },
            subject=_('Renewal Draft Created')
        )
        new_agreement.message_post(
            body=_('Duplicated from %(source)s.') % {'source': source.display_name},
            subject=_('Renewal Prepared')
        )
        snapshot_after = new_agreement._snapshot_terms()
        delta_json = self._compute_term_delta(snapshot_before, snapshot_after)
        self._create_change_log_entry(new_agreement, delta_json)
        digest_body = self._build_change_digest(snapshot_before, snapshot_after, delta_json)
        new_agreement.message_post(body=digest_body, subtype_xmlid='mail.mt_note')
        action = self.env.ref('rmc_manpower_contractor.action_rmc_agreement', raise_if_not_found=False)
        if action:
            data = action.read()[0]
        else:
            data = {
                'type': 'ir.actions.act_window',
                'res_model': 'rmc.contract.agreement',
            }
        data.update({
            'res_id': new_agreement.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'domain': [('id', '=', new_agreement.id)],
            'context': {'default_previous_agreement_id': source.id},
        })
        return data

    def _prepare_new_agreement_vals(self, source):
        revision = (source.revision_no or 1) + 1
        default_vals = {
            'name': _('New'),
            'state': 'draft',
            'previous_agreement_id': source.id,
            'next_agreement_id': False,
            'revision_no': revision,
            'validity_start': self.validity_start,
            'validity_end': self.validity_end,
            'start_date': self.validity_start,
            'end_date': self.validity_end,
            'sign_request_id': False,
            'sign_state': False,
            'is_agreement_signed': False,
            'preview_pdf': False,
            'preview_pdf_filename': False,
            'preview_cache_key': False,
        }
        vals = source.copy_data(default_vals)[0]
        for field in ['manpower_matrix_ids', 'clause_ids', 'bonus_rule_ids', 'message_follower_ids', 'message_ids', 'message_partner_ids', 'activity_ids']:
            vals.pop(field, None)
        vals['manpower_matrix_ids'] = self._matrix_commands()
        vals['clause_ids'] = self._clause_commands()
        vals['bonus_rule_ids'] = self._bonus_rule_commands()
        return vals

    def _matrix_commands(self):
        commands = [(5, 0, 0)]
        for line in self.matrix_line_ids:
            commands.append((0, 0, {
                'designation': line.designation,
                'employee_id': line.employee_id.id,
                'vehicle_id': line.vehicle_id.id,
                'headcount': line.headcount,
                'shift': line.shift,
                'remark': line.remark,
                'base_rate': line.base_rate,
            }))
        return commands

    def _compute_term_delta(self, snapshot_before, snapshot_after):
        if jsondiff is None:
            raise UserError(_('The python library "jsondiff" is required to compute renewal deltas.'))
        delta = jsondiff(snapshot_before, snapshot_after, marshal=True)
        return json.loads(json.dumps(delta, default=str))

    def _create_change_log_entry(self, agreement, delta_json):
        ChangeLog = self.env['rmc.agreement.change.log'].sudo()
        ChangeLog.create({
            'agreement_id': agreement.id,
            'changed_by_id': self.env.user.id,
            'changed_on': fields.Datetime.now(),
            'delta_json': delta_json,
        })

    def _build_change_digest(self, snapshot_before, snapshot_after, delta_json):
        sections = []
        before_financial = snapshot_before.get('financial', {})
        after_financial = snapshot_after.get('financial', {})
        labels = {
            'mgq_target': _('MGQ Target'),
            'part_a_fixed': _('Part-A Fixed'),
            'part_b_variable': _('Part-B Variable'),
        }
        for key, label in labels.items():
            if before_financial.get(key) != after_financial.get(key):
                sections.append('%s: %s → %s' % (
                    label,
                    before_financial.get(key, 0.0),
                    after_financial.get(key, 0.0),
                ))

        if snapshot_before.get('matrix') != snapshot_after.get('matrix'):
            sections.append(_('Manpower matrix updated.'))
        if snapshot_before.get('clauses') != snapshot_after.get('clauses'):
            sections.append(_('Clauses adjusted.'))
        if snapshot_before.get('bonus_rules') != snapshot_after.get('bonus_rules'):
            sections.append(_('Bonus/Penalty rules changed.'))

        if not sections:
            sections.append(_('No material term changes detected.'))

        summary_items = ''.join('<li>%s</li>' % html_escape(line) for line in sections)
        pretty_json_raw = json.dumps(delta_json or {}, indent=2, sort_keys=True, default=str)
        pretty_json = html_escape(pretty_json_raw)
        body = (
            '<p><strong>%s</strong></p>'
            '<ul>%s</ul>'
            '<details><summary>%s</summary><pre>%s</pre></details>'
        ) % (
            _('Renewal Term Changes'),
            summary_items,
            _('Raw JSON delta'),
            pretty_json,
        )
        return body

    def _clause_commands(self):
        commands = [(5, 0, 0)]
        for line in sorted(self.clause_line_ids, key=lambda l: (l.sequence, l.id)):
            commands.append((0, 0, {
                'sequence': line.sequence,
                'title': line.title,
                'body_html': line.body_html,
            }))
        return commands

    def _bonus_rule_commands(self):
        commands = [(5, 0, 0)]
        for line in sorted(self.bonus_rule_line_ids, key=lambda l: (l.sequence, l.id)):
            commands.append((0, 0, {
                'sequence': line.sequence,
                'name': line.name,
                'rule_type': line.rule_type,
                'trigger_condition': line.trigger_condition,
                'percentage': line.percentage,
                'notes': line.notes,
            }))
        return commands


class RmcAgreementRenewalMatrixLine(models.TransientModel):
    _name = 'rmc.agreement.renewal.matrix.line'
    _description = 'Renewal Wizard Manpower Line'

    wizard_id = fields.Many2one('rmc.agreement.renewal.wizard', required=True, ondelete='cascade')
    designation = fields.Char(required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    headcount = fields.Integer(default=1)
    shift = fields.Selection(
        selection=[
            ('day', 'Day Shift'),
            ('night', 'Night Shift'),
            ('rotational', 'Rotational'),
            ('general', 'General (8 hrs)')
        ],
        default='general'
    )
    remark = fields.Selection(
        selection=[
            ('part_a', 'Part-A (Fixed)'),
            ('part_b', 'Part-B (Variable - MGQ linked)')
        ],
        default='part_a'
    )
    base_rate = fields.Float(required=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
    total_amount = fields.Monetary(compute='_compute_total', currency_field='currency_id')

    @api.depends('headcount', 'base_rate')
    def _compute_total(self):
        for line in self:
            line.total_amount = (line.headcount or 0.0) * (line.base_rate or 0.0)


class RmcAgreementRenewalClauseLine(models.TransientModel):
    _name = 'rmc.agreement.renewal.clause.line'
    _description = 'Renewal Wizard Clause Line'

    wizard_id = fields.Many2one('rmc.agreement.renewal.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    title = fields.Char(required=True)
    body_html = fields.Html(string='Body', sanitize=False)


class RmcAgreementRenewalRuleLine(models.TransientModel):
    _name = 'rmc.agreement.renewal.rule.line'
    _description = 'Renewal Wizard Bonus/Penalty Rule'

    wizard_id = fields.Many2one('rmc.agreement.renewal.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Rule Label', required=True)
    rule_type = fields.Selection(
        selection=[('bonus', 'Bonus'), ('penalty', 'Penalty')],
        default='bonus',
        required=True
    )
    trigger_condition = fields.Char(string='Trigger')
    percentage = fields.Float(string='Adjustment (%)')
    notes = fields.Text(string='Notes')
