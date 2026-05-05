"""Inventory / Control Productivo blueprint routes."""
import logging
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ...extensions import db
from ...models.inventory import InventoryItem, InventoryMovement
from ...models.product import Product, Category
from ...models.recipe import Recipe, RecipeIngredient
from . import inventory_bp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inventory Items
# ---------------------------------------------------------------------------

@inventory_bp.route("/")
@login_required
def index():
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    low_stock = [i for i in items if i.is_low_stock]
    expiring = [i for i in items if i.is_expiring_soon]
    return render_template(
        "inventory/index.html",
        items=items,
        low_stock=low_stock,
        expiring=expiring,
    )


@inventory_bp.route("/insumos/nuevo", methods=["GET", "POST"])
@login_required
def create_item():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "pza").strip()
        unit_cost = request.form.get("unit_cost", "0")
        stock = request.form.get("stock", "0")
        min_stock = request.form.get("min_stock", "10")
        supplier = request.form.get("supplier", "").strip()
        expiry_date = request.form.get("expiry_date") or None

        if not name:
            flash("El nombre del insumo es requerido.", "danger")
            return render_template("inventory/item_form.html", item=None)

        item = InventoryItem(
            name=name,
            unit=unit,
            unit_cost=Decimal(unit_cost),
            stock=Decimal(stock),
            min_stock=Decimal(min_stock),
            supplier=supplier,
            expiry_date=expiry_date,
        )
        db.session.add(item)
        db.session.commit()

        if float(stock) > 0:
            movement = InventoryMovement(
                item_id=item.id,
                movement_type="entrada",
                quantity=Decimal(stock),
                unit_cost=Decimal(unit_cost),
                notes="Stock inicial",
                user_id=current_user.id,
            )
            db.session.add(movement)
            db.session.commit()

        flash(f"Insumo {name} creado correctamente.", "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory/item_form.html", item=None)


@inventory_bp.route("/insumos/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    if request.method == "POST":
        item.name = request.form.get("name", item.name).strip()
        item.unit = request.form.get("unit", item.unit).strip()
        item.unit_cost = Decimal(request.form.get("unit_cost", str(item.unit_cost)))
        item.min_stock = Decimal(request.form.get("min_stock", str(item.min_stock)))
        item.supplier = request.form.get("supplier", item.supplier or "").strip()
        item.expiry_date = request.form.get("expiry_date") or None
        db.session.commit()
        flash("Insumo actualizado correctamente.", "success")
        return redirect(url_for("inventory.index"))
    return render_template("inventory/item_form.html", item=item)


@inventory_bp.route("/movimientos", methods=["GET", "POST"])
@login_required
def movements():
    if request.method == "POST":
        item_id = request.form.get("item_id", type=int)
        movement_type = request.form.get("movement_type", "entrada")
        quantity = Decimal(request.form.get("quantity", "0"))
        unit_cost = Decimal(request.form.get("unit_cost", "0"))
        notes = request.form.get("notes", "").strip()

        item = InventoryItem.query.get_or_404(item_id)

        if movement_type in ("salida", "merma") and float(item.stock) < float(quantity):
            flash("Stock insuficiente para este movimiento.", "danger")
            return redirect(url_for("inventory.movements"))

        # Adjust stock
        if movement_type == "entrada":
            item.stock = Decimal(str(item.stock)) + quantity
            item.unit_cost = unit_cost if float(unit_cost) > 0 else item.unit_cost
        else:
            item.stock = Decimal(str(item.stock)) - quantity

        movement = InventoryMovement(
            item_id=item_id,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            notes=notes,
            user_id=current_user.id,
        )
        db.session.add(movement)
        db.session.commit()
        flash("Movimiento registrado correctamente.", "success")
        return redirect(url_for("inventory.movements"))

    items = InventoryItem.query.order_by(InventoryItem.name).all()
    recent = (
        InventoryMovement.query.order_by(InventoryMovement.created_at.desc()).limit(50).all()
    )
    return render_template("inventory/movements.html", items=items, recent=recent)


# ---------------------------------------------------------------------------
# Products / Platillos
# ---------------------------------------------------------------------------

@inventory_bp.route("/platillos")
@login_required
def products():
    all_products = Product.query.order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template("inventory/products.html", products=all_products, categories=categories)


@inventory_bp.route("/platillos/nuevo", methods=["GET", "POST"])
@login_required
def create_product():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0")
        cost = request.form.get("cost", "0")
        category_id = request.form.get("category_id", type=int)
        description = request.form.get("description", "").strip()

        if not name or not price:
            flash("Nombre y precio son requeridos.", "danger")
            return render_template("inventory/product_form.html", product=None, categories=categories)

        product = Product(
            name=name,
            price=Decimal(price),
            cost=Decimal(cost),
            category_id=category_id,
            description=description,
        )
        db.session.add(product)
        db.session.commit()
        flash(f"Platillo {name} creado correctamente.", "success")
        return redirect(url_for("inventory.products"))

    return render_template("inventory/product_form.html", product=None, categories=categories)


@inventory_bp.route("/platillos/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        product.name = request.form.get("name", product.name).strip()
        product.price = Decimal(request.form.get("price", str(product.price)))
        product.cost = Decimal(request.form.get("cost", str(product.cost)))
        product.category_id = request.form.get("category_id", type=int)
        product.description = request.form.get("description", product.description or "").strip()
        product.is_available = bool(request.form.get("is_available"))
        db.session.commit()
        flash("Platillo actualizado.", "success")
        return redirect(url_for("inventory.products"))
    return render_template("inventory/product_form.html", product=product, categories=categories)


# ---------------------------------------------------------------------------
# Recipes / Recetas
# ---------------------------------------------------------------------------

@inventory_bp.route("/recetas")
@login_required
def recipes():
    all_recipes = Recipe.query.join(Product).order_by(Product.name).all()
    return render_template("inventory/recipes.html", recipes=all_recipes)


@inventory_bp.route("/recetas/<int:product_id>", methods=["GET", "POST"])
@login_required
def recipe_detail(product_id):
    product = Product.query.get_or_404(product_id)
    recipe = product.recipe
    items = InventoryItem.query.order_by(InventoryItem.name).all()

    if request.method == "POST":
        if not recipe:
            recipe = Recipe(product_id=product.id)
            db.session.add(recipe)

        recipe.instructions = request.form.get("instructions", "").strip()
        recipe.portions = int(request.form.get("portions", 1))

        # Clear existing ingredients and rebuild
        for ri in list(recipe.ingredients):
            db.session.delete(ri)

        item_ids = request.form.getlist("ingredient_item_id")
        quantities = request.form.getlist("ingredient_quantity")
        units = request.form.getlist("ingredient_unit")

        for item_id, qty, unit in zip(item_ids, quantities, units):
            if item_id and qty:
                ri = RecipeIngredient(
                    recipe=recipe,
                    inventory_item_id=int(item_id),
                    quantity=Decimal(qty),
                    unit=unit,
                )
                db.session.add(ri)

        # Update product cost from theoretical recipe cost
        db.session.flush()
        product.cost = Decimal(str(recipe.theoretical_cost))
        db.session.commit()
        flash("Receta guardada correctamente.", "success")
        return redirect(url_for("inventory.recipes"))

    return render_template(
        "inventory/recipe_form.html", product=product, recipe=recipe, items=items
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@inventory_bp.route("/categorias")
@login_required
def categories():
    cats = Category.query.order_by(Category.name).all()
    return render_template("inventory/categories.html", categories=cats)


@inventory_bp.route("/categorias/nueva", methods=["POST"])
@login_required
def create_category():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    if not name:
        flash("El nombre de la categoría es requerido.", "danger")
    else:
        cat = Category(name=name, description=description)
        db.session.add(cat)
        db.session.commit()
        flash(f"Categoría {name} creada.", "success")
    return redirect(url_for("inventory.categories"))
