# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class AgreementSendPreviewWizard(models.TransientModel):
    _name = 'rmc.agreement.send.preview.wizard'
    _description = 'Agreement Preview Before Signature'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    pdf_preview = fields.Binary(
        string='Contract Preview',
        readonly=True
    )
    pdf_filename = fields.Char(string='Filename', readonly=True)

    validity_start = fields.Date(string='Valid From')
    validity_end = fields.Date(string='Valid Until')
    mgq_target = fields.Float(string='MGQ Target (m³)')
    part_a_fixed = fields.Monetary(string='Part-A Fixed', currency_field='currency_id')
    part_b_variable = fields.Monetary(string='Part-B Variable', currency_field='currency_id')
    notes = fields.Html(string='Notes')
    currency_id = fields.Many2one(
        related='agreement_id.currency_id',
        string='Currency',
        readonly=True
    )
    sign_template_id = fields.Many2one(
        'sign.template',
        string='Sign Template'
    )

    def _compute_matrix_totals(self, agreement):
        lines = agreement.manpower_matrix_ids
        if hasattr(lines, '_compute_total'):
            lines._compute_total()
        part_a = sum((line.total_amount or 0.0) for line in lines if line.remark == 'part_a')
        part_b = sum((line.total_amount or 0.0) for line in lines if line.remark == 'part_b')
        return part_a, part_b

    def _prepare_agreement_values(self):
        self.ensure_one()
        part_a = self.part_a_fixed
        part_b = self.part_b_variable
        if not part_a or not part_b:
            computed_a, computed_b = self._compute_matrix_totals(self.agreement_id)
            if not part_a:
                part_a = computed_a
            if not part_b:
                part_b = computed_b
        return {
            'validity_start': self.validity_start,
            'validity_end': self.validity_end,
            'mgq_target': self.mgq_target,
            'part_a_fixed': part_a,
            'part_b_variable': part_b,
            'notes': self.notes,
            'sign_template_id': self.sign_template_id.id if self.sign_template_id else False,
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        agreement = self.env['rmc.contract.agreement'].browse(self.env.context.get('active_id'))
        if not agreement:
            raise UserError(_('No agreement selected.'))

        # ensure latest values (including unsaved form edits) are flushed before reading
        self.env.flush_all()

        agreement._ensure_sign_template()

        pdf_bytes, filename = agreement._get_cached_preview_pdf()
        agreement_vals = agreement.read([
            'validity_start',
            'validity_end',
            'mgq_target',
            'part_a_fixed',
            'part_b_variable',
            'notes',
            'sign_template_id',
        ])[0]
        part_a_value = agreement_vals.get('part_a_fixed')
        part_b_value = agreement_vals.get('part_b_variable')

        computed_a, computed_b = self._compute_matrix_totals(agreement)
        currency = agreement.currency_id or self.env.company.currency_id
        rounding = currency.rounding if currency else 0.01

        if computed_a and (
            part_a_value in (False, None) or
            not float_is_zero(computed_a - (part_a_value or 0.0), precision_rounding=rounding)
        ):
            part_a_value = computed_a
        if computed_b and (
            part_b_value in (False, None) or
            not float_is_zero(computed_b - (part_b_value or 0.0), precision_rounding=rounding)
        ):
            part_b_value = computed_b

        res.update({
            'agreement_id': agreement.id,
            'validity_start': agreement_vals.get('validity_start'),
            'validity_end': agreement_vals.get('validity_end'),
            'mgq_target': agreement_vals.get('mgq_target'),
            'part_a_fixed': part_a_value,
            'part_b_variable': part_b_value,
            'notes': agreement_vals.get('notes'),
            'pdf_preview': base64.b64encode(pdf_bytes).decode('utf-8'),
            'pdf_filename': filename,
            'sign_template_id': agreement_vals.get('sign_template_id'),
        })
        return res

    def _apply_changes(self):
        self.ensure_one()
        values = self._prepare_agreement_values()
        # do not reset sign template if empty; respect existing value
        if not self.sign_template_id:
            values.pop('sign_template_id', None)
        template_was_updated = 'sign_template_id' in values
        self.agreement_id.write(values)
        self.agreement_id._update_manpower_totals_from_matrix()
        if template_was_updated:
            self.agreement_id._sync_signers_with_template()

    def _refresh_preview(self):
        self.ensure_one()
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.agreement_id._store_preview_pdf(pdf_bytes, filename)
        self.write({
            'pdf_preview': base64.b64encode(pdf_bytes).decode('utf-8'),
            'pdf_filename': filename,
            'part_a_fixed': self.agreement_id.part_a_fixed,
            'part_b_variable': self.agreement_id.part_b_variable,
        })

    def action_apply_changes(self):
        self.ensure_one()
        self._apply_changes()
        self._refresh_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_send(self):
        self.ensure_one()
        self._apply_changes()
        self.agreement_id._ensure_sign_template()
        if not self.agreement_id.sign_template_id:
            raise UserError(_('Please select a Sign Template before sending for signature.'))
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.agreement_id._store_preview_pdf(pdf_bytes, filename)
        self.agreement_id._refresh_sign_template(pdf_bytes, filename)
        self.write({
            'part_a_fixed': self.agreement_id.part_a_fixed,
            'part_b_variable': self.agreement_id.part_b_variable,
        })
        action = self.agreement_id.action_send_for_sign()
        return action

    def action_prepare_in_sign_app(self):
        self.ensure_one()
        self._apply_changes()
        self.agreement_id._ensure_sign_template()
        if not self.agreement_id.sign_template_id:
            raise UserError(_('Please select a Sign Template before preparing the Sign request.'))
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.agreement_id._store_preview_pdf(pdf_bytes, filename)
        self.agreement_id._refresh_sign_template(pdf_bytes, filename)
        self.write({
            'part_a_fixed': self.agreement_id.part_a_fixed,
            'part_b_variable': self.agreement_id.part_b_variable,
        })
        return self.agreement_id.action_push_to_sign_app()
