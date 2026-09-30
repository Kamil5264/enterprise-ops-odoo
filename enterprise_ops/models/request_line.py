from odoo import models,fields, api, _
from odoo.exceptions import ValidationError

class OperationalRequestLine(models.Model):
    _name = 'enterprise.ops.request.line'
    _description='Operational Request Line'
    _order = 'sequence, id'

    # relation to parent request model
    request_id = fields.Many2one(
        comodel_name='enterprise.ops.request',
        string = 'Request',
        required = True,
        ondelete = 'cascade',
        index = True

    )

    sequence = fields.Integer(
        string = 'Sequence',
        default = 10
    )
     # Simple text description for now. later we will replaces this with a
    # proper product_id (product.product) + uom_id link.

    product_name = fields.Char(
        string = 'Product/Service',
        required = True
    )

    quantity = fields.Integer(
        string  = 'Quantity',
        required = True,
        default  = 1
    )

    estimated_unit_price = fields.Monetary(
        string='Estimated Unit Price',
        currency_field='currency_id',
    )

    notes = fields.Char(string='Notes')

    currency_id = fields.Many2one(
        related='request_id.company_id.currency_id',
        string='Currency',
        store=True,
        readonly=True,
    )

    # computed subtotal
    subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        compute='_compute_subtotal',
        store=True,
    )

    @api.depends('quantity','estimated_unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.estimated_unit_price

    @api.onchange('quantity')
    def _onchange_quantity_warning(self):
        if self.quantity and self.quantity <= 0:
            return {'warning': {
                'title': _('Invalid Quantity'),
                'message': _('Quantity should be greater than zero.'),
            }}

    @api.onchange('estimated_unit_price')
    def _onchange_price_warning(self):
        if self.estimated_unit_price and self.estimated_unit_price < 0:
            return {'warning': {
                'title': _('Invalid Price'),
                'message': _('Estimated unit price cannot be negative.'),
            }}

    # ------------------------------------------------------------------
    # Server-side constraints
    # ------------------------------------------------------------------
    @api.constrains('quantity')
    def _check_quantity_positive(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_(
                    "Quantity must be greater than zero (line: %(product)s).",
                    product=line.product_name,
                ))

    @api.constrains('estimated_unit_price')
    def _check_price_non_negative(self):
        for line in self:
            if line.estimated_unit_price < 0:
                raise ValidationError(_(
                    "Estimated unit price cannot be negative (line: %(product)s).",
                    product=line.product_name,
                ))



