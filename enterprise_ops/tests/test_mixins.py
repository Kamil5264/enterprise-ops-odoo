from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCompanyOwnedMixin(TransactionCase):
   
    def test_operating_unit_uses_mixin_defaults(self):
        ou = self.env['enterprise.ops.operating.unit'].create({
            'name': 'Plant Z',
            'code': 'OU-MIX-1',
        })
        self.assertEqual(ou.company_id, self.env.company)
        self.assertTrue(ou.active)

    def test_department_uses_mixin_defaults(self):
        dept = self.env['enterprise.ops.department'].create({
            'name': 'Mixin Dept',
            'code': 'DEP-MIX-1',
        })
        self.assertEqual(dept.company_id, self.env.company)
        self.assertTrue(dept.active)

    def test_request_uses_mixin_defaults(self):
        dept = self.env['enterprise.ops.department'].create({
            'name': 'Mixin Dept 2',
            'code': 'DEP-MIX-2',
        })
        request = self.env['enterprise.ops.request'].create({
            'employee_id': self.env.user.id,
            'department_id': dept.id,
            'reason': 'Mixin test',
        })
        self.assertEqual(request.company_id, self.env.company)
        self.assertTrue(request.active)