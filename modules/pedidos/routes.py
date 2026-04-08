from . import pedidos
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from utils.security import role_required
from models import db, Pedido, DetallePedido, Producto, Cliente
from datetime import datetime
from .services import (
    obtener_pedidos, obtener_pedido, obtener_detalles_pedido, completar_pedido, cancelar_pedido,
    crear_pedido_manual, editar_pedido_propio,
    procesar_detalle_pedido,
    pagar_pedido,
    _asegurar_esquema_pedidos,
)

@pedidos.route('/')
@login_required
@role_required(1, 3)
def index():
    from forms import PedidoForm
    _asegurar_esquema_pedidos()
    pedidos, error = obtener_pedidos()
    productos = Producto.query.all()
    clientes = Cliente.query.all()
    form = PedidoForm()
    if error:
        current_app.logger.error(f"Error al cargar pedidos: {error}")
        flash("Error al cargar los pedidos", "danger")
        return redirect(url_for('produccion.index'))

    hoy = datetime.now().date()
    pedidos_pendientes = sum(1 for pedido in pedidos if pedido.get('estado') == 'Pendiente')
    pedidos_en_proceso = sum(1 for pedido in pedidos if pedido.get('estado') == 'En Proceso')
    pedidos_produccion_completada = sum(
        1
        for pedido in pedidos
        if (
            pedido.get('estado') == 'Producido'
            or (pedido.get('estado') == 'Completado' and pedido.get('requiere_produccion'))
        )
    )
    pedidos_completados_hoy = sum(
        1
        for pedido in pedidos
        if pedido.get('estado') in ('Completado', 'Pagado', 'Producido')
        and (
            (pedido.get('fecha_entrega') and pedido['fecha_entrega'].date() == hoy)
            or (pedido.get('fecha') and pedido['fecha'].date() == hoy)
        )
    )

    return render_template(
        'pedidos/index.html',
        pedidos=pedidos,
        productos=productos,
        clientes=clientes,
        form=form,
        pedidos_pendientes=pedidos_pendientes,
        pedidos_en_proceso=pedidos_en_proceso,
        pedidos_produccion_completada=pedidos_produccion_completada,
        pedidos_completados_hoy=pedidos_completados_hoy,
    )


@pedidos.route('/mis_pedidos')
@login_required
@role_required(4)
def mis_pedidos():
    _asegurar_esquema_pedidos()
    id_cliente = current_user.cliente.id_cliente
    pedidos, error = obtener_pedido(id_cliente)

    if error:
        current_app.logger.error(f"Error al cargar pedidos: {error}")
        flash("Error al cargar los pedidos", "danger")
        return redirect(url_for('tienda.menu'))

    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is not None and pedidos:
        ids_pedido = [p.get('id') for p in pedidos if p.get('id')]
        calificados = {
            int(doc.get('idVenta'))
            for doc in mongo_db.calificaciones_servicio.find(
                {'idVenta': {'$in': ids_pedido}},
                {'idVenta': 1}
            )
            if doc.get('idVenta') is not None
        }
        for pedido in pedidos:
            pedido['calificado'] = pedido.get('id') in calificados

    return render_template('pedidos/mis_pedidos.html', pedidos=pedidos)

@pedidos.route('/detalles/<int:id_pedido>')
@login_required
@role_required(1, 3, 4)
def ver_detalles_pedido(id_pedido):
    _asegurar_esquema_pedidos()

    pedido = Pedido.query.get(id_pedido)

    if not pedido:
        flash("Pedido no encontrado", "danger")
        return redirect(url_for('pedidos.mis_pedidos'))

    if current_user.id_rol == 4 and pedido.id_cliente != current_user.cliente.id_cliente:
        flash("No tienes permiso para ver este pedido", "danger")
        return redirect(url_for('pedidos.mis_pedidos'))

    puede_calificar = False
    ya_calificado = False
    mongo_db = getattr(current_app, 'mongo', None)

    if current_user.id_rol == 4 and (pedido.estado or '').strip().lower() in ('completado', 'pagado'):
        puede_calificar = True
        if mongo_db is not None:
            ya_calificado = mongo_db.calificaciones_servicio.find_one({'idVenta': pedido.id_pedido}) is not None

    mostrar_progreso_produccion = False
    produccion_total = 0
    produccion_completada = 0
    progreso_produccion = 0

    if pedido.produccion and pedido.detalles:
        mostrar_progreso_produccion = True
        produccion_total = len(pedido.detalles)

        detalles_prod = pedido.produccion.detalles or []
        productos_prod_completados = {
            dp.id_producto
            for dp in detalles_prod
            if getattr(dp, 'completado', False) or float(getattr(dp, 'cantidad_producida', 0) or 0) >= float(dp.cantidad or 0)
        }

        for detalle in pedido.detalles:
            if getattr(detalle, 'atendido', False):
                produccion_completada += 1
                continue

            if getattr(detalle, 'en_produccion', False):
                if detalle.id_producto in productos_prod_completados:
                    produccion_completada += 1
                continue

            stock_actual = float(getattr(detalle.producto, 'stock_actual', 0) or 0)
            requerido = float(detalle.cantidad or 0)
            if stock_actual >= requerido:
                produccion_completada += 1

        progreso_produccion = round((produccion_completada / produccion_total) * 100, 2) if produccion_total > 0 else 0
    elif any(getattr(d, 'en_produccion', False) for d in (pedido.detalles or [])):
        mostrar_progreso_produccion = True

    pedido_pagado = (pedido.estado or '').strip().lower() == 'pagado'

    return render_template(
        'pedidos/detalles_pedido.html',
        pedido=pedido,
        pedido_pagado=pedido_pagado,
        puede_calificar=puede_calificar,
        ya_calificado=ya_calificado,
        mostrar_progreso_produccion=mostrar_progreso_produccion,
        produccion_total=produccion_total,
        produccion_completada=produccion_completada,
        progreso_produccion=progreso_produccion,
    )


@pedidos.route('/pagar/<int:id_pedido>', methods=['POST'])
@login_required
@role_required(4)
def pagar(id_pedido):
    _asegurar_esquema_pedidos()

    pedido = Pedido.query.get(id_pedido)
    if not pedido:
        flash('Pedido no encontrado', 'danger')
        return redirect(url_for('pedidos.mis_pedidos'))

    if not current_user.cliente or pedido.id_cliente != current_user.cliente.id_cliente:
        flash('No tienes permiso para pagar este pedido', 'danger')
        return redirect(url_for('pedidos.mis_pedidos'))

    metodo_pago = (request.form.get('metodo_pago') or '').strip()
    datos_tarjeta = {
        'numero_tarjeta': request.form.get('numero_tarjeta', ''),
        'titular_tarjeta': request.form.get('titular_tarjeta', ''),
        'vencimiento_tarjeta': request.form.get('vencimiento_tarjeta', ''),
        'cvv_tarjeta': request.form.get('cvv_tarjeta', ''),
    }

    exito, mensaje = pagar_pedido(
        id_pedido=id_pedido,
        id_usuario=current_user.id_usuario,
        metodo_pago=metodo_pago,
        datos_tarjeta=datos_tarjeta,
    )
    flash(mensaje, 'success' if exito else 'danger')
    return redirect(url_for('pedidos.ver_detalles_pedido', id_pedido=id_pedido))


@pedidos.route('/calificar/<int:id_pedido>', methods=['POST'])
@login_required
@role_required(4)
def calificar_servicio(id_pedido):
    _asegurar_esquema_pedidos()

    pedido = Pedido.query.get(id_pedido)
    if not pedido:
        return jsonify({'success': False, 'message': 'Pedido no encontrado'}), 404

    if not current_user.cliente or pedido.id_cliente != current_user.cliente.id_cliente:
        return jsonify({'success': False, 'message': 'No tienes permiso para calificar este pedido'}), 403

    if (pedido.estado or '').strip().lower() not in ('completado', 'pagado'):
        return jsonify({'success': False, 'message': 'Solo puedes calificar pedidos completados'}), 400

    data = request.get_json(silent=True) or {}

    try:
        calificacion = int(data.get('calificacion', 0))
    except (TypeError, ValueError):
        calificacion = 0

    if calificacion < 1 or calificacion > 5:
        return jsonify({'success': False, 'message': 'La calificación general debe estar entre 1 y 5'}), 400

    comentario = (data.get('comentario') or '').strip()
    if not comentario:
        comentario = 'Sin comentario'

    productos = data.get('productos') or []
    if not isinstance(productos, list) or len(productos) == 0:
        return jsonify({'success': False, 'message': 'Debes calificar al menos un producto'}), 400

    productos_normalizados = []
    for p in productos:
        if not isinstance(p, dict):
            return jsonify({'success': False, 'message': 'Formato de productos inválido'}), 400

        nombre = (p.get('nombre') or '').strip()
        try:
            calif_producto = int(p.get('calificacion', 0))
        except (TypeError, ValueError):
            calif_producto = 0

        if not nombre or calif_producto < 1 or calif_producto > 5:
            return jsonify({'success': False, 'message': 'Cada producto debe tener nombre y calificación entre 1 y 5'}), 400

        productos_normalizados.append({
            'nombre': nombre,
            'calificacion': calif_producto,
        })

    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is None:
        return jsonify({'success': False, 'message': 'No se pudo acceder al almacenamiento de calificaciones'}), 500

    if mongo_db.calificaciones_servicio.find_one({'idVenta': pedido.id_pedido}):
        return jsonify({'success': False, 'message': 'Este pedido ya fue calificado y no se puede editar'}), 409

    documento = {
        'idVenta': pedido.id_pedido,
        'calificacion': calificacion,
        'comentario': comentario,
        'productos': productos_normalizados,
        'fecha': datetime.now().strftime('%Y-%m-%d'),
    }

    mongo_db.calificaciones_servicio.insert_one(documento)

    return jsonify({'success': True, 'message': 'Calificación guardada correctamente'})


@pedidos.route('/calificaciones', methods=['GET'])
@login_required
@role_required(1)
def reporte_calificaciones():
    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is None:
        flash('No se pudo acceder al almacenamiento de calificaciones', 'danger')
        return redirect(url_for('pedidos.index'))

    docs = list(
        mongo_db.calificaciones_servicio.find(
            {},
            {
                '_id': 0,
                'idVenta': 1,
                'calificacion': 1,
                'comentario': 1,
                'productos': 1,
                'fecha': 1,
            }
        )
    )

    ids_pedido = [doc.get('idVenta') for doc in docs if doc.get('idVenta')]
    pedidos_map = {
        pedido.id_pedido: pedido
        for pedido in Pedido.query.filter(Pedido.id_pedido.in_(ids_pedido)).all()
    } if ids_pedido else {}

    reporte = []
    for doc in docs:
        id_venta = doc.get('idVenta')
        pedido = pedidos_map.get(id_venta)

        cliente = 'Cliente'
        if pedido and pedido.cliente:
            if pedido.cliente.persona:
                nombre = (pedido.cliente.persona.nombre or '').strip()
                ap = (pedido.cliente.persona.apellido_p or '').strip()
                am = (pedido.cliente.persona.apellido_m or '').strip()
                cliente = ' '.join(v for v in [nombre, ap, am] if v) or nombre or cliente
            elif pedido.cliente.usuario:
                cliente = pedido.cliente.usuario.username or cliente

        productos = doc.get('productos') or []
        promedio_productos = 0.0
        if productos:
            promedio_productos = round(
                sum(float(p.get('calificacion') or 0) for p in productos) / len(productos),
                2,
            )

        reporte.append({
            'idVenta': id_venta,
            'cliente': cliente,
            'calificacion': doc.get('calificacion'),
            'comentario': doc.get('comentario') or '',
            'productos': productos,
            'fecha': doc.get('fecha') or '',
            'promedio_productos': promedio_productos,
        })

    reporte.sort(key=lambda r: r.get('fecha') or '', reverse=True)

    return render_template('pedidos/reporte_calificaciones.html', calificaciones=reporte)


@pedidos.route('/ticket/<int:id_pedido>')
@login_required
@role_required(1, 3, 4)
def ticket(id_pedido):
    _asegurar_esquema_pedidos()
    pedido = Pedido.query.get(id_pedido)

    if not pedido:
        flash("Pedido no encontrado", "danger")
        return redirect(url_for('pedidos.mis_pedidos'))

    if current_user.id_rol == 4 and pedido.id_cliente != current_user.cliente.id_cliente:
        flash("No tienes permiso para ver este ticket", "danger")
        return redirect(url_for('pedidos.mis_pedidos'))

    if (pedido.estado or '').strip().lower() != 'pagado':
        flash("El ticket solo está disponible cuando el pedido está pagado", "warning")
        if current_user.id_rol == 4:
            return redirect(url_for('pedidos.mis_pedidos'))
        return redirect(url_for('pedidos.ver_detalles_pedido', id_pedido=id_pedido))

    return render_template('pedidos/ticket.html', pedido=pedido)

from flask import request, redirect, url_for, flash
from flask_login import current_user
from .services import completar_o_producir

@pedidos.route('/procesar', methods=['POST'])
@login_required
@role_required(1, 3)
def procesar():
    _asegurar_esquema_pedidos()

    id_pedido = request.form.get('id_pedido')
    fecha_necesaria = request.form.get('fecha_necesaria')
    metodo_pago = request.form.get('metodo_pago')
    datos_tarjeta = {
        'numero_tarjeta': request.form.get('numero_tarjeta', ''),
        'titular_tarjeta': request.form.get('titular_tarjeta', ''),
        'vencimiento_tarjeta': request.form.get('vencimiento_tarjeta', ''),
        'cvv_tarjeta': request.form.get('cvv_tarjeta', ''),
    }

    exito, mensaje = completar_o_producir(
        id_pedido,
        current_user.id_usuario,
        fecha_necesaria,
        metodo_pago=metodo_pago,
        datos_tarjeta=datos_tarjeta,
    )

    if exito:
        if 'completado' in (mensaje or '').lower():
            flash(mensaje, 'success')
            return redirect(url_for('pedidos.ver_detalles_pedido', id_pedido=id_pedido))

        if "producción" in mensaje:
            flash(mensaje, "warning")  # 🔶 aviso
        else:
            flash(mensaje, "success")  # 🟢 éxito
    else:
        flash(mensaje, "danger")

    return redirect(url_for('pedidos.index'))


@pedidos.route('/crear', methods=['POST'])
@login_required
@role_required(1, 3)
def crear():
    _asegurar_esquema_pedidos()
    id_cliente = request.form.get('id_cliente')
    metodo_pago = request.form.get('metodo_pago')
    fecha_necesaria = request.form.get('fecha_necesaria')
    datos_tarjeta = {
        'numero_tarjeta': request.form.get('numero_tarjeta', ''),
        'titular_tarjeta': request.form.get('titular_tarjeta', ''),
        'vencimiento_tarjeta': request.form.get('vencimiento_tarjeta', ''),
        'cvv_tarjeta': request.form.get('cvv_tarjeta', ''),
    }
    ids_producto = request.form.getlist('id_producto[]')
    cantidades = request.form.getlist('cantidad[]')

    productos = []
    for idx in range(len(ids_producto)):
        productos.append({
            'id_producto': ids_producto[idx],
            'cantidad': cantidades[idx] if idx < len(cantidades) else None
        })

    exito, mensaje = crear_pedido_manual(
        id_cliente,
        productos,
        metodo_pago,
        current_user.id_usuario,
        datos_tarjeta=datos_tarjeta,
        fecha_necesaria=fecha_necesaria,
    )
    flash(mensaje, 'success' if exito else 'danger')

    return redirect(url_for('pedidos.index'))
    
@pedidos.route('/cancelar/<int:id_pedido>', methods=['POST'])
@login_required
@role_required(1, 3, 4)
def cancelar(id_pedido):
    _asegurar_esquema_pedidos()
    if current_user.id_rol == 4:
        pedido = Pedido.query.get(id_pedido)
        if not pedido or pedido.id_cliente != current_user.cliente.id_cliente:
            return {"success": False, "message": "No tienes permiso para cancelar este pedido"}, 403

    success, message = cancelar_pedido(id_pedido)

    if success:
        return {"success": True, "message": message}
    else:
        return {"success": False, "message": message}, 400


@pedidos.route('/editar/<int:id_pedido>', methods=['GET', 'POST'])
@login_required
@role_required(1, 4)
def editar(id_pedido):
    _asegurar_esquema_pedidos()
    pedido = Pedido.query.get(id_pedido)

    if not pedido or pedido.id_cliente != current_user.cliente.id_cliente:
        flash("No tienes permiso para editar este pedido", "danger")
        return redirect(url_for('pedidos.mis_pedidos'))

    if pedido.estado != 'Pendiente':
        flash("Solo puedes editar pedidos pendientes", "warning")
        return redirect(url_for('pedidos.mis_pedidos'))

    if request.method == 'POST':
        ids_producto = request.form.getlist('id_producto[]')
        cantidades = request.form.getlist('cantidad[]')
        metodo_pago = request.form.get('metodo_pago')

        productos = []
        for idx in range(len(ids_producto)):
            productos.append({
                'id_producto': ids_producto[idx],
                'cantidad': cantidades[idx] if idx < len(cantidades) else None
            })

        exito, mensaje = editar_pedido_propio(
            id_pedido,
            current_user.cliente.id_cliente,
            productos,
            metodo_pago,
            current_user.id_usuario,
        )

        flash(mensaje, 'success' if exito else 'danger')
        return redirect(url_for('pedidos.mis_pedidos'))

    productos = Producto.query.filter_by(estado=True).order_by(Producto.nombre.asc()).all()
    return render_template('pedidos/editar_pedido.html', pedido=pedido, productos=productos)


@pedidos.route('/detalle/<int:id_pedido>/<int:id_detalle>', methods=['POST'])
@login_required
@role_required(1, 3)
def procesar_detalle(id_pedido, id_detalle):
    _asegurar_esquema_pedidos()
    enviar_a_produccion = request.form.get('enviar_a_produccion') == '1'
    fecha_necesaria = request.form.get('fecha_necesaria')
    metodo_pago = request.form.get('metodo_pago')
    datos_tarjeta = {
        'numero_tarjeta': request.form.get('numero_tarjeta', ''),
        'titular_tarjeta': request.form.get('titular_tarjeta', ''),
        'vencimiento_tarjeta': request.form.get('vencimiento_tarjeta', ''),
        'cvv_tarjeta': request.form.get('cvv_tarjeta', ''),
    }

    exito, mensaje = procesar_detalle_pedido(
        id_pedido,
        id_detalle,
        current_user.id_usuario,
        enviar_a_produccion=enviar_a_produccion,
        fecha_necesaria=fecha_necesaria,
        metodo_pago=metodo_pago,
        datos_tarjeta=datos_tarjeta,
    )

    if exito:
        if pedido := Pedido.query.get(id_pedido):
            if (pedido.estado or '').lower() == 'completado':
                flash('Pedido completado correctamente.', 'success')
                return redirect(url_for('pedidos.ver_detalles_pedido', id_pedido=id_pedido))

        flash(mensaje, 'success')
    else:
        categoria = 'warning' if 'producción' in mensaje.lower() else 'danger'
        flash(mensaje, categoria)

    return redirect(url_for('pedidos.ver_detalles_pedido', id_pedido=id_pedido))