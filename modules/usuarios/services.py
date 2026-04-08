from sqlalchemy import text
from werkzeug.security import generate_password_hash
from models import db, Usuario, Persona, Rol
from flask import current_app
import logging

logger = logging.getLogger(__name__)


def _leer_valor(form_like, field_name):
    campo = getattr(form_like, field_name, None)
    if campo is not None and hasattr(campo, 'data'):
        return campo.data
    if hasattr(form_like, 'get'):
        return form_like.get(field_name)
    return None


def crear_usuario(form):
    try:
        password_hash = generate_password_hash(form.contrasena.data)
        
        # Obtener el rol para verificar que existe
        rol = Rol.query.filter_by(nombre=form.rol.data).first()
        if not rol:
            return False, f"Rol '{form.rol.data}' no encontrado"
        
        logger.info(f"Creando usuario: {form.username.data}, Rol: {rol.nombre} (ID: {rol.id_rol})")
        
        # Enviar el NOMBRE del rol en lugar del ID
        db.session.execute(text("""
            CALL sp_crearEmpleado(
                :nombre, :ap_p, :ap_m,
                :telefono, :correo, :direccion,
                :username, :password, :rol_nombre
            )
        """), {
            "nombre": form.nombre.data,
            "ap_p": form.apellido_p.data,
            "ap_m": form.apellido_m.data,
            "telefono": form.telefono.data,
            "correo": form.correo.data,
            "direccion": form.direccion.data,
            "username": form.username.data,
            "password": password_hash,
            "rol_nombre": rol.nombre  # Enviar el NOMBRE
        })

        db.session.commit()
        logger.info(f"Empleado creado: {form.username.data}")
        return True, "Empleado creado exitosamente"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear empleado: {str(e)}")
        return False, str(e)
    
def ver_usuarios():
    try:
        resultados = db.session.execute(text("CALL sp_verUsuarios()"))
        
        usuarios= []
        for row in resultados.fetchall():
            # Convertir estado a formato booleano o string
            estado = row[2]
            # Si es 1/0, convertir a True/False; si es string, dejar como está
            if isinstance(estado, (int, bool)):
                estado_display = 'Activo' if estado else 'Inactivo'
                estado_bool = bool(estado)
            else:
                estado_display = estado
                estado_bool = estado.lower() in ['Activo', 'True', '1', 'yes']
            
            usuarios.append({'id_usuario': row[0],
                'username': row[1],
                'estado_display': estado_display,
                'estado_bool': estado_bool,
                'nombre': row[3] if len(row) > 3 else None,
                'apellido_paterno': row[4] if len(row) > 4 else None,
                'apellido_materno': row[5] if len(row) > 5 else None,
                'rol_nombre': row[6] if len(row) > 6 else None,
            })
        return usuarios, None
    except Exception as e:
        return None, str(e)

def filtrar_usuarios(filtro):
    try:
        result = db.session.execute(
            text("CALL sp_filtrarUsuarios(:filtro)"), 
            {"filtro": filtro}
        )
        usuarios = result.fetchall()
        return usuarios, None
    except Exception as e:
        logger.error(f"Error al filtrar usuarios: {str(e)}")
        return None, str(e)
    
def desactivar_usuario(id_usuario):
    try:
        db.session.execute(
            text("CALL sp_eliminarUsuario(:id_usuario)"), 
            {"id_usuario": id_usuario}
        )
        db.session.commit()
        logger.info(f"Usuario {id_usuario} desactivado")
        return True, "Usuario desactivado exitosamente"
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al desactivar usuario: {str(e)}")
        return False, str(e)

def activar_usuario(id_usuario):
    try:
        db.session.execute(
            text("CALL sp_activarUsuario(:id_usuario)"), 
            {"id_usuario": id_usuario}
        )
        db.session.commit()
        logger.info(f"Usuario {id_usuario} activado")
        return True, "Usuario activado exitosamente"
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al activar usuario: {str(e)}")
        return False, str(e)
    
def obtener_usuario(id_usuario):
    try:
        result = db.session.execute(text("""
            SELECT 
                u.id_usuario,
                u.username,
                u.estado,
                r.id_rol,
                r.nombre as rol_nombre,
                p.nombre,
                p.apellido_p,
                p.apellido_m,
                p.correo,
                p.telefono,
                p.direccion
            FROM usuarios u
            INNER JOIN roles r ON u.id_rol = r.id_rol
            LEFT JOIN clientes c ON c.id_usuario = u.id_usuario
            LEFT JOIN empleados e ON e.id_usuario = u.id_usuario
            LEFT JOIN personas p ON p.id_persona = COALESCE(c.id_persona, e.id_persona)
            WHERE u.id_usuario = :id_usuario

        """), {"id_usuario": id_usuario})
        
        usuario = result.fetchone()
        if usuario:
            return {
                'id_usuario': usuario[0],
                'username': usuario[1],
                'estado': usuario[2],
                'id_rol': usuario[3],
                'rol_nombre': usuario[4],
                'nombre': usuario[5],
                'apellido_paterno': usuario[6],
                'apellido_materno': usuario[7],
                'correo': usuario[8],
                'telefono': usuario[9],
                'direccion': usuario[10]
            }, None
        return None, "Usuario no encontrado"
    except Exception as e:
        logger.error(f"Error al obtener usuario: {str(e)}")
        return None, str(e)
    
def actualizar_usuario(id_usuario, form):
    try:
        contrasena = _leer_valor(form, 'contrasena')
        password_hash = generate_password_hash(contrasena) if contrasena else None

        rol = Rol.query.filter_by(nombre=_leer_valor(form, 'rol')).first()
        if not rol:
            return False, "Rol no encontrado"

        db.session.execute(text("""
            CALL sp_actualizarUsuario(
                :id_usuario, :nombre, :ap_p, :ap_m,
                :telefono, :correo, :direccion,
                :username, :password, :id_rol
            )   
        """), {
            "id_usuario": id_usuario,
            "nombre": _leer_valor(form, 'nombre'),
            "ap_p": _leer_valor(form, 'apellido_p'),
            "ap_m": _leer_valor(form, 'apellido_m'),
            "telefono": _leer_valor(form, 'telefono') or None,
            "correo": _leer_valor(form, 'correo') or None,
            "direccion": _leer_valor(form, 'direccion') or None,
            "username": _leer_valor(form, 'username'),
            "password": password_hash,
            "id_rol": rol.id_rol
        })

        db.session.commit()
        logger.info(f"Usuario actualizado: {_leer_valor(form, 'username')}")
        return True, "Usuario actualizado"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al actualizar usuario: {str(e)}")
        return False, str(e)
    
# Función auxiliar para obtener todos los roles (para llenar selects)
def obtener_roles():
    """Obtiene todos los roles disponibles"""
    try:
        roles = Rol.query.all()
        return [(rol.id_rol, rol.nombre) for rol in roles], None
    except Exception as e:
        logger.error(f"Error al obtener roles: {str(e)}")
        return None, str(e)

def obtener_roles_nombres():
    """Obtiene solo los nombres de los roles"""
    try:
        roles = Rol.query.all()
        return [rol.nombre for rol in roles], None
    except Exception as e:
        logger.error(f"Error al obtener nombres de roles: {str(e)}")
        return None, str(e)