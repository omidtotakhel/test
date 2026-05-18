{
    "name": "Sale Order Line Delivery Report",
    "version": "18.0.1.0.0",
    "summary": "Report sale order lines showing delivered quantities",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["sale_management"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_order_line_delivery_report_views.xml",
    ],
    "installable": True,
    "application": False,
}