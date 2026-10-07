from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestRecordRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_employee = cls.env.ref('enterprise_ops.group_employee')
        cls.group_manager = cls.env.ref('enterprise_ops.group_manager')
        cls.group_admin = cls.env.ref('enterprise_ops.group_admin')

        Users = cls.env['res.users'].with_context(no_reset_password=True)

        cls.manager_user = Users.create({
            'name': 'Dept Manager',
            'login': 'rr_manager',
            'group_ids': [(6, 0, [cls.group_manager.id])],
        })
        cls.employee_a = Users.create({
            'name': 'Employee A',
            'login': 'rr_employee_a',
            'group_ids': [(6, 0, [cls.group_employee.id])],
        })
        cls.employee_b = Users.create({
            'name': 'Employee B',
            'login': 'rr_employee_b',
            'group_ids': [(6, 0, [cls.group_employee.id])],
        })
        cls.admin_user = Users.create({
            'name': 'Ops Admin',
            'login': 'rr_admin',
            'group_ids': [(6, 0, [cls.group_admin.id])],
        })

        cls.dept = cls.env['enterprise.ops.department'].create({
            'name': 'Record Rule Dept',
            'code': 'RR-01',
            'manager_id': cls.manager_user.id,
        })
        cls.other_dept = cls.env['enterprise.ops.department'].create({
            'name': 'Other Dept',
            'code': 'RR-02',
        })

        cls.request_a = cls.env['enterprise.ops.request'].with_user(cls.employee_a).create({
            'employee_id': cls.employee_a.id,
            'department_id': cls.dept.id,
            'reason': 'Employee A request',
            'line_ids': [(0, 0, {'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0})],
        })
        cls.request_other_dept = cls.env['enterprise.ops.request'].with_user(cls.employee_b).create({
            'employee_id': cls.employee_b.id,
            'department_id': cls.other_dept.id,
            'reason': 'Other dept request',
            'line_ids': [(0, 0, {'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0})],
        })

    def test_employee_cannot_see_others_request(self):
        with self.assertRaises(AccessError):
            self.request_other_dept.with_user(self.employee_a).read(['name'])

    def test_employee_search_excludes_others_requests(self):
        found = self.env['enterprise.ops.request'].with_user(self.employee_a).search([])
        self.assertIn(self.request_a.id, found.ids)
        self.assertNotIn(self.request_other_dept.id, found.ids)

    def test_rpc_direct_browse_cannot_bypass_rule(self):
        """Simulates an RPC call that already knows the record ID and
        skips search() entirely - record rules must still block it."""
        record = self.env['enterprise.ops.request'].with_user(self.employee_a).browse(
            self.request_other_dept.id
        )
        with self.assertRaises(AccessError):
            record.read(['name'])

    def test_manager_sees_own_department_request(self):
        found = self.env['enterprise.ops.request'].with_user(self.manager_user).search([])
        self.assertIn(self.request_a.id, found.ids)

    def test_manager_cannot_see_other_department_request(self):
        with self.assertRaises(AccessError):
            self.request_other_dept.with_user(self.manager_user).read(['name'])

    def test_admin_sees_all_requests_despite_implied_manager_group(self):
        """Regression test for the OR-combination pitfall: group_admin
        implies group_manager via implied_ids, so without the explicit
        unrestricted admin rule, this would incorrectly fail."""
        found = self.env['enterprise.ops.request'].with_user(self.admin_user).search([])
        self.assertIn(self.request_a.id, found.ids)
        self.assertIn(self.request_other_dept.id, found.ids)