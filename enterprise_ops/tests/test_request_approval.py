from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.manager = Users.create({
            'name': 'Approver',
            'login': 'appr_manager',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_manager').id])],
        })
        cls.employee = Users.create({
            'name': 'Requester',
            'login': 'appr_employee',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_employee').id])],
        })
        # manager_id set so T12's manager record rule lets the manager see these.
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Approval Dept',
            'code': 'APR-01',
            'manager_id': cls.manager.id,
        })

    def _submitted_request(self, requester=None):
        requester = requester or self.employee
        request = self.env['enterprise.ops.request'].with_user(requester).create({
            'employee_id': requester.id,
            'department_id': self.department.id,
            'reason': 'Approval test',
            'line_ids': [(0, 0, {
                'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0,
            })],
        })
        request.action_submit()
        return request

    def _wizard(self, requests, decision, user, reason=False):
        return self.env['enterprise.ops.request.approval'].with_user(user).create({
            'request_ids': [(6, 0, requests.ids)],
            'decision': decision,
            'rejection_reason': reason,
        })

    # ---------------- Wizard happy paths ----------------
    def test_wizard_approve_records_audit_fields(self):
        request = self._submitted_request()
        self._wizard(request, 'approve', self.manager).action_confirm()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.decision_user_id, self.manager)
        self.assertTrue(request.decision_date)
        self.assertFalse(request.rejection_reason)

    def test_wizard_reject_records_reason(self):
        request = self._submitted_request()
        self._wizard(request, 'reject', self.manager, 'Over budget').action_confirm()
        self.assertEqual(request.state, 'rejected')
        self.assertEqual(request.rejection_reason, 'Over budget')
        self.assertEqual(request.decision_user_id, self.manager)

    def test_wizard_batch_approve(self):
        r1, r2 = self._submitted_request(), self._submitted_request()
        self._wizard(r1 | r2, 'approve', self.manager).action_confirm()
        self.assertEqual((r1 | r2).mapped('state'), ['approved', 'approved'])

    # ---------------- Mandatory reason ----------------
    def test_reject_without_reason_via_wizard_blocked(self):
        request = self._submitted_request()
        with self.assertRaises(UserError):
            self._wizard(request, 'reject', self.manager, '   ').action_confirm()
        self.assertEqual(request.state, 'submitted')

    def test_reject_without_reason_via_direct_rpc_blocked(self):
        """Bypasses the wizard entirely - the model must still enforce it."""
        request = self._submitted_request()
        with self.assertRaises(UserError):
            request.with_user(self.manager).action_reject()
        self.assertEqual(request.state, 'submitted')

    # ---------------- Authorization ----------------
    def test_employee_cannot_approve_via_direct_rpc(self):
        request = self._submitted_request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).action_approve()
        self.assertEqual(request.state, 'submitted')

    def test_manager_cannot_approve_own_request(self):
        request = self._submitted_request(requester=self.manager)
        with self.assertRaises(UserError):
            request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, 'submitted')

    # ---------------- State rules still apply ----------------
    def test_cannot_approve_a_draft_via_wizard(self):
        request = self.env['enterprise.ops.request'].with_user(self.employee).create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Still draft',
        })
        with self.assertRaises(UserError):
            self._wizard(request, 'approve', self.manager).action_confirm()
        self.assertEqual(request.state, 'draft')

    def test_approval_clears_previous_rejection_reason(self):
        request = self._submitted_request()
        request.with_user(self.manager).action_reject(reason='First attempt')
        request.action_reset_draft()
        request.action_submit()
        request.with_user(self.manager).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertFalse(request.rejection_reason)

    # ---------------- Wizard-opening actions ----------------
    def test_open_wizard_action_for_manager(self):
        request = self._submitted_request()
        action = request.with_user(self.manager).action_open_reject_wizard()
        self.assertEqual(action['res_model'], 'enterprise.ops.request.approval')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(action['context']['default_decision'], 'reject')
        self.assertEqual(action['context']['default_request_ids'], request.ids)

    def test_employee_cannot_open_wizard(self):
        request = self._submitted_request()
        with self.assertRaises(AccessError):
            request.with_user(self.employee).action_open_approve_wizard()