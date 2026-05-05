"""Recipe model – stores theoretical cost per dish."""
from ..extensions import db


class Recipe(db.Model):
    """Dish recipe linked to a Product."""

    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), unique=True, nullable=False)
    instructions = db.Column(db.Text)
    portions = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    ingredients = db.relationship(
        "RecipeIngredient", backref="recipe", cascade="all, delete-orphan", lazy="joined"
    )

    @property
    def theoretical_cost(self):
        """Calculate total theoretical cost from all ingredients."""
        total = sum(
            float(ri.quantity) * float(ri.inventory_item.unit_cost)
            for ri in self.ingredients
            if ri.inventory_item
        )
        return round(total, 4)

    def __repr__(self) -> str:
        return f"<Recipe product_id={self.product_id}>"


class RecipeIngredient(db.Model):
    """Association between a Recipe and an InventoryItem with quantity."""

    __tablename__ = "recipe_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"), nullable=False)
    inventory_item_id = db.Column(
        db.Integer, db.ForeignKey("inventory_items.id"), nullable=False
    )
    quantity = db.Column(db.Numeric(10, 4), nullable=False)
    unit = db.Column(db.String(20))  # kg, L, pza, etc.

    inventory_item = db.relationship("InventoryItem")

    def __repr__(self) -> str:
        return f"<RecipeIngredient recipe={self.recipe_id} item={self.inventory_item_id}>"
