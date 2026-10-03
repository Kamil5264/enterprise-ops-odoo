 # -*- coding: utf-8 -*-
from odoo import fields, models


class CompanyOwnedMixin(models.AbstractModel):
    
    _name = 'enterprise.ops.company.owned.mixin'
    _description = 'Company-Owned Record Mixin'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(string='Active', default=True)