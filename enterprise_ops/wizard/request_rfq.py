# -*- coding: utf-8 -*-
from odoo import fields, models


class RequestRfqWizard(models.TransientModel):
    _name = 'enterprise.ops.request.rfq'
    _description = 'Create RFQ from Request'

    request_id = fields.Many2one(
        comodel_name='enterprise.ops.request',
        string='Request',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        order = self.request_id._create_rfq(self.partner_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }