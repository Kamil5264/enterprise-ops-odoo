# -*- coding: utf-8 -*-
import base64
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import file_open

from .common import with_implied

HEADER = ('request_key,employee_login,department_code,priority,request_date,'
          'reason,product_code,quantity,unit_price,notes')


@tagged('post_install', '-at_install')
class TestRequestImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def make_user(login, role_xmlid):
            role = cls.env.ref(role_xmlid)
            return Users.create({
                'name': login, 'login': login,
                'group_ids': [(6, 0, with_implied(role).ids)],
            })

        cls.employee_a = make_user('imp_employee_a', 'enterprise_ops.group_employee')
        cls.employee_b = make_user('imp_employee_b', 'enterprise_ops.group_employee')
        cls.finance = make_user('imp_finance', 'enterprise_ops.group_finance')
        Department = cls.env['enterprise.ops.department']
        cls.dept_1 = Department.create({'name': 'Import Dept 1', 'code': 'IMP-01'})
        cls.dept_2 = Department.create({'name': 'Import Dept 2', 'code': 'IMP-02'})
        Product = cls.env['product.product']
        cls.product_1 = Product.create({'name': 'Import Item 1', 'default_code': 'IMP-P1'})
        cls.product_2 = Product.create({'name': 'Import Item 2', 'default_code': 'IMP-P2'})
        Product.create({'name': 'Archived', 'default_code': 'IMP-ARCH', 'active': False})
        Product.create({'name': 'Sales Only', 'default_code': 'IMP-NOBUY',
                        'purchase_ok': False})
        Product.create({'name': 'Dup A', 'default_code': 'IMP-DUP'})
        Product.create({'name': 'Dup B', 'default_code': 'IMP-DUP'})

    # ---------------- helpers ----------------
    @property
    def Wizard(self):
        return self.env['enterprise.ops.request.import']

    def _csv(self, *rows, header=HEADER):
        return '\n'.join([header, *rows])

    def _import(self, text, user=None):
        wizard = self.Wizard
        if user:
            wizard = wizard.with_user(user)
        wizard = wizard.create({
            'csv_file': base64.b64encode(text.encode('utf-8')),
            'csv_filename': 'requests.csv',
        })
        wizard.action_import()
        return wizard

    def _count(self):
        return self.env['enterprise.ops.request'].search_count([])

    def _assert_rejected(self, text, *expected):
        before = self._count()
        wizard = self._import(text)
        self.assertEqual(wizard.state, 'draft')
        self.assertEqual(wizard.created_count, 0)
        self.assertEqual(self._count(), before, "nothing may be imported")
        for fragment in expected:
            self.assertIn(fragment, wizard.report)
        return wizard

    # ---------------- happy path ----------------
    def test_valid_file_creates_draft_requests(self):
        wizard = self._import(self._csv(
            'R1,,IMP-01,normal,2026-11-02,Spare parts,IMP-P1,2,10.5,first',
            'R1,,,,,,IMP-P2,3,20,second',
            'R2,,IMP-02,urgent,,Laptop,IMP-P1,1,900,',
        ))
        self.assertEqual(wizard.state, 'done')
        self.assertEqual(wizard.created_count, 2)
        first, second = wizard.request_ids.sorted('id')
        self.assertEqual(first.state, 'draft')
        self.assertEqual(first.department_id, self.dept_1)
        self.assertEqual(str(first.request_date), '2026-11-02')
        self.assertEqual(first.reason, 'Spare parts')
        self.assertEqual(len(first.line_ids), 2)
        self.assertEqual(first.line_ids[0].product_id, self.product_1)
        self.assertEqual(first.line_ids[0].quantity, 2)
        self.assertEqual(first.line_ids[0].estimated_unit_price, 10.5)
        self.assertEqual(first.line_ids[0].notes, 'first')
        self.assertEqual(first.amount_lines_total, 2 * 10.5 + 3 * 20)
        self.assertEqual(second.priority, '2')
        self.assertEqual(second.state, 'draft')

    def test_rows_of_one_request_need_not_be_adjacent(self):
        wizard = self._import(self._csv(
            'R1,,IMP-01,,,Reason one,IMP-P1,1,1,',
            'R2,,IMP-02,,,Reason two,IMP-P1,1,1,',
            'R1,,,,,,IMP-P2,1,1,',
        ))
        self.assertEqual(wizard.created_count, 2)
        by_reason = {r.reason: r for r in wizard.request_ids}
        self.assertEqual(len(by_reason['Reason one'].line_ids), 2)

    def test_header_may_be_repeated_on_later_rows_when_identical(self):
        wizard = self._import(self._csv(
            'R1,,IMP-01,high,,Same reason,IMP-P1,1,1,',
            'R1,,IMP-01,high,,Same reason,IMP-P2,1,1,',
        ))
        self.assertEqual(wizard.created_count, 1)
        self.assertEqual(len(wizard.request_ids.line_ids), 2)

    def test_blank_unit_price_means_zero(self):
        wizard = self._import(self._csv('R1,,IMP-01,,,Why,IMP-P1,1,,'))
        self.assertEqual(wizard.request_ids.line_ids.estimated_unit_price, 0.0)

    def test_importing_user_is_the_default_employee(self):
        wizard = self._import(self._csv('R1,,IMP-01,,,Mine,IMP-P1,1,1,'),
                              user=self.employee_a)
        self.assertEqual(wizard.request_ids.employee_id, self.employee_a)

    def test_bom_and_semicolon_files_are_accepted(self):
        header = HEADER.replace(',', ';')
        row = 'R1;;IMP-01;;;Why;IMP-P1;1;1;'
        text = '\ufeff' + header + '\n' + row
        created, messages = self.Wizard._process(text.encode('utf-8'))
        self.assertFalse(messages)
        self.assertEqual(len(created), 1)

    # ---------------- header consistency ----------------
    def test_conflicting_header_on_a_later_row_is_reported(self):
        self._assert_rejected(self._csv(
            'R1,,IMP-01,,,Why,IMP-P1,1,1,',
            'R1,,IMP-02,,,,IMP-P2,1,1,',
        ), "Row 3, column 'department_code'", "first row of request 'R1'")

    def test_required_header_values_on_the_first_row(self):
        self._assert_rejected(self._csv(
            'R1,,,,,,IMP-P1,1,1,',
        ), "Row 2, column 'department_code'", "Row 2, column 'reason'")

    # ---------------- all problems at once, all or nothing ----------------
    def test_every_problem_is_reported_in_one_go(self):
        wizard = self._assert_rejected(self._csv(
            'R1,,IMP-01,,,Why,IMP-P1,abc,1,',
            'R2,,NOPE,,,Why,IMP-P1,1,1,',
            'R3,,IMP-01,,,Why,UNKNOWN,1,1,',
        ),
            "3 problem(s) found",
            "Row 2, column 'quantity'",
            "Row 3, column 'department_code'",
            "Row 4, column 'product_code'",
        )
        self.assertLess(wizard.report.index('Row 2'), wizard.report.index('Row 4'))

    def test_one_bad_row_blocks_the_whole_file(self):
        self._assert_rejected(self._csv(
            'GOOD,,IMP-01,,,Fine,IMP-P1,1,1,',
            'BAD,,IMP-01,,,Broken,IMP-P1,0,1,',
        ), "Row 3, column 'quantity'")

    def test_fixed_file_can_be_imported_after_a_rejection(self):
        wizard = self._import(self._csv('R1,,IMP-01,,,Why,IMP-P1,0,1,'))
        self.assertEqual(wizard.state, 'draft')
        wizard.csv_file = base64.b64encode(
            self._csv('R1,,IMP-01,,,Why,IMP-P1,1,1,').encode())
        wizard.action_import()
        self.assertEqual(wizard.state, 'done')
        self.assertEqual(wizard.created_count, 1)

    # ---------------- cell validation ----------------
    def test_bad_quantities(self):
        for value in ('abc', '0', '-1', '1e3', 'nan', 'inf', '1_0', '"1,5"', '',
                      '99999999999999999999'):
            with self.subTest(quantity=value):
                self._assert_rejected(
                    self._csv('R1,,IMP-01,,,Why,IMP-P1,%s,1,' % value),
                    "Row 2, column 'quantity'",
                )

    def test_bad_prices(self):
        for value in ('-1', 'free', 'nan'):
            with self.subTest(unit_price=value):
                self._assert_rejected(
                    self._csv('R1,,IMP-01,,,Why,IMP-P1,1,%s,' % value),
                    "Row 2, column 'unit_price'",
                )

    def test_bad_date_and_priority(self):
        self._assert_rejected(self._csv(
            'R1,,IMP-01,whenever,02/11/2026,Why,IMP-P1,1,1,',
        ), "Row 2, column 'priority'", "Row 2, column 'request_date'")

    def test_missing_request_key(self):
        self._assert_rejected(self._csv(
            ',,IMP-01,,,Why,IMP-P1,1,1,',
        ), "Row 2, column 'request_key'")

    def test_too_many_cells(self):
        self._assert_rejected(self._csv(
            'R1,,IMP-01,,,Why,IMP-P1,1,1,notes,extra',
        ), "Row 2", "quoted")

    # ---------------- lookups ----------------
    def test_unknown_employee(self):
        self._assert_rejected(self._csv(
            'R1,nobody,IMP-01,,,Why,IMP-P1,1,1,',
        ), "Row 2, column 'employee_login'", "nobody")

    def test_ambiguous_product_code(self):
        self._assert_rejected(self._csv(
            'R1,,IMP-01,,,Why,IMP-DUP,1,1,',
        ), "Row 2, column 'product_code'", "must be unique")

    def test_archived_and_non_purchasable_products_are_rejected(self):
        self._assert_rejected(self._csv(
            'R1,,IMP-01,,,Why,IMP-ARCH,1,1,',
            'R2,,IMP-01,,,Why,IMP-NOBUY,1,1,',
        ), "Row 2, column 'product_code'", "Row 3, column 'product_code'")

    # ---------------- header and file level ----------------
    def test_unknown_column_is_rejected(self):
        self._assert_rejected(
            self._csv('R1,,IMP-01,,,Why,IMP-P1,1,1,',
                      header=HEADER.replace('quantity', 'quantiy')),
            "Unknown column(s): quantiy", "Missing required column(s): quantity",
        )

    def test_duplicated_column_is_rejected(self):
        self._assert_rejected(
            self._csv('R1,,IMP-01,,,Why,IMP-P1,1,1,', header=HEADER + ',notes'),
            "Duplicated column(s): notes",
        )

    def test_file_level_problems(self):
        process = self.Wizard._process
        self.assertIn("empty", process(b'')[1][0])
        self.assertIn("no data rows", process(HEADER.encode())[1][0])
        self.assertIn("UTF-8", process('caf\xe9'.encode('latin-1'))[1][0])

    def test_size_and_row_limits(self):
        Wizard = type(self.Wizard)
        row = 'R%s,,IMP-01,,,Why,IMP-P1,1,1,'
        text = self._csv(row % 1, row % 2, row % 3)
        with patch.object(Wizard, '_MAX_ROWS', 2):
            self._assert_rejected(text, "more than 2 data rows")
        with patch.object(Wizard, '_MAX_BYTES', 10):
            _created, messages = self.Wizard._process(text.encode())
            self.assertIn("larger", messages[0])

    # ---------------- security ----------------
    def test_employee_cannot_import_for_someone_else(self):
        before = self._count()
        wizard = self._import(
            self._csv('R1,imp_employee_b,IMP-01,,,Why,IMP-P1,1,1,'),
            user=self.employee_a,
        )
        self.assertEqual(wizard.state, 'draft')
        self.assertIn("not allowed", wizard.report)
        self.assertIn("Request 'R1'", wizard.report)
        self.assertEqual(self._count(), before)

    def test_finance_cannot_open_the_wizard(self):
        with self.assertRaises(AccessError):
            self.Wizard.with_user(self.finance).create({
                'csv_file': base64.b64encode(b'x'),
            })

    # ---------------- creation-phase failures roll everything back ----------
    def test_creation_failure_rolls_back_every_request(self):
        Wizard = type(self.Wizard)
        original = Wizard._create_request

        def flaky(wizard, vals):
            if vals['reason'] == 'boom':
                raise ValidationError('forced failure')
            return original(wizard, vals)

        before = self._count()
        with patch.object(Wizard, '_create_request', flaky):
            wizard = self._import(self._csv(
                'R1,,IMP-01,,,Fine,IMP-P1,1,1,',
                'R2,,IMP-01,,,boom,IMP-P1,1,1,',
            ))
        self.assertEqual(wizard.state, 'draft')
        self.assertIn("Request 'R2' (rows 3)", wizard.report)
        self.assertIn('forced failure', wizard.report)
        self.assertEqual(self._count(), before, "R1 must be rolled back too")

    # ---------------- UI and docs ----------------
    def test_menu_and_view_exist(self):
        menu = self.env.ref('enterprise_ops.menu_enterprise_ops_import')
        self.assertTrue(menu.group_ids)
        view = self.env.ref('enterprise_ops.view_request_import_form')
        self.assertIn('request_import_template.csv', view.arch_db)

    def test_template_file_matches_the_expected_header(self):
        with file_open('enterprise_ops/static/files/request_import_template.csv') as f:
            self.assertEqual(f.readline().strip(), HEADER)