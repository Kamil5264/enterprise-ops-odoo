from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDemoData(TransactionCase):
    """Skipped automatically on databases created without demo data."""

    EXPECTED_STATES = {
        'demo_req_draft': 'draft',
        'demo_req_submitted': 'submitted',
        'demo_req_stale': 'submitted',
        'demo_req_approved': 'approved',
        'demo_req_rejected': 'rejected',
        'demo_req_procurement': 'procurement',
        'demo_req_done': 'done',
        'demo_req_cancelled': 'cancelled',
    }
    MAINTENANCE = ('demo_req_draft', 'demo_req_stale',
                   'demo_req_rejected', 'demo_req_done')
    IT = ('demo_req_submitted', 'demo_req_approved',
          'demo_req_procurement', 'demo_req_cancelled')

    def setUp(self):
        super().setUp()
        if not self.env.ref('enterprise_ops.demo_req_draft',
                            raise_if_not_found=False):
            self.skipTest("Demo data is not loaded in this database.")

    # ---------------- helpers ----------------
    def _req(self, name):
        return self.env.ref('enterprise_ops.%s' % name)

    def _user(self, name):
        return self.env.ref('enterprise_ops.%s' % name)

    def _visible_names(self, user):
        Request = self.env['enterprise.ops.request']
        by_id = {self._req(n).id: n for n in self.EXPECTED_STATES}
        found = Request.with_user(user).search([('id', 'in', list(by_id))])
        return {by_id[i] for i in found.ids}

    # ---------------- coverage ----------------
    def test_every_workflow_state_has_a_demo_request(self):
        all_states = {
            key for key, _label in
            self.env['enterprise.ops.request']._fields['state'].selection
        }
        self.assertEqual(set(self.EXPECTED_STATES.values()), all_states)

    def test_requests_are_in_the_expected_states(self):
        for name, state in self.EXPECTED_STATES.items():
            self.assertEqual(self._req(name).state, state, name)

    def test_references_are_unique_and_sequence_based(self):
        names = [self._req(n).name for n in self.EXPECTED_STATES]
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, r'^REQ/\d{4}/\d{5}$')

    # ---------------- users ----------------
    def test_demo_users_have_the_intended_roles(self):
        employee = self.env.ref('enterprise_ops.group_employee')
        manager = self.env.ref('enterprise_ops.group_manager')
        self.assertIn(employee, self._user('demo_user_fatima').group_ids)
        self.assertNotIn(manager, self._user('demo_user_fatima').group_ids)
        self.assertIn(manager, self._user('demo_user_layla').group_ids)
        # Procurement and Finance must NOT inherit Employee's own-only rule.
        self.assertNotIn(employee, self._user('demo_user_khalid').group_ids)
        self.assertNotIn(employee, self._user('demo_user_nadia').group_ids)

    def test_visibility_matches_the_role_design(self):
        everything = set(self.EXPECTED_STATES)
        self.assertEqual(self._visible_names(self._user('demo_user_fatima')),
                         set(self.MAINTENANCE))
        self.assertEqual(self._visible_names(self._user('demo_user_yusuf')),
                         set(self.IT))
        self.assertEqual(self._visible_names(self._user('demo_user_layla')),
                         set(self.MAINTENANCE))
        self.assertEqual(self._visible_names(self._user('demo_user_omar')),
                         set(self.IT))
        self.assertEqual(self._visible_names(self._user('demo_user_khalid')),
                         everything)
        self.assertEqual(self._visible_names(self._user('demo_user_nadia')),
                         everything)

    # ---------------- scenarios behave as advertised ----------------
    def test_procurement_request_shows_additional_charges_in_total(self):
        request = self._req('demo_req_procurement')
        self.assertEqual(request.amount_lines_total, 3180.0)
        self.assertEqual(request.amount_additional_charges, 150.0)
        self.assertEqual(request.amount_total, 3330.0)

    def test_decisions_name_the_real_approver(self):
        rejected = self._req('demo_req_rejected')
        self.assertEqual(rejected.decision_user_id, self._user('demo_user_layla'))
        self.assertTrue(rejected.rejection_reason)
        self.assertTrue(rejected.decision_date)
        approved = self._req('demo_req_approved')
        self.assertEqual(approved.decision_user_id, self._user('demo_user_omar'))
        self.assertFalse(approved.rejection_reason)

    def test_stale_request_gets_a_reminder_for_its_manager(self):
        self.env['enterprise.ops.request']._cron_remind_stale_approvals()
        activity_type = self.env.ref(
            'enterprise_ops.mail_activity_type_approval_reminder'
        )
        reminders = self._req('demo_req_stale').activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type
        )
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders.user_id, self._user('demo_user_layla'))

    def test_fresh_submitted_request_is_not_stale(self):
        self.env['enterprise.ops.request']._cron_remind_stale_approvals()
        self.assertFalse(self._req('demo_req_submitted').activity_ids)

    def test_every_demo_line_uses_product_master_data(self):
        for name in self.EXPECTED_STATES:
            for line in self._req(name).line_ids:
                self.assertTrue(line.product_id, name)
                self.assertEqual(line.uom_id, line.product_id.uom_id, name)