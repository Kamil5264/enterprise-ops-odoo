from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Workflow Dept',
            'code': 'WF-01',
        })

    def _create_request_with_line(self):
        return self.env['enterprise.ops.request'].create({
            'employee_id': self.env.user.id,
            'department_id': self.department.id,
            'reason': 'Workflow test',
            'line_ids': [(0, 0, {
                'product_name': 'Item',
                'quantity': 1,
                'estimated_unit_price': 10.0,
            })],
        })

    def test_full_happy_path(self):
        request = self._create_request_with_line()
        self.assertEqual(request.state, 'draft')

        request.action_submit()
        self.assertEqual(request.state, 'submitted')

        request.action_approve()
        self.assertEqual(request.state, 'approved')

        request.action_send_to_procurement()
        self.assertEqual(request.state, 'procurement')

        request.action_done()
        self.assertEqual(request.state, 'done')

    def test_reject_and_reset_path(self):
        request = self._create_request_with_line()
        request.action_submit()
        request.action_reject(reason='Over budget')
        self.assertEqual(request.state, 'rejected')

        request.action_reset_draft()
        self.assertEqual(request.state, 'draft')

    def test_cannot_approve_a_draft_request(self):
        """Simulates an RPC call bypassing the UI button entirely -
        the button would be invisible in draft, but a direct method
        call must still be blocked server-side."""
        request = self._create_request_with_line()
        with self.assertRaises(UserError):
            request.action_approve()
        self.assertEqual(request.state, 'draft')

    def test_cannot_skip_procurement_straight_to_done(self):
        request = self._create_request_with_line()
        request.action_submit()
        request.action_approve()
        with self.assertRaises(UserError):
            request.action_done()
        self.assertEqual(request.state, 'approved')

    def test_cannot_reset_draft_from_submitted(self):
        request = self._create_request_with_line()
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_reset_draft()
        self.assertEqual(request.state, 'submitted')

    def test_cancel_allowed_from_multiple_states(self):
        request = self._create_request_with_line()
        request.action_submit()
        request.action_cancel()
        self.assertEqual(request.state, 'cancelled')

    def test_cannot_submit_without_lines(self):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.env.user.id,
            'department_id': self.department.id,
            'reason': 'No lines',
        })
        with self.assertRaises(UserError):
            request.action_submit()
        self.assertEqual(request.state, 'draft')