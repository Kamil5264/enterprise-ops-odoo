from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Security Dept',
            'code': 'SEC-01',
        })

        cls.group_employee = cls.env.ref('enterprise_ops.group_employee')
        cls.group_manager = cls.env.ref('enterprise_ops.group_manager')
        cls.group_finance = cls.env.ref('enterprise_ops.group_finance')
        cls.group_admin = cls.env.ref('enterprise_ops.group_admin')

        Users = cls.env['res.users'].with_context(no_reset_password=True)

        cls.employee_user = Users.create({
            'name': 'Test Employee',
            'login': 'test_employee_t11',
            'group_ids': [(6, 0, [cls.group_employee.id])],
        })
        cls.manager_user = Users.create({
            'name': 'Test Manager',
            'login': 'test_manager_t11',
            'group_ids': [(6, 0, [cls.group_manager.id])],
        })
        cls.finance_user = Users.create({
            'name': 'Test Finance',
            'login': 'test_finance_t11',
            'group_ids': [(6, 0, [cls.group_finance.id])],
        })
        cls.admin_user = Users.create({
            'name': 'Test Ops Admin',
            'login': 'test_opsadmin_t11',
            'group_ids': [(6, 0, [cls.group_admin.id])],
        })

    def _create_request_as(self, user):
        return self.env['enterprise.ops.request'].with_user(user).create({
            'employee_id': user.id,
            'department_id': self.department.id,
            'reason': 'Security test',
            'line_ids': [(0, 0, {
                'product_name': 'Item',
                'quantity': 1,
                'estimated_unit_price': 10.0,
            })],
        })

    def test_employee_can_create_own_request(self):
        request = self._create_request_as(self.employee_user)
        self.assertTrue(request)

    def test_employee_cannot_unlink_request(self):
        request = self._create_request_as(self.employee_user)
        with self.assertRaises(AccessError):
            request.with_user(self.employee_user).unlink()

    def test_employee_cannot_create_department(self):
        with self.assertRaises(AccessError):
            self.env['enterprise.ops.department'].with_user(self.employee_user).create({
                'name': 'Rogue Dept',
                'code': 'ROGUE-01',
            })

    def test_manager_can_approve_request(self):
        request = self._create_request_as(self.employee_user)
        request.with_user(self.manager_user).action_submit()
        request.with_user(self.manager_user).action_approve()
        self.assertEqual(request.state, 'approved')

    def test_manager_cannot_create_department(self):
        with self.assertRaises(AccessError):
            self.env['enterprise.ops.department'].with_user(self.manager_user).create({
                'name': 'Manager Dept',
                'code': 'MGR-01',
            })

    def test_finance_cannot_write_request(self):
        request = self._create_request_as(self.employee_user)
        with self.assertRaises(AccessError):
            request.with_user(self.finance_user).write({'reason': 'Hacked'})

    def test_finance_can_read_request(self):
        request = self._create_request_as(self.employee_user)
        request.with_user(self.finance_user).read(['name', 'state'])  # should not raise

    def test_admin_can_manage_master_data(self):
        dept = self.env['enterprise.ops.department'].with_user(self.admin_user).create({
            'name': 'Admin Dept',
            'code': 'ADM-01',
        })
        dept.with_user(self.admin_user).write({'name': 'Admin Dept Renamed'})
        dept.with_user(self.admin_user).unlink()