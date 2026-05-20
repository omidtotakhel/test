{
    "name": "Sale Order Line Delivery Menu",
    "version": "18.0.1.0.0",
    "summary": "Menu and views for sale order lines to deliver products",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["sale_management", "sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_order_line_views.xml",
    ],
    "installable": True,
    "application": False,
}