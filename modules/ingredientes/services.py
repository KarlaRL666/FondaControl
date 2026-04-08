from models import db, MateriaPrima, CategoriaIngrediente, Proveedor
import logging

logger = logging.getLogger(__name__)


def _proveedor_nombre(proveedor):
    if not proveedor or not proveedor.persona:
        return 'N/A'
    return f"{proveedor.persona.nombre} {proveedor.persona.apellido_p or ''}".strip()


def _to_dict(materia):
    return {
        'id_materia': materia.id_materia,
        'nombre': materia.nombre,
        'unidad_medida': materia.unidad_medida,
        'stock_actual': materia.stock_actual,
        'stock_minimo': materia.stock_minimo,
        'precio': materia.precio,
        'porcentaje_merma': materia.porcentaje_merma,
        'factor_conversion': materia.factor_conversion,
        'estado': materia.estado,
        'categoria_nombre': materia.categoria_ingrediente.nombre if materia.categoria_ingrediente else 'N/A',
        'proveedor_nombre': _proveedor_nombre(materia.proveedor),
        'id_categoria_ingrediente': materia.id_categoria_ingrediente,
        'id_proveedor': materia.id_proveedor,
    }


def crear_ingrediente(form):
    try:
        existe = MateriaPrima.query.filter_by(nombre=form.nombre.data).first()
        if existe:
            return False, 'Ya existe un ingrediente con ese nombre.'

        nuevo = MateriaPrima(
            nombre=form.nombre.data,
            unidad_medida=form.unidad_medida.data,
            stock_actual=form.stock_actual.data if form.stock_actual.data is not None else 0,
            stock_minimo=form.stock_minimo.data,
            precio=form.precio.data,
            porcentaje_merma=form.porcentaje_merma.data if form.porcentaje_merma.data is not None else 0,
            factor_conversion=form.factor_conversion.data if form.factor_conversion.data is not None else 1,
            id_categoria_ingrediente=form.id_categoria_ingrediente.data,
            id_proveedor=form.id_proveedor.data,
            estado=True,
        )

        db.session.add(nuevo)
        db.session.commit()
        logger.info(f"Ingrediente creado: {nuevo.nombre}")
        return True, 'Ingrediente creado correctamente.'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear ingrediente: {str(e)}")
        return False, str(e)


def obtener_ingredientes():
    try:
        materias = MateriaPrima.query.order_by(MateriaPrima.nombre.asc()).all()
        return [_to_dict(m) for m in materias], None
    except Exception as e:
        logger.error(f"Error al obtener ingredientes: {str(e)}")
        return None, str(e)


def filtrar_ingredientes(filtro):
    try:
        term = f"%{filtro}%"
        materias = MateriaPrima.query.join(CategoriaIngrediente, MateriaPrima.id_categoria_ingrediente == CategoriaIngrediente.id_categoria_ingrediente).filter(
            (MateriaPrima.nombre.ilike(term)) |
            (CategoriaIngrediente.nombre.ilike(term))
        ).order_by(MateriaPrima.nombre.asc()).all()
        return [_to_dict(m) for m in materias], None
    except Exception as e:
        logger.error(f"Error al filtrar ingredientes: {str(e)}")
        return None, str(e)


def obtener_ingrediente(id_ingrediente):
    try:
        materia = MateriaPrima.query.get(id_ingrediente)
        if not materia:
            return None, 'Ingrediente no encontrado.'
        return _to_dict(materia), None
    except Exception as e:
        logger.error(f"Error al obtener ingrediente: {str(e)}")
        return None, str(e)


def actualizar_ingrediente(id_ingrediente, form):
    try:
        materia = MateriaPrima.query.get(id_ingrediente)
        if not materia:
            return False, 'Ingrediente no encontrado.'

        if form.nombre.data:
            existente = MateriaPrima.query.filter(
                MateriaPrima.nombre == form.nombre.data,
                MateriaPrima.id_materia != id_ingrediente
            ).first()
            if existente:
                return False, 'Ya existe otro ingrediente con ese nombre.'
            materia.nombre = form.nombre.data

        if form.unidad_medida.data:
            materia.unidad_medida = form.unidad_medida.data
        if form.stock_actual.data is not None:
            materia.stock_actual = form.stock_actual.data
        if form.stock_minimo.data is not None:
            materia.stock_minimo = form.stock_minimo.data
        if form.precio.data is not None:
            materia.precio = form.precio.data
        if form.porcentaje_merma.data is not None:
            materia.porcentaje_merma = form.porcentaje_merma.data
        if form.factor_conversion.data is not None:
            materia.factor_conversion = form.factor_conversion.data
        if form.id_categoria_ingrediente.data:
            materia.id_categoria_ingrediente = form.id_categoria_ingrediente.data
        if form.id_proveedor.data:
            materia.id_proveedor = form.id_proveedor.data

        db.session.commit()
        return True, 'Ingrediente actualizado correctamente.'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar ingrediente: {str(e)}")
        return False, str(e)


def desactivar_ingrediente(id_ingrediente):
    try:
        materia = MateriaPrima.query.get(id_ingrediente)
        if not materia:
            return False, 'Ingrediente no encontrado.'
        materia.estado = False
        db.session.commit()
        return True, 'Ingrediente desactivado correctamente.'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al desactivar ingrediente: {str(e)}")
        return False, str(e)


def activar_ingrediente(id_ingrediente):
    try:
        materia = MateriaPrima.query.get(id_ingrediente)
        if not materia:
            return False, 'Ingrediente no encontrado.'
        materia.estado = True
        db.session.commit()
        return True, 'Ingrediente activado correctamente.'
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al activar ingrediente: {str(e)}")
        return False, str(e)


def sugerir_categoria_ingrediente_por_proveedor(id_proveedor):
    proveedor = Proveedor.query.get(id_proveedor)
    if not proveedor or not proveedor.categoria_proveedor:
        return None

    nombre_categoria_proveedor = proveedor.categoria_proveedor.nombre.strip().lower()
    categoria = CategoriaIngrediente.query.filter(
        db.func.lower(CategoriaIngrediente.nombre) == nombre_categoria_proveedor
    ).first()

    if categoria:
        return categoria.id_categoria_ingrediente

    categoria_default = CategoriaIngrediente.query.order_by(CategoriaIngrediente.nombre.asc()).first()
    return categoria_default.id_categoria_ingrediente if categoria_default else None


def obtener_categorias_ingrediente_por_proveedor(id_proveedor):
    proveedor = Proveedor.query.get(id_proveedor)
    if not proveedor or not proveedor.categoria_proveedor:
        return []

    nombre_categoria_proveedor = proveedor.categoria_proveedor.nombre.strip().lower()
    categoria_match = CategoriaIngrediente.query.filter(
        db.func.lower(CategoriaIngrediente.nombre) == nombre_categoria_proveedor
    ).all()

    return [{'id_categoria_ingrediente': c.id_categoria_ingrediente, 'nombre': c.nombre} for c in categoria_match]

def verificar_stock_minimo(id_ingrediente):
    try:
        materias_bajas = MateriaPrima.query.filter(MateriaPrima.stock_actual < MateriaPrima.stock_minimo).all()

        alertas = []
        
        for m in materias_bajas:
            alertas.append({
                'id_materia': m.id_materia,
                'nombre': m.nombre,
                'stock_actual': m.stock_actual,
                'stock_minimo': m.stock_minimo,
                'unidad_medida': m.unidad_medida
            })
        return alertas
    except Exception as e:
        return []