{
    "name": "Purchase Order Auditor",
    "version": "18.0.1.0.0",
    "summary": "Audit purchase orders against stock valuation, journal entries, and vendor bills",
    "category": "Purchases",
    "license": "LGPL-3",
    "depends": [
        "purchase_stock",
        "stock_account",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_order_views.xml",
    ],
    "installable": True,
    "application": False,
}