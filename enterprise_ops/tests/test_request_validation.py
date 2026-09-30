 # -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

@tagged('post_install', '-at_install')
class TestRequestValidation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['enterprise.ops.department'].create({
            'name': 'Validation Dept',
            'code': 'VAL-01',
        })
        cls.other_company = cls.env['res.company'].create({'name': 'Other Co'})
        cls.other_department = cls.env['enterprise.ops.department'].create({
            'name': 'Other Co Dept',
            'code': 'VAL-02',
            'company_id': cls.other_company.id,
        })

    def _create_request(self, **kwargs):
        vals = {
            'employee_id': self.env.user.id,
            'department_id': self.department.id,
            'reason': 'Validation test',
        }
        vals.update(kwargs)
        return self.env['enterprise.ops.request'].create(vals)

    # ---------------- Line-level constraints ----------------
    def test_quantity_must_be_positive(self):
        request = self._create_request()
        with self.assertRaises(ValidationError):
            self.env['enterprise.ops.request.line'].create({
                'request_id': request.id,
                'product_name': 'Bad Line',
                'quantity': 0,
                'estimated_unit_price': 10.0,
            })

    def test_price_cannot_be_negative(self):
        request = self._create_request()
        with self.assertRaises(ValidationError):
            self.env['enterprise.ops.request.line'].create({
                'request_id': request.id,
                'product_name': 'Bad Price',
                'quantity': 1,
                'estimated_unit_price': -5.0,
            })

    # ---------------- Request-level constraints ----------------
    def test_reason_cannot_be_blank(self):
        with self.assertRaises(ValidationError):
            self._create_request(reason='   ')

    def test_department_company_mismatch_blocked(self):
        
        with self.assertRaises(ValidationError):
            self._create_request(
                department_id=self.other_department.id,
                company_id=self.env.company.id,
            )

    # ---------------- Onchange UX ----------------
    def test_onchange_company_clears_mismatched_department(self):
        with Form(self.env['enterprise.ops.request']) as form:
            form.employee_id = self.env.user
            form.department_id = self.department
            form.reason = 'Onchange test'
            form.company_id = self.other_company
            self.assertFalse(form.department_id)