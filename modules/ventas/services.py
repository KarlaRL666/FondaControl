from models import db, Venta, DetalleVenta, Producto, Produccion, DetalleProduccion
import logging
from datetime import datetime, timedelta
from utils.caja_movimientos import registrar_ingreso_caja

logger = logging.getLogger(__name__)


def calcular_costo_unitario_producto(producto):
    """Calcula costo unitario estimado en base a receta e insumos vigentes."""
    if not producto or not producto.recetas:
        return 0.0

    receta = producto.recetas[0]
    if not receta or not receta.cantidad_produccion or receta.cantidad_produccion <= 0:
        return 0.0

    costo_total_receta = 0.0
    for detalle in receta.detalles:
        materia = detalle.materia_prima
        if not materia:
            continue
        costo_total_receta += float(detalle.cantidad) * float(materia.precio or 0)

    return costo_total_receta / float(receta.cantidad_produccion)

def obtener_ventas():
    try:
        ventas_db = (
            Venta.query
            .order_by(Venta.fecha.desc())
            .all()
        )

        ventas = []
        for venta in ventas_db:
            productos = []
            costo_total = 0.0

            for detalle in venta.detalles:
                producto = detalle.producto
                precio_unitario = (float(detalle.subtotal) / float(detalle.cantidad)) if detalle.cantidad else 0.0
                costo_unitario = calcular_costo_unitario_producto(producto)
                costo_subtotal = costo_unitario * float(detalle.cantidad)
                utilidad_subtotal = float(detalle.subtotal) - costo_subtotal
                costo_total += costo_subtotal

                productos.append({
                    'id_producto': producto.id_producto if producto else None,
                    'nombre': producto.nombre if producto else 'Producto',
                    'cantidad': detalle.cantidad,
                    'precio_unitario': precio_unitario,
                    'subtotal': float(detalle.subtotal),
                    'costo_unitario': costo_unitario,
                    'costo_subtotal': costo_subtotal,
                    'utilidad_subtotal': utilidad_subtotal,
                })

            utilidad_total = float(venta.total) - costo_total
            margen = (utilidad_total / float(venta.total) * 100.0) if venta.total else 0.0
            estado_pago = 'Pagado' if (venta.estado or '').strip().lower() == 'completada' else 'Pendiente de pago'

            ventas.append({
                'id_venta': venta.id_venta,
                'fecha': venta.fecha,
                'estado': venta.estado,
                'estado_pago': estado_pago,
                'total': float(venta.total),
                'metodo_pago': venta.metodo_pago,
                'productos': productos,
                'costo_total': costo_total,
                'utilidad_total': utilidad_total,
                'margen_porcentaje': margen,
            })

        return ventas, None
    except Exception as e:
        logger.error(f"Error al obtener ventas: {str(e)}")
        return None, str(e)


def obtener_detalle_venta(id_venta):
    try:
        venta = Venta.query.get(id_venta)
        if not venta:
            return None, "Venta no encontrada"

        costo_total = 0.0
        detalles = []

        for detalle in venta.detalles:
            producto = detalle.producto
            precio_unitario = (float(detalle.subtotal) / float(detalle.cantidad)) if detalle.cantidad else 0.0
            costo_unitario = calcular_costo_unitario_producto(producto)
            costo_subtotal = costo_unitario * float(detalle.cantidad)
            utilidad_subtotal = float(detalle.subtotal) - costo_subtotal
            costo_total += costo_subtotal

            detalles.append({
                'producto': producto.nombre if producto else 'Producto',
                'cantidad': detalle.cantidad,
                'precio_unitario': precio_unitario,
                'subtotal': float(detalle.subtotal),
                'costo_unitario': costo_unitario,
                'costo_subtotal': costo_subtotal,
                'utilidad_subtotal': utilidad_subtotal,
            })

        utilidad_total = float(venta.total) - costo_total
        margen = (utilidad_total / float(venta.total) * 100.0) if venta.total else 0.0
        estado_pago = 'Pagado' if (venta.estado or '').strip().lower() == 'completada' else 'Pendiente de pago'

        return {
            'id_venta': venta.id_venta,
            'fecha': venta.fecha,
            'metodo_pago': venta.metodo_pago,
            'estado': venta.estado,
            'estado_pago': estado_pago,
            'usuario': venta.usuario.username if venta.usuario else 'Usuario',
            'detalles': detalles,
            'total': float(venta.total),
            'costo_total': costo_total,
            'utilidad_total': utilidad_total,
            'margen_porcentaje': margen,
        }, None

    except Exception as e:
        logger.error(f"Error al obtener detalle de venta: {str(e)}")
        return None, str(e)
    
def _parse_fecha_necesaria(fecha_necesaria):
    valor = (fecha_necesaria or '').strip()
    if not valor:
        return datetime.now() + timedelta(days=1), None

    formatos = ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d')
    for fmt in formatos:
        try:
            fecha_dt = datetime.strptime(valor, fmt)
            if fecha_dt < datetime.now():
                return None, 'La fecha requerida no puede ser anterior al momento actual'
            return fecha_dt, None
        except ValueError:
            continue

    return None, 'Fecha requerida inválida'


def crear_venta(id_usuario, productos, fecha_necesaria=None):
    try:
        logger.info(f"Creando venta usuario={id_usuario}")

        if not productos:
            return False, "No hay productos en la venta", None

        total = 0
        detalles = []

        # 🔍 VALIDACIÓN
        for item in productos:

            if not item.get("id_producto") or not item.get("cantidad"):
                return False, "Producto inválido", None

            try:
                id_producto = int(item["id_producto"])
                cantidad = int(item["cantidad"])
            except Exception:
                return False, "Datos incorrectos", None

            if cantidad <= 0:
                return False, "Cantidad inválida", None

            producto = Producto.query.get(id_producto)

            if not producto:
                return False, f"Producto {id_producto} no existe", None

            if not producto.estado:
                return False, f"{producto.nombre} no disponible", None

            subtotal = producto.precio * cantidad
            total += subtotal

            detalles.append({
                "producto": producto,
                "cantidad": cantidad,
                "subtotal": subtotal
            })

        # 🧾 CREAR VENTA
        venta = Venta(
            id_usuario=id_usuario,
            fecha=datetime.utcnow(),
            total=total,
            metodo_pago='Efectivo',
            estado="Pendiente"
        )

        db.session.add(venta)
        db.session.flush()

        # 📦 DETALLES
        for d in detalles:
            db.session.add(DetalleVenta(
                id_venta=venta.id_venta,
                id_producto=d["producto"].id_producto,
                cantidad=d["cantidad"],
                subtotal=d["subtotal"]
            ))

        db.session.commit()

        return True, "Venta registrada. Captura el método de pago para completarla.", venta.id_venta

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error crear_venta: {str(e)}")
        return False, str(e), None


def completar_venta_pago(id_venta, metodo_pago, id_usuario, fecha_necesaria=None):
    try:
        venta = Venta.query.get(id_venta)
        if not venta:
            return False, 'Venta no encontrada'

        if venta.estado == 'Cancelada':
            return False, 'La venta está cancelada'

        if venta.estado == 'Completada':
            return True, 'La venta ya estaba completada'

        metodo_pago = (metodo_pago or '').strip().title()
        if metodo_pago not in ('Efectivo', 'Tarjeta', 'Transferencia'):
            return False, 'Método de pago inválido'

        faltantes = {}
        for detalle in (venta.detalles or []):
            producto = detalle.producto
            if not producto:
                continue

            stock_actual = int(producto.stock_actual or 0)
            cantidad = int(detalle.cantidad or 0)
            if stock_actual < cantidad:
                faltantes[producto.id_producto] = max(
                    faltantes.get(producto.id_producto, 0),
                    cantidad - stock_actual,
                )

        if faltantes:
            fecha_necesaria_dt, error_fecha = _parse_fecha_necesaria(fecha_necesaria)
            if error_fecha:
                return False, error_fecha

            produccion = Produccion(
                fecha_solicitud=datetime.now(),
                estado='Solicitada',
                fecha_necesaria=fecha_necesaria_dt,
                id_usuario=id_usuario,
                id_pedido=None,
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
            return False, 'Stock insuficiente. Se envió la venta a producción.'

        for detalle in (venta.detalles or []):
            producto = detalle.producto
            if not producto:
                continue
            producto.stock_actual = float(producto.stock_actual or 0) - float(detalle.cantidad or 0)

        venta.metodo_pago = metodo_pago
        venta.estado = 'Completada'
        registrar_ingreso_caja(
            venta.total,
            f'Venta #{venta.id_venta}',
            fecha=datetime.now(),
        )
        db.session.commit()
        return True, 'Venta completada correctamente'

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error completar_venta_pago: {str(e)}")
        return False, str(e)
            
def agregar_producto_a_venta(id_venta, id_producto, cantidad):
    try:
        
        venta= Venta.query.get(id_venta)

        if not venta:
            return False, "Venta no encontrada"

        producto = Producto.query.get(id_producto)

        detalle = DetalleVenta(
            id_venta=id_venta,
            id_producto=id_producto,
            cantidad=cantidad,
            subtotal=cantidad * producto.precio
        )
        db.session.add(detalle)
        db.session.commit()
        return True, "Producto agregado a la venta"
    except Exception as e:
        db.session.rollback()
        return False, str(e)
    
def editar_venta(id_venta, form):
    try:
        venta = Venta.query.get(id_venta)

        if not venta:
            return False, "Venta no encontrada"

        venta.fecha = form.fecha.data
        venta.total = form.total.data
        venta.metodo_pago = form.metodo_pago.data

        db.session.commit()
        return True, "Venta actualizada"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def ajustar_total_venta(id_venta):
    try:
        venta = Venta.query.get(id_venta)

        if not venta:
            return False, "Venta no encontrada"

        total_calculado = sum(d.subtotal for d in venta.detalles)
        venta.total = total_calculado

        db.session.commit()
        return True, "Total de la venta ajustado"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def disminuir_stock_productos(id_venta):
    try:
        venta = Venta.query.get(id_venta)

        if not venta:
            return False, "Venta no encontrada"

        for detalle in venta.detalles:
            producto = Producto.query.get(detalle.id_producto)
            if producto.stock_actual >= detalle.cantidad:
                producto.stock_actual -= detalle.cantidad
            else:
                return False, f"Stock insuficiente para el producto {producto.nombre}"

        db.session.commit()
        return True, "Stock de productos ajustado"
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def obtener_menu():
    """Obtiene productos activos para el menú"""
    try:
        productos = Producto.query.filter_by(estado=True).all()

        resultado = []
        for p in productos:
            resultado.append({
                "id": p.id_producto,
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": p.precio,
                "imagen": p.imagen  # base64
            })

        return resultado, None

    except Exception as e:
        logger.error(f"Error al obtener menú: {str(e)}")
        return None, str(e)