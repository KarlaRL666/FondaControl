"""POS blueprint routes – sales, orders, ticket printing and cash close."""
import logging
import uuid
from datetime import datetime, date
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from ...extensions import db
from ...models.product import Product, Category
from ...models.sale import Sale, SaleItem, CashRegisterClose
from . import pos_bp

logger = logging.getLogger(__name__)


def _generate_folio() -> str:
    """Generate a unique sale folio."""
    today = date.today().strftime("%Y%m%d")
    short_id = str(uuid.uuid4()).split("-")[0].upper()
    return f"VTA-{today}-{short_id}"


# ---------------------------------------------------------------------------
# POS terminal
# ---------------------------------------------------------------------------

@pos_bp.route("/")
@login_required
def index():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    products = Product.query.filter_by(is_available=True).order_by(Product.name).all()
    open_sales = (
        Sale.query.filter_by(status=Sale.STATUS_OPEN)
        .order_by(Sale.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "pos/index.html",
        categories=categories,
        products=products,
        open_sales=open_sales,
    )


# ---------------------------------------------------------------------------
# Sale CRUD (JSON API consumed by JS)
# ---------------------------------------------------------------------------

@pos_bp.route("/ventas", methods=["POST"])
@login_required
def create_sale():
    """Create a new open sale / order."""
    data = request.get_json(silent=True) or {}
    table_number = str(data.get("table_number", "")).strip() or None
    notes = str(data.get("notes", "")).strip() or None

    sale = Sale(
        folio=_generate_folio(),
        user_id=current_user.id,
        status=Sale.STATUS_OPEN,
        table_number=table_number,
        notes=notes,
    )
    db.session.add(sale)
    db.session.commit()
    logger.info("Sale %s created by %s", sale.folio, current_user.username)
    return jsonify({"id": sale.id, "folio": sale.folio}), 201


@pos_bp.route("/ventas/<int:sale_id>")
@login_required
def get_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    items = [
        {
            "id": i.id,
            "product_id": i.product_id,
            "name": i.product.name,
            "quantity": i.quantity,
            "unit_price": float(i.unit_price),
            "subtotal": float(i.subtotal),
            "notes": i.notes,
        }
        for i in sale.items
    ]
    return jsonify(
        {
            "id": sale.id,
            "folio": sale.folio,
            "status": sale.status,
            "subtotal": float(sale.subtotal),
            "total": float(sale.total),
            "items": items,
        }
    )


@pos_bp.route("/ventas/<int:sale_id>/items", methods=["POST"])
@login_required
def add_item(sale_id):
    """Add or update an item in a sale."""
    sale = Sale.query.get_or_404(sale_id)
    if sale.status != Sale.STATUS_OPEN:
        return jsonify({"error": "La venta no está abierta"}), 400

    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))
    notes = str(data.get("notes", "")).strip() or None

    if not product_id or quantity < 1:
        return jsonify({"error": "Datos inválidos"}), 422

    product = Product.query.get_or_404(product_id)
    existing = next((i for i in sale.items if i.product_id == product_id), None)

    if existing:
        existing.quantity += quantity
        existing.subtotal = Decimal(str(existing.quantity)) * existing.unit_price
    else:
        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
            subtotal=Decimal(str(quantity)) * product.price,
            notes=notes,
        )
        db.session.add(item)
        db.session.flush()

    db.session.expire(sale)
    sale.recalculate()
    db.session.commit()
    return jsonify({"total": float(sale.total), "items_count": len(sale.items)}), 200


@pos_bp.route("/ventas/<int:sale_id>/items/<int:item_id>", methods=["DELETE"])
@login_required
def remove_item(sale_id, item_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.status != Sale.STATUS_OPEN:
        return jsonify({"error": "La venta no está abierta"}), 400
    item = SaleItem.query.filter_by(id=item_id, sale_id=sale_id).first_or_404()
    db.session.delete(item)
    sale.recalculate()
    db.session.commit()
    return jsonify({"total": float(sale.total)}), 200


@pos_bp.route("/ventas/<int:sale_id>/pagar", methods=["POST"])
@login_required
def pay_sale(sale_id):
    """Process payment for a sale."""
    sale = Sale.query.get_or_404(sale_id)
    if sale.status != Sale.STATUS_OPEN:
        return jsonify({"error": "La venta no está abierta"}), 400

    data = request.get_json(silent=True) or {}
    payment_method = data.get("payment_method", "efectivo")
    amount_paid = Decimal(str(data.get("amount_paid", 0)))

    if amount_paid < sale.total:
        return jsonify({"error": "Pago insuficiente"}), 422

    sale.payment_method = payment_method
    sale.amount_paid = amount_paid
    sale.change_given = amount_paid - sale.total
    sale.status = Sale.STATUS_PAID
    db.session.commit()
    logger.info("Sale %s paid (%.2f)", sale.folio, sale.total)
    return jsonify(
        {
            "folio": sale.folio,
            "total": float(sale.total),
            "change": float(sale.change_given),
        }
    )


@pos_bp.route("/ventas/<int:sale_id>/cancelar", methods=["POST"])
@login_required
def cancel_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.status == Sale.STATUS_PAID:
        return jsonify({"error": "No se puede cancelar una venta pagada"}), 400
    sale.status = Sale.STATUS_CANCELLED
    db.session.commit()
    return jsonify({"message": "Venta cancelada"})


# ---------------------------------------------------------------------------
# Ticket / comanda
# ---------------------------------------------------------------------------

@pos_bp.route("/ventas/<int:sale_id>/ticket")
@login_required
def ticket(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template("pos/ticket.html", sale=sale)


# ---------------------------------------------------------------------------
# Cash register close
# ---------------------------------------------------------------------------

@pos_bp.route("/cierre-caja", methods=["GET", "POST"])
@login_required
def cash_close():
    if request.method == "POST":
        opening_balance = Decimal(str(request.form.get("opening_balance", 0)))
        notes = request.form.get("notes", "").strip()

        # Aggregate today's sales
        today = date.today()
        paid_sales = Sale.query.filter(
            Sale.status == Sale.STATUS_PAID,
            db.func.date(Sale.created_at) == today,
        ).all()

        total_sales = sum(float(s.total) for s in paid_sales)
        total_cash = sum(float(s.total) for s in paid_sales if s.payment_method == "efectivo")
        total_card = sum(float(s.total) for s in paid_sales if s.payment_method == "tarjeta")

        close = CashRegisterClose(
            user_id=current_user.id,
            opening_balance=opening_balance,
            closing_balance=Decimal(str(total_cash)) + opening_balance,
            total_sales=Decimal(str(total_sales)),
            total_cash=Decimal(str(total_cash)),
            total_card=Decimal(str(total_card)),
            notes=notes,
            shift_end=datetime.utcnow(),
        )
        db.session.add(close)
        db.session.commit()
        flash("Cierre de caja registrado correctamente.", "success")
        return render_template("pos/cash_close_report.html", close=close, sales=paid_sales)

    return render_template("pos/cash_close.html")


# ---------------------------------------------------------------------------
# Sales history
# ---------------------------------------------------------------------------

@pos_bp.route("/historial")
@login_required
def history():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Sale.query.order_by(Sale.created_at.desc()).paginate(page=page, per_page=20)
    )
    return render_template("pos/history.html", pagination=pagination)
