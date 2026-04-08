from models import db, MateriaPrima, Producto, Compra, DetalleCompra, Pedido, Produccion, DetalleProduccion
from datetime import datetime, timedelta
from flask import session


def _filtrar_alertas_vistas(alertas, session_key):
    vistas = set(session.get(session_key, []) or [])
    if not vistas:
        return alertas
    return [a for a in (alertas or []) if (a.get('clave') not in vistas)]


def _merge_vistas(session_obj, session_key, claves):
    previas = set(session_obj.get(session_key, []) or [])
    nuevas = set(claves or [])
    session_obj[session_key] = list(previas.union(nuevas))


def construir_contexto_alertas(user):
    alertas_materias = []
    alertas_productos = []
    alertas_pedidos_cliente = []
    alertas_pedidos_pendientes = []
    alertas_compras_solicitadas = []
    alertas_producciones_solicitadas = []
    total_alertas = 0

    if not user.is_authenticated:
        return {
            'current_user': user,
            'alertas_materias': alertas_materias,
            'alertas_productos': alertas_productos,
            'alertas_pedidos_cliente': alertas_pedidos_cliente,
            'alertas_pedidos_pendientes': alertas_pedidos_pendientes,
            'alertas_pedido_necesita_produccion': alertas_pedidos_cliente,
            'alertas_produccion_necesita_compra': alertas_producciones_solicitadas,
            'alertas_urgente': alertas_compras_solicitadas + alertas_producciones_solicitadas + alertas_pedidos_cliente,
            'alertas_compras_solicitadas': alertas_compras_solicitadas,
            'alertas_producciones_solicitadas': alertas_producciones_solicitadas,
            'alertas_nuevo_pedido': alertas_pedidos_cliente,
            'alertas_cambio_estado_pedido': alertas_pedidos_cliente,
            'alertas_cambio_estado_produccion': alertas_producciones_solicitadas,
            'alertas_cambio_estado_compra': alertas_compras_solicitadas,
            'alertas_stock_total': total_alertas,
            'alertas_total': total_alertas,
        }

    if user.id_rol in [1, 3]:
        hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        manana_inicio = hoy_inicio + timedelta(days=1)

        # alerta de materias primas con stock bajo
        materias_bajas = (
            MateriaPrima.query
            .filter(MateriaPrima.stock_actual <= MateriaPrima.stock_minimo)
            .order_by(MateriaPrima.nombre.asc())
            .all()
        )

        ids_materias_bajas = [m.id_materia for m in materias_bajas]
        ids_materias_solicitadas = set()

        if ids_materias_bajas:
            filas_solicitadas = (
                db.session.query(DetalleCompra.id_materia)
                .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
                .filter(
                    Compra.estado.in_(['Solicitada', 'En Camino']),
                    DetalleCompra.id_materia.in_(ids_materias_bajas)
                )
                .distinct()
                .all()
            )
            ids_materias_solicitadas = {fila[0] for fila in filas_solicitadas}

        # alertas de materias primas con stock bajo y si ya hay una compra solicitada para esa materia
        alertas_materias = [
            {
                'id': m.id_materia,
                'nombre': m.nombre,
                'stock_actual': m.stock_actual,
                'stock_minimo': m.stock_minimo,
                'unidad_medida': m.unidad_medida,
                'compra_solicitada': m.id_materia in ids_materias_solicitadas,
                'clave': f"materia:{m.id_materia}:{m.stock_actual}:{m.stock_minimo}",
            }
            for m in materias_bajas
        ]

        # alerta de productos con stock bajo
        productos_bajos = (
            Producto.query
            .filter(Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.nombre.asc())
            .all()
        )
        
        # Obtener productos que ya tienen producción solicitada o en proceso
        ids_productos_bajos = [p.id_producto for p in productos_bajos]
        ids_productos_con_produccion = set()
        
        if ids_productos_bajos:
            producciones_activas = (
                db.session.query(db.func.distinct(DetalleProduccion.id_producto))
                .join(Produccion, Produccion.id_produccion == DetalleProduccion.id_produccion)
                .filter(
                    Produccion.estado.in_(['Solicitada', 'En Proceso']),
                    DetalleProduccion.id_producto.in_(ids_productos_bajos)
                )
                .all()
            )
            ids_productos_con_produccion = {fila[0] for fila in producciones_activas}
        
        # alertas de productos con stock bajo y si ya hay una producción solicitada
        alertas_productos = [
            {
                'id': p.id_producto,
                'nombre': p.nombre,
                'stock_actual': p.stock_actual,
                'stock_minimo': p.stock_minimo,
                'produccion_solicitada': p.id_producto in ids_productos_con_produccion,
                'clave': f"producto:{p.id_producto}:{p.stock_actual}:{p.stock_minimo}",
            }
            for p in productos_bajos
        ]

        alertas_compras_solicitadas = (
            Compra.query
            .filter(Compra.estado == 'Solicitada')
            .order_by(Compra.fecha.desc())
            .limit(10)
            .all()
        )
        
        alertas_compras_solicitadas = [
            {
                'id_compra': compra.id_compra,
                'estado': compra.estado,
                'fecha': compra.fecha,
                'total': compra.total,
                'clave': f"{compra.id_compra}:{compra.estado}",
            }
            for compra in alertas_compras_solicitadas
        ]

        producciones_pendientes = (
            Produccion.query
            .filter(Produccion.estado.in_(['Solicitada', 'En Proceso']))
            .order_by(Produccion.fecha_solicitud.desc())
            .limit(10)
            .all()
        )
        alertas_producciones_solicitadas = [
            {
                'id_produccion': produccion.id_produccion,
                'estado': produccion.estado,
                'fecha_solicitud': produccion.fecha_solicitud,
                'fecha_necesaria': produccion.fecha_necesaria,
                'clave': f"{produccion.id_produccion}:{produccion.estado}",
            }
            for produccion in producciones_pendientes
        ]

        pedidos_pendientes = (
            Pedido.query
            .filter(
                Pedido.estado == 'Pendiente',
                Pedido.fecha >= hoy_inicio,
                Pedido.fecha < manana_inicio,
            )
            .order_by(Pedido.fecha.desc())
            .limit(10)
            .all()
        )
        alertas_pedidos_pendientes = [
            {
                'id_pedido': pedido.id_pedido,
                'estado': pedido.estado,
                'fecha': pedido.fecha,
                'clave': f"{pedido.id_pedido}:{pedido.estado}",
            }
            for pedido in pedidos_pendientes
        ]

        alertas_materias = _filtrar_alertas_vistas(alertas_materias, 'alertas_vistas_materias')
        alertas_productos = _filtrar_alertas_vistas(alertas_productos, 'alertas_vistas_productos')
        alertas_compras_solicitadas = _filtrar_alertas_vistas(alertas_compras_solicitadas, 'alertas_vistas_compras')
        alertas_producciones_solicitadas = _filtrar_alertas_vistas(alertas_producciones_solicitadas, 'alertas_vistas_producciones')
        alertas_pedidos_pendientes = _filtrar_alertas_vistas(alertas_pedidos_pendientes, 'alertas_vistas_pedidos')
        
        alertas_pedidos_cliente = []

        total_alertas = (
            len(alertas_materias)
            + len(alertas_productos)
            + len(alertas_compras_solicitadas)
            + len(alertas_producciones_solicitadas)
            + len(alertas_pedidos_pendientes)
        )

        
    elif user.id_rol == 2:
        producciones_solicitadas = (
            Produccion.query
            .filter(Produccion.estado.in_(['Solicitada', 'En Proceso']))
            .order_by(Produccion.fecha_solicitud.desc())
            .limit(10)
            .all()
        )

        alertas_producciones_solicitadas = [
            {
                'id_produccion': produccion.id_produccion,
                'estado': produccion.estado,
                'fecha_solicitud': produccion.fecha_solicitud,
                'fecha_necesaria': produccion.fecha_necesaria,
                'clave': f"{produccion.id_produccion}:{produccion.estado}",
            }
            for produccion in producciones_solicitadas
        ]
        alertas_producciones_solicitadas = _filtrar_alertas_vistas(alertas_producciones_solicitadas, 'alertas_vistas_producciones')
        total_alertas = len(alertas_producciones_solicitadas)

    elif user.id_rol == 3:
        materias_bajas = (
            MateriaPrima.query
            .filter(MateriaPrima.stock_actual <= MateriaPrima.stock_minimo)
            .order_by(MateriaPrima.nombre.asc())
            .all()
        )

        ids_materias_bajas = [m.id_materia for m in materias_bajas]
        ids_materias_solicitadas = set()

        if ids_materias_bajas:
            filas_solicitadas = (
                db.session.query(DetalleCompra.id_materia)
                .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
                .filter(
                    Compra.estado.in_(['Solicitada', 'En Camino']),
                    DetalleCompra.id_materia.in_(ids_materias_bajas)
                )
                .distinct()
                .all()
            )
            ids_materias_solicitadas = {fila[0] for fila in filas_solicitadas}

        alertas_materias = [
            {
                'id': m.id_materia,
                'nombre': m.nombre,
                'stock_actual': m.stock_actual,
                'stock_minimo': m.stock_minimo,
                'unidad_medida': m.unidad_medida,
                'compra_solicitada': m.id_materia in ids_materias_solicitadas,
                'clave': f"materia:{m.id_materia}:{m.stock_actual}:{m.stock_minimo}",
            }
            for m in materias_bajas
        ]

        compras_solicitadas = (
            Compra.query
            .filter(Compra.estado == 'Solicitada')
            .order_by(Compra.fecha.desc())
            .limit(10)
            .all()
        )
        alertas_compras_solicitadas = [
            {
                'id_compra': compra.id_compra,
                'estado': compra.estado,
                'fecha': compra.fecha,
                'total': compra.total,
                'clave': f"{compra.id_compra}:{compra.estado}",
            }
            for compra in compras_solicitadas
        ]

        productos_bajos = (
            Producto.query
            .filter(Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.nombre.asc())
            .all()
        )
        
        # Obtener productos que ya tienen producción solicitada o en proceso
        ids_productos_bajos_rol3 = [p.id_producto for p in productos_bajos]
        ids_productos_con_produccion_rol3 = set()
        
        if ids_productos_bajos_rol3:
            producciones_activas_rol3 = (
                db.session.query(db.func.distinct(DetalleProduccion.id_producto))
                .join(Produccion, Produccion.id_produccion == DetalleProduccion.id_produccion)
                .filter(
                    Produccion.estado.in_(['Solicitada', 'En Proceso']),
                    DetalleProduccion.id_producto.in_(ids_productos_bajos_rol3)
                )
                .all()
            )
            ids_productos_con_produccion_rol3 = {fila[0] for fila in producciones_activas_rol3}
        
        alertas_productos = [
            {
                'id': p.id_producto,
                'nombre': p.nombre,
                'stock_actual': p.stock_actual,
                'stock_minimo': p.stock_minimo,
                'produccion_solicitada': p.id_producto in ids_productos_con_produccion_rol3,
                'clave': f"producto:{p.id_producto}:{p.stock_actual}:{p.stock_minimo}",
            }
            for p in productos_bajos
        ]

        alertas_materias = _filtrar_alertas_vistas(alertas_materias, 'alertas_vistas_materias')
        alertas_productos = _filtrar_alertas_vistas(alertas_productos, 'alertas_vistas_productos')
        alertas_compras_solicitadas = _filtrar_alertas_vistas(alertas_compras_solicitadas, 'alertas_vistas_compras')

        total_alertas = len(alertas_compras_solicitadas) + len(alertas_productos) + len(alertas_materias)

    elif user.id_rol == 4:
        id_cliente = user.cliente.id_cliente if user.cliente else None
        if id_cliente:
            pedidos_actualizados = (
                Pedido.query
                .filter(
                    Pedido.id_cliente == id_cliente,
                    Pedido.estado != 'Pendiente'
                )
                .order_by(Pedido.fecha.desc())
                .limit(10)
                .all()
            )

            alertas_pedidos_cliente = [
                {
                    'id_pedido': p.id_pedido,
                    'estado': p.estado,
                    'fecha': p.fecha,
                    'clave': f"{p.id_pedido}:{p.estado}",
                }
                for p in pedidos_actualizados
            ]
            alertas_pedidos_cliente = _filtrar_alertas_vistas(alertas_pedidos_cliente, 'alertas_vistas_pedidos')
        total_alertas = len(alertas_pedidos_cliente)

    return {
        'current_user': user,
        'alertas_materias': alertas_materias,
        'alertas_productos': alertas_productos,
        'alertas_pedidos_cliente': alertas_pedidos_cliente,
        'alertas_pedidos_pendientes': alertas_pedidos_pendientes,
        'alertas_compras_solicitadas': alertas_compras_solicitadas,
        'alertas_producciones_solicitadas': alertas_producciones_solicitadas,
        'alertas_stock_total': total_alertas,
        'alertas_total': total_alertas,
    }


def marcar_alertas_vistas(user, session_obj):
    contexto = construir_contexto_alertas(user)

    _merge_vistas(session_obj, 'alertas_vistas_materias', [a.get('clave') for a in contexto.get('alertas_materias', [])])
    _merge_vistas(session_obj, 'alertas_vistas_productos', [a.get('clave') for a in contexto.get('alertas_productos', [])])
    _merge_vistas(session_obj, 'alertas_vistas_compras', [a.get('clave') for a in contexto.get('alertas_compras_solicitadas', [])])
    _merge_vistas(session_obj, 'alertas_vistas_producciones', [a.get('clave') for a in contexto.get('alertas_producciones_solicitadas', [])])
    _merge_vistas(session_obj, 'alertas_vistas_pedidos', [a.get('clave') for a in contexto.get('alertas_pedidos_cliente', [])])
    _merge_vistas(session_obj, 'alertas_vistas_pedidos', [a.get('clave') for a in contexto.get('alertas_pedidos_pendientes', [])])

    session_obj.modified = True


def limpiar_alertas(user, session_obj):
    marcar_alertas_vistas(user, session_obj)