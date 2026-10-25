# -*- coding: utf-8 -*-
import contextlib

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from .common import with_implied


@tagged('post_install', '-at_install')
class TestPaymentStatusLogic(TransactionCase):
    """Pure mapping: strings in, status out. No accounting involved."""

    def _status(self, *states):
        return self.env['enterprise.ops.request']._payment_status_of(states)

    def test_no_bills_means_none(self):
        self.assertEqual(self._status(), 'none')

    def test_unpaid_bills(self):
        self.assertEqual(self._status('not_paid'), 'unpaid')
        self.assertEqual(self._status('not_paid', 'not_paid'), 'unpaid')

    def test_partially_paid_bill(self):
        self.assertEqual(self._status('partial'), 'partial')

    def test_paid_and_in_payment_both_count_as_paid(self):
        self.assertEqual(self._status('paid'), 'paid')
        self.assertEqual(self._status('in_payment'), 'paid')
        self.assertEqual(self._status('paid', 'in_payment'), 'paid')

    def test_one_paid_one_unpaid_is_partial(self):
        self.assertEqual(self._status('paid', 'not_paid'), 'partial')

    def test_reversed_bills_are_ignored(self):
        self.assertEqual(self._status('reversed'), 'none')
        self.assertEqual(self._status('reversed', 'paid'), 'paid')
        self.assertEqual(self._status('reversed', 'not_paid'), 'unpaid')

    def test_unknown_state_is_never_shown_as_paid(self):
        self.assertEqual(self._status('something_new'), 'unpaid')
        self.assertEqual(self._status('paid', 'something_new'), 'partial')


@tagged('post_install', '-at_install')
class TestRequestPayment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        employee_group = cls.env.ref('enterprise_ops.group_employee')
        cls.employee = Users.create({
            'name': 'pay_employee', 'login': 'pay_employee',
            'group_ids': [(6, 0, with_implied(employee_group).ids)],
        })
        cls.vendor = cls.env['res.partner'].create({'name': 'Payment Test Vendor'})
        cls.product = cls.env['product.product'].create({
            'name': 'Payment Test Item',
            'default_code': 'ENT-OPS-PAY',
            'purchase_method': 'purchase',
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Payment Dept', 'code': 'PAY-01',
        })

    # ---------------- helpers ----------------
    def _request(self):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Payment test',
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 2,
                'estimated_unit_price': 10.0,
            })],
        })
        request.action_submit()
        request.action_approve()
        request.action_send_to_procurement()
        return request

    def _status(self, request):
        request.invalidate_recordset()
        return request.payment_status

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

    def _draft_bill(self, request):
        order = request._create_rfq(self.vendor)
        order.button_confirm()
        order.action_create_invoice()
        return order.invoice_ids

    def _posted_bill(self, request):
        bill = self._draft_bill(request)
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        return bill

    # ---------------- cannot be falsified ----------------
    def test_status_is_derived_not_stored(self):
        field = self.env['enterprise.ops.request']._fields['payment_status']
        self.assertFalse(field.store)
        self.assertFalse(field.inverse)
        self.assertTrue(field.readonly)

    def test_writing_a_status_does_not_change_it(self):
        """The realistic attacker: the requester, who has write access on
        their own request, calling write() over RPC. How the ORM refuses
        (error or silent ignore) differs by version; the invariant is the
        outcome."""
        request = self._request()
        with contextlib.suppress(Exception):
            request.with_user(self.employee).write({'payment_status': 'paid'})
        self.assertEqual(self._status(request), 'none')

    def test_requester_can_read_the_status_without_accounting_rights(self):
        request = self._request()
        request.invalidate_recordset()
        self.assertEqual(request.with_user(self.employee).payment_status, 'none')

    # ---------------- derived from real bills (needs a purchase journal) ----
    def test_draft_bill_does_not_count(self):
        self._require_purchase_journal()
        request = self._request()
        self._draft_bill(request)
        self.assertEqual(self._status(request), 'none')

    def test_posted_unpaid_bill(self):
        self._require_purchase_journal()
        request = self._request()
        self._posted_bill(request)
        self.assertEqual(self._status(request), 'unpaid')

    def test_status_follows_the_bills_payment_state(self):
        """Payment is simulated by setting the bill's payment_state: the
        payment-registration wizard API was not verified for Odoo 19, and
        this test is about OUR derivation, not about Odoo's reconciliation."""
        self._require_purchase_journal()
        request = self._request()
        bill = self._posted_bill(request)
        for payment_state, expected in (
            ('partial', 'partial'),
            ('in_payment', 'paid'),
            ('paid', 'paid'),
            ('not_paid', 'unpaid'),
        ):
            bill.payment_state = payment_state
            self.assertEqual(self._status(request), expected, payment_state)

    def test_one_paid_bill_and_one_unpaid_bill_is_partial(self):
        self._require_purchase_journal()
        request = self._request()
        first = self._posted_bill(request)
        self._posted_bill(request)
        first.payment_state = 'paid'
        self.assertEqual(self._status(request), 'partial')

    # ---------------- UI ----------------
    def test_views_show_the_payment_status(self):
        form = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('payment_status', form.arch_db)