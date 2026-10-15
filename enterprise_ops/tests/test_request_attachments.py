from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestAttachments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        employee_group = cls.env.ref('enterprise_ops.group_employee')
        finance_group = cls.env.ref('enterprise_ops.group_finance')

        cls.employee_a = Users.create({
            'name': 'Evidence Employee A', 'login': 'att_emp_a',
            'group_ids': [(6, 0, (employee_group | employee_group.implied_ids).ids)],
        })
        cls.employee_b = Users.create({
            'name': 'Evidence Employee B', 'login': 'att_emp_b',
            'group_ids': [(6, 0, (employee_group | employee_group.implied_ids).ids)],
        })
        cls.finance = Users.create({
            'name': 'Evidence Finance', 'login': 'att_finance',
            'group_ids': [(6, 0, (finance_group | finance_group.implied_ids).ids)],
        })
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Evidence Dept', 'code': 'ATT-01',
        })

    # ---------------- helpers ----------------
    def _request(self, requester=None):
        requester = requester or self.employee_a
        return self.env['enterprise.ops.request'].create({
            'employee_id': requester.id,
            'department_id': self.department.id,
            'reason': 'Attachment test',
        })

    def _attach(self, request, name='quotation.pdf', user=None):
        attachments = self.env['ir.attachment']
        if user:
            attachments = attachments.with_user(user)
        return attachments.create({
            'name': name,
            'raw': b'evidence',
            'res_model': request._name,
            'res_id': request.id,
        })

    # ---------------- count and button ----------------
    def test_attachment_count(self):
        request = self._request()
        self.assertEqual(request.attachment_count, 0)
        self._attach(request, 'quotation.pdf')
        self._attach(request, 'specification.pdf')
        self.assertEqual(request.attachment_count, 2)

    def test_count_is_correct_for_several_requests_at_once(self):
        r1, r2 = self._request(), self._request()
        self._attach(r1)
        self._attach(r2, 'a.pdf')
        self._attach(r2, 'b.pdf')
        self.assertEqual((r1 | r2).mapped('attachment_count'), [1, 2])

    def test_action_targets_only_this_requests_documents(self):
        r1, r2 = self._request(), self._request()
        a1 = self._attach(r1)
        self._attach(r2)
        action = r1.action_view_attachments()
        found = self.env['ir.attachment'].search(action['domain'])
        self.assertEqual(found, a1)
        self.assertEqual(action['context']['default_res_id'], r1.id)

    def test_form_has_documents_button(self):
        view = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('action_view_attachments', view.arch_db)

    # ---------------- evidence belongs to the original ----------------
    def test_duplicate_does_not_copy_evidence(self):
        request = self._request()
        self._attach(request)
        self.assertEqual(request.copy().attachment_count, 0)

    # ---------------- security (inherited from the record) ----------------
    def test_owner_can_attach_to_own_request(self):
        request = self._request(self.employee_a)
        self._attach(request, user=self.employee_a)
        self.assertEqual(request.attachment_count, 1)

    def test_other_employee_cannot_read_evidence(self):
        request = self._request(self.employee_a)
        attachment = self._attach(request)
        with self.assertRaises(AccessError):
            attachment.with_user(self.employee_b).read(['name'])
        found = self.env['ir.attachment'].with_user(self.employee_b).search(
            [('res_model', '=', request._name)]
        )
        self.assertNotIn(attachment.id, found.ids)

    def test_other_employee_cannot_attach_to_someone_elses_request(self):
        request = self._request(self.employee_a)
        with self.assertRaises(AccessError):
            self._attach(request, user=self.employee_b)

    def test_finance_can_read_but_not_add_evidence(self):
        request = self._request(self.employee_a)
        attachment = self._attach(request)
        attachment.with_user(self.finance).read(['name'])  # must not raise
        with self.assertRaises(AccessError):
            self._attach(request, 'late.pdf', user=self.finance)