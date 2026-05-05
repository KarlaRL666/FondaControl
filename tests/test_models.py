"""Tests for models – Product, InventoryItem, Sale, Recipe."""
import pytest
from decimal import Decimal
from app.models.product import Product, Category
from app.models.inventory import InventoryItem, InventoryMovement
from app.models.sale import Sale, SaleItem
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User


class TestProductModel:
    def test_product_margin(self, db):
        p = Product(name="Test Dish", price=Decimal("50.00"), cost=Decimal("20.00"))
        assert p.margin == 60.0

    def test_product_margin_zero_price(self, db):
        p = Product(name="Free", price=Decimal("0.00"), cost=Decimal("0.00"))
        assert p.margin == 0.0

    def test_product_repr(self, db):
        p = Product(name="Sopa", price=Decimal("30.00"))
        assert "Sopa" in repr(p)


class TestInventoryModel:
    def test_is_low_stock(self, db):
        item = InventoryItem(
            name="Tomate", unit="kg", unit_cost=Decimal("20.00"),
            stock=Decimal("5.0"), min_stock=Decimal("10.0")
        )
        db.session.add(item)
        db.session.commit()
        assert item.is_low_stock is True

    def test_not_low_stock(self, db):
        item = InventoryItem(
            name="Sal", unit="kg", unit_cost=Decimal("5.00"),
            stock=Decimal("50.0"), min_stock=Decimal("10.0")
        )
        db.session.add(item)
        db.session.commit()
        assert item.is_low_stock is False

    def test_inventory_repr(self, db):
        item = InventoryItem(name="Aceite", unit="L", unit_cost=Decimal("30.00"), stock=Decimal("5.0"))
        assert "Aceite" in repr(item)


class TestSaleModel:
    def test_recalculate(self, db, admin_user):
        sale = Sale(folio="VTA-TEST-001", user_id=admin_user.id)
        db.session.add(sale)
        db.session.flush()

        cat = Category(name="TestCat")
        db.session.add(cat)
        db.session.flush()

        product = Product(name="Guisado", price=Decimal("45.00"), category_id=cat.id)
        db.session.add(product)
        db.session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("45.00"),
            subtotal=Decimal("90.00"),
        )
        db.session.add(item)
        db.session.flush()

        # Expire the cache so sale.items is loaded fresh from DB
        db.session.expire(sale)
        sale.recalculate()

        assert float(sale.subtotal) == 90.0
        assert float(sale.total) == 90.0

    def test_sale_repr(self, db):
        s = Sale(folio="VTA-X-001", user_id=1)
        assert "VTA-X-001" in repr(s)


class TestRecipeModel:
    def test_theoretical_cost(self, db):
        item = InventoryItem(
            name="Pollo", unit="kg", unit_cost=Decimal("80.00"), stock=Decimal("10.0")
        )
        db.session.add(item)
        db.session.flush()

        cat = Category(name="RecipeCat")
        db.session.add(cat)
        db.session.flush()

        product = Product(name="Pollo Guisado", price=Decimal("65.00"), category_id=cat.id)
        db.session.add(product)
        db.session.flush()

        recipe = Recipe(product_id=product.id, portions=1)
        db.session.add(recipe)
        db.session.flush()

        ri = RecipeIngredient(
            recipe_id=recipe.id,
            inventory_item_id=item.id,
            quantity=Decimal("0.25"),
            unit="kg",
        )
        db.session.add(ri)
        db.session.commit()

        # Reload recipe from DB to ensure fresh state
        db.session.expire(recipe)

        # 0.25 kg × $80/kg = $20
        assert recipe.theoretical_cost == pytest.approx(20.0, rel=1e-3)
