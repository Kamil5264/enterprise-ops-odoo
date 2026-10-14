from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestChatter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.manager = Users.create({
            'name': 'Chatter Manager',
            'login': 'chat_manager',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_manager').id])],
        })
        cls.employee = Users.create({
            'name': 'Chatter Employee',
            'login': 'chat_employee',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_employee').id])],
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Chatter Dept',
            'code': 'CHT-01',
            'manager_id': cls.manager.id,
        })
        cls.other_department = cls.env['enterprise.ops.department'].create({
            'name': 'Second Chatter Dept',
            'code': 'CHT-02',
        })

    # ---------------- helpers ----------------
    def _request(self):
        return self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Chatter test',
            'line_ids': [(0, 0, {
                'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0,
            })],
        })

    def _tracked(self, request, field_name):
        return request.message_ids.tracking_value_ids.filtered(
            lambda t: t.field_id.name == field_name
        )

    def _bodies(self, request):
        return [str(m.body or '') for m in request.message_ids]

    # ---------------- tracked fields ----------------
    def test_state_changes_are_tracked(self):
        request = self._request()
        request.action_submit()
        request.with_user(self.manager).action_approve()
        changes = [(t.old_value_char, t.new_value_char)
                   for t in self._tracked(request, 'state')]
        self.assertIn(('Draft', 'Submitted'), changes)
        self.assertIn(('Submitted', 'Approved'), changes)

    def test_amount_total_change_is_tracked(self):
        """Computed + stored field: proves tracking fires when a line
        price change recomputes the total."""
        request = self._request()
        request.line_ids.estimated_unit_price = 25.0
        changes = [(t.old_value_float, t.new_value_float)
                   for t in self._tracked(request, 'amount_total')]
        self.assertIn((10.0, 25.0), changes)

    def test_additional_charges_change_is_tracked(self):
        request = self._request()
        request.amount_additional_charges = 5.0
        changes = [(t.old_value_float, t.new_value_float)
                   for t in self._tracked(request, 'amount_additional_charges')]
        self.assertIn((0.0, 5.0), changes)

    def test_priority_change_is_tracked(self):
        request = self._request()
        request.priority = '2'
        changes = [(t.old_value_char, t.new_value_char)
                   for t in self._tracked(request, 'priority')]
        self.assertIn(('Normal', 'Urgent'), changes)

    def test_department_change_is_tracked(self):
        request = self._request()
        request.department_id = self.other_department
        self.assertEqual(len(self._tracked(request, 'department_id')), 1)

    def test_untracked_field_change_is_not_logged(self):
        request = self._request()
        request.request_date = '2020-01-01'
        self.assertFalse(self._tracked(request, 'request_date'))

    # ---------------- rejection note ----------------
    def test_rejection_reason_is_in_history(self):
        request = self._request()
        request.action_submit()
        request.with_user(self.manager).action_reject(reason='Over budget')
        self.assertTrue(any(
            'Rejected. Reason:' in b and 'Over budget' in b
            for b in self._bodies(request)
        ))

    def test_rejection_reason_is_html_escaped(self):
        request = self._request()
        request.action_submit()
        request.with_user(self.manager).action_reject(
            reason='<script>alert(1)</script>'
        )
        bodies = ' '.join(self._bodies(request))
        self.assertIn('&lt;script&gt;', bodies)
        self.assertNotIn('<script>', bodies)

    # ---------------- visibility ----------------
    def test_employee_can_read_own_request_history(self):
        request = self._request()
        request.action_submit()
        messages = request.with_user(self.employee).message_ids
        self.assertTrue(messages)

    def test_form_view_has_chatter(self):
        view = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('<chatter', view.arch_db)