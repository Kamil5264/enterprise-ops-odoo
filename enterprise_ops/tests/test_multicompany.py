from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})

        cls.dept_a = cls.env['enterprise.ops.department'].create({
            'name': 'Dept A', 'code': 'MC-A', 'company_id': cls.company_a.id,
        })
        cls.dept_b = cls.env['enterprise.ops.department'].create({
            'name': 'Dept B', 'code': 'MC-B', 'company_id': cls.company_b.id,
        })

        cls.group_employee = cls.env.ref('enterprise_ops.group_employee')
        cls.group_admin = cls.env.ref('enterprise_ops.group_admin')

        Users = cls.env['res.users'].with_context(no_reset_password=True)

        cls.employee_a = Users.create({
            'name': 'Employee Company A',
            'login': 'mc_employee_a',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'group_ids': [(6, 0, [cls.group_employee.id])],
        })
        cls.employee_b = Users.create({
            'name': 'Employee Company B',
            'login': 'mc_employee_b',
            'company_id': cls.company_b.id,
            'company_ids': [(6, 0, [cls.company_b.id])],
            'group_ids': [(6, 0, [cls.group_employee.id])],
        })
        # Admin whose allowed companies are deliberately limited to A only -
        # proves T12's "admin sees all" rule does NOT bypass company isolation.
        cls.admin_a_only = Users.create({
            'name': 'Admin (Company A only)',
            'login': 'mc_admin_a',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'group_ids': [(6, 0, [cls.group_admin.id])],
        })

        cls.request_a = cls.env['enterprise.ops.request'].with_user(cls.employee_a).create({
            'employee_id': cls.employee_a.id,
            'department_id': cls.dept_a.id,
            'company_id': cls.company_a.id,
            'reason': 'Company A request',
            'line_ids': [(0, 0, {'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0})],
        })
        cls.request_b = cls.env['enterprise.ops.request'].with_user(cls.employee_b).create({
            'employee_id': cls.employee_b.id,
            'department_id': cls.dept_b.id,
            'company_id': cls.company_b.id,
            'reason': 'Company B request',
            'line_ids': [(0, 0, {'product_name': 'Item', 'quantity': 1, 'estimated_unit_price': 10.0})],
        })

    def test_employee_search_excludes_other_company_department(self):
        found = self.env['enterprise.ops.department'].with_user(self.employee_a).search([])
        self.assertIn(self.dept_a.id, found.ids)
        self.assertNotIn(self.dept_b.id, found.ids)

    def test_employee_cannot_browse_other_company_request(self):
        """RPC-bypass simulation: direct browse() with a known ID, not search()."""
        record = self.env['enterprise.ops.request'].with_user(self.employee_a).browse(
            self.request_b.id
        )
        with self.assertRaises(AccessError):
            record.read(['name'])

    def test_request_line_isolated_by_parent_company(self):
        other_company_line = self.request_b.line_ids[0]
        record = other_company_line.with_user(self.employee_a)
        with self.assertRaises(AccessError):
            record.read(['product_name'])

    def test_admin_restricted_to_allowed_companies_despite_role_rule(self):
        """Regression test: T12 gives group_admin an unrestricted
        role-scope rule, but T13's global company-isolation rule must
        still apply via AND-combination. An admin whose allowed
        companies is limited to Company A must NOT see Company B data."""
        found = self.env['enterprise.ops.request'].with_user(self.admin_a_only).search([])
        self.assertIn(self.request_a.id, found.ids)
        self.assertNotIn(self.request_b.id, found.ids)

        with self.assertRaises(AccessError):
            self.request_b.with_user(self.admin_a_only).read(['name'])