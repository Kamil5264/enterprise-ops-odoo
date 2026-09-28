from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRequestCompute(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'IT',
            'code': 'IT-01',
        })

    def _create_request(self, lines_vals=None):
        return self.env['enterprise.ops.request'].create({
            'employee_id': self.env.user.id,
            'department_id': self.department.id,
            'reason': 'Test request',
            'line_ids': [(0, 0, vals) for vals in (lines_vals or [])],
        })

    def test_lines_total_sums_subtotals(self):
        request = self._create_request([
            {'product_name': 'Laptop', 'quantity': 2, 'estimated_unit_price': 500.0},
            {'product_name': 'Mouse', 'quantity': 3, 'estimated_unit_price': 20.0},
        ])
        self.assertEqual(request.amount_lines_total, 1060.0)
        self.assertEqual(request.amount_total, 1060.0)

    def test_additional_charges_included_in_total(self):
        request = self._create_request([
            {'product_name': 'Laptop', 'quantity': 1, 'estimated_unit_price': 1000.0},
        ])
        request.amount_additional_charges = 50.0
        self.assertEqual(request.amount_total, 1050.0)

    def test_inverse_amount_total_back_calculates_charges(self):
        request = self._create_request([
            {'product_name': 'Laptop', 'quantity': 1, 'estimated_unit_price': 1000.0},
        ])
        request.amount_total = 1200.0
        self.assertEqual(request.amount_additional_charges, 200.0)

    def test_adding_line_updates_total_live(self):
        request = self._create_request([
            {'product_name': 'Laptop', 'quantity': 1, 'estimated_unit_price': 100.0},
        ])
        self.assertEqual(request.amount_total, 100.0)

        request.write({'line_ids': [(0, 0, {
            'product_name': 'Extra Item',
            'quantity': 1,
            'estimated_unit_price': 50.0,
        })]})

        self.assertEqual(request.amount_lines_total, 150.0)
        self.assertEqual(request.amount_total, 150.0)