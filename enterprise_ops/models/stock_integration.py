from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from odoo.tools import float_compare


class OperationalRequestStock(models.Model):
    """Inventory side of the request, kept apart from request.py the way
    core keeps purchase_stock apart from purchase."""
    _inherit = 'enterprise.ops.request'

    receipt_status = fields.Selection(
        selection=[
            ('none', 'No Order Confirmed'),
            ('pending', 'Waiting for Goods'),
            ('partial', 'Partially Received'),
            ('full', 'Fully Received'),
        ],
        string='Receipt Status',
        compute='_compute_receipt_status',
    )
    picking_count = fields.Integer(
        string='Receipts',
        compute='_compute_picking_count',
        groups='stock.group_stock_user',
    )

    @api.model
    def _receipt_status_of(self, po_lines):
        """Status for a set of confirmed PO lines. Each line compares its own
        received quantity with its own ordered quantity, both in the PO line's
        unit, so no UoM conversion is needed."""
        po_lines = list(po_lines)
        if not po_lines:
            return 'none'
        if all(float_compare(l.qty_received, l.product_qty, precision_digits=3) >= 0
               for l in po_lines):
            return 'full'
        if any(float_compare(l.qty_received, 0.0, precision_digits=3) > 0
               for l in po_lines):
            return 'partial'
        return 'pending'

    @api.depends(
        'purchase_order_ids.state',
        'purchase_order_ids.order_line.qty_received',
        'purchase_order_ids.order_line.product_qty',
    )
    def _compute_receipt_status(self):
        # sudo: this is a STATUS, readable by everyone who can read the request
        # (scoped to self.ids, so the request's own record rules still apply).
        # Vendor, price and receipt documents stay hidden from them.
        lines = self.env['purchase.order.line'].sudo().search([
            ('request_line_id.request_id', 'in', self.ids),
            ('order_id.state', 'in', ('purchase', 'done')),
        ])
        by_request = {}
        for line in lines:
            by_request.setdefault(line.request_line_id.request_id.id, []).append(line)
        for request in self:
            request.receipt_status = self._receipt_status_of(
                by_request.get(request.id, [])
            )

    @api.depends('purchase_order_ids.picking_ids')
    def _compute_picking_count(self):
        orders = self.env['purchase.order'].sudo().search(
            [('request_id', 'in', self.ids)]
        )
        for request in self:
            request.picking_count = len(
                orders.filtered(lambda o: o.request_id == request).picking_ids
            )

    def action_view_receipts(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(_("You do not have access to inventory receipts."))
        # ids are found with sudo, but the list is opened with the user's own
        # rights, so stock record rules still decide what is visible.
        pickings = self.env['purchase.order'].sudo().search(
            [('request_id', '=', self.id)]
        ).picking_ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receipts'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
        }


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # A Char, deliberately NOT a Many2one: showing a Many2one needs read access
    # to the request, and warehouse staff are not one of our roles.
    request_reference = fields.Char(
        string='Source Request',
        compute='_compute_request_reference',
    )

    @api.depends('move_ids.purchase_line_id.order_id.request_id')
    def _compute_request_reference(self):
        for picking in self:
            picking.request_reference = (
                picking.sudo().purchase_id.request_id.name or False
            )