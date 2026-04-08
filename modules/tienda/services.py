from models import db, Producto, Categoria, CategoriaPlatillo, Carrito, DetalleCarrito, Pedido, DetallePedido, PedidoMeta, MateriaPrima, CategoriaIngrediente
from flask_login import current_user
from flask import current_app
from datetime import datetime, timedelta
import re
import logging

logger = logging.getLogger(__name__)

MINUTOS_ANTICIPO_PEDIDO = 30


def _parse_fecha_requerida_pedido(fecha_requerida):
    valor = (fecha_requerida or '').strip()
    if not valor:
        return None, "Debes indicar fecha y hora para tu pedido"

    formatos = ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d')
    fecha_dt = None
    for fmt in formatos:
        try:
            fecha_dt = datetime.strptime(valor, fmt)
            break
        except ValueError:
            continue

    if not fecha_dt:
        return None, "Fecha y hora del pedido inválida"

    minimo_permitido = datetime.now() + timedelta(minutes=MINUTOS_ANTICIPO_PEDIDO)
    if fecha_dt < minimo_permitido:
        return None, f"La fecha y hora requerida debe ser al menos {MINUTOS_ANTICIPO_PEDIDO} minutos después de ahora"

    return fecha_dt, None

# ===============================
# OBTENER MENÚ
# ===============================
def obtener_menu():
    try:
        productos = Producto.query.filter_by(estado=True).all()

        calificaciones_por_producto = {}
        mongo_db = getattr(current_app, 'mongo', None)
        if mongo_db is not None:
            try:
                docs = mongo_db.calificaciones_servicio.find({}, {'_id': 0, 'productos': 1})
                for doc in docs:
                    for prod in (doc.get('productos') or []):
                        nombre = (prod.get('nombre') or '').strip()
                        cal = prod.get('calificacion')
                        if not nombre:
                            continue
                        try:
                            cal = float(cal)
                        except (TypeError, ValueError):
                            continue
                        calificaciones_por_producto.setdefault(nombre, []).append(cal)
            except Exception as mongo_error:
                logger.warning(f"No se pudieron cargar calificaciones del menú: {mongo_error}")

        resultado = []
        for p in productos:
            receta = p.recetas[0] if p.recetas else None
            ingredientes = []
            if receta:
                for detalle in receta.detalles:
                    if not detalle.materia_prima:
                        continue
                    ingredientes.append({
                        "nombre": detalle.materia_prima.nombre,
                        "cantidad": float(detalle.cantidad or 0),
                        "unidad": detalle.unidad_medida or detalle.materia_prima.unidad_medida,
                    })
            cals = calificaciones_por_producto.get((p.nombre or '').strip(), [])
            calificacion_promedio = round(sum(cals) / len(cals), 1) if cals else 0.0

            resultado.append({
                "id": p.id_producto,
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": p.precio,
                "imagen": p.imagen,
                "categoria": p.categoria_platillo.nombre if p.categoria_platillo else "Sin categoria",
                "ingredientes": ingredientes,
                "calificacion_promedio": calificacion_promedio,
                "total_calificaciones": len(cals),
            })

        return resultado, None

    except Exception as e:
        logger.error(f"Error al obtener menú: {str(e)}")
        return None, str(e)


# ===============================
# OBTENER O CREAR CARRITO
# ===============================
def obtener_o_crear_carrito():
    try:
        if not current_user.is_authenticated:
            return None, "Usuario no autenticado"

        cliente = getattr(current_user, "cliente", None)

        if not cliente:
            return None, "Usuario sin cliente asociado"

        carrito = Carrito.query.filter_by(
            id_cliente=cliente.id_cliente,
            estado='Abierto'
        ).first()

        if not carrito:
            carrito = Carrito(
                id_cliente=cliente.id_cliente,
                total=0,
                fecha_creacion=datetime.utcnow(),
                estado='Abierto'
            )
            db.session.add(carrito)
            db.session.flush()

        return carrito, None

    except Exception as e:
        logger.error(f"Error al obtener o crear carrito: {str(e)}")
        return None, str(e)


# ===============================
# AGREGAR PRODUCTO AL CARRITO
# ===============================
def agregar_producto_carrito(id_producto, cantidad=1):
    try:
        carrito, error = obtener_o_crear_carrito()
        if error:
            return False, error

        producto = Producto.query.get(id_producto)

        if not producto:
            return False, "Producto no encontrado"

        if not producto.estado:
            return False, "Producto no disponible"

        detalle = DetalleCarrito.query.filter_by(
            id_carrito=carrito.id_carrito,
            id_producto=id_producto
        ).first()

        if detalle:
            detalle.cantidad += cantidad
            detalle.subtotal = detalle.cantidad * producto.precio
        else:
            detalle = DetalleCarrito(
                id_carrito=carrito.id_carrito,
                id_producto=id_producto,
                cantidad=cantidad,
                subtotal=producto.precio * cantidad
            )
            db.session.add(detalle)

        # Recalcular total correctamente
        carrito.total = sum(d.subtotal for d in carrito.detalles)

        db.session.commit()
        return True, "Producto agregado al carrito"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al agregar producto: {str(e)}")
        return False, str(e)


# ===============================
# OBTENER CARRITO
# ===============================
def obtener_carrito():
    try:
        carrito, error = obtener_o_crear_carrito()
        if error:
            return None, error

        data = {
            "id": carrito.id_carrito,
            "total": carrito.total,
            "productos": []
        }

        for d in carrito.detalles:
            data["productos"].append({
                "id_detalle": d.id_detalle,
                "id_producto": d.id_producto,
                "producto": d.producto.nombre,
                "precio": d.producto.precio,
                "cantidad": d.cantidad,
                "subtotal": d.subtotal
            })
        

        return data, None

    except Exception as e:
        logger.error(f"Error al obtener carrito: {str(e)}")
        return None, str(e)


# ===============================
# REDUCIR CANTIDAD
# ===============================
def reducir_cantidad_carrito(id_detalle):
    try:
        detalle = DetalleCarrito.query.get(id_detalle)

        if not detalle:
            return False, "Detalle no encontrado"

        carrito = detalle.carrito

        if detalle.cantidad > 1:
            detalle.cantidad -= 1
            detalle.subtotal = detalle.cantidad * detalle.producto.precio
        else:
            db.session.delete(detalle)

        carrito.total = sum(d.subtotal for d in carrito.detalles)

        db.session.commit()
        return True, "Cantidad reducida"

    except Exception as e:
        db.session.rollback()
        return False, str(e)


# ===============================
# AUMENTAR CANTIDAD
# ===============================
def agregar_cantidad_carrito(id_detalle):
    try:
        detalle = DetalleCarrito.query.get(id_detalle)

        if not detalle:
            return False, "Detalle no encontrado"

        carrito = detalle.carrito

        detalle.cantidad += 1
        detalle.subtotal = detalle.cantidad * detalle.producto.precio

        carrito.total = sum(d.subtotal for d in carrito.detalles)

        db.session.commit()
        return True, "Cantidad aumentada"

    except Exception as e:
        db.session.rollback()
        return False, str(e)


# ===============================
# FINALIZAR PEDIDO
# ===============================
def _luhn_valido(numero_tarjeta):
    digitos = [int(d) for d in numero_tarjeta if d.isdigit()]
    checksum = 0
    par = len(digitos) % 2
    for i, d in enumerate(digitos):
        if i % 2 == par:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _validar_datos_tarjeta(numero, titular, vencimiento, cvv):
    numero_limpio = re.sub(r'\s+', '', (numero or '').strip())
    titular = (titular or '').strip()
    vencimiento = (vencimiento or '').strip()
    cvv = (cvv or '').strip()

    if not re.fullmatch(r'\d{13,19}', numero_limpio):
        return False, "Número de tarjeta inválido"

    # Permitimos tarjetas de prueba/locales: validamos formato y longitud sin exigir Luhn.

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


def finalizar_pedido(metodo_pago=None, datos_tarjeta=None, fecha_requerida=None):
    """
    Creates a pedido WITHOUT capturing payment details.
    Payment data will be captured later at caja when order is ready for delivery.
    """
    try:
        if not current_user.is_authenticated:
            return False, "Usuario no autenticado"

        cliente = current_user.cliente

        carrito = Carrito.query.filter_by(
            id_cliente=cliente.id_cliente,
            estado='Abierto'
        ).first()

        if not carrito:
            return False, "Carrito no encontrado"

        if not carrito.detalles:
            return False, "El carrito está vacío"

        fecha_requerida_dt, error_fecha = _parse_fecha_requerida_pedido(fecha_requerida)
        if error_fecha:
            return False, error_fecha

        # Determinar si requiere producción
        detalles = []
        for d in carrito.detalles:
            detalles.append({
                'id_producto': d.id_producto,
                'cantidad': d.cantidad,
                'subtotal': d.subtotal
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

        total = sum(d.subtotal for d in carrito.detalles)
        pedido = Pedido(
            id_cliente=cliente.id_cliente,
            total=total,
            fecha=datetime.utcnow(),
            fecha_entrega=fecha_requerida_dt,
            estado='En Proceso' if requiere_produccion else 'Pendiente',
            requiere_produccion=requiere_produccion,
        )
        db.session.add(pedido)
        db.session.flush()

        productos_detalle = []
        for d in carrito.detalles:
            detalle_pedido = DetallePedido(
                id_pedido=pedido.id_pedido,
                id_producto=d.id_producto,
                cantidad=d.cantidad,
                subtotal=d.subtotal,
                en_produccion=d.id_producto in faltantes
            )
            db.session.add(detalle_pedido)
            productos_detalle.append({'id_producto': d.id_producto, 'cantidad': d.cantidad})

        if requiere_produccion:
            from models import Produccion, DetalleProduccion
            produccion = Produccion(
                fecha_solicitud=datetime.now(),
                estado='Solicitada',
                fecha_necesaria=fecha_requerida_dt,
                id_usuario=cliente.id_usuario if hasattr(cliente, 'id_usuario') else None,
                id_pedido=pedido.id_pedido,
            )
            db.session.add(produccion)
            db.session.flush()
            # Agregar todos los productos del pedido a detalle de produccion
            for prod in productos_detalle:
                detalle_prod = DetalleProduccion(
                    id_produccion=produccion.id_produccion,
                    id_producto=prod['id_producto'],
                    id_materia=None,
                    cantidad=float(prod['cantidad']),
                )
                db.session.add(detalle_prod)
            db.session.commit()

        # Limpiar carrito
        for detalle in carrito.detalles:
            db.session.delete(detalle)
        carrito.total = 0
        carrito.estado = 'Cerrado'
        carrito.metodo_pago = None
        db.session.commit()

        if requiere_produccion:
            return True, "Pedido generado y enviado a producción"
        return True, "Pedido generado correctamente"

    except Exception as e:
        db.session.rollback()
        return False, str(e)
    
def obtener_categorias():
    try:
        categorias = CategoriaPlatillo.query.filter_by(estado=True).order_by(CategoriaPlatillo.nombre.asc()).all()
        return [{"id": c.id_categoria_platillo, "nombre": c.nombre} for c in categorias], None
    except Exception as e:
        logger.error(f"Error al obtener categorías: {str(e)}")
        return None, str(e)


# ===============================
# OBTENER CATEGORÍAS DE INGREDIENTES
# ===============================
def obtener_categorias_ingrediente():
    try:
        categorias = CategoriaIngrediente.query.filter_by(estado=True).order_by(CategoriaIngrediente.nombre.asc()).all()
        return [{"id": c.id_categoria_ingrediente, "nombre": c.nombre} for c in categorias], None
    except Exception as e:
        logger.error(f"Error al obtener categorías de ingredientes: {str(e)}")
        return None, str(e)


# ===============================
# OBTENER MATERIAS PRIMAS POR CATEGORÍA
# ===============================
def obtener_materias_primas(categoria_id=None):
    try:
        query = MateriaPrima.query.filter_by(estado=True)
        
        if categoria_id:
            query = query.filter_by(id_categoria_ingrediente=categoria_id)
        
        materias_primas = query.order_by(MateriaPrima.nombre.asc()).all()
        
        resultado = []
        for mp in materias_primas:
            unidad = (mp.unidad_medida or '').strip().lower()
            es_kg = unidad in ('kg', 'kilo', 'kilos', 'kilogramo', 'kilogramos')

            stock_actual = float(mp.stock_actual)
            stock_minimo = float(mp.stock_minimo)

            resultado.append({
                "id": mp.id_materia,
                "nombre": mp.nombre,
                "unidad_medida": mp.unidad_medida,
                "stock_actual": stock_actual,
                "stock_minimo": stock_minimo,
                "stock_actual_gr": stock_actual * 1000 if es_kg else stock_actual,
                "stock_minimo_gr": stock_minimo * 1000 if es_kg else stock_minimo,
                "stock_convertido_gr": es_kg,
                "precio": float(mp.precio),
                "porcentaje_merma": float(mp.porcentaje_merma),
                "factor_conversion": float(mp.factor_conversion),
                "categoria": mp.categoria_ingrediente.nombre if mp.categoria_ingrediente else "Sin categoría",
                "proveedor": mp.proveedor.persona.nombre if mp.proveedor and mp.proveedor.persona else "Sin proveedor"
            })
        
        return resultado, None
    
    except Exception as e:
        logger.error(f"Error al obtener materias primas: {str(e)}")
        return None, str(e)