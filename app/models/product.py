"""Product and Category models."""
from ..extensions import db


class Category(db.Model):
    """Menu category (e.g. Sopas, Guisados, Bebidas)."""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    products = db.relationship("Product", backref="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category {self.name!r}>"


class Product(db.Model):
    """Sellable product / dish."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    cost = db.Column(db.Numeric(10, 2), default=0.00)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    image_url = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    sale_items = db.relationship("SaleItem", backref="product", lazy="dynamic")
    recipe = db.relationship("Recipe", uselist=False, backref="product")

    @property
    def margin(self):
        """Profit margin percentage."""
        if self.price and self.cost and float(self.price) > 0:
            return round((1 - float(self.cost) / float(self.price)) * 100, 2)
        return 0.0

    def __repr__(self) -> str:
        return f"<Product {self.name!r} ${self.price}>"
