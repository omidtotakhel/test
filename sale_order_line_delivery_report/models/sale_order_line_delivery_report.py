from odoo import api, fields, models, tools


class SaleOrderLineDeliveryReport(models.Model):
    _name = "sale.order.line.delivery.report"
    _description = "Sale Order Line Delivery Report"
    _auto = False
    _order = "order_date desc, id desc"

    order_id = fields.Many2one("sale.order", string="Sales Order", readonly=True)
    order_name = fields.Char(string="Order Reference", readonly=True)
    order_date = fields.Datetime(string="Order Date", readonly=True)
    customer_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    salesperson_id = fields.Many2one("res.users", string="Salesperson", readonly=True)

    order_line_id = fields.Many2one("sale.order.line", string="Order Line", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_template_id = fields.Many2one("product.template", string="Product Template", readonly=True)
    product_uom_qty = fields.Float(string="Ordered Qty", readonly=True)
    qty_delivered = fields.Float(string="Delivered Qty", readonly=True)
    product_uom = fields.Many2one("uom.uom", string="Unit of Measure", readonly=True)
    price_unit = fields.Float(string="Unit Price", readonly=True)
    price_subtotal = fields.Float(string="Subtotal", readonly=True, digits="Product Price")
    state = fields.Selection(
        selection=[
            ("draft", "Quotation"),
            ("sent", "Quotation Sent"),
            ("sale", "Sales Order"),
            ("done", "Locked"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        readonly=True,
    )

    @api.model
    def _select(self):
        return """
            SELECT
                sol.id AS id,
                so.id AS order_id,
                so.name AS order_name,
                so.date_order AS order_date,
                so.partner_id AS customer_id,
                so.company_id AS company_id,
                so.user_id AS salesperson_id,
                sol.id AS order_line_id,
                sol.product_id AS product_id,
                pt.id AS product_template_id,
                sol.product_uom_qty AS product_uom_qty,
                sol.qty_delivered AS qty_delivered,
                sol.product_uom AS product_uom,
                sol.price_unit AS price_unit,
                sol.price_subtotal AS price_subtotal,
                so.state AS state
        """

    @api.model
    def _from(self):
        return """
            FROM sale_order_line sol
            JOIN sale_order so ON so.id = sol.order_id
            LEFT JOIN product_product pp ON pp.id = sol.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
        """

    @api.model
    def _where(self):
        return """
            WHERE sol.display_type IS NULL
              AND sol.qty_delivered > 0
        """

    @property
    def _table_query(self):
        return "%s %s %s" % (self._select(), self._from(), self._where())