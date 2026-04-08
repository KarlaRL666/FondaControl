from models import db, Compra, DetalleCompra, MateriaPrima, Proveedor, Produccion, Caja, MovimientoCaja, Pedido, PedidoMeta
from flask import current_app
from sqlalchemy import text, func, and_, or_, not_
from datetime import datetime, timedelta
from utils.produccion_stock import calcular_requerimientos_para_producto
from utils.schema_guard import asegurar_columnas
import logging

logger = logging.getLogger(__name__)


def _normalizar_metodo_pago(metodo_pago):
    metodo = (metodo_pago or '').strip().title()
    if metodo not in {'Efectivo', 'Tarjeta', 'Transferencia'}:
        return None
    return metodo


def _obtener_caja_abierta():
    return Caja.query.filter_by(estado='Abierta').order_by(Caja.fecha.desc()).first()


def _obtener_inicio_fin_caja(caja):
    if not caja:
        return None, None

    inicio = caja.fecha
    fin = None

    cierre_marcador = (
        MovimientoCaja.query
        .filter_by(id_caja=caja.id_caja, descripcion='__CIERRE_CAJA__')
        .order_by(MovimientoCaja.fecha.desc())
        .first()
    )
    if cierre_marcador:
        fin = cierre_marcador.fecha
    else:
        siguiente_caja = (
            Caja.query
            .filter(Caja.fecha > caja.fecha)
            .order_by(Caja.fecha.asc())
            .first()
        )
        if siguiente_caja:
            fin = siguiente_caja.fecha

    if fin is None:
        fin = datetime.now() + timedelta(days=1)

    return inicio, fin


def _calcular_efectivo_disponible(caja):
    if not caja:
        return 0.0

    inicio, fin = _obtener_inicio_fin_caja(caja)
    if not inicio or not fin:
        return float(caja.monto_inicial or 0.0)

    total_ventas_efectivo = (
        db.session.query(func.coalesce(func.sum(Pedido.total), 0.0))
        .outerjoin(PedidoMeta, PedidoMeta.id_pedido == Pedido.id_pedido)
        .filter(
            Pedido.estado == 'Completado',
            PedidoMeta.metodo_pago == 'Efectivo',
            or_(
                and_(Pedido.fecha_entrega.isnot(None), Pedido.fecha_entrega >= inicio, Pedido.fecha_entrega < fin),
                and_(Pedido.fecha_entrega.is_(None), Pedido.fecha >= inicio, Pedido.fecha < fin),
            ),
        )
        .scalar()
    )

    total_compras_efectivo = (
        db.session.query(func.coalesce(func.sum(Compra.total), 0.0))
        .filter(
            Compra.estado == 'Completada',
            Compra.metodo_pago == 'Efectivo',
            or_(
                and_(Compra.fecha_entrega.isnot(None), Compra.fecha_entrega >= inicio, Compra.fecha_entrega < fin),
                and_(Compra.fecha_entrega.is_(None), Compra.fecha >= inicio, Compra.fecha < fin),
            ),
        )
        .scalar()
    )

    ingresos_manual = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0.0))
        .filter(
            MovimientoCaja.id_caja == caja.id_caja,
            MovimientoCaja.tipo == 'Ingreso',
            MovimientoCaja.descripcion != '__CIERRE_CAJA__',
            or_(MovimientoCaja.descripcion.is_(None), not_(MovimientoCaja.descripcion.like('Pedido #%'))),
        )
        .scalar()
    )

    egresos_manual = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0.0))
        .filter(
            MovimientoCaja.id_caja == caja.id_caja,
            MovimientoCaja.tipo == 'Egreso',
            or_(MovimientoCaja.descripcion.is_(None), not_(MovimientoCaja.descripcion.like('Compra #%'))),
        )
        .scalar()
    )

    disponible = (
        float(caja.monto_inicial or 0.0)
        + float(total_ventas_efectivo or 0.0)
        + float(ingresos_manual or 0.0)
        - float(total_compras_efectivo or 0.0)
        - float(egresos_manual or 0.0)
    )
    return max(disponible, 0.0)


def obtener_efectivo_disponible_para_compra():
    caja = _obtener_caja_abierta()
    if not caja:
        return 0.0, False
    return round(_calcular_efectivo_disponible(caja), 2), True


def _asegurar_esquema_compras():
    asegurar_columnas(
        'compras',
        [
            ('tarjeta_titular', 'VARCHAR(120)'),
            ('tarjeta_ultimos4', 'VARCHAR(4)'),
            ('tarjeta_vencimiento', 'VARCHAR(5)'),
        ],
    )

    asegurar_columnas(
        'detalle_compra',
        [
            ('recibido', 'BOOLEAN NOT NULL DEFAULT 0'),
        ],
    )


def crear_solicitud_compra_desde_alerta(id_materia, id_usuario):
    try:
        _asegurar_esquema_compras()
        materia = MateriaPrima.query.get(id_materia)

        if not materia:
            return None, "Materia prima no encontrada"

        if materia.stock_actual >= materia.stock_minimo:
            return None, "La materia prima ya no está por debajo del mínimo"

        cantidad = materia.stock_minimo - materia.stock_actual
        subtotal = cantidad * materia.precio

        compra = Compra(
            fecha=datetime.now(),
            total=subtotal,
            id_proveedor=materia.id_proveedor,
            id_usuario=id_usuario,
            estado="Solicitada"
        )

        db.session.add(compra)
        db.session.flush()

        db.session.add(DetalleCompra(
            id_compra=compra.id_compra,
            id_materia=materia.id_materia,
            cantidad=cantidad,
            precio_u=materia.precio,
            subtotal=subtotal
        ))

        db.session.commit()
        return compra.id_compra, f"Solicitud de compra creada para {materia.nombre}"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear solicitud de compra desde alerta: {str(e)}")
        return None, str(e)


def crear_solicitud_compra_manual(form, id_usuario):
    try:
        _asegurar_esquema_compras()
        materias = form.getlist('id_materia[]')
        cantidades = form.getlist('cantidad[]')
        proveedores = form.getlist('id_proveedor[]')

        lineas = []

        for index, materia_id in enumerate(materias):
            if not materia_id:
                continue

            cantidad_raw = cantidades[index] if index < len(cantidades) else ''
            proveedor_raw = proveedores[index] if index < len(proveedores) else ''

            try:
                cantidad = float(cantidad_raw)
            except (TypeError, ValueError):
                return None, f"Cantidad inválida en la fila {index + 1}"

            if cantidad <= 0:
                return None, f"La cantidad debe ser mayor a cero en la fila {index + 1}"

            materia = MateriaPrima.query.get(int(materia_id))
            if not materia:
                return None, f"Materia prima no encontrada en la fila {index + 1}"

            proveedor_id = int(proveedor_raw) if proveedor_raw else materia.id_proveedor
            if proveedor_id != materia.id_proveedor:
                return None, f"El proveedor de la fila {index + 1} no corresponde a la materia prima seleccionada"
            proveedor = Proveedor.query.get(proveedor_id)
            if not proveedor:
                return None, f"Proveedor no encontrado en la fila {index + 1}"

            subtotal = cantidad * materia.precio

            lineas.append({
                'materia': materia,
                'cantidad': cantidad,
                'proveedor': proveedor,
                'subtotal': subtotal,
            })

        if not lineas:
            return None, "Agrega al menos una materia prima"

        compras_creadas = []
        lineas_por_proveedor = {}

        for linea in lineas:
            lineas_por_proveedor.setdefault(linea['proveedor'].id_proveedor, {
                'proveedor': linea['proveedor'],
                'lineas': []
            })['lineas'].append(linea)

        for grupo in lineas_por_proveedor.values():
            compra = Compra(
                fecha=datetime.now(),
                total=0,
                id_proveedor=grupo['proveedor'].id_proveedor,
                id_usuario=id_usuario,
                estado='Solicitada'
            )

            db.session.add(compra)
            db.session.flush()

            total_compra = 0

            for linea in grupo['lineas']:
                detalle = DetalleCompra(
                    id_compra=compra.id_compra,
                    id_materia=linea['materia'].id_materia,
                    cantidad=linea['cantidad'],
                    precio_u=linea['materia'].precio,
                    subtotal=linea['subtotal']
                )
                db.session.add(detalle)
                total_compra += linea['subtotal']

            compra.total = total_compra
            compras_creadas.append(compra)

        db.session.commit()

        if len(compras_creadas) == 1:
            return compras_creadas[0].id_compra, 'Solicitud de compra creada correctamente'

        return [compra.id_compra for compra in compras_creadas], f'Se crearon {len(compras_creadas)} solicitudes agrupadas por proveedor'

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear solicitud de compra manual: {str(e)}")
        return None, str(e)


def obtener_materias_faltantes_produccion(id_materia_prioritaria=None):
    _asegurar_esquema_compras()
    sugerencias = {}
    requerimientos = {}

    producciones = Produccion.query.filter(Produccion.estado.in_(['Solicitada', 'En Proceso'])).all()

    for produccion in producciones:
        for detalle_prod in produccion.detalles:
            producto = detalle_prod.producto
            if not producto:
                continue

            filas, error = calcular_requerimientos_para_producto(producto, float(detalle_prod.cantidad or 0))
            if error:
                continue

            for fila in filas:
                materia = fila['materia']
                requerido = float(fila['requerido'])
                requerimientos[materia.id_materia] = requerimientos.get(materia.id_materia, 0.0) + requerido

    materias_requeridas_ids = list(requerimientos.keys())
    compras_pendientes_por_materia = {}

    if materias_requeridas_ids:
        pendientes = (
            db.session.query(
                DetalleCompra.id_materia,
                func.coalesce(func.sum(DetalleCompra.cantidad), 0)
            )
            .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
            .filter(
                Compra.estado.in_(['Solicitada', 'En Camino', 'En Proceso']),
                DetalleCompra.id_materia.in_(materias_requeridas_ids)
            )
            .group_by(DetalleCompra.id_materia)
            .all()
        )
        compras_pendientes_por_materia = {
            id_materia: float(total_pendiente or 0)
            for id_materia, total_pendiente in pendientes
        }

    for id_materia, requerido_total in requerimientos.items():
        materia = MateriaPrima.query.get(id_materia)
        if not materia:
            continue

        pendiente_compra = compras_pendientes_por_materia.get(id_materia, 0.0)
        faltante = round(max(0, requerido_total - materia.stock_actual - pendiente_compra), 2)
        if faltante > 0:
            sugerencias[id_materia] = {
                'id_materia': id_materia,
                'cantidad_sugerida': faltante,
            }

    if id_materia_prioritaria and id_materia_prioritaria not in sugerencias:
        materia_prioritaria = MateriaPrima.query.get(id_materia_prioritaria)
        if materia_prioritaria:
            faltante_minimo = max(0, materia_prioritaria.stock_minimo - materia_prioritaria.stock_actual)
            if faltante_minimo > 0:
                sugerencias[id_materia_prioritaria] = {
                    'id_materia': id_materia_prioritaria,
                    'cantidad_sugerida': round(faltante_minimo, 2),
                }

    return list(sugerencias.values())


def obtener_materias_alerta_stock_bajo(id_materia_prioritaria=None):
    _asegurar_esquema_compras()
    materias_alerta = (
        MateriaPrima.query
        .filter(MateriaPrima.stock_actual <= MateriaPrima.stock_minimo)
        .order_by(MateriaPrima.nombre.asc())
        .all()
    )

    sugerencias = []
    for materia in materias_alerta:
        faltante = max(0, materia.stock_minimo - materia.stock_actual)
        sugerencias.append({
            'id_materia': materia.id_materia,
            'cantidad_sugerida': faltante if faltante > 0 else 10,
        })

    if id_materia_prioritaria:
        for index, item in enumerate(sugerencias):
            if item['id_materia'] == id_materia_prioritaria:
                sugerencias.insert(0, sugerencias.pop(index))
                break

    return sugerencias


def aplicar_cambios_compra(compra, form, permitir_editar_cantidad=False):
    total = 0

    for detalle in compra.detalles:
        if permitir_editar_cantidad and not getattr(detalle, 'recibido', False):
            cantidad = form.get(f"cantidad_{detalle.id_detalle}")
            if cantidad not in (None, ""):
                cantidad_normalizada = str(cantidad).replace(',', '.').strip()
                cantidad_valor = float(cantidad_normalizada)
                if cantidad_valor <= 0:
                    raise ValueError(f"La cantidad debe ser mayor a cero en la línea {detalle.id_detalle}")
                detalle.cantidad = cantidad_valor

        precio = form.get(f"precio_{detalle.id_detalle}")

        if precio not in (None, ""):
            precio_normalizado = str(precio).replace(',', '.').strip()
            detalle.precio_u = float(precio_normalizado)

        detalle.subtotal = detalle.cantidad * detalle.precio_u

        if detalle.materia_prima:
            detalle.materia_prima.precio = detalle.precio_u

        total += detalle.subtotal

    compra.total = total

def obtener_compras():
    try:
        _asegurar_esquema_compras()
        result = db.session.execute(text("""
    SELECT 
        c.id_compra,
        c.fecha,
        c.fecha_entrega,
        c.estado,
        c.desde_produccion,
        u.username AS responsable,
        m.nombre AS nombre_materia,
        d.cantidad,
        d.recibido,
        m.stock_actual,
        m.stock_minimo,
        d.cantidad
    FROM compras c
    JOIN usuarios u ON c.id_usuario = u.id_usuario
    JOIN detalle_compra d ON c.id_compra = d.id_compra
    JOIN materias_primas m ON d.id_materia = m.id_materia
    WHERE c.estado IN ('Solicitada', 'En Proceso', 'Completada')
    ORDER BY c.fecha ASC
"""))

        compras_dict = {}

        for row in result.mappings():
            id_compra = row['id_compra']

            # Si la compra no existe, la creamos
            if id_compra not in compras_dict:
                compras_dict[id_compra] = {
                    'id_compra': id_compra,
                    'fecha': row['fecha'],
                    'fecha_entrega': row['fecha_entrega'],
                    'estado': row['estado'],
                    'desde_produccion': bool(row['desde_produccion']),
                    'responsable': row['responsable'],
                    'materias_primas': []
                    }
                
            if row['stock_actual'] < row['stock_minimo']:
                compras_dict[id_compra]['stock_suficiente'] = False

            # Agregamos materia prima a la compra
            compras_dict[id_compra]['materias_primas'].append({
                'nombre': row['nombre_materia'],
                'stock_actual': row['stock_actual'],
                'stock_minimo': row['stock_minimo'],
                'cantidad': row['cantidad'],
                'recibido': bool(row['recibido']),
            })

        compras = list(compras_dict.values())

        for compra in compras:
            estado = (compra.get('estado') or '').strip().lower()
            total_materias = len(compra.get('materias_primas') or [])
            materias_ok = sum(1 for m in compra.get('materias_primas') or [] if m.get('recibido'))
            avance_lineas = round((materias_ok / total_materias) * 100, 2) if total_materias > 0 else 0

            if estado in ('completada', 'completado'):
                progreso = 100
            elif estado == 'en camino':
                progreso = max(60, int(avance_lineas))
            elif estado == 'solicitada':
                progreso = max(20, min(55, int(avance_lineas)))
            else:
                progreso = int(avance_lineas)

            compra['progreso'] = progreso
            compra['avance_lineas'] = avance_lineas

        return compras, None

    except Exception as e:
        logger.error(f"Error al obtener compras: {str(e)}")
        return None, str(e)
    
def obtener_compra(id_compra):
    try:
        _asegurar_esquema_compras()
        compra = Compra.query.get(id_compra)

        if not compra:
            return None, "Compra no encontrada"

        lineas_totales = len(compra.detalles or [])
        lineas_recibidas = sum(1 for item in compra.detalles if getattr(item, 'recibido', False))
        porcentaje_entrega = round((lineas_recibidas / lineas_totales) * 100, 2) if lineas_totales > 0 else 0

        data = {
            "id": compra.id_compra,
            "fecha": compra.fecha,
            "fecha_entrega": compra.fecha_entrega,
            "estado": compra.estado,
            "id_proveedor": compra.id_proveedor,
            "metodo_pago": compra.metodo_pago,
            "tarjeta_titular": compra.tarjeta_titular,
            "tarjeta_ultimos4": compra.tarjeta_ultimos4,
            "tarjeta_vencimiento": compra.tarjeta_vencimiento,
            "total": compra.total,
            "lineas_totales": lineas_totales,
            "lineas_recibidas": lineas_recibidas,
            "porcentaje_entrega": porcentaje_entrega,
            "materias_primas": []
        }

        for d in compra.detalles:
            materia = d.materia_prima

            data["materias_primas"].append({
                "id_detalle": d.id_detalle,
                "id_materia": materia.id_materia,
                "nombre": materia.nombre,
                "cantidad": d.cantidad,
                "precio_unitario": d.precio_u,  # 🔥 CORRECTO
                "subtotal": d.subtotal,
                "stock_actual": materia.stock_actual,
                "recibido": getattr(d, 'recibido', False),
            })

        return data, None

    except Exception as e:
        return None, str(e)
        
def completar_compra(id_compra, form=None, permitir_editar_cantidad=False):
    try:
        _asegurar_esquema_compras()
        compra = Compra.query.get(id_compra)

        if not compra:
            return False, "Compra no encontrada"

        if compra.estado == "Completada":
            return False, "Ya fue completada"

        if form is not None:
            aplicar_cambios_compra(compra, form, permitir_editar_cantidad=permitir_editar_cantidad)

        lineas_pendientes = [d for d in compra.detalles if not getattr(d, 'recibido', False)]

        metodo_pago = _normalizar_metodo_pago(compra.metodo_pago)
        if not metodo_pago:
            return False, 'Selecciona un método de pago válido para completar la compra'

        if metodo_pago == 'Efectivo' and lineas_pendientes:
            caja_abierta = _obtener_caja_abierta()
            if not caja_abierta:
                return False, 'No hay caja abierta para registrar el egreso en efectivo'

            costo_pendiente = sum(float(item.subtotal or 0) for item in lineas_pendientes)
            efectivo_disponible = _calcular_efectivo_disponible(caja_abierta)
            if costo_pendiente > efectivo_disponible:
                return False, (
                    f'Efectivo insuficiente en caja. Disponible: ${efectivo_disponible:.2f}. '
                    'Ajusta cantidades o usa otro método de pago.'
                )

            db.session.add(MovimientoCaja(
                fecha=datetime.now(),
                tipo='Egreso',
                monto=costo_pendiente,
                descripcion=f'Compra #{compra.id_compra} - Completar compra',
                id_caja=caja_abierta.id_caja,
            ))

        for detalle in lineas_pendientes:
            materia = detalle.materia_prima
            if not materia:
                continue
            materia.stock_actual = float(materia.stock_actual or 0) + float(detalle.cantidad or 0)
            detalle.recibido = True

        compra.estado = "Completada"
        if not compra.fecha_entrega:
            compra.fecha_entrega = datetime.now()

        db.session.commit()

        return True, "Compra completada correctamente"

    except Exception as e:
        db.session.rollback()
        return False, str(e)


def recibir_detalle_compra(id_compra, id_detalle, form=None):
    try:
        _asegurar_esquema_compras()

        compra = Compra.query.get(id_compra)
        if not compra:
            return False, "Compra no encontrada"

        detalle = DetalleCompra.query.get(id_detalle)
        if not detalle or detalle.id_compra != compra.id_compra:
            return False, "La línea no pertenece a esta compra"

        if getattr(detalle, 'recibido', False):
            return True, "La línea ya fue recibida"

        cantidad_recibir = float(detalle.cantidad or 0)

        if form is not None:
            precio = form.get(f"precio_{detalle.id_detalle}")
            if precio not in (None, ""):
                precio_normalizado = str(precio).replace(',', '.').strip()
                detalle.precio_u = float(precio_normalizado)

            cantidad_form = form.get('cantidad_recibir')
            if cantidad_form not in (None, ''):
                cantidad_normalizada = str(cantidad_form).replace(',', '.').strip()
                cantidad_recibir = float(cantidad_normalizada)

        cantidad_original = float(detalle.cantidad or 0)
        if cantidad_recibir <= 0:
            return False, 'La cantidad a recibir debe ser mayor a cero'
        if cantidad_recibir > cantidad_original:
            return False, 'La cantidad a recibir no puede ser mayor a la solicitada'

        detalle.cantidad = cantidad_recibir
        detalle.subtotal = detalle.cantidad * detalle.precio_u

        metodo_pago = _normalizar_metodo_pago(compra.metodo_pago)
        if not metodo_pago:
            return False, 'Selecciona un método de pago válido antes de recibir la línea'

        if metodo_pago == 'Efectivo':
            caja_abierta = _obtener_caja_abierta()
            if not caja_abierta:
                return False, 'No hay caja abierta para registrar el egreso en efectivo'

            efectivo_disponible = _calcular_efectivo_disponible(caja_abierta)
            costo_linea = float(detalle.subtotal or 0)

            if costo_linea > efectivo_disponible:
                return False, (
                    f'Efectivo insuficiente en caja. Disponible: ${efectivo_disponible:.2f}. '
                    'Reduce la cantidad a comprar o usa otro método de pago.'
                )

            movimiento = MovimientoCaja(
                fecha=datetime.now(),
                tipo='Egreso',
                monto=costo_linea,
                descripcion=f'Compra #{compra.id_compra} - Línea #{detalle.id_detalle}',
                id_caja=caja_abierta.id_caja,
            )
            db.session.add(movimiento)

        if detalle.materia_prima:
            detalle.materia_prima.precio = detalle.precio_u

        materia = detalle.materia_prima
        materia.stock_actual += cantidad_recibir
        detalle.recibido = True

        if all(getattr(item, 'recibido', False) for item in compra.detalles):
            compra.estado = "Completada"
            if not compra.fecha_entrega:
                compra.fecha_entrega = datetime.now()
        else:
            compra.estado = "En Camino"

        compra.total = sum(float(item.subtotal or 0) for item in compra.detalles)
        db.session.commit()
        return True, 'La línea fue recibida y pagada correctamente'

    except Exception as e:
        db.session.rollback()
        return False, str(e)


def eliminar_solicitud_compra(id_compra):
    try:
        _asegurar_esquema_compras()
        compra = Compra.query.get(id_compra)

        if not compra:
            return False, 'Compra no encontrada'

        estado = (compra.estado or '').strip().lower()
        if estado in {'completada', 'completado'}:
            return False, 'No se puede eliminar una compra completada'

        if any(getattr(det, 'recibido', False) for det in (compra.detalles or [])):
            return False, 'No se puede eliminar porque ya hay líneas recibidas'

        db.session.delete(compra)
        db.session.commit()
        return True, 'Solicitud de compra eliminada correctamente'

    except Exception as e:
        db.session.rollback()
        return False, str(e)