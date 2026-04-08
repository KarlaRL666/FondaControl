from sqlalchemy.exc import SQLAlchemyError
from models import db, Persona, Proveedor, CategoriaProveedor, CategoriaIngrediente
import logging

logger = logging.getLogger(__name__)


def _leer_valor(form_like, field_name):
    campo = getattr(form_like, field_name, None)
    if campo is not None and hasattr(campo, 'data'):
        return campo.data
    if hasattr(form_like, 'get'):
        return form_like.get(field_name)
    return None


def _obtener_o_crear_categoria(form_like):
    usar_nueva = str(_leer_valor(form_like, 'usar_categoria_nueva') or '').lower() in ('1', 'true', 'on', 'yes')
    nombre_nueva = (_leer_valor(form_like, 'nombre_nueva_categoria') or '').strip()

    if usar_nueva and nombre_nueva:
        categoria = CategoriaProveedor.query.filter(db.func.lower(CategoriaProveedor.nombre) == nombre_nueva.lower()).first()
        if not categoria:
            categoria = CategoriaProveedor(nombre=nombre_nueva, estado=True)
            db.session.add(categoria)
            db.session.flush()

        # Mantener catálogo paralelo para sugerencias de ingredientes
        categoria_ing = CategoriaIngrediente.query.filter(db.func.lower(CategoriaIngrediente.nombre) == nombre_nueva.lower()).first()
        if not categoria_ing:
            db.session.add(CategoriaIngrediente(nombre=nombre_nueva, estado=True))

        return categoria.id_categoria_proveedor, None

    categoria_id = _leer_valor(form_like, 'id_categoria_proveedor')
    if not categoria_id:
        return None, "Categoría de proveedor no válida"

    categoria = CategoriaProveedor.query.get(int(categoria_id))
    if not categoria:
        return None, "Categoría de proveedor no válida"

    return categoria.id_categoria_proveedor, None


def _normalizar_error_bd(error):
    original = getattr(error, "orig", None)
    if original is not None and getattr(original, "args", None):
        mensaje = str(original.args[1] if len(original.args) > 1 else original.args[0])
    else:
        mensaje = str(error)

    if "Correo o telefono ya existen" in mensaje:
        return "Correo o teléfono ya existen"

    return mensaje

def crear_proveedor(form):
    try:
        logger.info(f"Creando proveedor: {form.nombre.data}")

        categoria_id, error_categoria = _obtener_o_crear_categoria({
            'id_categoria_proveedor': form.id_categoria_proveedor.data,
            'usar_categoria_nueva': form.usar_categoria_nueva.data,
            'nombre_nueva_categoria': form.nombre_nueva_categoria.data,
        })
        if error_categoria:
            return False, error_categoria

        existe_tel = Persona.query.filter_by(telefono=form.telefono.data).first()
        if existe_tel:
            return False, "El teléfono ya está registrado"

        existe_correo = Persona.query.filter_by(correo=form.correo.data).first()
        if existe_correo:
            return False, "El correo ya está registrado"

        persona = Persona(
            nombre=form.nombre.data,
            apellido_p=form.apellido_p.data,
            apellido_m=form.apellido_m.data,
            telefono=form.telefono.data,
            correo=form.correo.data,
            direccion=form.direccion.data,
        )
        db.session.add(persona)
        db.session.flush()

        proveedor = Proveedor(
            id_persona=persona.id_persona,
            id_categoria_proveedor=categoria_id,
            estado=True,
        )
        db.session.add(proveedor)

        db.session.commit()
        logger.info(f"Proveedor creado: {form.nombre.data}")
        return True, "Proveedor creado exitosamente"

    except SQLAlchemyError as e:
        db.session.rollback()
        mensaje = _normalizar_error_bd(e)
        logger.error(f"Error al crear proveedor: {mensaje}")
        return False, mensaje

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear proveedor: {str(e)}")
        return False, str(e)

def ver_proveedores():
    try:
        proveedores_db = Proveedor.query.join(Persona).join(CategoriaProveedor).order_by(Persona.nombre.asc()).all()

        proveedores = []
        for prov in proveedores_db:
            persona = prov.persona
            proveedores.append({
                'id_proveedor': prov.id_proveedor,
                'nombre': persona.nombre if persona else None,
                'apellido_paterno': persona.apellido_p if persona else None,
                'apellido_materno': persona.apellido_m if persona else None,
                'telefono': persona.telefono if persona else None,
                'correo': persona.correo if persona else None,
                'categoria_proveedor': prov.categoria_proveedor.nombre if prov.categoria_proveedor else 'N/A',
                'estado_display': 'Activo' if prov.estado else 'Inactivo',
                'estado_bool': bool(prov.estado)
            })
        return proveedores, None
    except Exception as e:
        return None, str(e)

def filtrar_proveedores(filtro):
    try:
        term = f"%{filtro}%"
        proveedores = Proveedor.query.join(Persona).join(CategoriaProveedor).filter(
            (Persona.nombre.ilike(term)) |
            (Persona.apellido_p.ilike(term)) |
            (Persona.apellido_m.ilike(term)) |
            (Persona.correo.ilike(term)) |
            (CategoriaProveedor.nombre.ilike(term))
        ).all()
        return proveedores, None
    except Exception as e:
        logger.error(f"Error al filtrar proveedores: {str(e)}")
        return None, str(e)
    
def desactivar_proveedor(id_proveedor):
    try:
        proveedor = Proveedor.query.get(id_proveedor)
        if not proveedor:
            return False, "Proveedor no encontrado"
        proveedor.estado = False
        db.session.commit()
        logger.info(f"Proveedor {id_proveedor} desactivado")
        return True, "Proveedor desactivado exitosamente"
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al desactivar proveedor: {str(e)}")
        return False, str(e)

def activar_proveedor(id_proveedor):
    try:
        proveedor = Proveedor.query.get(id_proveedor)
        if not proveedor:
            return False, "Proveedor no encontrado"
        proveedor.estado = True
        db.session.commit()
        logger.info(f"Proveedor {id_proveedor} activado")
        return True, "Proveedor activado exitosamente"
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al activar proveedor: {str(e)}")
        return False, str(e)

def obtener_proveedor(id_proveedor):
    try:
        proveedor = Proveedor.query.get(id_proveedor)
        if proveedor and proveedor.persona:
            compras = []
            compras_ordenadas = sorted(
                proveedor.compras or [],
                key=lambda compra: compra.fecha or datetime.min,
                reverse=True,
            )

            for compra in compras_ordenadas:
                compras.append({
                    'id_compra': compra.id_compra,
                    'fecha': compra.fecha,
                    'fecha_entrega': compra.fecha_entrega,
                    'estado': compra.estado,
                    'total': compra.total,
                    'metodo_pago': compra.metodo_pago,
                    'detalles': [
                        {
                            'materia': detalle.materia_prima.nombre if detalle.materia_prima else 'Materia prima',
                            'cantidad': detalle.cantidad,
                            'precio_u': detalle.precio_u,
                            'subtotal': detalle.subtotal,
                        }
                        for detalle in compra.detalles
                    ],
                })

            return {
                'id_proveedor': proveedor.id_proveedor,
                'nombre': proveedor.persona.nombre,
                'apellido_paterno': proveedor.persona.apellido_p,
                'apellido_materno': proveedor.persona.apellido_m,
                'correo': proveedor.persona.correo,
                'telefono': proveedor.persona.telefono,
                'direccion': proveedor.persona.direccion,
                'id_categoria_proveedor': proveedor.id_categoria_proveedor,
                'categoria_proveedor': proveedor.categoria_proveedor.nombre if proveedor.categoria_proveedor else None,
                'estado': proveedor.estado,
                'compras': compras,
            }, None
        return None, "Proveedor no encontrado"
    except Exception as e:
        logger.error(f"Error al obtener proveedor: {str(e)}")
        return None, str(e)

def actualizar_proveedor(id_proveedor, form):
    try:
        proveedor = Proveedor.query.get(id_proveedor)
        if not proveedor or not proveedor.persona:
            return False, "Proveedor no encontrado"

        categoria_id, error_categoria = _obtener_o_crear_categoria(form)
        if error_categoria:
            return False, error_categoria

        proveedor.persona.nombre = _leer_valor(form, 'nombre')
        proveedor.persona.apellido_p = _leer_valor(form, 'apellido_p')
        proveedor.persona.apellido_m = _leer_valor(form, 'apellido_m')
        proveedor.persona.telefono = _leer_valor(form, 'telefono') or None
        proveedor.persona.correo = _leer_valor(form, 'correo') or None
        proveedor.persona.direccion = _leer_valor(form, 'direccion') or None
        proveedor.id_categoria_proveedor = int(categoria_id)

        db.session.commit()
        logger.info(f"Proveedor actualizado: {_leer_valor(form, 'nombre')}")
        return True, "Proveedor actualizado"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar proveedor: {str(e)}")
        return False, str(e)