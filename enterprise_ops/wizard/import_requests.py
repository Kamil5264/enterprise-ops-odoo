# -*- coding: utf-8 -*-
import base64
import csv
import io
import re
from collections import defaultdict
from datetime import datetime

from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError

# Plain decimals only. float() would also accept 'nan', 'inf', '1e5', '1_000'.
_NUMBER = re.compile(r'[+-]?(\d+(\.\d*)?|\.\d+)')


class _ImportRollback(Exception):
    """Raised on purpose to roll the whole import back."""


class RequestImportWizard(models.TransientModel):
    _name = 'enterprise.ops.request.import'
    _description = 'Import Requests from CSV'

    _MAX_BYTES = 2 * 1024 * 1024
    _MAX_ROWS = 1000
    _MAX_NUMBER = 10 ** 12
    _MAX_REPORTED = 100
    _COLUMNS = (
        'request_key', 'employee_login', 'department_code', 'priority',
        'request_date', 'reason', 'product_code', 'quantity',
        'unit_price', 'notes',
    )
    _REQUIRED_COLUMNS = (
        'request_key', 'department_code', 'reason', 'product_code', 'quantity',
    )
    _PRIORITIES = {
        '0': '0', 'normal': '0', '1': '1', 'high': '1', '2': '2', 'urgent': '2',
    }

    csv_file = fields.Binary(string='CSV File', required=True)
    csv_filename = fields.Char()
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('done', 'Done')],
        default='draft',
    )
    report = fields.Text(string='Result', readonly=True)
    created_count = fields.Integer(readonly=True)
    request_ids = fields.Many2many(
        comodel_name='enterprise.ops.request',
        relation='enterprise_ops_request_import_rel',
        column1='wizard_id',
        column2='request_id',
        string='Imported Requests',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    def action_import(self):
        self.ensure_one()
        created, messages = self._process(base64.b64decode(self.csv_file or b''))
        if messages:
            self.write({
                'state': 'draft',
                'report': self._format_errors(messages),
                'created_count': 0,
                'request_ids': [(5, 0, 0)],
            })
        else:
            shown = ', '.join(created[:20].mapped('name'))
            if len(created) > 20:
                shown += ', ...'
            self.write({
                'state': 'done',
                'report': _(
                    "Imported %(requests)s request(s) with %(lines)s line(s) "
                    "as drafts: %(names)s.\nReview them and submit when ready.",
                    requests=len(created),
                    lines=len(created.line_ids),
                    names=shown,
                ),
                'created_count': len(created),
                'request_ids': [(6, 0, created.ids)],
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Requests'),
            'res_model': 'enterprise.ops.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.request_ids.ids)],
        }

    # ------------------------------------------------------------------
    # Pipeline: read -> group -> resolve -> create
    # ------------------------------------------------------------------
    def _process(self, raw):
        """Returns (created requests, sorted error messages). Either some
        requests were created and there are no messages, or nothing was
        created and there is at least one message."""
        Request = self.env['enterprise.ops.request']
        errors = []  # (row number or 0 for file-level, text)
        created = Request
        if not raw:
            errors.append((0, _("The file is empty.")))
        elif len(raw) > self._MAX_BYTES:
            errors.append((0, _(
                "The file is larger than %(mb)s MB.",
                mb=self._MAX_BYTES // (1024 * 1024),
            )))
        else:
            try:
                text = raw.decode('utf-8-sig')  # utf-8-sig strips an Excel BOM
            except UnicodeDecodeError:
                errors.append((0, _("The file must be UTF-8 encoded text (CSV).")))
            else:
                rows = self._read_rows(text, errors)
                if not errors:
                    groups = self._group_rows(rows, errors)
                    # Resolve even when rows had problems, so ONE report
                    # lists everything that is wrong.
                    self._resolve(groups, errors)
                    if not errors:
                        created, errors = self._create_all(groups)
        messages = [text for _row, text in sorted(errors, key=lambda e: e[0])]
        return created, messages

    def _read_rows(self, text, errors):
        first_line = text.splitlines()[0] if text.strip() else ''
        if not first_line.strip():
            errors.append((0, _("The file has no header row.")))
            return []
        delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = []
        try:
            header = [h.strip().lower() for h in next(reader)]
            problems = self._check_header(header)
            if problems:
                errors.extend((0, problem) for problem in problems)
                return []
            # Header is row 1, so data starts at row 2 (as in a spreadsheet).
            for number, cells in enumerate(reader, start=2):
                if not any(cell.strip() for cell in cells):
                    continue
                if len(rows) >= self._MAX_ROWS:
                    errors.append((number, _(
                        "The file has more than %(max)s data rows; "
                        "split it into smaller files.", max=self._MAX_ROWS,
                    )))
                    break
                if len(cells) > len(header):
                    self._add_error(errors, number, _(
                        "has %(cells)s cells but the header has only %(cols)s "
                        "columns (a comma inside a value must be quoted)",
                        cells=len(cells), cols=len(header),
                    ))
                    continue
                cells = cells + [''] * (len(header) - len(cells))
                rows.append((number, {h: c.strip() for h, c in zip(header, cells)}))
        except csv.Error as exc:
            errors.append((0, _("The CSV could not be read: %(error)s", error=exc)))
            return []
        if not rows and not errors:
            errors.append((0, _("The file has no data rows.")))
        return rows

    def _check_header(self, header):
        problems = []
        unknown = [h for h in header if h not in self._COLUMNS]
        duplicated = sorted({h for h in header if h and header.count(h) > 1})
        missing = [c for c in self._REQUIRED_COLUMNS if c not in header]
        if unknown:
            problems.append(_(
                "Unknown column(s): %(cols)s. Allowed columns: %(allowed)s.",
                cols=', '.join(h or _('(empty name)') for h in unknown),
                allowed=', '.join(self._COLUMNS),
            ))
        if duplicated:
            problems.append(_(
                "Duplicated column(s): %(cols)s.", cols=', '.join(duplicated),
            ))
        if missing:
            problems.append(_(
                "Missing required column(s): %(cols)s.", cols=', '.join(missing),
            ))
        return problems

    def _group_rows(self, rows, errors):
        groups = {}
        for number, row in rows:
            key = row.get('request_key', '')
            if not key:
                self._add_error(errors, number, _("is required"), 'request_key')
                continue
            first = key not in groups
            if first:
                groups[key] = {
                    'key': key, 'first_row': number,
                    'rows': [], 'header': {}, 'lines': [],
                }
            group = groups[key]
            group['rows'].append(number)
            self._read_header_cells(group, number, row, first, errors)
            self._read_line_cells(group, number, row, errors)
        return groups

    def _read_header_cells(self, group, number, row, first, errors):
        parsed = {
            'employee_login': row.get('employee_login', ''),
            'department_code': row.get('department_code', ''),
            'reason': row.get('reason', ''),
            'priority': self._parse_priority(row.get('priority', ''), number, errors),
            'request_date': self._parse_date(row.get('request_date', ''), number, errors),
        }
        if first:
            group['header'].update(parsed)
            for column in ('department_code', 'reason'):
                if not parsed[column]:
                    self._add_error(errors, number, _(
                        "is required on the first row of a request"), column)
            return
        for column, value in parsed.items():
            if value in (None, ''):
                continue  # blank on a later row: inherits the first row
            if value != group['header'].get(column):
                self._add_error(errors, number, _(
                    "differs from row %(first)s, the first row of request '%(key)s'",
                    first=group['first_row'], key=group['key'],
                ), column)

    def _read_line_cells(self, group, number, row, errors):
        code = row.get('product_code', '')
        if not code:
            self._add_error(errors, number, _("is required"), 'product_code')
        quantity = self._parse_number(
            row.get('quantity', ''), number, 'quantity', errors, positive=True)
        price_raw = row.get('unit_price', '')
        price = 0.0
        if price_raw:
            price = self._parse_number(
                price_raw, number, 'unit_price', errors, positive=False)
        group['lines'].append({
            'row': number, 'product_code': code, 'quantity': quantity,
            'unit_price': price, 'notes': row.get('notes', ''),
        })

    def _parse_number(self, raw, number, column, errors, positive):
        if not raw:
            self._add_error(errors, number, _("is required"), column)
            return None
        if not _NUMBER.fullmatch(raw):
            self._add_error(errors, number, _(
                "must be a plain number such as 12 or 12.5 (got '%(value)s')",
                value=raw), column)
            return None
        value = float(raw)
        if value > self._MAX_NUMBER:
            self._add_error(errors, number, _("is too large"), column)
            return None
        if positive and value <= 0:
            self._add_error(errors, number, _("must be greater than zero"), column)
            return None
        if not positive and value < 0:
            self._add_error(errors, number, _("cannot be negative"), column)
            return None
        return value

    def _parse_priority(self, raw, number, errors):
        if not raw:
            return None
        value = self._PRIORITIES.get(raw.lower())
        if value is None:
            self._add_error(errors, number, _(
                "must be normal, high or urgent (or 0, 1, 2); got '%(value)s'",
                value=raw), 'priority')
        return value

    def _parse_date(self, raw, number, errors):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            self._add_error(errors, number, _(
                "must be a date written YYYY-MM-DD (got '%(value)s')", value=raw),
                'request_date')
            return None

    def _resolve(self, groups, errors):
        """Look employees, departments and products up in ONE query each."""
        env = self.env
        company = env.company
        headers = [g['header'] for g in groups.values()]

        logins = {h.get('employee_login') for h in headers} - {None, ''}
        users = {
            u.login: u for u in env['res.users'].search(
                [('login', 'in', list(logins))])
        } if logins else {}

        dept_codes = {h.get('department_code') for h in headers} - {None, ''}
        departments = {
            d.code: d for d in env['enterprise.ops.department'].search([
                ('code', 'in', list(dept_codes)),
                ('company_id', '=', company.id),
            ])
        } if dept_codes else {}

        product_codes = {
            line['product_code'] for g in groups.values() for line in g['lines']
        } - {''}
        products = defaultdict(list)
        if product_codes:
            for product in env['product.product'].search([
                ('default_code', 'in', list(product_codes)),
                ('purchase_ok', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ]):
                products[product.default_code].append(product)

        for group in groups.values():
            header = group['header']
            login = header.get('employee_login')
            if login:
                group['employee'] = users.get(login)
                if not group['employee']:
                    self._add_error(errors, group['first_row'], _(
                        "no active user with login '%(login)s'", login=login),
                        'employee_login')
            else:
                group['employee'] = env.user
            code = header.get('department_code')
            if code:
                group['department'] = departments.get(code)
                if not group['department']:
                    self._add_error(errors, group['first_row'], _(
                        "no department with code '%(code)s' in company '%(company)s'",
                        code=code, company=company.name), 'department_code')
            for line in group['lines']:
                if not line['product_code']:
                    continue
                matches = products.get(line['product_code'], [])
                if not matches:
                    self._add_error(errors, line['row'], _(
                        "no active, purchasable product with code '%(code)s'",
                        code=line['product_code']), 'product_code')
                elif len(matches) > 1:
                    self._add_error(errors, line['row'], _(
                        "code '%(code)s' matches %(count)s products; "
                        "product codes must be unique",
                        code=line['product_code'], count=len(matches)),
                        'product_code')
                else:
                    line['product'] = matches[0]

    def _request_vals(self, group):
        header = group['header']
        vals = {
            'employee_id': group['employee'].id,
            'department_id': group['department'].id,
            'reason': header['reason'],
            'priority': header.get('priority') or '0',
            'line_ids': [(0, 0, {
                'product_id': line['product'].id,
                'quantity': line['quantity'],
                'estimated_unit_price': line['unit_price'],
                'notes': line['notes'] or False,
            }) for line in group['lines']],
        }
        if header.get('request_date'):
            vals['request_date'] = header['request_date']
        return vals

    def _create_request(self, vals):
        # One call, one seam: runs with the CURRENT user's rights, so ACL,
        # record rules (T12/T13) and every constraint apply as usual.
        return self.env['enterprise.ops.request'].create(vals)

    def _create_all(self, groups):
        Request = self.env['enterprise.ops.request']
        created = Request
        errors = []
        try:
            with self.env.cr.savepoint():
                for group in groups.values():
                    try:
                        with self.env.cr.savepoint():
                            created |= self._create_request(self._request_vals(group))
                    except UserError as exc:  # also AccessError, ValidationError
                        errors.append((group['first_row'], self._request_error(group, exc)))
                if errors:
                    raise _ImportRollback()
        except _ImportRollback:
            return Request, errors
        return created, []

    def _request_error(self, group, exc):
        if isinstance(exc, AccessError):
            reason = _(
                "You are not allowed to create this request "
                "(employee '%(employee)s', department '%(department)s').",
                employee=group['employee'].name,
                department=group['department'].name,
            )
        else:
            reason = str(exc)
        return _(
            "Request '%(key)s' (rows %(rows)s): %(reason)s",
            key=group['key'],
            rows=', '.join(str(r) for r in group['rows']),
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def _add_error(self, errors, number, message, column=None):
        if column:
            text = _("Row %(row)s, column '%(column)s': %(message)s",
                     row=number, column=column, message=message)
        else:
            text = _("Row %(row)s: %(message)s", row=number, message=message)
        errors.append((number, text))

    def _format_errors(self, messages):
        shown = messages[:self._MAX_REPORTED]
        text = _(
            "%(count)s problem(s) found. Nothing was imported.",
            count=len(messages),
        ) + "\n\n" + "\n".join("• " + message for message in shown)
        if len(messages) > self._MAX_REPORTED:
            text += "\n" + _(
                "... and %(more)s more.", more=len(messages) - self._MAX_REPORTED,
            )
        return text