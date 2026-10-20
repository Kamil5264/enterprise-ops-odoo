from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import get_test_product, with_implied


@tagged('post_install', '-at_install')
class TestRequestPurchase(TransactionCase):

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

        cls.procurement = make_user('po_procurement', 'enterprise_ops.group_procurement')
        cls.manager = make_user('po_manager', 'enterprise_ops.group_manager')
        cls.employee = make_user('po_employee', 'enterprise_ops.group_employee')
        cls.vendor = cls.env['res.partner'].create({'name': 'Test Vendor'})
        cls.product = get_test_product(cls.env)
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'PO Dept', 'code': 'POD-01', 'manager_id': cls.manager.id,
        })

    # ---------------- helpers ----------------
    def _request(self, state='procurement'):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Purchase test',
            'line_ids': [
                (0, 0, {'product_id': self.product.id, 'quantity': 2,
                        'estimated_unit_price': 10.0, 'product_name': 'Item A'}),
                (0, 0, {'product_id': self.product.id, 'quantity': 5,
                        'estimated_unit_price': 20.0, 'product_name': 'Item B'}),
            ],
        })
        if state != 'draft':
            request.action_submit()
        if state in ('approved', 'procurement'):
            request.action_approve()
        if state == 'procurement':
            request.action_send_to_procurement()
        return request

    def _rfq(self, request, user=None):
        request = request.with_user(user or self.procurement)
        return request._create_rfq(self.vendor)

    # ---------------- configuration guard ----------------
    def test_procurement_implies_purchase_user(self):
        self.assertIn(
            self.env.ref('purchase.group_purchase_user'),
            self.env.ref('enterprise_ops.group_procurement').implied_ids,
        )

    # ---------------- creating the RFQ ----------------
    def test_rfq_is_a_draft_with_source_references(self):
        request = self._request()
        order = self._rfq(request)
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(order.origin, request.name)
        self.assertEqual(order.request_id, request)
        self.assertEqual(order.company_id, request.company_id)

    def test_every_request_line_is_traced_to_a_po_line(self):
        request = self._request()
        order = self._rfq(request)
        by_source = {pl.request_line_id: pl for pl in order.order_line}
        self.assertEqual(set(by_source), set(request.line_ids))
        for line in request.line_ids:
            po_line = by_source[line]
            self.assertEqual(po_line.product_id, line.product_id)
            self.assertEqual(po_line.product_qty, line.quantity)
            self.assertEqual(po_line.name, line.product_name)

    def test_trace_works_in_both_directions(self):
        request = self._request()
        order = self._rfq(request)
        self.assertEqual(request.purchase_order_ids, order)
        self.assertEqual(request.purchase_count, 1)

    def test_multiple_rfqs_per_request_are_allowed(self):
        request = self._request()
        self._rfq(request)
        self._rfq(request)
        self.assertEqual(request.purchase_count, 2)

    def test_creation_is_noted_in_the_chatter(self):
        request = self._request()
        order = self._rfq(request)
        bodies = ' '.join(str(m.body or '') for m in request.message_ids)
        self.assertIn('RFQ created:', bodies)
        self.assertIn(order.name, bodies)

    def test_duplicated_rfq_does_not_keep_the_source(self):
        order = self._rfq(self._request())
        self.assertFalse(order.copy().request_id)

    # ---------------- who and when ----------------
    def test_rfq_only_from_procurement_state(self):
        for state in ('draft', 'submitted', 'approved'):
            request = self._request(state)
            with self.assertRaises(UserError):
                self._rfq(request)

    def test_manager_cannot_create_rfq(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.manager).action_create_rfq()
        with self.assertRaises(AccessError):
            request.with_user(self.manager)._create_rfq(self.vendor)

    def test_employee_cannot_create_rfq(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).action_create_rfq()

    def test_procurement_gets_the_wizard_action(self):
        request = self._request()
        action = request.with_user(self.procurement).action_create_rfq()
        self.assertEqual(action['res_model'], 'enterprise.ops.request.rfq')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(action['context']['default_request_id'], request.id)

    # ---------------- the wizard ----------------
    def test_wizard_creates_the_rfq_and_opens_it(self):
        request = self._request()
        wizard = self.env['enterprise.ops.request.rfq'].with_user(
            self.procurement
        ).create({'request_id': request.id, 'partner_id': self.vendor.id})
        action = wizard.action_confirm()
        self.assertEqual(action['res_model'], 'purchase.order')
        order = self.env['purchase.order'].browse(action['res_id'])
        self.assertEqual(order.request_id, request)

    def test_wizard_is_not_available_to_a_manager(self):
        request = self._request()
        with self.assertRaises(AccessError):
            self.env['enterprise.ops.request.rfq'].with_user(self.manager).create({
                'request_id': request.id, 'partner_id': self.vendor.id,
            })

    # ---------------- server-side link rules ----------------
    def test_po_cannot_link_to_a_request_not_in_procurement(self):
        draft = self._request('draft')
        with self.assertRaises(ValidationError):
            self.env['purchase.order'].create({
                'partner_id': self.vendor.id, 'request_id': draft.id,
            })

    def test_po_line_must_belong_to_the_linked_request(self):
        order = self._rfq(self._request())
        other_line = self._request().line_ids[0]
        with self.assertRaises(ValidationError):
            order.order_line[0].request_line_id = other_line

    # ---------------- visibility ----------------
    def test_purchase_fields_are_hidden_from_users_without_purchase_rights(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).read(['purchase_count'])

    def test_views_expose_the_integration(self):
        form = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('action_create_rfq', form.arch_db)
        self.assertIn('action_view_purchase_orders', form.arch_db)