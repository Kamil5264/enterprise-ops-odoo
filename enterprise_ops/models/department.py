from odoo import models, fields

class  Department(models.Model):
    _name = 'enterprise.ops.department'
    _description = 'Department'
    _order = 'name'

    name = fields.Char(string = 'Name', required = True, index = True)
    code  = fields.Char(string = 'Code', required = True, )
    manager_id = fields.Many2one(
        comodel_name ='res.users',
        string = 'Manager'
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string =  'company',
        required = True,
        default=lambda self: self.env.company,


    )
    active = fields.Boolean(string = 'Active', default = True)

    _sql_constraints = [
        (
            'code_company_uniq',
            'UNIQUE(code, company_id)',
            'Department code must bu unique per company'
        ),
    ]
