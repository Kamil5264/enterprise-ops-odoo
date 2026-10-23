from odoo.tests.common import TransactionCase, tagged

from .common import with_implied


@tagged('post_install', '-at_install')
class TestRequestAccounting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def make_user(login, group_xmlid):
            group = cls.env.ref(group_xmlid)
            return Users.create({
                'name': login, 'login': login,
                'group_ids': [(6, 0, with_implied(group).ids)],
            })

        cls.employee = make_user('acc_employee', 'enterprise_ops.group_employee')
        cls.accountant = make_user('acc_accountant', 'account.group_account_invoice')
        cls.vendor = cls.env['res.partner'].create({'name': 'Billing Test Vendor'})
        # 'On ordered quantities': a bill can be created without receiving
        # goods, so these tests do not depend on the stock-receipt flow.
        cls.product = cls.env['product.product'].create({
            'name': 'Billing Test Item',
            'default_code': 'ENT-OPS-BILL',
            'purchase_method': 'purchase',
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Billing Dept', 'code': 'BIL-01',
        })

    # ---------------- helpers ----------------
    def _request(self):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Billing test',
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 2,
                'estimated_unit_price': 10.0,
            })],
        })
        request.action_submit()
        request.action_approve()
        request.action_send_to_procurement()
        return request

    def _confirmed_order(self, request):
        order = request._create_rfq(self.vendor)
        order.button_confirm()
        return order

    def _require_purchase_journal(self):
        journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            self.skipTest(
                "No purchase journal: install a chart of accounts "
                "(fiscal localization) to run the bill tests."
            )

    def _billed_order(self, request):
        order = self._confirmed_order(request)
        order.action_create_invoice()
        return order

    # ---------------- access and structure (no bills needed) ----------------
    def test_bill_count_is_zero_without_bills(self):
        request = self._request()
        self._confirmed_order(request)
        request.invalidate_recordset()
        self.assertEqual(request.bill_count, 0)

    def test_bill_field_is_restricted_to_billing_users(self):
        field = self.env['enterprise.ops.request']._fields['bill_count']
        self.assertIn('account.group_account_invoice', field.groups)

    def test_employee_cannot_read_the_bill_count(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).read(['bill_count'])

    def test_employee_cannot_open_the_bills(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).action_view_bills()

    def test_views_expose_the_trace(self):
        form = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('action_view_bills', form.arch_db)
        bill_form = self.env.ref('enterprise_ops.view_move_form_enterprise_ops')
        self.assertIn('request_reference', bill_form.arch_db)

    # ---------------- the trace (needs a purchase journal) ----------------
    def test_bill_is_reachable_from_the_request(self):
        self._require_purchase_journal()
        request = self._request()
        order = self._billed_order(request)
        bills = order.invoice_ids
        self.assertEqual(len(bills), 1)
        request.invalidate_recordset()
        self.assertEqual(request.bill_count, 1)
        action = request.action_view_bills()
        self.assertEqual(self.env['account.move'].search(action['domain']), bills)

    def test_bill_shows_its_source_request(self):
        self._require_purchase_journal()
        request = self._request()
        bill = self._billed_order(request).invoice_ids
        self.assertEqual(bill.request_reference, request.name)

    def test_accountant_sees_the_reference_but_cannot_open_the_request(self):
        self._require_purchase_journal()
        request = self._request()
        bill = self._billed_order(request).invoice_ids
        self.assertEqual(bill.with_user(self.accountant).request_reference,
                         request.name)
        with self.assertRaises(AccessError):
            request.with_user(self.accountant).read(['name'])

    def test_each_requests_bill_is_counted_separately(self):
        self._require_purchase_journal()
        first, second = self._request(), self._request()
        self._billed_order(first)
        self._billed_order(second)
        (first | second).invalidate_recordset()
        self.assertEqual(first.bill_count, 1)
        self.assertEqual(second.bill_count, 1)

    def test_bill_without_a_purchase_has_no_reference(self):
        self._require_purchase_journal()
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.vendor.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Manual line', 'quantity': 1, 'price_unit': 5.0,
            })],
        })
        self.assertFalse(bill.request_reference)