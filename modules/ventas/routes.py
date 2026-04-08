from . import ventas
from flask import render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Producto, Cliente, Venta, DetalleVenta, db
from utils.security import role_required
from .services import(
    crear_venta, obtener_ventas, obtener_detalle_venta, completar_venta_pago
)
import traceback

# 📋 LISTADO
@ventas.route('/')
@login_required
@role_required(1, 3)
def index():
    ventas, error = obtener_ventas()
    if error:
        current_app.logger.error(f"Error al cargar ventas: {error}")
        flash("Error al cargar las ventas", "danger")
    
    return render_template('ventas/index.html', ventas=ventas)


@ventas.route('/detalles/<int:id_venta>')
@login_required
@role_required(1, 3)
def detalles(id_venta):
    venta, error = obtener_detalle_venta(id_venta)
    if error:
        current_app.logger.error(f"Error al cargar detalle de venta {id_venta}: {error}")
        flash(error, "danger")
        return redirect(url_for('ventas.index'))

    return render_template('ventas/detalles.html', venta=venta)


# 🧾 FORMULARIO
@ventas.route('/nueva')
@login_required
@role_required(1, 3)
def nueva():
    from forms import VentaForm
    productos = Producto.query.filter_by(estado=1).all()
    clientes = Cliente.query.all()
    form = VentaForm()
    
    id_pedido = request.args.get('id_pedido', type=int)
    pedido_preload = None
    
    if id_pedido:
        from models import Pedido
        pedido_preload = Pedido.query.get(id_pedido)
    
    return render_template('ventas/crear.html', productos=productos, clientes=clientes, pedido_preload=pedido_preload, form=form)


@ventas.route('/guardar', methods=['POST'])
@login_required
@role_required(1, 3)
def guardar():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "No se recibieron datos"}), 400

        productos = data.get("productos")
        fecha_necesaria = data.get("fecha_necesaria")

        if not productos:
            return jsonify({"success": False, "message": "Agrega productos"}), 400

        ok, msg, id_venta = crear_venta(
            current_user.id_usuario,
            productos,
            fecha_necesaria=fecha_necesaria,
        )

        return jsonify({"success": ok, "message": msg, "id_venta": id_venta})

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Error interno del servidor"
        }), 500


@ventas.route('/completar/<int:id_venta>', methods=['POST'])
@login_required
@role_required(1, 3)
def completar(id_venta):
    try:
        data = request.get_json(silent=True) or {}
        metodo_pago = (data.get('metodo_pago') or '').strip()
        fecha_necesaria = data.get('fecha_necesaria')

        ok, msg = completar_venta_pago(
            id_venta=id_venta,
            metodo_pago=metodo_pago,
            id_usuario=current_user.id_usuario,
            fecha_necesaria=fecha_necesaria,
        )
        return jsonify({'success': ok, 'message': msg})

    except Exception as e:
        current_app.logger.error(f"Error al completar venta {id_venta}: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'}), 500
        
@ventas.route('/eliminar', methods=['POST'])
@login_required
@role_required(1, 3)
def eliminar():
    try:
        data = request.get_json(silent=True) or {}
        id_venta_raw = data.get('id_venta')
        try:
            id_venta = int(id_venta_raw) if id_venta_raw is not None else None
        except (TypeError, ValueError):
            id_venta = None

        if not id_venta:
            return jsonify({"success": False, "message": "ID de venta inválido"}), 400

        venta = Venta.query.get(id_venta)
        if not venta:
            return jsonify({"success": False, "message": "Venta no encontrada"}), 404

        if venta.estado == 'Cancelada':
            return jsonify({"success": False, "message": "La venta ya está cancelada"}), 400

        # Revertir stock de productos al cancelar.
        for detalle in venta.detalles:
            if detalle.producto:
                detalle.producto.stock_actual = float(detalle.producto.stock_actual or 0) + float(detalle.cantidad or 0)

        venta.estado = 'Cancelada'
        db.session.commit()

        return jsonify({"success": True, "message": "Venta cancelada correctamente"})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al cancelar venta: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500