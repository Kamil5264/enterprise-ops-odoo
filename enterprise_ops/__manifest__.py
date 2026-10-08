{
    "name": "Enterprise Operations",
    "version": "19.0.1.0.0",
    "category": "Operations/Procurement",
    "summary": "Employee Request → Approval → Procurement → Inventory → Accounting",

    "description": """
Enterprise Operations & Procurement Management
==============================================

Replaces email/Excel based purchasing requests with a single auditable
Odoo application covering:

* Employee purchase/service requests
* Manager approval workflow
* Procurement (RFQ/PO) integration
* Inventory receipt traceability
* Accounting (vendor bill) linkage
* Multi-company security
* Management KPI reporting 

 """,

    # Ownership
    "author": "Mohammad Kamil",
    "license": "LGPL-3",

    # Dependencies
    "depends": [
        "base",
    ],

    # Data files loaded on install/update
    "data": [
    'security/security.xml',
    'security/ir.model.access.csv',
    'data/sequence.xml',
    'views/request_search.xml',
    'views/request_views.xml',
    'views/menu.xml',
    'views/master_data_views.xml',
],

    # Behaviour flags
    "installable": True,
    "application": True,
    "auto_install": False,
}