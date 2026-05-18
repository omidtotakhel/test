from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    qty_to_deliver = fields.Float(
        string="To Deliver",
        compute="_compute_qty_to_deliver",
        store=True,
        digits="Product Unit of Measure",
        help="Remaining quantity to deliver for this sales order line.",
    )

    @api.depends("product_uom_qty", "qty_delivered", "display_type")
    def _compute_qty_to_deliver(self):
        for line in self:
            if line.display_type:
                line.qty_to_deliver = 0.0
            else:
                line.qty_to_deliver = max(line.product_uom_qty - line.qty_delivered, 0.0)