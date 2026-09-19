# Enterprise Operations & Procurement (enterprise_ops)

## Client Problem
A large industrial client currently manages purchasing requests through
email and Excel spreadsheets. This causes:
- No controlled approval trail
- No traceability from request -> purchase -> receipt -> vendor bill
- No visibility for management (spend by company/department/supplier)
- No enforced multi-company data isolation

## Solution
A single Odoo application (`enterprise_ops`) that models the full
operational purchasing lifecycle:

```
Employee -> Request -> Manager Approval -> Procurement Review ->
RFQ/PO -> Vendor Delivery -> Receipt -> Vendor Bill ->
Payment Status -> Reports / OWL Dashboard
```

## Current Status: T01 - Bootstrap
This ticket only establishes the module skeleton:
- `__manifest__.py` - module metadata and dependency declaration
- `views/menu.xml` - root App menu + placeholder submenus
- No business models yet (added starting T02/T03)
- Odoo core is **not** modified anywhere in this project

## Setup (Local Dev)
1. Copy/symlink this folder into your Odoo `addons_path`.
2. Restart the Odoo server (or update the apps list from the UI:
   Settings > General Settings > Activate developer mode > Apps > Update Apps List).
3. In Apps, remove the default "Apps" filter, search "Enterprise Operations".
4. Click Install.

## Architecture (will grow ticket by ticket)
See `docs/architecture.md` (added in later tickets) for the full
Employee -> Request -> Approval -> Purchase -> Inventory -> Accounting ->
Reporting/OWL diagram.

## Security Model
See `security/security.xml` and `security/ir.model.access.csv`
(added starting T11) for the full role matrix.

## Tests
See `tests/` (added starting T05) and each ticket's PR for the exact
test command used, e.g.:
```
odoo-bin -c odoo.conf -i enterprise_ops --test-enable --stop-after-init -d test_db
```
