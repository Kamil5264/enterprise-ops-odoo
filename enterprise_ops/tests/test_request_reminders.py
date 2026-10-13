from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestReminders(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.manager = Users.create({
            'name': 'Reminder Manager',
            'login': 'rem_manager',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_manager').id])],
        })
        cls.employee = Users.create({
            'name': 'Reminder Employee',
            'login': 'rem_employee',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_employee').id])],
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Reminder Dept',
            'code': 'REM-01',
            'manager_id': cls.manager.id,
        })
        cls.activity_type = cls.env.ref(
            'enterprise_ops.mail_activity_type_approval_reminder'
        )

    # ---------------- helpers ----------------
    def _submitted_request(self, department=None, requester=None, age_days=5):
        request = self.env['enterprise.ops.request'].create({
            'employee_id': (requester or self.employee).id,
            'department_id': (department or self.department).id,
            'reason': 'Reminder test',
            'line_ids': [(0, 0, {
                'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0,
            })],
        })
        request.action_submit()
        request.submitted_date = fields.Datetime.now() - timedelta(days=age_days)
        return request

    def _run_cron(self):
        self.env['enterprise.ops.request']._cron_remind_stale_approvals()

    def _reminders(self, request):
        return request.activity_ids.filtered(
            lambda a: a.activity_type_id == self.activity_type
        )

    # ---------------- core behaviour ----------------
    def test_stale_request_gets_one_reminder_for_department_manager(self):
        request = self._submitted_request()
        self._run_cron()
        reminders = self._reminders(request)
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders.user_id, self.manager)
        self.assertTrue(request.last_reminder_date)

    def test_fresh_request_is_not_reminded(self):
        request = self._submitted_request(age_days=0)
        self._run_cron()
        self.assertFalse(self._reminders(request))

    def test_only_submitted_requests_are_considered(self):
        draft = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Still draft',
        })
        draft.submitted_date = fields.Datetime.now() - timedelta(days=10)
        approved = self._submitted_request()
        approved.action_approve()
        self._run_cron()
        self.assertFalse(self._reminders(draft))
        self.assertFalse(self._reminders(approved))

    # ---------------- anti-spam ----------------
    def test_running_cron_twice_does_not_duplicate(self):
        request = self._submitted_request()
        self._run_cron()
        self._run_cron()
        self.assertEqual(len(self._reminders(request)), 1)

    def test_no_new_reminder_while_one_is_still_open(self):
        request = self._submitted_request()
        self._run_cron()
        # Even after the repeat window has long passed, an open reminder
        # must prevent stacking another one.
        request.last_reminder_date = fields.Datetime.now() - timedelta(days=30)
        self._run_cron()
        self.assertEqual(len(self._reminders(request)), 1)

    def test_reminder_repeats_only_after_done_and_repeat_window(self):
        request = self._submitted_request()
        self._run_cron()
        # Removing the activity has the same effect as marking it done.
        self._reminders(request).unlink()

        self._run_cron()  # still inside the repeat window
        self.assertFalse(self._reminders(request))

        request.last_reminder_date = fields.Datetime.now() - timedelta(days=4)
        self._run_cron()  # window passed, request still pending
        self.assertEqual(len(self._reminders(request)), 1)

    def test_resubmission_resets_reminder_cycle(self):
        request = self._submitted_request()
        self._run_cron()
        self.assertTrue(request.last_reminder_date)
        request.action_reject(reason='Needs changes')
        request.action_reset_draft()
        request.action_submit()
        self.assertFalse(request.last_reminder_date)
        self.assertLess(
            fields.Datetime.now() - request.submitted_date, timedelta(minutes=1)
        )

    # ---------------- skipped cases ----------------
    def test_department_without_manager_is_skipped(self):
        dept = self.env['enterprise.ops.department'].create({
            'name': 'No Manager Dept', 'code': 'REM-02',
        })
        request = self._submitted_request(department=dept)
        self._run_cron()
        self.assertFalse(self._reminders(request))
        self.assertFalse(request.last_reminder_date)

    def test_manager_who_is_the_requester_is_skipped(self):
        request = self._submitted_request(requester=self.manager)
        self._run_cron()
        self.assertFalse(self._reminders(request))