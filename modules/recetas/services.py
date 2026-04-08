from models import db, Receta, RecetaDetalle, MateriaPrima, Producto
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _precio_referencia(unidad_base, precio_unitario_base):
    unidad_base = (unidad_base or '').lower()
    precio_unitario_base = float(precio_unitario_base or 0)

    if unidad_base == 'g':
        return '1 kg', round(precio_unitario_base * 1000, 2)
    if unidad_base == 'ml':
        return '1 l', round(precio_unitario_base * 1000, 2)
    if unidad_base in {'kg', 'l', 'pz'}:
        return f'1 {unidad_base}', round(precio_unitario_base, 2)
    return f'1 {unidad_base or "unidad"}', round(precio_unitario_base, 2)


def _normalizar_cantidad(id_materia, cantidad, unidad_detalle):
    materia = MateriaPrima.query.get(id_materia)
    if not materia:
        return None, 'Materia prima no encontrada'

    unidad_base = (materia.unidad_medida or '').lower()
    unidad_detalle = (unidad_detalle or unidad_base).lower()
    cantidad = float(cantidad or 0)

    if cantidad <= 0:
        return None, 'La cantidad debe ser mayor a cero'

    mapa = {
        ('kg', 'g'): 1000.0,
        ('g', 'kg'): 0.001,
        ('l', 'ml'): 1000.0,
        ('ml', 'l'): 0.001,
    }

    if unidad_detalle == unidad_base:
        return cantidad, None

    factor = mapa.get((unidad_detalle, unidad_base))
    if factor is None:
        return None, f'No se puede convertir de {unidad_detalle} a {unidad_base}'

    return round(cantidad * factor, 6), None


def _cantidad_base_detalle(detalle):
    if not detalle or not detalle.materia_prima:
        return 0.0

    # Preferimos la cantidad ya normalizada guardada en BD para evitar
    # inconsistencias en registros legacy donde la unidad capturada cambió.
    cantidad_guardada = float(detalle.cantidad_requerida or 0)
    if cantidad_guardada > 0:
        return cantidad_guardada

    cantidad_receta = float(detalle.cantidad or 0)
    unidad_detalle = detalle.unidad_medida or detalle.materia_prima.unidad_medida

    cantidad_base, error_normalizacion = _normalizar_cantidad(
        detalle.id_materia,
        cantidad_receta,
        unidad_detalle,
    )

    if error_normalizacion:
        return float(detalle.cantidad_requerida or detalle.cantidad or 0)

    return float(cantidad_base or 0)


def obtener_recetas():
    try:
        recetas = Receta.query.order_by(Receta.fecha_creacion.desc()).all()
        resultado = []
        for receta in recetas:
            resultado.append({
                'id_receta': receta.id_receta,
                'producto_nombre': receta.producto.nombre if receta.producto else 'N/A',
                'rendimiento': receta.rendimiento,
                'cantidad_produccion': receta.cantidad_produccion,
                'unidad_produccion': receta.unidad_produccion,
                'estado': receta.estado,
                'fecha_creacion': receta.fecha_creacion,
                'detalles': [
                    {
                        'materia_nombre': detalle.materia_prima.nombre if detalle.materia_prima else 'N/A',
                        'cantidad': detalle.cantidad,
                        'unidad_detalle': detalle.unidad_medida,
                    }
                    for detalle in receta.detalles
                ]
            })
        return resultado, None
    except Exception as e:
        logger.error(f'Error al obtener recetas: {str(e)}')
        return None, str(e)


def crear_receta(id_producto, rendimiento=100, cantidad_produccion=1, unidad_produccion='pz', nota=None, detalles=None):
    """Crea una receta para un producto"""
    try:
        producto = Producto.query.get(id_producto)
        if not producto:
            return None, "Producto no encontrado"
        
        receta = Receta(
            id_producto=id_producto,
            rendimiento=rendimiento,
            cantidad_produccion=cantidad_produccion,
            unidad_produccion=unidad_produccion,
            nota=nota,
            estado=True
        )
        
        db.session.add(receta)
        db.session.flush()
        
        if detalles:
            for detalle in detalles:
                agregar_ingrediente_a_receta(
                    receta.id_receta,
                    detalle['id_materia'],
                    detalle['cantidad'],
                    detalle.get('unidad_medida')
                )
        
        db.session.commit()
        return receta, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear receta: {str(e)}")
        return None, str(e)


def actualizar_receta(id_receta, rendimiento=None, cantidad_produccion=None, unidad_produccion=None, nota=None):
    """Actualiza una receta existente"""
    try:
        receta = Receta.query.get(id_receta)
        if not receta:
            return None, "Receta no encontrada"
        
        if rendimiento is not None:
            receta.rendimiento = rendimiento
        if cantidad_produccion is not None:
            receta.cantidad_produccion = cantidad_produccion
        if unidad_produccion is not None:
            receta.unidad_produccion = unidad_produccion
        if nota is not None:
            receta.nota = nota
        
        db.session.commit()
        return receta, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar receta: {str(e)}")
        return None, str(e)


def agregar_ingrediente_a_receta(id_receta, id_materia, cantidad, unidad_medida=None):
    """Agrega un ingrediente a una receta"""
    try:
        receta = Receta.query.get(id_receta)
        materia = MateriaPrima.query.get(id_materia)
        
        if not receta or not materia:
            return None, "Receta o material no encontrado"
        
        cantidad_requerida, error_normalizacion = _normalizar_cantidad(id_materia, cantidad, unidad_medida)
        if error_normalizacion:
            return None, error_normalizacion

        materia = MateriaPrima.query.get(id_materia)
        unidad_final = (unidad_medida or (materia.unidad_medida if materia else '') or '').lower()

        existente = RecetaDetalle.query.filter_by(
            id_receta=id_receta,
            id_materia=id_materia
        ).first()
        
        if existente:
            existente.cantidad = cantidad
            existente.unidad_medida = unidad_final
            existente.cantidad_requerida = cantidad_requerida
            detalle = existente
        else:
            detalle = RecetaDetalle(
                id_receta=id_receta,
                id_materia=id_materia,
                cantidad=cantidad,
                unidad_medida=unidad_final,
                cantidad_requerida=cantidad_requerida
            )
            db.session.add(detalle)
        
        db.session.commit()
        return detalle, None
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al agregar ingrediente: {str(e)}")
        return None, str(e)


def calcular_costo_receta(id_receta):
    """Calcula el costo total de una receta"""
    try:
        receta = Receta.query.get(id_receta)
        if not receta:
            return 0
        
        costo_total = 0.0
        for detalle in receta.detalles:
            if not detalle.materia_prima:
                continue
            costo_total += _cantidad_base_detalle(detalle) * float(detalle.materia_prima.precio or 0)
        return costo_total
    except Exception as e:
        logger.error(f"Error al calcular costo: {str(e)}")
        return 0


def calcular_rendimiento_automatico(id_receta):
    """Calcula el rendimiento automáticamente"""
    try:
        receta = Receta.query.get(id_receta)
        if not receta or not receta.detalles:
            return 0
        
        cantidad_ingredientes = len(receta.detalles)
        return 50.0 if cantidad_ingredientes == 1 else (100.0 if cantidad_ingredientes > 0 else 0)
    except Exception as e:
        logger.error(f"Error al calcular rendimiento: {str(e)}")
        return 0


def serializar_receta(receta):
    """Serializa una receta para JSON"""
    if not receta:
        return None
    
    return {
        'id_receta': receta.id_receta,
        'id_producto': receta.id_producto,
        'producto_nombre': receta.producto.nombre if receta.producto else None,
        'rendimiento': receta.rendimiento,
        'cantidad_produccion': receta.cantidad_produccion,
        'unidad_produccion': receta.unidad_produccion,
        'nota': receta.nota,
        'estado': receta.estado,
        'fecha_creacion': receta.fecha_creacion.isoformat(),
        'detalles': [
            {
                'id_detalle': d.id_detalle,
                'ingrediente': d.materia_prima.nombre,
                'cantidad': d.cantidad,
                'unidad': d.materia_prima.unidad_medida,
                    'unidad_detalle': d.unidad_medida,
                'precio': d.materia_prima.precio,
                    'subtotal': (d.cantidad_requerida or d.cantidad) * d.materia_prima.precio
            }
            for d in receta.detalles
        ],
        'costo_total': calcular_costo_receta(receta.id_receta)
    }


def obtener_receta_detalle(id_receta):
    try:
        receta = Receta.query.get(id_receta)
        if not receta:
            return None, "Receta no encontrada"

        data = {
            'id_receta': receta.id_receta,
            'id_producto': receta.id_producto,
            'producto_nombre': receta.producto.nombre if receta.producto else 'N/A',
            'rendimiento': float(receta.rendimiento or 0),
            'cantidad_produccion': float(receta.cantidad_produccion or 0),
            'unidad_produccion': receta.unidad_produccion or 'pz',
            'nota': receta.nota,
            'estado': bool(receta.estado),
            'fecha_creacion': receta.fecha_creacion,
            'detalles': [
                {
                    'id_detalle': detalle.id_detalle,
                    'id_materia': detalle.id_materia,
                    'materia_nombre': detalle.materia_prima.nombre if detalle.materia_prima else 'N/A',
                    'unidad': detalle.materia_prima.unidad_medida if detalle.materia_prima else '',
                    'unidad_detalle': detalle.unidad_medida or (detalle.materia_prima.unidad_medida if detalle.materia_prima else ''),
                    'precio': float(detalle.materia_prima.precio or 0) if detalle.materia_prima else 0,
                    'cantidad_receta': float(detalle.cantidad or 0),
                    'cantidad': _cantidad_base_detalle(detalle),
                    'subtotal': _cantidad_base_detalle(detalle) * float(detalle.materia_prima.precio or 0) if detalle.materia_prima else 0,
                }
                for detalle in receta.detalles
            ],
        }

        for item in data['detalles']:
            unidad_base = item.get('unidad')
            precio_unitario = item.get('precio', 0)
            ref_etiqueta, ref_precio = _precio_referencia(unidad_base, precio_unitario)
            item['precio_referencia_etiqueta'] = ref_etiqueta
            item['precio_referencia'] = ref_precio

        data['costo_total'] = sum(item['subtotal'] for item in data['detalles'])
        return data, None
    except Exception as e:
        logger.error(f"Error al obtener detalle de receta: {str(e)}")
        return None, str(e)


def obtener_materias_activas():
    try:
        materias = (
            MateriaPrima.query
            .filter_by(estado=True)
            .order_by(MateriaPrima.nombre.asc())
            .all()
        )
        return materias, None
    except Exception as e:
        logger.error(f"Error al obtener materias activas: {str(e)}")
        return None, str(e)


def actualizar_receta_completa(id_receta, rendimiento, cantidad_produccion, unidad_produccion, nota, detalles_payload, estado=True):
    try:
        receta = Receta.query.get(id_receta)
        if not receta:
            return False, "Receta no encontrada"

        if rendimiento is None or float(rendimiento) < 0:
            return False, "El rendimiento debe ser un valor válido"

        if cantidad_produccion is None or float(cantidad_produccion) <= 0:
            return False, "La cantidad de producción debe ser mayor a cero"

        if not (unidad_produccion or '').strip():
            return False, "La unidad de producción es obligatoria"

        if not detalles_payload:
            return False, "Debes agregar al menos un ingrediente"

        detalles_normalizados = []
        for idx, item in enumerate(detalles_payload, start=1):
            id_materia = int(item.get('id_materia', 0))
            cantidad = float(item.get('cantidad', 0))
            unidad_medida = (item.get('unidad_medida') or '').strip().lower()

            if id_materia <= 0:
                return False, f"Ingrediente inválido en la fila {idx}"
            if cantidad <= 0:
                return False, f"La cantidad debe ser mayor a cero en la fila {idx}"

            materia = MateriaPrima.query.get(id_materia)
            if not materia:
                return False, f"Materia prima no encontrada en la fila {idx}"

            if not unidad_medida:
                unidad_medida = (materia.unidad_medida or '').lower()

            cantidad_requerida, error_normalizacion = _normalizar_cantidad(id_materia, cantidad, unidad_medida)
            if error_normalizacion:
                return False, f"Fila {idx}: {error_normalizacion}"

            detalles_normalizados.append({
                'id_materia': id_materia,
                'cantidad': cantidad,
                'unidad_medida': unidad_medida,
                'cantidad_requerida': cantidad_requerida,
            })

        receta.rendimiento = float(rendimiento)
        receta.cantidad_produccion = float(cantidad_produccion)
        receta.unidad_produccion = (unidad_produccion or '').strip()
        receta.nota = (nota or '').strip() or None
        receta.estado = bool(estado)

        RecetaDetalle.query.filter_by(id_receta=receta.id_receta).delete()

        for detalle in detalles_normalizados:
            db.session.add(RecetaDetalle(
                id_receta=receta.id_receta,
                id_materia=detalle['id_materia'],
                cantidad=detalle['cantidad'],
                unidad_medida=detalle['unidad_medida'],
                cantidad_requerida=detalle['cantidad_requerida'],
            ))

        db.session.commit()
        return True, "Receta actualizada correctamente"
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar receta completa: {str(e)}")
        return False, str(e)
