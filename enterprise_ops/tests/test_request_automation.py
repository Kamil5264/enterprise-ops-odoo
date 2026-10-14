# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestAutomation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.manager = Users.create({
            'name': 'Auto Manager',
            'login': 'auto_manager',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_manager').id])],
        })
        cls.employee = Users.create({
            'name': 'Auto Employee',
            'login': 'auto_employee',
            'group_ids': [(6, 0, [cls.env.ref('enterprise_ops.group_employee').id])],
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Automation Dept',
            'code': 'AUT-01',
            'manager_id': cls.manager.id,
        })
        cls.activity_type = cls.env.ref(
            'enterprise_ops.mail_activity_type_approval_reminder'
        )

    # ---------------- helpers ----------------
    def _request_with_reminder(self):
        """A stale submitted request that already has its reminder."""
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.employee.id,
            'department_id': self.department.id,
            'reason': 'Automation test',
            'line_ids': [(0, 0, {
                'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0,
            })],
        })
        request.action_submit()
        request.submitted_date = fields.Datetime.now() - timedelta(days=5)
        self.env['enterprise.ops.request']._cron_remind_stale_approvals()
        self.assertEqual(len(self._reminders(request)), 1)
        return request

    def _reminders(self, request):
        return request.activity_ids.filtered(
            lambda a: a.activity_type_id == self.activity_type
        )

    def _closing_messages(self, request):
        return request.message_ids.filtered(
            lambda m: 'Closed automatically' in str(m.body or '')
        )

    # ---------------- the event ----------------
    def test_approval_closes_the_reminder(self):
        request = self._request_with_reminder()
        request.with_user(self.manager).action_approve()
        self.assertFalse(self._reminders(request))
        self.assertEqual(len(self._closing_messages(request)), 1)

    def test_rejection_closes_the_reminder(self):
        request = self._request_with_reminder()
        request.with_user(self.manager).action_reject(reason='No budget')
        self.assertFalse(self._reminders(request))

    def test_employee_cancelling_own_request_closes_managers_reminder(self):
        """The housekeeping runs with sudo: the employee has no rights on
        the manager's activity, yet the cancel must neither fail nor
        leave the reminder behind."""
        request = self._request_with_reminder()
        request.with_user(self.employee).action_cancel()
        self.assertEqual(request.state, 'cancelled')
        self.assertFalse(self._reminders(request))

    # ---------------- idempotency ----------------
    def test_running_it_again_is_a_noop(self):
        request = self._request_with_reminder()
        request.with_user(self.manager).action_approve()
        self.assertEqual(request._close_obsolete_reminders(), 0)
        self.assertEqual(request._close_obsolete_reminders(), 0)
        self.assertEqual(len(self._closing_messages(request)), 1)

    def test_pending_request_keeps_its_reminder(self):
        request = self._request_with_reminder()
        self.assertEqual(request._close_obsolete_reminders(), 0)
        self.assertEqual(len(self._reminders(request)), 1)

    def test_mixed_selection_only_closes_obsolete_reminders(self):
        pending = self._request_with_reminder()
        decided = self._request_with_reminder()
        # Bypass the transition hook to simulate a leftover from before
        # this automation existed.
        decided.write({'state': 'approved'})
        self.assertEqual((pending | decided)._close_obsolete_reminders(), 1)
        self.assertEqual(len(self._reminders(pending)), 1)
        self.assertFalse(self._reminders(decided))

    # ---------------- the manual server action ----------------
    def test_server_action_cleans_up_leftovers(self):
        leftover = self._request_with_reminder()
        leftover.write({'state': 'approved'})
        action = self.env.ref('enterprise_ops.server_action_close_obsolete_reminders')
        action.with_context(
            active_model='enterprise.ops.request',
            active_ids=leftover.ids,
        ).run()
        self.assertFalse(self._reminders(leftover))