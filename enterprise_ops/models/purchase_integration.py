from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    request_id = fields.Many2one(
        comodel_name='enterprise.ops.request',
        string = 'Source Request',
        copy =  False,
        index = True,
        ondelete = 'restrict'
    )

    @api.constrains('request_id', 'company_id')
    def _check_request_link(self):
       for order in  self.filtered('request_id'):
          request =  order.request_id
          if request.state not in ('procurement','done'):
             raise ValidationError(_(
                "Request %(request)s is not in procurement, so it cannot be linked to a purchase order",
                request = request.name
             ))

          if request.company_id!= order.company_id:
             raise ValidationError(_("Request %(request)s belongs to company '%(request_company)s' but this order is in '%(order_company)s' ",
                                     request = request.name,
                                     request_company = request.company_id.name,
                                     order_company = order.company_id.name
                                     ))
           

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    request_line_id = fields.Many2one(
        comodel_name='enterprise.ops.request.line',
        string='Source Request Line',
        copy=False,
        index=True,
        ondelete='restrict',
    )

    @api.constrains('request_line_id', 'order_id')
    def _check_request_line_matches_order(self):
        for line in self.filtered('request_line_id'):
            if line.request_line_id.request_id != line.order_id.request_id:
                raise ValidationError(_(
                    "Line '%(line)s' comes from request %(line_request)s, "
                    "which is not the request this order is linked to.",
                    line=line.request_line_id.product_name,
                    line_request=line.request_line_id.request_id.name,
                ))