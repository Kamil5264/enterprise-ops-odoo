from odoo import models, api, fields, _
from odoo.exceptions import AccessError


class OperationalRequestAccounting(models.Model):
    _inherit = 'enterprise.ops.request'

    bill_count = fields.Integer(
        string = 'Vendor Bills',
        compute = '_compute_bill_count',
        groups = 'account.group_account_invoice'
    )


    payment_status = fields.Selection(
        selection=[
            ('none','Nothing Billed'),
            ('unpaid','Unpaid'),
            ('partial','Partially Paid'),
            ('paid','paid')
        ],
        string='Payment Status',
        compute = '_compute_payment_status',
    )



    @api.depends('purchase_order_ids.invoice_ids')
    def _compute_bill_count(self):
        orders = self.env['purchase.order'].sudo().search(
            [('request_id','in',self.ids)])

        for request in self:
            request.bill_count = len(
                orders.filtered(lambda o: o.request_id == request).invoice_ids
            )


    @api.model
    def _payment_status_of(self, payment_states):
       
        relevant = [s for s in payment_states if s != 'reversed']
        if not relevant:
            return 'none'
        if all(s in ('paid', 'in_payment') for s in relevant):
            return 'paid'
        if any(s in ('paid', 'in_payment', 'partial') for s in relevant):
            return 'partial'
        return 'unpaid'

    @api.depends(
        'purchase_order_ids.invoice_ids.state',
        'purchase_order_ids.invoice_ids.payment_state',
        'purchase_order_ids.invoice_ids.move_type',
    )
    def _compute_payment_status(self):
        orders = self.env['purchase.order'].sudo().search(
            [('request_id', 'in', self.ids)]
        )
        for request in self:
            bills = orders.filtered(
                lambda o: o.request_id == request
            ).invoice_ids.filtered(
                lambda b: b.move_type == 'in_invoice' and b.state == 'posted'
            )
            request.payment_status = self._payment_status_of(
                bills.mapped('payment_state')
            )


    def action_view_bills(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_("you do not have access t0 vendor bills"))
        bills = self.env['purchase.order'].sudo().search([('request_id','=',self.id)]).invoice_ids
        return{
            'type':'ir.actions.act_window',
            'name':_('Vendor Bills'),
            'res_model':'account.move',
            'view_mode':'list,form',
            'domain':[('id','in',bills.ids)]
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    request_reference = fields.Char(
        string = 'Source Request',
        compute = '_compute_request_reference'
    ) 

    @api.depends('invoice_line_ids.purchase_line_id.order_id.request_id')
    def _compute_request_reference(self):
        for move in self:
            requests = move.sudo().invoice_line_ids.purchase_line_id.order_id.request_id
            move.request_reference = ','.join(requests.mapped('name')) or False


