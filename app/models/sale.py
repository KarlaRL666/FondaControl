"""Sale, SaleItem and CashRegisterClose models."""
from datetime import datetime
from ..extensions import db


class Sale(db.Model):
    """A completed sale transaction."""

    __tablename__ = "sales"

    STATUS_OPEN = "abierta"
    STATUS_PAID = "pagada"
    STATUS_CANCELLED = "cancelada"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(15), default=STATUS_OPEN, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), default=0.00)
    tax = db.Column(db.Numeric(10, 2), default=0.00)
    total = db.Column(db.Numeric(10, 2), default=0.00)
    payment_method = db.Column(db.String(20), default="efectivo")  # efectivo | tarjeta
    amount_paid = db.Column(db.Numeric(10, 2), default=0.00)
    change_given = db.Column(db.Numeric(10, 2), default=0.00)
    table_number = db.Column(db.String(10))
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship(
        "SaleItem", backref="sale", cascade="all, delete-orphan", lazy="joined"
    )
    cash_close = db.relationship("CashRegisterClose", backref="sale", uselist=False)

    def recalculate(self) -> None:
        """Recalculate subtotal and total from sale items."""
        self.subtotal = sum(float(i.subtotal) for i in self.items)
        self.tax = round(float(self.subtotal) * 0.0, 2)  # IVA opcional
        self.total = round(float(self.subtotal) + float(self.tax), 2)

    def __repr__(self) -> str:
        return f"<Sale {self.folio!r} total={self.total}>"


class SaleItem(db.Model):
    """A line item within a Sale."""

    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    notes = db.Column(db.String(120))

    def __repr__(self) -> str:
        return f"<SaleItem sale={self.sale_id} product={self.product_id} qty={self.quantity}>"


class CashRegisterClose(db.Model):
    """Daily / shift cash register close record."""

    __tablename__ = "cash_register_closes"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    opening_balance = db.Column(db.Numeric(10, 2), default=0.00)
    closing_balance = db.Column(db.Numeric(10, 2), default=0.00)
    total_sales = db.Column(db.Numeric(10, 2), default=0.00)
    total_cash = db.Column(db.Numeric(10, 2), default=0.00)
    total_card = db.Column(db.Numeric(10, 2), default=0.00)
    notes = db.Column(db.Text)
    shift_start = db.Column(db.DateTime, default=datetime.utcnow)
    shift_end = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<CashClose id={self.id} total={self.total_sales}>"
