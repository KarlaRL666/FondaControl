from . import dashboard
from flask import render_template, request, current_app, Response, flash
from flask_login import login_required, current_user
from utils.security import role_required
from models import db, Pedido, DetallePedido, Producto, CategoriaPlatillo, Caja as CajaModel
from .services import obtener_reportes_mongo, obtener_metricas_bitacora_mongo, obtener_resumen_ventas_mongo
from sqlalchemy import func
from datetime import datetime, timedelta
import math
import csv
from io import StringIO


@dashboard.route('/', methods=['GET', 'POST'])
@login_required
@role_required(1)
def index():
    hoy = datetime.now().date()
    ahora = datetime.now()
    inicio_semana = hoy - timedelta(days=6)
    fecha_operacion = func.coalesce(Pedido.fecha_entrega, Pedido.fecha)

    turno_inicio_programado_txt = '08:10'
    turno_cierre_programado_txt = '22:00'
    caja_abierta = CajaModel.query.filter_by(estado='Abierta').order_by(CajaModel.fecha.desc()).first()
    turno_inicio_real_txt = caja_abierta.fecha.strftime('%H:%M') if caja_abierta else 'Pendiente'
    turno_inicio_programado = datetime.combine(hoy, datetime.min.time()).replace(hour=8, minute=10)
    turno_inicio_retrasado = bool(ahora >= turno_inicio_programado and not caja_abierta)

    ventas_hoy_total = db.session.query(func.coalesce(func.sum(Pedido.total), 0)).filter(
        func.date(fecha_operacion) == hoy,
        Pedido.estado == 'Completado'
    ).scalar() or 0

    pedidos_completados_hoy = db.session.query(func.count(Pedido.id_pedido)).filter(
        func.date(fecha_operacion) == hoy,
        Pedido.estado == 'Completado'
    ).scalar() or 0

    # Serie diaria de ventas (últimos 7 días)
    filas_ventas = db.session.query(
        func.date(fecha_operacion).label('fecha'),
        func.coalesce(func.sum(Pedido.total), 0).label('total')
    ).filter(
        func.date(fecha_operacion) >= inicio_semana,
        Pedido.estado == 'Completado'
    ).group_by(func.date(fecha_operacion)).all()

    mapa_ventas = {str(fila.fecha): float(fila.total or 0) for fila in filas_ventas}

    ventas_diarias_labels = []
    ventas_diarias_data = []
    for i in range(7):
        dia = inicio_semana + timedelta(days=i)
        ventas_diarias_labels.append(dia.strftime('%d/%m'))
        ventas_diarias_data.append(mapa_ventas.get(str(dia), 0))

    top_productos = db.session.query(
        Producto.nombre.label('nombre'),
        func.coalesce(func.sum(DetallePedido.cantidad), 0).label('cantidad'),
        func.coalesce(func.sum(DetallePedido.subtotal), 0).label('monto')
    ).join(DetallePedido, DetallePedido.id_producto == Producto.id_producto).join(
        Pedido, Pedido.id_pedido == DetallePedido.id_pedido
    ).filter(
        Pedido.estado == 'Completado',
        func.date(fecha_operacion) == hoy
    ).group_by(Producto.id_producto, Producto.nombre).order_by(
        func.sum(DetallePedido.cantidad).desc()
    ).limit(5).all()

    top_presentaciones = db.session.query(
        CategoriaPlatillo.nombre.label('nombre'),
        func.coalesce(func.sum(DetallePedido.cantidad), 0).label('cantidad')
    ).join(Producto, Producto.id_categoria_platillo == CategoriaPlatillo.id_categoria_platillo).join(
        DetallePedido, DetallePedido.id_producto == Producto.id_producto
    ).join(
        Pedido, Pedido.id_pedido == DetallePedido.id_pedido
    ).filter(
        Pedido.estado == 'Completado',
        func.date(fecha_operacion) == hoy
    ).group_by(CategoriaPlatillo.id_categoria_platillo, CategoriaPlatillo.nombre).order_by(
        func.sum(DetallePedido.cantidad).desc()
    ).limit(5).all()

    pedidos_recientes = (
        Pedido.query
        .filter(Pedido.estado == 'Completado')
        .order_by(
            Pedido.fecha_entrega.is_(None).asc(),
            Pedido.fecha_entrega.desc(),
            Pedido.fecha.desc(),
        )
        .limit(5)
        .all()
    )

    actividad_reciente = []
    for pedido in pedidos_recientes:
        fecha_ref = pedido.fecha_entrega or pedido.fecha
        actividad_reciente.append({
            'id_pedido': pedido.id_pedido,
            'fecha': fecha_ref,
            'texto': f"Pedido #{pedido.id_pedido} completado",
            'monto': float(pedido.total or 0),
        })

    top_producto = top_productos[0] if top_productos else None
    top_presentacion = top_presentaciones[0] if top_presentaciones else None

    return render_template(
        'dashboard/index.html',
        ventas_hoy_total=float(ventas_hoy_total),
        ventas_diarias_labels=ventas_diarias_labels,
        ventas_diarias_data=ventas_diarias_data,
        top_productos_dashboard=top_productos,
        top_presentaciones_labels=[fila.nombre for fila in top_presentaciones],
        top_presentaciones_data=[int(fila.cantidad or 0) for fila in top_presentaciones],
        top_producto_nombre=top_producto.nombre if top_producto else 'Sin ventas',
        top_producto_cantidad=int(top_producto.cantidad) if top_producto else 0,
        top_presentacion_nombre=top_presentacion.nombre if top_presentacion else 'Sin ventas',
        top_presentacion_cantidad=int(top_presentacion.cantidad) if top_presentacion else 0,
        pedidos_completados_hoy=int(pedidos_completados_hoy),
        actividad_reciente=actividad_reciente,
        turno_inicio_programado_txt=turno_inicio_programado_txt,
        turno_cierre_programado_txt=turno_cierre_programado_txt,
        turno_inicio_real_txt=turno_inicio_real_txt,
        turno_inicio_retrasado=turno_inicio_retrasado,
    )


@dashboard.route('/bitacora', methods=['GET'])
@login_required
@role_required(1)
def bitacora():
    # === CORRECCIÓN PRINCIPAL ===
    mongo_db = getattr(current_app, 'mongo', None)
    
    if mongo_db is None:
        flash("La bitácora de acciones no está disponible porque la conexión a MongoDB no está establecida.", "warning")
        return render_template(
            'dashboard/bitacora.html',
            eventos=[],
            eventos_recientes=None,
            page=1,
            total_pages=1,
            total_items=0,
            total_modulos=0,
            per_page=20,
            q='',
            modulo='',
            usuario='',
            rol=None,
            metodo='',
            status='',
            fecha_desde='',
            fecha_hasta='',
            modulos_disponibles=[],
            roles_disponibles=[],
        )

    # === Resto del código (con mongo_db en lugar de current_app.mongo) ===
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(request.args.get('per_page', 20, type=int), 10), 100)
    
    q = (request.args.get('q') or '').strip()
    modulo = (request.args.get('modulo') or '').strip()
    usuario = (request.args.get('usuario') or '').strip()
    rol = request.args.get('rol', type=int)
    metodo = (request.args.get('metodo') or '').strip().upper()
    status = request.args.get('status', type=int)
    exportar = request.args.get('export', '').lower() == 'csv'
    fecha_desde_raw = (request.args.get('fecha_desde') or '').strip()
    fecha_hasta_raw = (request.args.get('fecha_hasta') or '').strip()

    filtros = {}
    if modulo:
        filtros['modulo'] = modulo
    if metodo:
        filtros['metodo'] = metodo
    if usuario:
        filtros['usuario.username'] = {'$regex': usuario, '$options': 'i'}
    if rol is not None:
        filtros['usuario.rol'] = rol
    if status is not None:
        filtros['status_code'] = status

    if q:
        filtros['$or'] = [
            {'endpoint': {'$regex': q, '$options': 'i'}},
            {'ruta': {'$regex': q, '$options': 'i'}},
            {'usuario.username': {'$regex': q, '$options': 'i'}},
            {'modulo': {'$regex': q, '$options': 'i'}},
        ]

    if fecha_desde_raw or fecha_hasta_raw:
        rango = {}
        if fecha_desde_raw:
            try:
                rango['$gte'] = datetime.strptime(fecha_desde_raw, '%Y-%m-%d')
            except ValueError:
                pass
        if fecha_hasta_raw:
            try:
                rango['$lte'] = datetime.strptime(fecha_hasta_raw, '%Y-%m-%d') + timedelta(days=1)
            except ValueError:
                pass
        if rango:
            filtros['fecha'] = rango

    collection = mongo_db.bitacora_acciones   # ← Usamos la variable segura

    if exportar:
        eventos_export = list(collection.find(filtros).sort('fecha', -1).limit(5000))
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['fecha', 'modulo', 'metodo', 'ruta', 'endpoint', 'status_code', 'usuario', 'rol', 'ip'])
        for evento in eventos_export:
            user_data = evento.get('usuario') or {}
            writer.writerow([
                evento.get('fecha').strftime('%Y-%m-%d %H:%M:%S') if evento.get('fecha') else '',
                evento.get('modulo') or '',
                evento.get('metodo') or '',
                evento.get('ruta') or '',
                evento.get('endpoint') or '',
                evento.get('status_code') or '',
                user_data.get('username') or '',
                user_data.get('rol') or '',
                evento.get('ip') or '',
            ])
        csv_data = output.getvalue()
        output.close()
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=bitacora.csv'}
        )

    total_items = collection.count_documents(filtros)
    total_pages = max(1, math.ceil(total_items / per_page))
    if page > total_pages:
        page = total_pages

    eventos_cursor = (
        collection
        .find(filtros)
        .sort('fecha', -1)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )

    eventos = list(eventos_cursor)
    modulos_disponibles = sorted([m for m in collection.distinct('modulo') if m])
    roles_disponibles = sorted([r for r in collection.distinct('usuario.rol') if r is not None])

    eventos_recientes = eventos[0].get('fecha') if eventos else None

    return render_template(
        'dashboard/bitacora.html',
        eventos=eventos,
        eventos_recientes=eventos_recientes,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        total_modulos=len(modulos_disponibles),
        per_page=per_page,
        q=q,
        modulo=modulo,
        usuario=usuario,
        rol=rol,
        metodo=metodo,
        status=status,
        fecha_desde=fecha_desde_raw,
        fecha_hasta=fecha_hasta_raw,
        modulos_disponibles=modulos_disponibles,
        roles_disponibles=roles_disponibles,
    )


@dashboard.route('/reportes-mongo', methods=['GET'])
@login_required
@role_required(1)
def reportes_mongo():
    dias = request.args.get('dias', 7, type=int) or 7
    if dias not in (7, 15, 30):
        dias = 7

    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is None:
        flash('MongoDB no está disponible para generar reportes.', 'warning')
        return render_template(
            'dashboard/reportes_mongo.html',
            reportes={},
            metricas={'modulos': [], 'metodos': [], 'usuarios': [], 'por_dia': []},
            resumen_ventas={'periodo_dias': dias, 'ventas_contadas': 0, 'subtotal_acumulado': 0.0, 'total_acumulado': 0.0, 'ticket_promedio': 0.0, 'ultima_fecha': 'N/D'},
            colecciones=[],
            total_documentos=0,
            dias=dias,
        )

    reportes, error_reportes = obtener_reportes_mongo(mongo_db)
    metricas, error_metricas = obtener_metricas_bitacora_mongo(mongo_db, dias=dias)
    resumen_ventas, error_resumen_ventas = obtener_resumen_ventas_mongo(mongo_db, dias=dias)

    if error_reportes:
        flash(f'No se pudieron cargar reportes de Mongo: {error_reportes}', 'warning')
        reportes = {}

    if error_metricas:
        flash(f'No se pudieron calcular métricas Mongo: {error_metricas}', 'warning')
        metricas = {'modulos': [], 'metodos': [], 'usuarios': [], 'por_dia': []}

    if error_resumen_ventas:
        flash(f'No se pudo calcular el resumen de ventas: {error_resumen_ventas}', 'warning')
        resumen_ventas = {'periodo_dias': dias, 'ventas_contadas': 0, 'subtotal_acumulado': 0.0, 'total_acumulado': 0.0, 'ticket_promedio': 0.0, 'ultima_fecha': 'N/D'}

    if reportes is None:
        reportes = {}

    # En ventas de sucursal mostramos consolidado por rango, sin campo de cliente.
    reportes['reporteVentas'] = resumen_ventas or {'periodo_dias': dias, 'ventas_contadas': 0, 'subtotal_acumulado': 0.0, 'total_acumulado': 0.0, 'ticket_promedio': 0.0, 'ultima_fecha': 'N/D'}

    colecciones = sorted([c for c in mongo_db.list_collection_names() if c])

    total_documentos = 0
    for nombre in colecciones:
        try:
            total_documentos += int(mongo_db[nombre].count_documents({}))
        except Exception:
            continue

    return render_template(
        'dashboard/reportes_mongo.html',
        reportes=reportes or {},
        metricas=metricas or {'modulos': [], 'metodos': [], 'usuarios': [], 'por_dia': []},
        resumen_ventas=resumen_ventas or {'periodo_dias': dias, 'ventas_contadas': 0, 'subtotal_acumulado': 0.0, 'total_acumulado': 0.0, 'ticket_promedio': 0.0, 'ultima_fecha': 'N/D'},
        colecciones=colecciones,
        total_documentos=total_documentos,
        dias=dias,
    )