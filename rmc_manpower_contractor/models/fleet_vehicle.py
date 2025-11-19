# -*- coding: utf-8 -*-

from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    rmc_agreement_ids = fields.Many2many(
        'rmc.contract.agreement',
        'rmc_agreement_vehicle_rel',
        'vehicle_id',
        'agreement_id',
        string='RMC Agreements',
        help='Agreements that reference this vehicle for manpower tracking.'
    )
