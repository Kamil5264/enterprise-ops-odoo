# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestSequence(TransactionCase):

    REFERENCE_PATTERN = r'^REQ/\d{4}/\d{5}$'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Sequence Dept',
            'code': 'SEQ-01',
        })

    def _vals(self, **kwargs):
        vals = {
            'employee_id': self.env.user.id,
            'department_id': self.department.id,
            'reason': 'Sequence test',
        }
        vals.update(kwargs)
        return vals

    def test_reference_format(self):
        request = self.env['enterprise.ops.request'].create(self._vals())
        self.assertRegex(request.name, self.REFERENCE_PATTERN)

    def test_references_are_unique_and_consecutive(self):
        r1 = self.env['enterprise.ops.request'].create(self._vals())
        r2 = self.env['enterprise.ops.request'].create(self._vals())
        self.assertNotEqual(r1.name, r2.name)
        self.assertEqual(
            int(r2.name.split('/')[-1]),
            int(r1.name.split('/')[-1]) + 1,
        )

    def test_batch_create_gets_distinct_references(self):
        records = self.env['enterprise.ops.request'].create([
            self._vals(), self._vals(), self._vals(),
        ])
        self.assertEqual(len(set(records.mapped('name'))), 3)

    def test_duplicate_gets_a_fresh_reference(self):
        request = self.env['enterprise.ops.request'].create(self._vals())
        copy = request.copy()
        self.assertNotEqual(copy.name, request.name)
        self.assertRegex(copy.name, self.REFERENCE_PATTERN)

    def test_client_supplied_name_is_ignored(self):
        """RPC caller tries to spoof a reference - must be overwritten."""
        request = self.env['enterprise.ops.request'].create(
            self._vals(name='HACKED/0001')
        )
        self.assertNotEqual(request.name, 'HACKED/0001')
        self.assertRegex(request.name, self.REFERENCE_PATTERN)

    def test_missing_sequence_fails_loudly(self):
        self.env['ir.sequence'].search(
            [('code', '=', 'enterprise.ops.request')]
        ).unlink()
        with self.assertRaises(UserError):
            self.env['enterprise.ops.request'].create(self._vals())