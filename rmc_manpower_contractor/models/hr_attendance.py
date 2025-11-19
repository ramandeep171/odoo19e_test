# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', readonly=True)

    def _notify_agreements(self, employees):
        Agreement = self.env['rmc.contract.agreement']
        agreements = Agreement.search([
            '|',
            ('manpower_matrix_ids.employee_id', 'in', employees.ids),
            ('driver_ids', 'in', employees.ids)
        ]) if employees else Agreement.browse()
        if agreements:
            agreements._refresh_agreements_for_employees(employees)
        ctx_skip = dict(self.env.context, skip_agreement_notify=True)
        for attendance in self:
            existing_attendance = attendance.exists()
            employee = attendance.employee_id
            agreement = agreements.filtered(lambda ag: employee in (ag.driver_ids | ag.manpower_matrix_ids.mapped('employee_id')))
            target_agreement_id = agreement[:1].id if agreement else False
            if not existing_attendance:
                continue
            current_agreement_id = existing_attendance.agreement_id.id if existing_attendance.agreement_id else False
            if target_agreement_id == current_agreement_id:
                continue
            existing_attendance.with_context(ctx_skip).write({'agreement_id': target_agreement_id})

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('skip_agreement_notify'):
            return super().create(vals_list)
        attendances = super().create(vals_list)
        attendances._notify_agreements(attendances.mapped('employee_id'))
        return attendances

    def write(self, vals):
        if self.env.context.get('skip_agreement_notify'):
            return super().write(vals)
        employees_before = self.mapped('employee_id')
        result = super().write(vals)
        employees_after = self.mapped('employee_id')
        employees = (employees_before | employees_after)
        if employees:
            self._notify_agreements(employees)
        return result

    def unlink(self):
        if self.env.context.get('skip_agreement_notify'):
            return super().unlink()
        employees = self.mapped('employee_id')
        result = super().unlink()
        if employees:
            self._notify_agreements(employees)
        return result
