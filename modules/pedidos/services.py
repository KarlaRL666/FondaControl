from models import db, Pedido, DetallePedido, Produccion, Producto, DetalleProduccion, PedidoMeta, Cliente, Persona, Usuario, Rol
from flask import current_app
from sqlalchemy import text
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.security import generate_password_hash
from utils.schema_guard import asegurar_columnas
from utils.caja_movimientos import registrar_ingreso_caja
import uuid
import re
import logging

logger = logging.getLogger(__name__)


def _asegurar_meta_pago_pedido(pedido, id_usuario, metodo_pago=None, datos_tarjeta=None):
    metodo = (metodo_pago or '').strip()
    if metodo not in ('Efectivo', 'Tarjeta', 'Transferencia'):
        metodo = 'Efectivo'

    tarjeta_titular = None
    tarjeta_ultimos4 = None
    tarjeta_vencimiento = None

    if metodo == 'Tarjeta':
        datos_tarjeta = datos_tarjeta or {}
        numero_tarjeta = datos_tarjeta.get('numero_tarjeta')
        titular_tarjeta = datos_tarjeta.get('titular_tarjeta')
        vencimiento_tarjeta = datos_tarjeta.get('vencimiento_tarjeta')
        cvv_tarjeta = datos_tarjeta.get('cvv_tarjeta')

        valido, error = _validar_datos_tarjeta(
            numero_tarjeta,
            titular_tarjeta,
            vencimiento_tarjeta,
            cvv_tarjeta,
        )
        if not valido:
            return False, error

        numero_limpio = re.sub(r'\s+', '', (numero_tarjeta or '').strip())
        tarjeta_titular = (titular_tarjeta or '').strip()
        tarjeta_ultimos4 = numero_limpio[-4:] if len(numero_limpio) >= 4 else None
        tarjeta_vencimiento = (vencimiento_tarjeta or '').strip()

    meta = PedidoMeta.query.get(pedido.id_pedido)
    if not meta:
        meta = PedidoMeta(
            id_pedido=pedido.id_pedido,
            metodo_pago=metodo,
            id_usuario=id_usuario,
        )
        db.session.add(meta)
    else:
        if not (meta.metodo_pago or '').strip():
            meta.metodo_pago = metodo
        elif metodo_pago and metodo in ('Efectivo', 'Tarjeta', 'Transferencia'):
            meta.metodo_pago = metodo

        meta.id_usuario = id_usuario

    if metodo == 'Tarjeta':
        meta.tarjeta_titular = tarjeta_titular
        meta.tarjeta_ultimos4 = tarjeta_ultimos4
        meta.tarjeta_vencimiento = tarjeta_vencimiento
    else:
        meta.tarjeta_titular = None
        meta.tarjeta_ultimos4 = None
        meta.tarjeta_vencimiento = None

    return True, None


def _parse_fecha_necesaria(fecha_necesaria):
    valor = (fecha_necesaria or '').strip()
    if not valor:
        return None, 'Debes indicar fecha y hora requerida para producción'

    formatos = ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d')
    fecha_dt = None
    for fmt in formatos:
        try:
            fecha_dt = datetime.strptime(valor, fmt)
            break
        except ValueError:
            continue

    if not fecha_dt:
        return None, 'Fecha y hora de producción inválida'

    if fecha_dt.date() < datetime.now().date():
        return None, 'La fecha requerida no puede ser menor a hoy'

    return fecha_dt, None


def _asegurar_esquema_pedidos():
    asegurar_columnas(
        'detalle_pedido',
        [
            ('atendido', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('en_produccion', 'BOOLEAN NOT NULL DEFAULT 0'),
        ],
    )


def _validar_datos_tarjeta(numero, titular, vencimiento, cvv):
    numero_limpio = re.sub(r'\s+', '', (numero or '').strip())
    titular = (titular or '').strip()
    vencimiento = (vencimiento or '').strip()
    cvv = (cvv or '').strip()

    if not re.fullmatch(r'\d{13,19}', numero_limpio):
        return False, "Número de tarjeta inválido"

    if len(titular) < 3:
        return False, "Ingresa el nombre del titular"

    if not re.fullmatch(r'(0[1-9]|1[0-2])/\d{2}', vencimiento):
        return False, "Fecha de vencimiento inválida (MM/AA)"

    mes, anio = vencimiento.split('/')
    mes = int(mes)
    anio = 2000 + int(anio)
    hoy = datetime.utcnow()

    if (anio < hoy.year) or (anio == hoy.year and mes < hoy.month):
        return False, "La tarjeta está vencida"

    if not re.fullmatch(r'\d{3,4}', cvv):
        return False, "CVV inválido"

    return True, None


def _obtener_o_crear_cliente_sucursal():
    cliente_sucursal = (
        Cliente.query
        .join(Persona, Persona.id_persona == Cliente.id_persona)
        .filter(func.lower(Persona.nombre) == 'venta en sucursal')
        .first()
    )

    if cliente_sucursal:
        return cliente_sucursal, None

    rol_cliente = Rol.query.filter(func.lower(Rol.nombre) == 'cliente').first()
    if not rol_cliente:
        return None, "No existe el rol Cliente configurado"

    ts = datetime.utcnow().strftime('%H%M%S%f')
    telefono = ts[-10:]

    persona = Persona(
        nombre='Venta en sucursal',
        apellido_p='Mostrador',
        apellido_m='',
        telefono=telefono,
        correo=f"venta.sucursal.{ts}@local.com",
        direccion='Sucursal'
    )
    db.session.add(persona)
    db.session.flush()

    usuario = Usuario(
        username=f"venta_sucursal_{ts}",
        contrasena=generate_password_hash(uuid.uuid4().hex),
        estado=True,
        fs_uniquifier=str(uuid.uuid4()),
        id_rol=rol_cliente.id_rol,
    )
    db.session.add(usuario)
    db.session.flush()

    cliente = Cliente(
        id_usuario=usuario.id_usuario,
        id_persona=persona.id_persona,
    )
    db.session.add(cliente)
    db.session.flush()

    return cliente, None


def crear_pedido_manual(id_cliente, productos, metodo_pago, id_usuario, datos_tarjeta=None, fecha_necesaria=None):
    try:
        _asegurar_esquema_pedidos()
        if not id_cliente:
            cliente_sucursal, error_cliente = _obtener_o_crear_cliente_sucursal()
            if error_cliente:
                return False, error_cliente
            id_cliente = cliente_sucursal.id_cliente

        if not productos:
            return False, "Debes agregar al menos un producto"

        detalles = []
        total = 0

        for item in productos:
            id_producto = item.get('id_producto')
            cantidad = item.get('cantidad')

            if not id_producto or not cantidad:
                return False, "Cada renglón debe tener producto y cantidad"

            try:
                id_producto = int(id_producto)
                cantidad = int(cantidad)
            except (TypeError, ValueError):
                return False, "Los datos del pedido son inválidos"

            if cantidad <= 0:
                return False, "La cantidad debe ser mayor a cero"

            producto = Producto.query.get(id_producto)
            if not producto or not producto.estado:
                return False, f"Producto inválido: {id_producto}"

            subtotal = float(producto.precio) * cantidad
            total += subtotal

            detalles.append({
                'id_producto': id_producto,
                'cantidad': cantidad,
                'subtotal': subtotal
            })

        requeridos_por_producto = {}
        for d in detalles:
            requeridos_por_producto[d['id_producto']] = requeridos_por_producto.get(d['id_producto'], 0) + d['cantidad']

        faltantes = {}
        for id_producto, cantidad_total in requeridos_por_producto.items():
            producto = Producto.query.get(id_producto)
            stock_actual = int(producto.stock_actual or 0)
            if stock_actual < cantidad_total:
                faltantes[id_producto] = cantidad_total - stock_actual

        requiere_produccion = bool(faltantes)

        fecha_necesaria_dt = None
        if requiere_produccion:
            fecha_necesaria_dt, error_fecha = _parse_fecha_necesaria(fecha_necesaria)
            if error_fecha:
                return False, error_fecha

        pedido = Pedido(
            id_cliente=int(id_cliente),
            total=total,
            fecha=datetime.utcnow(),
            fecha_entrega=None,
            estado='En Proceso' if requiere_produccion else 'Pendiente',
            requiere_produccion=requiere_produccion,
        )

        db.session.add(pedido)
        db.session.flush()

        for d in detalles:
            db.session.add(DetallePedido(
                id_pedido=pedido.id_pedido,
                id_producto=d['id_producto'],
                cantidad=d['cantidad'],
                subtotal=d['subtotal'],
                en_produccion=d['id_producto'] in faltantes,
            ))

        if requiere_produccion:
            produccion = Produccion(
                fecha_solicitud=datetime.now(),
                estado='Solicitada',
                fecha_necesaria=fecha_necesaria_dt,
                id_usuario=id_usuario,
                id_pedido=pedido.id_pedido,
            )
            db.session.add(produccion)
            db.session.flush()

            for id_producto, cantidad_faltante in faltantes.items():
                db.session.add(DetalleProduccion(
                    id_produccion=produccion.id_produccion,
                    id_producto=id_producto,
                    id_materia=None,
                    cantidad=float(cantidad_faltante),
                ))

        db.session.commit()
        if requiere_produccion:
            return True, 'Pedido creado y enviado directamente a producción'
        return True, 'Pedido creado correctamente'

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear pedido manual: {str(e)}")
        return False, str(e)

def obtener_pedidos():
    try:
        _asegurar_esquema_pedidos()
        result = db.session.execute(text("""
    SELECT
        p.id_pedido,
        p.fecha,
        p.fecha_entrega,
        p.estado,
        pe.nombre AS cliente_nombre,
        pm.metodo_pago,
        ru.username AS usuario_responsable,
        pr.nombre AS nombre_producto,
        pr.stock_actual,
        d.cantidad,
        d.atendido,
        d.en_produccion
    FROM pedidos p
    LEFT JOIN clientes c ON c.id_cliente = p.id_cliente
    LEFT JOIN personas pe ON pe.id_persona = c.id_persona
    LEFT JOIN pedidos_meta pm ON pm.id_pedido = p.id_pedido
    LEFT JOIN usuarios ru ON ru.id_usuario = pm.id_usuario
    JOIN detalle_pedido d ON p.id_pedido = d.id_pedido
    JOIN productos pr ON d.id_producto = pr.id_producto
    WHERE p.estado IN ('Pendiente', 'En Proceso', 'Completado', 'Producido', 'Pagado')
    ORDER BY p.fecha ASC
"""))

        pedidos_dict = {}

        for row in result.mappings():
            id_pedido = row['id_pedido']

            # Si el pedido no existe, lo creamos
            if id_pedido not in pedidos_dict:
                es_sucursal = (row['cliente_nombre'] or '').strip().lower() == 'venta en sucursal'
                estado_row = row['estado'] or 'Pendiente'
                estado_row_lower = str(estado_row).strip().lower()
                pedidos_dict[id_pedido] = {
                    'id_pedido': id_pedido,
                    'fecha': row['fecha'],
                    'fecha_entrega': row['fecha_entrega'],
                    'estado': estado_row,
                    'estado_pago': 'Pagado' if estado_row_lower == 'pagado' else 'Pendiente de pago',
                    'estado_mostrado': 'Pagado' if estado_row_lower == 'pagado' else estado_row,
                    'tipo_venta': 'sucursal' if es_sucursal else 'en_linea',
                    'metodo_pago': row['metodo_pago'] or 'N/D',
                    'usuario_responsable': row['usuario_responsable'] or 'N/D',
                    'productos': [], 
                    'stock_suficiente': True
                }
                
            if row['stock_actual'] < row['cantidad']:
                pedidos_dict[id_pedido]['stock_suficiente'] = False

            # Agregamos producto al pedido
            pedidos_dict[id_pedido]['productos'].append({
                'nombre': row['nombre_producto'],
                'stock_actual': row['stock_actual'],
                'cantidad': row['cantidad'],
                'atendido': bool(row['atendido']),
                'en_produccion': bool(row['en_produccion']),
            })

        pedidos = list(pedidos_dict.values())

        for pedido in pedidos:
            estado = (pedido.get('estado') or '').strip().lower()
            pedido_pagado = estado == 'pagado'
            pedido['estado_pago'] = 'Pagado' if pedido_pagado else 'Pendiente de pago'
            pedido['estado_mostrado'] = 'Pagado' if pedido_pagado else pedido.get('estado')
            total_productos = len(pedido.get('productos') or [])
            productos_cubiertos = sum(
                1 for p in pedido.get('productos') or []
                if p.get('atendido') or p.get('en_produccion')
            )
            avance_lineas = round((productos_cubiertos / total_productos) * 100, 2) if total_productos > 0 else 0

            if estado in ('completado', 'pagado'):
                progreso = 100
            elif estado == 'producido':
                progreso = 90
            elif estado == 'en proceso':
                progreso = max(60, int(avance_lineas))
            elif estado == 'pendiente':
                progreso = max(25, min(55, int(avance_lineas)))
            else:
                progreso = int(avance_lineas)

            pedido['progreso'] = progreso
            pedido['avance_lineas'] = avance_lineas

        return pedidos, None

    except Exception as e:
        logger.error(f"Error al obtener pedidos: {str(e)}")
        return None, str(e)
    
def obtener_pedido(id_cliente):
    try:
        _asegurar_esquema_pedidos()
        logger.info(f"Obteniendo pedidos para cliente: {id_cliente}")
        
        if not id_cliente:
            logger.warning("ID de cliente no proporcionado")
            return None, "ID de cliente no proporcionado."
        
        pedidos = Pedido.query.filter_by(id_cliente=id_cliente).order_by(Pedido.fecha.desc()).all()
        
        resultado = []
        for p in pedidos:
            # Calcular total real sumando subtotales de los detalles
            detalles = p.detalles or []
            total_real = sum(float(getattr(d, 'subtotal', 0) or 0) for d in detalles)
            fecha_estimada = p.fecha + timedelta(days=3) if p.fecha else None
            fecha_requerida = p.fecha_entrega or None
            total_detalles = len(detalles)
            cubiertos = sum(1 for d in detalles if getattr(d, 'atendido', False) or getattr(d, 'en_produccion', False))
            avance_lineas = round((cubiertos / total_detalles) * 100, 2) if total_detalles > 0 else 0

            estado = (p.estado or '').strip().lower()
            pago_capturado = estado == 'pagado'
            if estado in ('completado', 'pagado'):
                progreso = 100
            elif estado == 'producido':
                progreso = 90
            elif estado == 'en proceso':
                # Nunca mostrar 100% en proceso, máximo 95
                progreso = min(95, max(60, int(avance_lineas)))
            elif estado == 'pendiente':
                progreso = max(25, min(55, int(avance_lineas)))
            elif estado == 'cancelado':
                progreso = 0
            else:
                progreso = int(avance_lineas)

            resultado.append({
                'id': p.id_pedido,
                'fecha': p.fecha,
                'fecha_estimada': fecha_estimada,
                'fecha_entrega': p.fecha_entrega,
                'fecha_requerida': fecha_requerida,
                'total': total_real,
                'requiere_produccion': p.requiere_produccion,
                'estado': p.estado,
                'estado_pago': 'Pagado' if pago_capturado else 'Pendiente de pago',
                'estado_mostrado': 'Pagado' if pago_capturado else p.estado,
                'metodo_pago': p.meta_pedido.metodo_pago if p.meta_pedido else 'N/D',
                'usuario_responsable': p.meta_pedido.usuario.username if p.meta_pedido and p.meta_pedido.usuario else 'N/D',
                'progreso': progreso,
                # Pre-format the dates for the template (safest approach)
                'fecha_str': p.fecha.strftime('%d/%m/%Y') if p.fecha else '',
                'fecha_entrega_str': p.fecha_entrega.strftime('%d/%m/%Y') if p.fecha_entrega else '',
                'fecha_estimada_str': fecha_estimada.strftime('%d/%m/%Y') if fecha_estimada else '',
                'fecha_requerida_str': fecha_requerida.strftime('%d/%m/%Y %H:%M') if fecha_requerida else ''
            })
        
        logger.info(f"Pedidos obtenidos: {len(resultado)} para cliente: {id_cliente}")
        return resultado, None
        
    except Exception as e:
        logger.error(f"Error al obtener pedidos: {str(e)}")
        return None, str(e)
    
def obtener_detalles_pedido(id_pedido):
    try:
        _asegurar_esquema_pedidos()
        logger.info(f"Obteniendo detalles para pedido: {id_pedido}")
        detalles = DetallePedido.query.filter_by(id_pedido=id_pedido).all()
        resultado = []
        for d in detalles:
            resultado.append({
                'id': d.id_detalle,
                'id_pedido': d.id_pedido,
                'id_producto': d.id_producto,
                'cantidad': d.cantidad
            })
        logger.info(f"Detalles obtenidos para pedido {id_pedido}: {len(resultado)}")
        return resultado, None
    except Exception as e:
        logger.error(f"Error al obtener detalles del pedido: {str(e)}")
        return None, str(e)
        
def completar_pedido(id_pedido):
    try:
        _asegurar_esquema_pedidos()
        pedido = Pedido.query.get(id_pedido)
        if not pedido:
            return False, "Pedido no encontrado"

        for detalle in pedido.detalles:
            if getattr(detalle, 'atendido', False):
                continue

            producto = detalle.producto
            if not producto:
                continue
            stock_requerido = float(detalle.cantidad or 0)
            if float(producto.stock_actual or 0) < stock_requerido:
                return False, f"Stock insuficiente para el producto '{producto.nombre}'"

        for detalle in pedido.detalles:
            if getattr(detalle, 'atendido', False):
                continue

            producto = detalle.producto
            if not producto:
                continue
            producto.stock_actual -= float(detalle.cantidad or 0)
            detalle.atendido = True
            detalle.en_produccion = False

        pedido.estado = "Completado"
        pedido.fecha_entrega = datetime.now()
        pedido.requiere_produccion = False

        db.session.commit()
        return True, "Pedido completado"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def cancelar_pedido(id_pedido):
    try:
        pedido = Pedido.query.get(id_pedido)
        
        if not pedido:
            return False, "Pedido no encontrado"
        
        estado = (pedido.estado or "").strip().lower()

        if estado == "completado":
            return False, "No se puede cancelar un pedido completado"
        elif estado == "cancelado":
            return False, "El pedido ya está cancelado"
        elif estado in ("en proceso", "producido"):
            return False, "No se puede cancelar un pedido en proceso"
        elif estado not in ("pendiente", "solicitado"):
            return False, "Solo se pueden cancelar pedidos solicitados"
        
        pedido.estado = "Cancelado"
        
        db.session.commit()
        return True, "Pedido cancelado con éxito"
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def editar_pedido_propio(id_pedido, id_cliente, productos, metodo_pago, id_usuario):
    try:
        pedido = Pedido.query.get(id_pedido)

        if not pedido:
            return False, "Pedido no encontrado"

        if pedido.id_cliente != id_cliente:
            return False, "No tienes permiso para editar este pedido"

        if pedido.estado != 'Pendiente':
            return False, "Solo puedes editar pedidos pendientes"

        detalles = []
        total = 0

        for item in productos:
            id_producto = item.get('id_producto')
            cantidad = item.get('cantidad')

            if not id_producto or not cantidad:
                return False, "Cada renglón debe tener producto y cantidad"

            try:
                id_producto = int(id_producto)
                cantidad = int(cantidad)
            except (TypeError, ValueError):
                return False, "Los datos del pedido son inválidos"

            if cantidad <= 0:
                return False, "La cantidad debe ser mayor a cero"

            producto = Producto.query.get(id_producto)
            if not producto or not producto.estado:
                return False, f"Producto inválido: {id_producto}"

            subtotal = float(producto.precio) * cantidad
            total += subtotal

            detalles.append({
                'id_producto': id_producto,
                'cantidad': cantidad,
                'subtotal': subtotal,
            })

        if not detalles:
            return False, "Debes agregar al menos un producto"

        DetallePedido.query.filter_by(id_pedido=pedido.id_pedido).delete()

        for d in detalles:
            db.session.add(DetallePedido(
                id_pedido=pedido.id_pedido,
                id_producto=d['id_producto'],
                cantidad=d['cantidad'],
                subtotal=d['subtotal']
            ))

        pedido.total = total
        db.session.commit()

        return True, "Pedido actualizado correctamente"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al editar pedido propio: {str(e)}")
        return False, str(e)

def completar_o_producir(id_pedido, id_usuario, fecha_necesaria=None, metodo_pago=None, datos_tarjeta=None):
    try:
        _asegurar_esquema_pedidos()
        pedido = Pedido.query.get(id_pedido)

        if not pedido:
            return False, "Pedido no encontrado"

        requerimientos_por_producto = {}
        for detalle in pedido.detalles:
            producto = Producto.query.get(detalle.id_producto)
            if not producto:
                continue

            if getattr(detalle, 'atendido', False):
                continue

            item = requerimientos_por_producto.setdefault(
                producto.id_producto,
                {
                    "producto": producto,
                    "cantidad_pedida": 0.0,
                    "stock_requerido": 0.0,
                    "stock_actual": float(producto.stock_actual or 0),
                }
            )
            cantidad_detalle = float(detalle.cantidad or 0)
            item["cantidad_pedida"] += cantidad_detalle
            item["stock_requerido"] += cantidad_detalle

        faltantes_por_producto = {}
        for id_producto, item in requerimientos_por_producto.items():
            faltante_stock = round(max(0.0, item["stock_requerido"] - item["stock_actual"]), 6)
            if faltante_stock > 0:
                faltante_produccion = round(faltante_stock, 6)
                faltantes_por_producto[id_producto] = {
                    "producto": item["producto"],
                    "faltante": faltante_produccion,
                    "faltante_stock": faltante_stock,
                    "cantidad_pedida": item["cantidad_pedida"],
                    "stock_requerido": item["stock_requerido"],
                    "stock_actual": item["stock_actual"],
                }

        necesita_produccion = len(faltantes_por_producto) > 0

        if not necesita_produccion:
            for item in requerimientos_por_producto.values():
                producto = item["producto"]
                producto.stock_actual -= item["stock_requerido"]
            for detalle in pedido.detalles:
                if getattr(detalle, 'atendido', False):
                    continue
                detalle.atendido = True
                detalle.en_produccion = False

            pedido.estado = "Completado"
            pedido.fecha_entrega = datetime.now()
            pedido.requiere_produccion = False

            db.session.commit()

            return True, "Pedido completado sin producción"

        if not fecha_necesaria and pedido.fecha_entrega:
            fecha_necesaria = pedido.fecha_entrega.strftime('%Y-%m-%d %H:%M')

        if not fecha_necesaria:
            return False, "Debes indicar la fecha en que se necesita la producción"

        fecha_necesaria_dt, error_fecha = _parse_fecha_necesaria(fecha_necesaria)
        if error_fecha:
            return False, error_fecha

        produccion = pedido.produccion
        if not produccion:
            produccion = Produccion(
                fecha_solicitud=datetime.now(),
                estado="Solicitada",
                fecha_necesaria=fecha_necesaria_dt,
                id_usuario=id_usuario,
                id_pedido=id_pedido
            )
            db.session.add(produccion)
            db.session.flush()
        else:
            produccion.fecha_necesaria = fecha_necesaria_dt
            produccion.id_usuario = id_usuario
            if not produccion.fecha_solicitud:
                produccion.fecha_solicitud = datetime.now()
            if not produccion.estado or produccion.estado == 'Completada':
                produccion.estado = 'Solicitada'

        for item in faltantes_por_producto.values():
            db.session.add(DetalleProduccion(
                id_produccion=produccion.id_produccion,
                id_producto=item["producto"].id_producto,
                id_materia=None,
                cantidad=item["faltante"]
            ))

        for detalle in pedido.detalles:
            if getattr(detalle, 'atendido', False):
                continue

            producto = detalle.producto
            if not producto:
                continue

            stock_requerido = float(detalle.cantidad or 0)
            if float(producto.stock_actual or 0) >= stock_requerido:
                producto.stock_actual -= stock_requerido
                detalle.atendido = True
                detalle.en_produccion = False
            else:
                detalle.en_produccion = True

        pedido.estado = "En Proceso"
        pedido.requiere_produccion = True

        db.session.commit()

        return True, "Se envió a producción"

    except Exception as e:
        db.session.rollback()
        return False, str(e)


def procesar_detalle_pedido(id_pedido, id_detalle, id_usuario, enviar_a_produccion=False, fecha_necesaria=None, metodo_pago=None, datos_tarjeta=None):
    try:
        _asegurar_esquema_pedidos()

        pedido = Pedido.query.get(id_pedido)
        if not pedido:
            return False, "Pedido no encontrado"

        detalle = DetallePedido.query.get(id_detalle)
        if not detalle or detalle.id_pedido != pedido.id_pedido:
            return False, "La línea no pertenece a este pedido"

        if getattr(detalle, 'atendido', False):
            return True, "La línea ya fue entregada"

        producto = detalle.producto
        if not producto:
            return False, "Producto no encontrado"

        if enviar_a_produccion:
            if getattr(detalle, 'en_produccion', False):
                return True, "La línea ya está en producción"

            produccion = pedido.produccion
            if not produccion:
                fecha_necesaria_valor = fecha_necesaria
                if not fecha_necesaria_valor and pedido.fecha_entrega:
                    fecha_necesaria_valor = pedido.fecha_entrega.strftime('%Y-%m-%d %H:%M')

                fecha_necesaria_dt, error_fecha = _parse_fecha_necesaria(fecha_necesaria_valor)
                if error_fecha:
                    return False, error_fecha

                produccion = Produccion(
                    fecha_solicitud=datetime.now(),
                    estado="Solicitada",
                    fecha_necesaria=fecha_necesaria_dt,
                    id_usuario=id_usuario,
                    id_pedido=id_pedido
                )
                db.session.add(produccion)
                db.session.flush()

            db.session.add(DetalleProduccion(
                id_produccion=produccion.id_produccion,
                id_producto=producto.id_producto,
                id_materia=None,
                cantidad=detalle.cantidad,
            ))

            detalle.en_produccion = True
            pedido.estado = 'En Proceso'
            pedido.requiere_produccion = True
            db.session.commit()
            return True, f"La línea de {producto.nombre} fue enviada a producción"

        stock_requerido = float(detalle.cantidad or 0)
        if float(producto.stock_actual or 0) < stock_requerido:
            return False, f"Stock insuficiente para '{producto.nombre}'. Envía la línea a producción"

        producto.stock_actual -= stock_requerido
        detalle.atendido = True
        detalle.en_produccion = False

        if all(getattr(item, 'atendido', False) for item in pedido.detalles):
            pedido.estado = 'Completado'
            pedido.fecha_entrega = datetime.now()
            pedido.requiere_produccion = False
        else:
            pedido.estado = 'En Proceso'

        db.session.commit()
        return True, f"La línea de {producto.nombre} fue entregada"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al procesar detalle del pedido: {str(e)}")
        return False, str(e)


def pagar_pedido(id_pedido, id_usuario, metodo_pago, datos_tarjeta=None):
    try:
        _asegurar_esquema_pedidos()
        pedido = Pedido.query.get(id_pedido)
        if not pedido:
            return False, 'Pedido no encontrado'

        if (pedido.estado or '').strip().lower() != 'completado':
            return False, 'Solo se puede pagar un pedido completado'

        ok_pago, err_pago = _asegurar_meta_pago_pedido(
            pedido,
            id_usuario,
            metodo_pago=metodo_pago,
            datos_tarjeta=datos_tarjeta,
        )
        if not ok_pago:
            return False, err_pago

        pedido.estado = 'Pagado'

        ok_caja, err_caja = registrar_ingreso_caja(
            pedido.total,
            f'Pedido #{pedido.id_pedido}',
            fecha=datetime.now(),
        )
        if not ok_caja:
            db.session.rollback()
            return False, err_caja or 'No se pudo registrar el pago en caja'

        db.session.commit()
        return True, 'Pago registrado correctamente'

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error al pagar pedido: {str(e)}')
        return False, str(e)