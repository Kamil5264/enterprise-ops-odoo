from types import SimpleNamespace

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from .common import get_test_product, with_implied


@tagged('post_install', '-at_install')
class TestReceiptStatusLogic(TransactionCase):
    """Pure logic: no stock flow involved, so it cannot be broken by the
    receipt-validation API."""

    def _status(self, *pairs):
        lines = [SimpleNamespace(product_qty=o, qty_received=r) for o, r in pairs]
        return self.env['enterprise.ops.request']._receipt_status_of(lines)

    def test_no_confirmed_lines_means_none(self):
        self.assertEqual(self._status(), 'none')

    def test_nothing_received_is_pending(self):
        self.assertEqual(self._status((5, 0)), 'pending')

    def test_some_received_is_partial(self):
        self.assertEqual(self._status((5, 2)), 'partial')

    def test_one_line_done_one_pending_is_partial(self):
        self.assertEqual(self._status((2, 2), (3, 0)), 'partial')

    def test_everything_received_is_full(self):
        self.assertEqual(self._status((2, 2), (3, 3)), 'full')

    def test_over_receipt_counts_as_full(self):
        self.assertEqual(self._status((5, 6)), 'full')

    def test_float_noise_does_not_break_full(self):
        self.assertEqual(self._status((0.3, 0.1 + 0.2)), 'full')


@tagged('post_install', '-at_install')
class TestRequestStockChain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def make_user(login, role_xmlid):
            role = cls.env.ref(role_xmlid)
            return Users.create({
                'name': login, 'login': login,
                'group_ids': [(6, 0, with_implied(role).ids)],
            })

        cls.employee = make_user('stk_employee', 'enterprise_ops.group_employee')
        cls.warehouse = make_user('stk_warehouse', 'stock.group_stock_user')
        cls.vendor = cls.env['res.partner'].create({'name': 'Stock Test Vendor'})
        cls.product_a = get_test_product(cls.env)
        cls.product_b = cls.env['product.product'].create({
            'name': 'Enterprise Ops Test Item B',
            'default_code': 'ENT-OPS-TEST-B',
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Stock Dept', 'code': 'STK-01',
        })

    # ---------------- helpers ----------------
    def _request(self):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Stock test',
            'line_ids': [
                (0, 0, {'product_id': self.product_a.id, 'quantity': 2,
                        'estimated_unit_price': 10.0}),
                (0, 0, {'product_id': self.product_b.id, 'quantity': 5,
                        'estimated_unit_price': 20.0}),
            ],
        })
        request.action_submit()
        request.action_approve()
        request.action_send_to_procurement()
        return request

    def _confirmed_order(self, request):
        order = request._create_rfq(self.vendor)
        order.button_confirm()
        return order

    def _status(self, request):
        request.invalidate_recordset()
        return request.receipt_status

    # ---------------- status follows the purchase side ----------------
    def test_status_is_none_before_any_order(self):
        self.assertEqual(self._status(self._request()), 'none')

    def test_draft_rfq_does_not_count(self):
        request = self._request()
        request._create_rfq(self.vendor)
        self.assertEqual(self._status(request), 'none')

    def test_confirmed_order_waits_for_goods(self):
        request = self._request()
        self._confirmed_order(request)
        self.assertEqual(self._status(request), 'pending')

    def test_cancelled_order_is_ignored(self):
        request = self._request()
        order = self._confirmed_order(request)
        order.button_cancel()
        self.assertEqual(self._status(request), 'none')

    def test_status_is_computed_per_request_in_a_batch(self):
        waiting, untouched = self._request(), self._request()
        self._confirmed_order(waiting)
        both = (waiting | untouched)
        both.invalidate_recordset()
        self.assertEqual(
            {r.id: r.receipt_status for r in both},
            {waiting.id: 'pending', untouched.id: 'none'},
        )

    # ---------------- the chain request -> PO -> receipt ----------------
    def test_receipt_is_reachable_from_the_request(self):
        request = self._request()
        order = self._confirmed_order(request)
        self.assertTrue(order.picking_ids)
        request.invalidate_recordset()
        self.assertEqual(request.picking_count, len(order.picking_ids))

    def test_receipts_action_lists_exactly_the_requests_receipts(self):
        request = self._request()
        order = self._confirmed_order(request)
        action = request.action_view_receipts()
        self.assertEqual(action['res_model'], 'stock.picking')
        found = self.env['stock.picking'].search(action['domain'])
        self.assertEqual(found, order.picking_ids)

    def test_receipt_shows_its_source_request(self):
        request = self._request()
        order = self._confirmed_order(request)
        for picking in order.picking_ids:
            self.assertEqual(picking.request_reference, request.name)

    # ---------------- who sees what ----------------
    def test_warehouse_sees_the_reference_but_cannot_open_the_request(self):
        request = self._request()
        order = self._confirmed_order(request)
        picking = order.picking_ids.with_user(self.warehouse)
        self.assertEqual(picking.request_reference, request.name)
        with self.assertRaises(AccessError):
            request.with_user(self.warehouse).read(['name'])

    def test_employee_sees_the_status_without_purchase_or_stock_rights(self):
        request = self._request()
        self._confirmed_order(request)
        request.invalidate_recordset()
        own = request.with_user(self.employee)
        self.assertEqual(own.receipt_status, 'pending')
        with self.assertRaises(AccessError):
            own.read(['purchase_count'])

    def test_receipts_action_needs_stock_rights(self):
        request = self._request()
        self._confirmed_order(request)
        with self.assertRaises(AccessError):
            request.with_user(self.employee).action_view_receipts()

    # ---------------- real receiving ----------------
    def test_receiving_goods_moves_the_status(self):
        """Uses the stock-move quantity API, the one part not verified
        against the Odoo 19 source. If this test breaks while the logic
        tests above pass, fix this helper, not the production code."""
        request = self._request()
        order = self._confirmed_order(request)
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)

        moves = {m.product_id: m for m in picking.move_ids}
        moves[self.product_a].quantity = 2   # first line complete
        moves[self.product_b].quantity = 0   # second line not yet
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(self._status(request), 'partial')

        backorder = self.env['stock.picking'].search(
            [('backorder_id', '=', picking.id)]
        )
        self.assertEqual(len(backorder), 1)
        backorder.move_ids.quantity = 5
        backorder.button_validate()
        self.assertEqual(self._status(request), 'full')

    # ---------------- UI ----------------
    def test_views_expose_the_chain(self):
        form = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('receipt_status', form.arch_db)
        self.assertIn('action_view_receipts', form.arch_db)
        picking_form = self.env.ref('enterprise_ops.view_picking_form_enterprise_ops')
        self.assertIn('request_reference', picking_form.arch_db)