from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare, float_is_zero


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    audit_state = fields.Selection(
        [
            ("not_audited", "Not Audited"),
            ("ok", "Matched"),
            ("issue", "Issue Found"),
        ],
        string="Audit Status",
        default="not_audited",
        copy=False,
        tracking=True,
    )
    audit_last_date = fields.Datetime(
        string="Last Audit Date",
        copy=False,
        readonly=True,
    )
    audit_issue_count = fields.Integer(
        string="Audit Issue Count",
        compute="_compute_audit_summary",
        store=False,
    )
    audit_summary = fields.Text(
        string="Audit Summary",
        compute="_compute_audit_summary",
        store=False,
    )
    audit_stock_value = fields.Monetary(
        string="Received Stock Value",
        compute="_compute_audit_amounts",
        currency_field="currency_id",
        store=False,
    )
    audit_stock_account_value = fields.Monetary(
        string="Stock Valuation Journal Value",
        compute="_compute_audit_amounts",
        currency_field="currency_id",
        store=False,
    )
    audit_bill_value = fields.Monetary(
        string="Vendor Bill Value",
        compute="_compute_audit_amounts",
        currency_field="currency_id",
        store=False,
    )
    audit_purchase_value = fields.Monetary(
        string="Purchase Order Value",
        compute="_compute_audit_amounts",
        currency_field="currency_id",
        store=False,
    )
    audit_line_ids = fields.One2many(
        "purchase.order.audit.line",
        "purchase_order_id",
        string="Audit Lines",
        readonly=True,
        copy=False,
    )

    def action_run_audit(self):
        for order in self:
            order._run_purchase_audit()
        return True

    def action_open_audit_lines(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("purchase_order_auditor.action_purchase_order_audit_line")
        action["domain"] = [("purchase_order_id", "=", self.id)]
        action["context"] = {
            "default_purchase_order_id": self.id,
            "search_default_group_by_check_type": 1,
        }
        return action

    @api.depends(
        "amount_total",
        "currency_id",
        "order_line.qty_received",
        "order_line.price_unit",
        "order_line.product_qty",
        "invoice_ids",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.invoice_line_ids.price_subtotal",
        "picking_ids.state",
    )
    def _compute_audit_amounts(self):
        for order in self:
            purchase_value = order.amount_total
            stock_value = order._get_received_stock_value()
            stock_account_value = order._get_stock_valuation_accounting_value()
            bill_value = order._get_bill_value()

            order.audit_purchase_value = purchase_value
            order.audit_stock_value = stock_value
            order.audit_stock_account_value = stock_account_value
            order.audit_bill_value = bill_value

    @api.depends("audit_line_ids.message", "audit_line_ids.severity")
    def _compute_audit_summary(self):
        for order in self:
            issues = order.audit_line_ids.filtered(lambda l: l.severity in ("warning", "error"))
            order.audit_issue_count = len(issues)
            if not issues:
                order.audit_summary = _("No audit issues found.")
            else:
                order.audit_summary = "\n".join(
                    ["[%s] %s" % (line.severity.upper(), line.message) for line in issues]
                )

    def _run_purchase_audit(self):
        self.ensure_one()
        self.audit_line_ids.unlink()
        AuditLine = self.env["purchase.order.audit.line"]

        audit_lines_vals = []
        precision = self.currency_id.rounding

        purchase_total = self.amount_total
        bill_total = self._get_bill_value()
        stock_total = self._get_received_stock_value()
        stock_account_total = self._get_stock_valuation_accounting_value()

        audit_lines_vals.extend(self._audit_document_presence())
        audit_lines_vals.extend(self._audit_qty_consistency())
        audit_lines_vals.extend(
            self._audit_amount_match(
                "po_vs_bill",
                _("Purchase Order vs Vendor Bills"),
                purchase_total,
                bill_total,
                precision,
                _("Vendor bill total does not match purchase order total."),
            )
        )
        audit_lines_vals.extend(
            self._audit_amount_match(
                "stock_vs_valuation",
                _("Received Stock vs Stock Valuation Journal Entries"),
                stock_total,
                stock_account_total,
                precision,
                _("Stock valuation journal entries do not match received stock value."),
            )
        )

        if self.order_line.filtered(lambda l: l.qty_received > 0):
            audit_lines_vals.extend(
                self._audit_amount_match(
                    "received_vs_bill",
                    _("Received Stock vs Vendor Bills"),
                    stock_total,
                    bill_total,
                    precision,
                    _("Vendor bills do not match received stock value."),
                )
            )

        if audit_lines_vals:
            AuditLine.create(audit_lines_vals)

        self.audit_last_date = fields.Datetime.now()
        self.audit_state = "issue" if self.audit_line_ids.filtered(lambda l: l.severity in ("warning", "error")) else "ok"

    def _audit_document_presence(self):
        self.ensure_one()
        vals = []

        done_pickings = self.picking_ids.filtered(lambda p: p.state == "done")
        bills = self.invoice_ids.filtered(lambda m: m.move_type in ("in_invoice", "in_refund") and m.state != "cancel")

        if not done_pickings:
            vals.append(self._prepare_audit_line(
                "documents",
                "warning",
                _("No completed receipt found for this purchase order."),
                _("Check if products were received or receipts are still pending."),
            ))

        if not bills:
            vals.append(self._prepare_audit_line(
                "documents",
                "warning",
                _("No vendor bill found for this purchase order."),
                _("Create or link the vendor bill for this purchase order."),
            ))

        valuation_layers = self._get_related_valuation_layers()
        if self.order_line.filtered(lambda l: l.product_id.type == "product") and not valuation_layers:
            vals.append(self._prepare_audit_line(
                "documents",
                "warning",
                _("No stock valuation layers found for storable products."),
                _("Check whether automated valuation is enabled and stock moves were posted."),
            ))

        account_moves = self._get_related_stock_account_moves()
        if self.order_line.filtered(lambda l: l.product_id.type == "product") and not account_moves:
            vals.append(self._prepare_audit_line(
                "documents",
                "warning",
                _("No stock valuation journal entries found."),
                _("Check stock valuation configuration and posting of inventory accounting entries."),
            ))
        return vals

    def _audit_qty_consistency(self):
        self.ensure_one()
        vals = []

        for line in self.order_line.filtered(lambda l: not l.display_type):
            product = line.product_id
            if line.product_qty and line.qty_received > line.product_qty:
                vals.append(self._prepare_audit_line(
                    "quantity",
                    "warning",
                    _("%s received quantity is greater than ordered quantity.") % product.display_name,
                    _("Ordered: %(ordered)s, Received: %(received)s", ordered=line.product_qty, received=line.qty_received),
                    purchase_order_line_id=line.id,
                ))
            billed_qty = sum(
                line_vals.quantity
                for move in self.invoice_ids.filtered(lambda m: m.state != "cancel" and m.move_type in ("in_invoice", "in_refund"))
                for line_vals in move.invoice_line_ids.filtered(lambda invl: invl.purchase_line_id == line)
            )
            if line.qty_received and float_compare(billed_qty, line.qty_received, precision_rounding=line.product_uom.rounding) != 0:
                vals.append(self._prepare_audit_line(
                    "quantity",
                    "warning",
                    _("%s billed quantity does not match received quantity.") % product.display_name,
                    _("Received: %(received)s, Billed: %(billed)s", received=line.qty_received, billed=billed_qty),
                    purchase_order_line_id=line.id,
                ))
        return vals

    def _audit_amount_match(self, check_type, check_name, source_amount, target_amount, precision, message):
        self.ensure_one()
        vals = []
        if float_compare(source_amount, target_amount, precision_rounding=precision) != 0:
            diff = source_amount - target_amount
            vals.append(self._prepare_audit_line(
                check_type,
                "error",
                message,
                _("%(name)s difference: %(diff).2f", name=check_name, diff=diff),
            ))
        else:
            vals.append(self._prepare_audit_line(
                check_type,
                "info",
                _("%s matched successfully.") % check_name,
                _("%(name)s source and target amounts are aligned.", name=check_name),
            ))
        return vals

    def _prepare_audit_line(self, check_type, severity, message, details=False, purchase_order_line_id=False):
        self.ensure_one()
        return {
            "purchase_order_id": self.id,
            "purchase_order_line_id": purchase_order_line_id,
            "check_type": check_type,
            "severity": severity,
            "message": message,
            "details": details or False,
        }

    def _get_bill_value(self):
        self.ensure_one()
        total = 0.0
        bills = self.invoice_ids.filtered(lambda m: m.state != "cancel" and m.move_type == "in_invoice")
        refunds = self.invoice_ids.filtered(lambda m: m.state != "cancel" and m.move_type == "in_refund")

        for bill in bills:
            total += bill.currency_id._convert(
                bill.amount_total,
                self.currency_id,
                self.company_id,
                bill.invoice_date or bill.date or fields.Date.context_today(self),
            )
        for refund in refunds:
            total -= refund.currency_id._convert(
                refund.amount_total,
                self.currency_id,
                self.company_id,
                refund.invoice_date or refund.date or fields.Date.context_today(self),
            )
        return total

    def _get_received_stock_value(self):
        self.ensure_one()
        total = 0.0
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id.type == "product"):
            qty = min(line.qty_received, line.product_qty) if line.product_qty else line.qty_received
            total += qty * line.price_unit
        return total

    def _get_related_valuation_layers(self):
        self.ensure_one()
        move_ids = self.picking_ids.move_ids_without_package.ids + self.picking_ids.move_ids.ids
        move_ids = list(set(move_ids))
        if not move_ids:
            return self.env["stock.valuation.layer"]
        return self.env["stock.valuation.layer"].search([("stock_move_id", "in", move_ids)])

    def _get_stock_valuation_accounting_value(self):
        self.ensure_one()
        total = 0.0
        valuation_layers = self._get_related_valuation_layers()
        for layer in valuation_layers:
            total += abs(layer.value)
        return total

    def _get_related_stock_account_moves(self):
        self.ensure_one()
        valuation_layers = self._get_related_valuation_layers()
        account_moves = valuation_layers.mapped("account_move_id").filtered(lambda m: m.state != "cancel")
        return account_moves


class PurchaseOrderAuditLine(models.Model):
    _name = "purchase.order.audit.line"
    _description = "Purchase Order Audit Line"
    _order = "purchase_order_id desc, severity desc, id desc"

    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    purchase_order_line_id = fields.Many2one(
        "purchase.order.line",
        string="Purchase Order Line",
        ondelete="set null",
    )
    check_type = fields.Selection(
        [
            ("documents", "Documents"),
            ("quantity", "Quantity"),
            ("po_vs_bill", "PO vs Bill"),
            ("stock_vs_valuation", "Stock vs Valuation"),
            ("received_vs_bill", "Received vs Bill"),
        ],
        string="Check Type",
        required=True,
    )
    severity = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Severity",
        required=True,
    )
    message = fields.Char(
        string="Message",
        required=True,
    )
    details = fields.Text(string="Details")
    company_id = fields.Many2one(
        related="purchase_order_id.company_id",
        store=True,
        readonly=True,
    )