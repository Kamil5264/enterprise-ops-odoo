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
    product_id = fields.Many2one(
        comodel_name = 'product.product',
        string = 'Product',
        required = True,
        index = True,
        domain = "[('purchase_ok','=',True)]",
    )

    product_name = fields.Char(
        string='Description',
        compute = '_compute_product_name',
        store = True,
        readonly = True,
        precompute = True,
        required = True
    )

    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
        compute='_compute_uom_id',
        store=True,
        readonly=True,
        precompute=True,
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

    @api.depends('product_id')
    def _compute_product_name(self):
        for line in self:
            if line.product_id:
                line.product_name = line.product_id.display_name

 
    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    

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

    @api.constrains('product_id')
    def _check_product_allowed(self):
        # The view domain is only UX; this is the real enforcement.
        for line in self:
            product = line.product_id
            if not product.purchase_ok:
                raise ValidationError(_(
                    "Product '%(product)s' cannot be purchased.",
                    product=product.display_name,
                ))
            company = line.request_id.company_id
            if product.company_id and product.company_id != company:
                raise ValidationError(_(
                    "Product '%(product)s' belongs to company '%(product_company)s', "
                    "not to this request's company '%(company)s'.",
                    product=product.display_name,
                    product_company=product.company_id.name,
                    company=company.name,
                ))



