from models import db, Producto, CategoriaPlatillo, MateriaPrima
from flask import current_app
from sqlalchemy import inspect, text
import logging
import os

from utils.file_uploads import save_image_file

logger = logging.getLogger(__name__)


def _normalizar_cantidad_materia(materia, cantidad, unidad_detalle):
    unidad_base = (getattr(materia, 'unidad_medida', '') or '').strip().lower()
    unidad_detalle = (unidad_detalle or unidad_base or '').strip().lower()
    cantidad = float(cantidad or 0)

    if cantidad <= 0:
        return 0.0, 'La cantidad debe ser mayor a cero.'

    if not unidad_base or unidad_detalle == unidad_base:
        return cantidad, None

    mapa = {
        ('kg', 'g'): 1000.0,
        ('g', 'kg'): 0.001,
        ('l', 'ml'): 1000.0,
        ('ml', 'l'): 0.001,
    }

    factor = mapa.get((unidad_detalle, unidad_base))
    if factor is None:
        return 0.0, f'No se puede convertir de {unidad_detalle} a {unidad_base}'

    return round(cantidad * factor, 6), None


def _asegurar_columnas_esquema():
    inspector = inspect(db.engine)
    columnas_productos = {columna['name'] for columna in inspector.get_columns('productos')}
    columnas_recetas = {columna['name'] for columna in inspector.get_columns('recetas')}
    columnas_detalle = {columna['name'] for columna in inspector.get_columns('receta_detalle')}

    alter_statements = []

    if 'cantidad_produccion' not in columnas_recetas:
        alter_statements.append("ALTER TABLE recetas ADD COLUMN cantidad_produccion DOUBLE NOT NULL DEFAULT 1")
    if 'unidad_produccion' not in columnas_recetas:
        alter_statements.append("ALTER TABLE recetas ADD COLUMN unidad_produccion VARCHAR(20) NOT NULL DEFAULT 'pz'")

    if 'unidad_medida' not in columnas_detalle:
        alter_statements.append("ALTER TABLE receta_detalle ADD COLUMN unidad_medida VARCHAR(20) NOT NULL DEFAULT 'g'")
    if 'cantidad_requerida' not in columnas_detalle:
        alter_statements.append("ALTER TABLE receta_detalle ADD COLUMN cantidad_requerida DOUBLE NOT NULL DEFAULT 0")

    if alter_statements:
        for statement in alter_statements:
            db.session.execute(text(statement))
        db.session.commit()


def _calcular_costos_producto(producto):
    receta = producto.recetas[0] if producto.recetas else None
    if not receta:
        return 0.0, 0.0, 0.0

    costo_total_receta = 0.0
    for detalle in receta.detalles:
        materia = detalle.materia_prima
        if not materia:
            continue

        cantidad_base, error_conversion = _normalizar_cantidad_materia(
            materia,
            float(detalle.cantidad or 0),
            (detalle.unidad_medida or (materia.unidad_medida if materia else '') or '').strip().lower(),
        )

        if error_conversion:
            cantidad_base = float(detalle.cantidad_requerida or detalle.cantidad or 0)

        precio_base = float(materia.precio or 0)
        costo_total_receta += cantidad_base * precio_base

    produccion = float(receta.cantidad_produccion or 1)
    costo_unitario = costo_total_receta / produccion if produccion > 0 else costo_total_receta
    ganancia_monto = float(producto.precio or 0) - costo_unitario
    ganancia_porcentaje = (ganancia_monto / float(producto.precio or 1)) * 100 if float(producto.precio or 0) > 0 else 0
    return round(costo_unitario, 2), round(ganancia_monto, 2), round(ganancia_porcentaje, 2)


def _resolver_categoria_platillo(form, requerida=True):
    usar_nueva = bool(getattr(form, 'usar_categoria_nueva', None) and form.usar_categoria_nueva.data)
    nombre_nueva = (getattr(form, 'nombre_nueva_categoria', None).data or '').strip() if getattr(form, 'nombre_nueva_categoria', None) else ''

    if usar_nueva:
        if not nombre_nueva:
            return None, "Debes indicar el nombre de la nueva categoría."

        categoria = CategoriaPlatillo.query.filter(db.func.lower(CategoriaPlatillo.nombre) == nombre_nueva.lower()).first()
        if not categoria:
            categoria = CategoriaPlatillo(nombre=nombre_nueva, estado=True)
            db.session.add(categoria)
            db.session.flush()
        return categoria.id_categoria_platillo, None

    categoria_id = form.id_categoria_platillo.data if hasattr(form, 'id_categoria_platillo') else None
    if categoria_id:
        categoria = CategoriaPlatillo.query.get(int(categoria_id))
        if not categoria:
            return None, "La categoría seleccionada no es válida."
        return categoria.id_categoria_platillo, None

    if requerida:
        return None, "Debes seleccionar una categoría o crear una nueva."

    return None, None

def crear_producto(form):
    """Crear un nuevo producto"""
    try:
        _asegurar_columnas_esquema()
        logger.info(f"Creando producto: {form.nombre.data}")
        
        # Verificar si el nombre ya existe
        producto_existente = Producto.query.filter_by(nombre=form.nombre.data).first()
        if producto_existente:
            return False, "Ya existe un producto con ese nombre."

        categoria_id, error_categoria = _resolver_categoria_platillo(form, requerida=True)
        if error_categoria:
            return False, error_categoria
        
        imagen_relativa = None
        imagen_file = form.imagen.data
        if imagen_file and getattr(imagen_file, 'filename', None):
            upload_root = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'])
            imagen_relativa, image_error = save_image_file(
                imagen_file,
                upload_root,
                'productos',
                current_app.config['ALLOWED_IMAGE_EXTENSIONS']
            )
            if image_error:
                return False, image_error

        nuevo_producto = Producto(
            nombre=form.nombre.data,
            descripcion=form.descripcion.data if form.descripcion.data else None,
            precio=form.precio.data,
            stock_actual=form.stock_actual.data,
            stock_minimo=form.stock_minimo.data,
            id_categoria_platillo=categoria_id,
            imagen=imagen_relativa,
            estado=True
        )
        
        db.session.add(nuevo_producto)
        db.session.flush()

        db.session.commit()
        logger.info(f"Producto creado exitosamente: {form.nombre.data}")
        return True, "Producto creado exitosamente", nuevo_producto.id_producto
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear producto: {str(e)}")
        return False, str(e), None


def obtener_productos(filtro_estado=None):
    """Obtener todos los productos"""
    try:
        _asegurar_columnas_esquema()
        query = Producto.query
        
        if filtro_estado is not None:
            query = query.filter_by(estado=filtro_estado)
        
        productos = query.all()
        
        # Obtener calificaciones de MongoDB
        mongo_db = getattr(current_app, 'mongo', None)
        calificaciones_por_producto = {}
        if mongo_db is not None:
            try:
                calificaciones = mongo_db.calificaciones_servicio.find()
                for cal in calificaciones:
                    id_venta = cal.get('idVenta')
                    cal_general = cal.get('calificacion', 0)
                    productos_cal = cal.get('productos', [])
                    
                    for prod_cal in productos_cal:
                        nombre_prod = prod_cal.get('nombre', '')
                        cal_prod = prod_cal.get('calificacion', 0)
                        
                        if nombre_prod not in calificaciones_por_producto:
                            calificaciones_por_producto[nombre_prod] = []
                        
                        calificaciones_por_producto[nombre_prod].append(cal_prod)
            except Exception as e:
                logger.warning(f"Error al obtener calificaciones de MongoDB: {str(e)}")
        
        resultado = []
        for prod in productos:
            receta = prod.recetas[0] if prod.recetas else None
            costo_unitario, ganancia_monto, ganancia_porcentaje = _calcular_costos_producto(prod)
            
            # Calcular promedio de calificación para este producto
            calificacion_promedio = 0
            if prod.nombre in calificaciones_por_producto:
                cals = calificaciones_por_producto[prod.nombre]
                if cals:
                    calificacion_promedio = round(sum(cals) / len(cals), 1)
            
            resultado.append({
                'id_producto': prod.id_producto,
                'nombre': prod.nombre,
                'descripcion': prod.descripcion,
                'precio': prod.precio,
                'stock_actual': prod.stock_actual,
                'stock_minimo': prod.stock_minimo,
                'categoria_nombre': prod.categoria_platillo.nombre if prod.categoria_platillo else 'N/A',
                'id_categoria_platillo': prod.id_categoria_platillo,
                'imagen': prod.imagen,
                'estado': prod.estado,
                'fecha_creacion': prod.fecha_creacion,
                'estado_display': 'Activo' if prod.estado else 'Inactivo',
                'id_receta': receta.id_receta if receta else None,
                'tiene_receta': bool(receta),
                'unidad_stock': (receta.unidad_produccion if receta and receta.unidad_produccion else 'pz'),
                'costo_unitario': costo_unitario,
                'ganancia_monto': ganancia_monto,
                'ganancia_porcentaje': ganancia_porcentaje,
                'calificacion_promedio': calificacion_promedio,
            })
        
        return resultado, None
        
    except Exception as e:
        logger.error(f"Error al obtener productos: {str(e)}")
        return None, str(e)


def obtener_producto(id_producto):
    """Obtener detalles de un producto específico"""
    try:
        _asegurar_columnas_esquema()
        producto = Producto.query.get(id_producto)
        
        if not producto:
            return None, "Producto no encontrado."
        
        resultado = {
            'id_producto': producto.id_producto,
            'nombre': producto.nombre,
            'descripcion': producto.descripcion,
            'precio': producto.precio,
            'stock_actual': producto.stock_actual,
            'stock_minimo': producto.stock_minimo,
            'categoria_nombre': producto.categoria_platillo.nombre if producto.categoria_platillo else 'N/A',
            'id_categoria_platillo': producto.id_categoria_platillo,
            'imagen': producto.imagen,
            'estado': producto.estado,
            'fecha_creacion': producto.fecha_creacion,
            'estado_display': 'Activo' if producto.estado else 'Inactivo',
            'id_receta': producto.recetas[0].id_receta if producto.recetas else None,
        }
        costo_unitario, ganancia_monto, ganancia_porcentaje = _calcular_costos_producto(producto)
        resultado['costo_unitario'] = costo_unitario
        resultado['ganancia_monto'] = ganancia_monto
        resultado['ganancia_porcentaje'] = ganancia_porcentaje
        
        return resultado, None
        
    except Exception as e:
        logger.error(f"Error al obtener producto: {str(e)}")
        return None, str(e)


def actualizar_producto(id_producto, form):
    """Actualizar un producto existente"""
    try:
        _asegurar_columnas_esquema()
        producto = Producto.query.get(id_producto)
        
        if not producto:
            return False, "Producto no encontrado."
        
        # Verificar si el nuevo nombre ya existe en otro producto
        if form.nombre.data and form.nombre.data != producto.nombre:
            producto_existente = Producto.query.filter_by(nombre=form.nombre.data).first()
            if producto_existente:
                return False, "Ya existe otro producto con ese nombre."
        
        logger.info(f"Actualizando producto: {id_producto}")
        
        if form.nombre.data:
            producto.nombre = form.nombre.data
        if form.descripcion.data:
            producto.descripcion = form.descripcion.data
        if form.precio.data:
            producto.precio = form.precio.data
        if form.stock_actual.data is not None:
            producto.stock_actual = form.stock_actual.data
        if form.stock_minimo.data is not None:
            producto.stock_minimo = form.stock_minimo.data

        categoria_id, error_categoria = _resolver_categoria_platillo(form, requerida=False)
        if error_categoria:
            return False, error_categoria
        if categoria_id:
            producto.id_categoria_platillo = categoria_id

        imagen_file = form.imagen.data
        if imagen_file and getattr(imagen_file, 'filename', None):
            upload_root = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'])
            imagen_relativa, image_error = save_image_file(
                imagen_file,
                upload_root,
                'productos',
                current_app.config['ALLOWED_IMAGE_EXTENSIONS']
            )
            if image_error:
                return False, image_error
            producto.imagen = imagen_relativa
        
        db.session.commit()
        logger.info(f"Producto actualizado: {id_producto}")
        return True, "Producto actualizado exitosamente"
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar producto: {str(e)}")
        return False, str(e)


def desactivar_producto(id_producto):
    """Desactivar un producto (eliminación lógica)"""
    try:
        producto = Producto.query.get(id_producto)
        
        if not producto:
            return False, "Producto no encontrado."
        
        logger.info(f"Desactivando producto: {id_producto}")
        
        producto.estado = False
        db.session.commit()
        logger.info(f"Producto desactivado: {id_producto}")
        return True, "Producto desactivado exitosamente"
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al desactivar producto: {str(e)}")
        return False, str(e)


def activar_producto(id_producto):
    """Activar un producto (recuperación lógica)"""
    try:
        producto = Producto.query.get(id_producto)
        
        if not producto:
            return False, "Producto no encontrado."
        
        logger.info(f"Activando producto: {id_producto}")
        
        producto.estado = True
        db.session.commit()
        logger.info(f"Producto activado: {id_producto}")
        return True, "Producto activado exitosamente"
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al activar producto: {str(e)}")
        return False, str(e)


def buscar_productos(termino):
    """Buscar productos por nombre o descripción"""
    try:
        productos = Producto.query.filter(
            (Producto.nombre.ilike(f'%{termino}%')) |
            (Producto.descripcion.ilike(f'%{termino}%'))
        ).filter_by(estado=True).all()
        
        resultado = []
        for prod in productos:
            resultado.append({
                'id_producto': prod.id_producto,
                'nombre': prod.nombre,
                'descripcion': prod.descripcion,
                'precio': prod.precio,
                'stock_actual': prod.stock_actual,
                'stock_minimo': prod.stock_minimo,
                'categoria_nombre': prod.categoria_platillo.nombre if prod.categoria_platillo else 'N/A',
                'id_categoria_platillo': prod.id_categoria_platillo,
                'imagen': prod.imagen,
                'estado': prod.estado,
                'fecha_creacion': prod.fecha_creacion,
                'estado_display': 'Activo'
            })
        
        return resultado, None
        
    except Exception as e:
        logger.error(f"Error al buscar productos: {str(e)}")
        return None, str(e)

def obtener_categorias():
    try:
        logger.info("Obteniendo categorías de platillo")
        resultados = CategoriaPlatillo.query.filter_by(estado=True).order_by(CategoriaPlatillo.nombre.asc()).all()
        return resultados, None
    except Exception as e:
        logger.error(f"Error al obtener categorías: {str(e)}")
        return None, str(e)
