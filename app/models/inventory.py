"""Inventory models – raw ingredients, movements and waste tracking."""
from datetime import datetime
from ..extensions import db


class InventoryItem(db.Model):
    """A raw ingredient or supply item."""

    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(255))
    unit = db.Column(db.String(20), nullable=False, default="pza")  # kg, L, pza, etc.
    unit_cost = db.Column(db.Numeric(10, 4), nullable=False, default=0.0)
    stock = db.Column(db.Numeric(10, 4), nullable=False, default=0.0)
    min_stock = db.Column(db.Numeric(10, 4), default=10.0)
    expiry_date = db.Column(db.Date, nullable=True)
    supplier = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    movements = db.relationship(
        "InventoryMovement", backref="item", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def is_low_stock(self) -> bool:
        return float(self.stock) <= float(self.min_stock)

    @property
    def is_expiring_soon(self) -> bool:
        if not self.expiry_date:
            return False
        delta = (self.expiry_date - datetime.utcnow().date()).days
        return 0 <= delta <= 7

    def __repr__(self) -> str:
        return f"<InventoryItem {self.name!r} stock={self.stock}{self.unit}>"


class InventoryMovement(db.Model):
    """Records every stock change (entry, exit, waste)."""

    __tablename__ = "inventory_movements"

    MOVEMENT_TYPES = ("entrada", "salida", "merma")

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    movement_type = db.Column(db.String(10), nullable=False)  # entrada | salida | merma
    quantity = db.Column(db.Numeric(10, 4), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 4), default=0.0)
    notes = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return (
            f"<InventoryMovement {self.movement_type} "
            f"item={self.item_id} qty={self.quantity}>"
        )
