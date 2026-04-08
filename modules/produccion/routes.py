from . import produccion
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from utils.security import role_required
from datetime import datetime
from .services import (
    obtener_producciones,
    completar_o_solicitar_compra,
    ver_orden_produccion,
    crear_solicitud_produccion_desde_alerta,
    procesar_detalle_produccion,
    eliminar_solicitud_produccion,
    _asegurar_esquema_produccion,
)
from models import Producto
from math import ceil

@produccion.route('/', methods=['GET'])
@login_required
@role_required(1, 2, 3)
def index():
    _asegurar_esquema_produccion()
    producciones, error = obtener_producciones()

    if error:
        flash("Error al cargar producción", "danger")
        return redirect(url_for('productos.index'))

    hoy = datetime.now().date()
    total_ordenes = len(producciones)
    ordenes_solicitadas = sum(1 for p in producciones if p.get('estado') == 'Solicitada')
    ordenes_en_proceso = sum(1 for p in producciones if p.get('estado') == 'En Proceso')
    ordenes_completadas_hoy = sum(
        1
        for p in producciones
        if p.get('estado') == 'Completada'
        and p.get('fecha_completada')
        and p['fecha_completada'].date() == hoy
    )

    return render_template(
        'produccion/index.html',
        producciones=producciones,
        total_ordenes=total_ordenes,
        ordenes_solicitadas=ordenes_solicitadas,
        ordenes_en_proceso=ordenes_en_proceso,
        ordenes_completadas_hoy=ordenes_completadas_hoy,
    )

@produccion.route('/ver/<int:id>')
@login_required
@role_required(1, 2, 3)
def ver(id):
    _asegurar_esquema_produccion()
    prod, error = ver_orden_produccion(id)

    if error:
        flash("Error al cargar producción", "danger")
        return redirect(url_for('produccion.index'))

    prod['prioridad'] = 'Media'
    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is not None:
        meta = mongo_db.produccion_meta.find_one({'id_produccion': id})
        if meta and meta.get('prioridad'):
            prod['prioridad'] = meta.get('prioridad')

    id_compra = request.args.get('id_compra', type=int)
    return render_template('produccion/ver.html', produccion=prod, id_compra=id_compra)
@produccion.route('/iniciar/<int:id>')
def iniciar(id):
    success, message = iniciar_produccion(id)

    if success:
        flash(message, "success")
    else:
        flash(message, "error")

    return redirect(url_for('produccion.index'))

@produccion.route('/completar/<int:id>', methods=['POST'])
@login_required
@role_required(1, 2, 3)
def completar(id):
    fecha_requerida_compra = request.form.get('fecha_requerida_compra')

    success, message, id_compra = completar_o_solicitar_compra(
        id,
        id_usuario=current_user.id_usuario,
        fecha_requerida_compra=fecha_requerida_compra,
    )

    if success:
        flash(message, "success")
    else:
        categoria = 'warning' if id_compra else 'error'
        flash(message, categoria)

    if id_compra:
        return redirect(url_for('produccion.ver', id=id, id_compra=id_compra))

    return redirect(url_for('produccion.ver', id=id))


@produccion.route('/detalle/<int:id_produccion>/<int:id_detalle>', methods=['POST'])
@login_required
@role_required(1, 2, 3)
def procesar_detalle(id_produccion, id_detalle):
    fecha_requerida_compra = request.form.get('fecha_requerida_compra')
    cantidad_producir = request.form.get('cantidad_producir')

    success, message, id_compra = procesar_detalle_produccion(
        id_produccion,
        id_detalle,
        current_user.id_usuario,
        fecha_requerida_compra=fecha_requerida_compra,
        cantidad_producir=cantidad_producir,
    )

    if success:
        flash(message, 'success')
    else:
        categoria = 'warning' if 'solicitud de compra' in message.lower() else 'danger'
        flash(message, categoria)

    if id_compra:
        return redirect(url_for('produccion.ver', id=id_produccion, id_compra=id_compra))

    return redirect(url_for('produccion.ver', id=id_produccion))

@produccion.route('/cancelar/<int:id>')
@login_required
@role_required(1)
def cancelar(id):
    success, message = eliminar_solicitud_produccion(id)

    if success:
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(url_for('produccion.index'))


@produccion.route('/alerta/<int:id_producto>', methods=['GET', 'POST'])
@login_required
@role_required(1, 2, 3)
def crear_desde_alerta(id_producto):
    producto = Producto.query.get(id_producto)

    if not producto:
        flash('Producto no encontrado', 'danger')
        return redirect(url_for('caja.index'))

    if request.method == 'POST':
        cantidad = request.form.get('cantidad', 10)
        fecha_necesaria = request.form.get('fecha_necesaria')
        prioridad = request.form.get('prioridad', 'Media')
        id_produccion, mensaje = crear_solicitud_produccion_desde_alerta(
            id_producto,
            current_user.id_usuario,
            cantidad=cantidad,
            fecha_necesaria=fecha_necesaria,
            prioridad=prioridad,
        )

        if id_produccion:
            flash(mensaje, 'success')
            return redirect(url_for('produccion.ver', id=id_produccion))

        flash(mensaje, 'danger')
        return redirect(url_for('produccion.crear_desde_alerta', id_producto=id_producto))

    stock_actual = float(producto.stock_actual or 0)
    stock_minimo = float(producto.stock_minimo or 0)
    faltante = max(0.0, stock_minimo - stock_actual)
    cantidad_sugerida = max(1, ceil(faltante)) if faltante > 0 else 1

    return render_template(
        'produccion/solicitud_alerta.html',
        producto=producto,
        cantidad_sugerida=cantidad_sugerida,
        faltante=faltante,
        prioridad_sugerida='Media',
    )