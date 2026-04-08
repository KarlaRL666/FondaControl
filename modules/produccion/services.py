from models import db, Pedido, Produccion, Compra, DetalleCompra, Producto, DetalleProduccion
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import text, func
from utils.produccion_stock import calcular_requerimientos_para_producto
from utils.schema_guard import asegurar_columnas
import logging
import os
logger = logging.getLogger(__name__)


def _buscar_compra_pendiente_desde_produccion(ids_materias):
    if not ids_materias:
        return None

    compra_pendiente = (
        Compra.query
        .join(DetalleCompra, DetalleCompra.id_compra == Compra.id_compra)
        .filter(
            Compra.desde_produccion.is_(True),
            Compra.estado.in_(['Solicitada', 'En Camino', 'En Proceso']),
            DetalleCompra.id_materia.in_(ids_materias),
        )
        .order_by(Compra.fecha.desc())
        .first()
    )
    return compra_pendiente.id_compra if compra_pendiente else None


def _asegurar_esquema_produccion():
    asegurar_columnas(
        'detalle_produccion',
        [
            ('completado', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('cantidad_producida', 'DOUBLE NOT NULL DEFAULT 0'),
        ],
    )


def _porcentaje_progreso_produccion(produccion, avance_stock=None):
    estado = (produccion.estado or '').strip().lower()
    if estado == 'completada':
        return 100
    if estado == 'en proceso':
        return max(60, int(avance_stock or 0))
    if estado == 'solicitada':
        return max(20, min(55, int(avance_stock or 0)))
    return int(avance_stock or 0)


def _parse_fecha_requerida_compra(fecha_requerida):
    valor = (fecha_requerida or '').strip()
    if not valor:
        return None, 'Debes indicar fecha y hora requerida para la compra'

    formatos = ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d')
    fecha_dt = None
    for fmt in formatos:
        try:
            fecha_dt = datetime.strptime(valor, fmt)
            break
        except ValueError:
            continue

    if not fecha_dt:
        return None, 'Fecha requerida inválida para la compra'

    if fecha_dt < datetime.now():
        return None, 'La fecha requerida no puede ser anterior al momento actual'

    return fecha_dt, None


def _construir_requerimientos_produccion(produccion):
    requerimientos_por_materia = {}
    total_items = 0
    items_cubiertos = 0
    errores_producto = []

    for detalle in produccion.detalles:
        producto = detalle.producto
        cantidad_total = float(detalle.cantidad or 0)
        cantidad_producida = float(getattr(detalle, 'cantidad_producida', 0) or 0)
        cantidad_producir = max(0.0, cantidad_total - cantidad_producida)
        if not producto or cantidad_total <= 0:
            continue

        total_items += 1
        if cantidad_producir <= 0 or getattr(detalle, 'completado', False):
            items_cubiertos += 1
            continue

        filas, error = calcular_requerimientos_para_producto(producto, cantidad_producir)
        if error:
            nombre_producto = getattr(producto, 'nombre', f'Producto #{getattr(detalle, "id_producto", "N/D")}')
            errores_producto.append(f"{nombre_producto}: {error}")
            continue

        for fila in filas:
            materia = fila['materia']

            item = requerimientos_por_materia.setdefault(
                materia.id_materia,
                {
                    'materia': materia,
                    'requerido': 0.0,
                    'requerido_base': 0.0,
                    'stock_base': float(fila['stock_base']),
                }
            )
            item['requerido'] += float(fila['requerido'])
            item['requerido_base'] += float(fila['requerido_base'])

    avance_stock = round((items_cubiertos / total_items) * 100, 2) if total_items > 0 else 0.0
    return requerimientos_por_materia, avance_stock, errores_producto


def crear_solicitud_produccion_desde_alerta(id_producto, id_usuario, cantidad=10, fecha_necesaria=None, prioridad='Media'):
    try:
        _asegurar_esquema_produccion()
        producto = Producto.query.get(id_producto)

        if not producto:
            return None, "Producto no encontrado"

        cantidad = float(cantidad or 0)
        if cantidad <= 0:
            return None, "La cantidad a producir debe ser mayor a cero"

        fecha_necesaria_dt = None
        if fecha_necesaria:
            try:
                fecha_necesaria_dt = datetime.strptime(fecha_necesaria, '%Y-%m-%d')
            except ValueError:
                return None, "La fecha necesaria no es válida"

        if not fecha_necesaria_dt:
            fecha_necesaria_dt = datetime.now() + timedelta(days=3)

        prioridad = (prioridad or 'Media').strip().title()
        if prioridad not in {'Alta', 'Media', 'Baja'}:
            prioridad = 'Media'

        produccion = Produccion(
            fecha_solicitud=datetime.now(),
            fecha_necesaria=fecha_necesaria_dt,
            estado="Solicitada",
            id_usuario=id_usuario,
        )

        db.session.add(produccion)
        db.session.flush()

        db.session.add(DetalleProduccion(
            id_produccion=produccion.id_produccion,
            id_producto=producto.id_producto,
            id_materia=None,
            cantidad=cantidad
        ))

        mongo_db = getattr(current_app, 'mongo', None)
        if mongo_db is not None:
            mongo_db.produccion_meta.update_one(
                {'id_produccion': produccion.id_produccion},
                {
                    '$set': {
                        'id_produccion': produccion.id_produccion,
                        'id_producto': producto.id_producto,
                        'prioridad': prioridad,
                        'fecha_necesaria': fecha_necesaria_dt,
                        'fecha_actualizacion': datetime.utcnow(),
                    }
                },
                upsert=True,
            )

        db.session.commit()
        return produccion.id_produccion, f"Solicitud de producción creada para {producto.nombre} con {cantidad:g} unidades (prioridad {prioridad})"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear solicitud de producción desde alerta: {str(e)}")
        return None, str(e)


def procesar_detalle_produccion(id_produccion, id_detalle, id_usuario, fecha_requerida_compra=None, cantidad_producir=None):
    try:
        _asegurar_esquema_produccion()

        produccion = Produccion.query.get(id_produccion)
        if not produccion:
            return False, "Producción no encontrada", None

        detalle = DetalleProduccion.query.get(id_detalle)
        if not detalle or detalle.id_produccion != produccion.id_produccion:
            return False, "La línea de producción no pertenece a esta orden", None

        cantidad_total = float(detalle.cantidad or 0)
        cantidad_producida_actual = float(getattr(detalle, 'cantidad_producida', 0) or 0)
        cantidad_restante = round(max(0.0, cantidad_total - cantidad_producida_actual), 2)

        if cantidad_restante <= 0 or getattr(detalle, 'completado', False):
            detalle.completado = True
            db.session.commit()
            return True, "La línea ya estaba completada", None

        producto = detalle.producto
        if not producto:
            return False, "Producto no encontrado", None

        try:
            veces_producir = int(cantidad_producir or 1)
        except (TypeError, ValueError):
            return False, "La cantidad a producir debe ser un número entero (veces a producir la receta)", None

        if veces_producir <= 0:
            return False, "Debes producir al menos 1 vez la receta", None

        # Calcular cantidad real basada en la receta
        cantidad_por_receta = 1.0
        receta = producto.recetas[0] if getattr(producto, 'recetas', None) else None
        if receta:
            cantidad_por_receta = float(receta.cantidad_produccion or 1)
        
        cantidad_producir_real = veces_producir * cantidad_por_receta

        if cantidad_producir_real > cantidad_restante:
            return False, f"No puedes producir {veces_producir} veces la receta ({cantidad_producir_real} unidades). Máximo {int(cantidad_restante / cantidad_por_receta)} veces.", None

        filas, error_req = calcular_requerimientos_para_producto(producto, cantidad_producir_real)
        if error_req:
            return False, error_req, None

        faltantes = []
        for fila in filas:
            materia = fila['materia']
            requerido = float(fila['requerido'])
            stock_actual = float(materia.stock_actual or 0)
            if stock_actual < requerido:
                faltantes.append({
                    'materia': materia,
                    'faltante': round(requerido - stock_actual, 2),
                })

        if faltantes:
            ids_materias_faltantes = [item['materia'].id_materia for item in faltantes]
            compra_pendiente_id = _buscar_compra_pendiente_desde_produccion(ids_materias_faltantes)
            if compra_pendiente_id:
                return False, 'Ya existe una solicitud de compra pendiente para esta producción', compra_pendiente_id

            fecha_entrega, error_fecha = _parse_fecha_requerida_compra(fecha_requerida_compra)
            if error_fecha:
                return False, error_fecha, None

            compra = Compra(
                fecha=datetime.now(),
                total=0,
                fecha_entrega=fecha_entrega,
                desde_produccion=True,
                id_proveedor=None,
                id_usuario=id_usuario,
                estado='Solicitada',
            )
            db.session.add(compra)
            db.session.flush()

            total_compra = 0
            for item in faltantes:
                materia = item['materia']
                cantidad_compra = round(float(item['faltante']), 2)
                subtotal = float(materia.precio or 0) * cantidad_compra
                total_compra += subtotal

                db.session.add(DetalleCompra(
                    id_compra=compra.id_compra,
                    id_materia=materia.id_materia,
                    cantidad=cantidad_compra,
                    precio_u=materia.precio,
                    subtotal=subtotal,
                ))

            compra.total = total_compra
            produccion.estado = 'En Proceso'
            db.session.commit()
            return True, f'Se generó una solicitud de compra para {veces_producir} veces de la receta ({cantidad_producir_real} unidades)', compra.id_compra

        for fila in filas:
            materia = fila['materia']
            materia.stock_actual = float(materia.stock_actual or 0) - float(fila['requerido'])

        producto.stock_actual = float(producto.stock_actual or 0) + float(cantidad_producir_real)
        detalle.cantidad_producida = round(cantidad_producida_actual + cantidad_producir_real, 2)

        if detalle.cantidad_producida >= (cantidad_total - 0.0001):
            detalle.cantidad_producida = cantidad_total
            detalle.completado = True

        if all(getattr(item, 'completado', False) for item in produccion.detalles):
            produccion.estado = 'Completada'
            produccion.fecha_completada = datetime.now()
            if produccion.pedido:
                produccion.pedido.estado = 'Producido'
        else:
            produccion.estado = 'En Proceso'

        db.session.commit()
        if detalle.completado:
            return True, f'La línea de {producto.nombre} se completó correctamente', None

        restante = round(max(0.0, cantidad_total - float(detalle.cantidad_producida or 0)), 2)
        return True, f'Se registró producción de {producto.nombre}. Producido: +{cantidad_producir_real}. Restante: {restante}', None

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al procesar detalle de producción: {str(e)}")
        return False, str(e), None

def obtener_producciones():
    try:
        _asegurar_esquema_produccion()
        producciones = []

        rows = Produccion.query.order_by(Produccion.fecha_necesaria.asc()).all()
        for row in rows:
            fecha_necesaria = row.fecha_necesaria

            dias_restantes = None
            if fecha_necesaria:
                dias_restantes = (fecha_necesaria - datetime.now()).days

            _, avance_stock, _ = _construir_requerimientos_produccion(row)
            progreso = _porcentaje_progreso_produccion(row, avance_stock)

            producciones.append({
                'id_produccion': row.id_produccion,
                'estado': row.estado,
                'fecha_solicitud': row.fecha_solicitud,
                'fecha_completada': row.fecha_completada,
                'fecha_necesaria': fecha_necesaria,
                'usuario': row.usuario.username if row.usuario else 'N/D',
                'dias_restantes': dias_restantes,
                'progreso': progreso,
                'avance_stock': avance_stock,
            })

        return producciones, None

    except Exception as e:
        logger.error(f"Error al obtener producciones: {str(e)}")
        return None, str(e)
    
def completar_o_solicitar_compra(id_produccion, id_usuario, fecha_requerida_compra=None):
    try:
        _asegurar_esquema_produccion()
        prod = Produccion.query.get(id_produccion)

        if not prod:
            return False, "Producción no encontrada", None

        requerimientos_por_materia, _, errores_requerimientos = _construir_requerimientos_produccion(prod)

        if errores_requerimientos:
            return False, "No se puede producir: faltan ingredientes configurados en la receta del producto.", None

        compras_pendientes_por_materia = {}
        ids_materias_requeridas = list(requerimientos_por_materia.keys())

        if ids_materias_requeridas:
            pendientes = (
                db.session.query(
                    DetalleCompra.id_materia,
                    func.coalesce(func.sum(DetalleCompra.cantidad), 0)
                )
                .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
                .filter(
                    Compra.estado.in_(['Solicitada', 'En Camino', 'En Proceso']),
                    DetalleCompra.id_materia.in_(ids_materias_requeridas)
                )
                .group_by(DetalleCompra.id_materia)
                .all()
            )
            compras_pendientes_por_materia = {
                id_materia: float(total_pendiente or 0)
                for id_materia, total_pendiente in pendientes
            }

        faltantes_global = []
        for id_materia, item in requerimientos_por_materia.items():
            pendiente_compra = compras_pendientes_por_materia.get(id_materia, 0.0)
            stock_actual = float(item['materia'].stock_actual or 0)
            faltante = round(max(0.0, item["requerido"] - stock_actual - pendiente_compra), 2)
            if faltante > 0:
                faltantes_global.append({
                    "materia": item["materia"],
                    "faltante": faltante,
                    "stock_actual": stock_actual,
                    "requerido": item["requerido"],
                    "pendiente_compra": pendiente_compra,
                })
            
        # determinar si se completa o se solicita compra
        if faltantes_global:
            ids_materias_faltantes = [item['materia'].id_materia for item in faltantes_global]
            compra_pendiente_id = _buscar_compra_pendiente_desde_produccion(ids_materias_faltantes)
            if compra_pendiente_id:
                return False, 'Ya existe una solicitud de compra pendiente para esta producción', compra_pendiente_id

            fecha_entrega, error_fecha = _parse_fecha_requerida_compra(fecha_requerida_compra)
            if error_fecha:
                return False, error_fecha, None
                        
            # generar solicitud de compra
            nueva_compra = Compra(
                fecha=datetime.now(),
                total=0,
                fecha_entrega=fecha_entrega,
                desde_produccion=True,
                id_proveedor=None,
                id_usuario=id_usuario
            )

            db.session.add(nueva_compra)
            db.session.flush()

            total_compra = 0

            for f in faltantes_global:
                materia = f['materia']
                faltante = round(float(f['faltante']), 2)

                subtotal = materia.precio * faltante
                total_compra += subtotal

                detalle_compra = DetalleCompra(
                    id_compra=nueva_compra.id_compra,
                    id_materia=materia.id_materia,
                    cantidad=faltante,
                    precio_u=materia.precio,
                    subtotal=subtotal
                )
                db.session.add(detalle_compra)

            nueva_compra.total = total_compra

            prod.estado = "En Proceso"
            db.session.commit()
            
            logger.info(f"Compra generada con {len(faltantes_global)} materias faltantes para producción {id_produccion}")
            return False, "Faltan ingredientes. Se generó solicitud de compra con las cantidades solicitadas.", nueva_compra.id_compra
            
        # si no hay faltantes, se descuenta materia prima y se completa
        for item in requerimientos_por_materia.values():
            materia = item['materia']
            materia.stock_actual = float(materia.stock_actual or 0) - float(item['requerido'])

        for detalle in prod.detalles:
            if getattr(detalle, 'completado', False):
                continue
            producto = detalle.producto
            if not producto:
                continue
            producto.stock_actual = float(producto.stock_actual or 0) + float(detalle.cantidad or 0)
            detalle.completado = True

        prod.estado = "Completada"
        prod.fecha_completada = datetime.now()
        
        if prod.pedido:
            prod.pedido.estado = "Producido"
        
        db.session.commit()
        return True, "Producción completada y stock actualizado", None

    except Exception as e:
        db.session.rollback()
        return False, str(e), None
    
def ver_orden_produccion(id_produccion):
    try:
        _asegurar_esquema_produccion()
        prod = Produccion.query.get(id_produccion)

        if not prod:
            return None, "Producción no encontrada"

        filas = []
        materias_con_faltante = set()

        for detalle in prod.detalles:
            producto = detalle.producto
            cantidad = float(detalle.cantidad or 0)
            cantidad_producida = round(float(getattr(detalle, 'cantidad_producida', 0) or 0), 2)
            cantidad_restante = round(max(0.0, cantidad - cantidad_producida), 2)

            # Calcular cantidad por receta (cuánto produce UNA receta)
            cantidad_por_receta = 1.0
            veces_restantes = 1
            receta = producto.recetas[0] if (producto and getattr(producto, 'recetas', None)) else None
            if receta:
                cantidad_por_receta = float(receta.cantidad_produccion or 1)
                veces_restantes = max(0, int(cantidad_restante / cantidad_por_receta)) if cantidad_por_receta > 0 else 0

            cantidad_para_requerimiento = cantidad_restante if cantidad_restante > 0 else cantidad
            filas_req, error_req = calcular_requerimientos_para_producto(producto, cantidad_para_requerimiento)
            if error_req:
                filas_req = []

            completado = bool(getattr(detalle, 'completado', False) or cantidad_restante <= 0)
            ingredientes = []
            for fila in filas_req:
                materia = fila['materia']
                faltante = False if completado else float(fila['faltante']) > 0
                if faltante:
                    materias_con_faltante.add(materia.id_materia)
                ingredientes.append({
                    "nombre": materia.nombre,
                    "requerido": round(float(fila['requerido']), 2),
                    "stock": round(float(materia.stock_actual or 0), 2),
                    "unidad": materia.unidad_medida,
                    "faltante": faltante,
                })

            progreso_fila = 100 if cantidad <= 0 else round((cantidad_producida / cantidad) * 100, 2)
            progreso_fila = max(0, min(100, progreso_fila))
            total_ing = len(ingredientes)
            sin_ingredientes = total_ing == 0
            faltantes = sum(1 for i in ingredientes if i['faltante'])
                
            filas.append({
                "id_detalle": detalle.id_detalle,
                "producto": producto.nombre if producto else f"Producto #{detalle.id_producto}",
                "cantidad": cantidad,
                "cantidad_producida": cantidad_producida,
                "cantidad_restante": cantidad_restante,
                "cantidad_por_receta": round(cantidad_por_receta, 2),
                "veces_restantes": veces_restantes,
                "ingredientes": ingredientes,
                "completado": completado,
                "sin_ingredientes": sin_ingredientes,
                "puede_completar": not completado and not sin_ingredientes and faltantes == 0,
                "progreso": progreso_fila,
            })
            

        data = {
            "id_produccion": prod.id_produccion,
            "fecha": prod.fecha_solicitud,
            "fecha_solicitud": prod.fecha_solicitud,
            "fecha_completada": prod.fecha_completada,
            "fecha_necesaria": prod.fecha_necesaria,
            "estado": prod.estado,
            "filas": filas,
            "compra_pendiente_id": _buscar_compra_pendiente_desde_produccion(list(materias_con_faltante)),
        }

        data['progreso'] = round(sum(f['progreso'] for f in filas) / len(filas), 2) if filas else 0

        return data, None

    except Exception as e:
        return None, str(e)
    
def validar_materia_prima_produccion(detalle):
    _asegurar_esquema_produccion()
    if getattr(detalle, 'completado', False):
        return []

    faltantes = []

    cantidad_total = float(detalle.cantidad or 0)
    cantidad_producida = float(getattr(detalle, 'cantidad_producida', 0) or 0)
    cantidad_restante = max(0.0, cantidad_total - cantidad_producida)

    if cantidad_restante <= 0:
        return []

    filas, error = calcular_requerimientos_para_producto(detalle.producto, cantidad_restante)
    if error:
        return []

    for fila in filas:
        materia = fila['materia']
        requerido = float(fila['requerido'])
        if float(fila['faltante']) > 0:
            faltantes.append({
                "materia": materia,
                "faltante": float(fila['faltante']),
                "stock_actual": float(materia.stock_actual or 0),
                "requerido": requerido
            })

    return faltantes


def eliminar_solicitud_produccion(id_produccion):
    try:
        _asegurar_esquema_produccion()
        prod = Produccion.query.get(id_produccion)

        if not prod:
            return False, 'Producción no encontrada'

        if (prod.estado or '').strip().lower() == 'completada':
            return False, 'No se puede eliminar una producción completada'

        pedido = prod.pedido
        if pedido:
            for detalle in (pedido.detalles or []):
                if getattr(detalle, 'atendido', False):
                    continue
                detalle.en_produccion = False

            pendientes = any(not getattr(d, 'atendido', False) for d in (pedido.detalles or []))
            pedido.requiere_produccion = False
            if pendientes and (pedido.estado or '').strip().lower() != 'completado':
                pedido.estado = 'Pendiente'

        db.session.delete(prod)
        db.session.commit()
        return True, 'Solicitud de producción eliminada correctamente'

    except Exception as e:
        db.session.rollback()
        return False, str(e)
