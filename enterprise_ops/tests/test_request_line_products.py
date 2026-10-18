# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import get_test_product


@tagged('post_install', '-at_install')
class TestRequestLineProducts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Product Dept', 'code': 'PRD-01',
        })
        cls.request = cls.env['enterprise.ops.request'].create({
            'employee_id': cls.env.user.id,
            'department_id': cls.department.id,
            'reason': 'Product test',
        })
        cls.product = get_test_product(cls.env)

    def _line(self, **kwargs):
        vals = {
            'request_id': self.request.id,
            'product_id': self.product.id,
            'quantity': 1,
            'estimated_unit_price': 10.0,
        }
        vals.update(kwargs)
        return self.env['enterprise.ops.request.line'].create(vals)

    # ---------------- master data drives the line ----------------
    def test_product_is_required(self):
        field = self.env['enterprise.ops.request.line']._fields['product_id']
        self.assertTrue(field.required)

    def test_description_is_filled_from_the_product(self):
        line = self._line()
        self.assertEqual(line.product_name, self.product.display_name)

    def test_uom_comes_from_the_product(self):
        line = self._line()
        self.assertTrue(line.uom_id)
        self.assertEqual(line.uom_id, self.product.uom_id)

    def test_description_can_be_customised_and_is_kept(self):
        line = self._line(product_name='Custom wording for procurement')
        self.assertEqual(line.product_name, 'Custom wording for procurement')

    def test_changing_the_product_resets_description(self):
        line = self._line(product_name='Custom wording')
        other = self.env['product.product'].create({
            'name': 'Another Test Item', 'default_code': 'ENT-OPS-TEST-2',
        })
        line.product_id = other
        self.assertEqual(line.product_name, other.display_name)

    def test_price_is_not_taken_from_the_product(self):
        """Cost and sales price have the wrong meaning/visibility for a
        requester: the estimate stays whatever the user entered."""
        self.product.standard_price = 777.0
        line = self._line(estimated_unit_price=10.0)
        self.assertEqual(line.estimated_unit_price, 10.0)

    # ---------------- UoM is a snapshot ----------------
    def test_uom_is_a_snapshot_of_the_product_at_selection_time(self):
        dozen = self.env.ref('uom.product_uom_dozen', raise_if_not_found=False)
        if not dozen:
            self.skipTest("Dozen UoM is not available in this database.")
        dozen_product = self.env['product.product'].create({
            'name': 'Boxed Test Item',
            'default_code': 'ENT-OPS-DOZ',
            'uom_id': dozen.id,
        })
        line = self._line(product_id=dozen_product.id)
        self.assertEqual(line.uom_id, dozen)
        # The product's UoM changes later: the existing line must not.
        dozen_product.uom_id = self.product.uom_id
        self.assertEqual(line.uom_id, dozen)

    # ---------------- server-side enforcement ----------------
    def test_non_purchasable_product_is_blocked(self):
        sales_only = self.env['product.product'].create({
            'name': 'Sales Only Item',
            'default_code': 'ENT-OPS-SALES',
            'purchase_ok': False,
        })
        with self.assertRaises(ValidationError):
            self._line(product_id=sales_only.id)

    def test_product_of_another_company_is_blocked(self):
        other_company = self.env['res.company'].create({'name': 'Product Co B'})
        foreign = self.env['product.product'].create({
            'name': 'Company B Only Item',
            'default_code': 'ENT-OPS-COB',
            'company_id': other_company.id,
        })
        with self.assertRaises(ValidationError):
            self._line(product_id=foreign.id)

    def test_shared_product_is_allowed(self):
        self.assertFalse(self.product.company_id)
        self.assertTrue(self._line())

    # ---------------- UI ----------------
    def test_form_uses_the_product_picker(self):
        view = self.env.ref('enterprise_ops.view_request_form')
        self.assertIn('product_id', view.arch_db)
        self.assertIn('uom_id', view.arch_db)