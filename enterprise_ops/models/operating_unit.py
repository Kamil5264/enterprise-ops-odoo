from odoo import models, fields

class OperatingUnit(models.Model):
    _name = 'enterprise.ops.operating.unit'
    _description = 'Operating Unit'
    _order = 'name'

    name = fields.Char(string = 'Name', required = True, index = True)
    code = fields.Char(string = 'Code', required = True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required = True,
        default = lambda self: self.env.company)
    
    active = fields.Boolean(string  = 'Active', default = True)

    _sql_constraints = [
        (
            'company_code_uniq',
            'unique(code,company_id)',
            'Operating unit code must be unique per company'
        )
    ]

