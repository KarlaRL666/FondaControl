from datetime import datetime

from flask import current_app
from sqlalchemy import func, or_, text
from werkzeug.security import generate_password_hash

from models import db, Cliente, Persona, Pedido, Usuario
from utils.bitacora import registrar_evento


def obtener_clientes(q=None, estado='all'):
    try:
        query = (
            db.session.query(
                Cliente.id_cliente.label('id_cliente'),
                Usuario.id_usuario.label('id_usuario'),
                Usuario.username.label('username'),
                Usuario.estado.label('estado_usuario'),
                Persona.nombre.label('nombre'),
                Persona.apellido_p.label('apellido_p'),
                Persona.apellido_m.label('apellido_m'),
                Persona.correo.label('correo'),
                Persona.telefono.label('telefono'),
                Persona.direccion.label('direccion'),
                func.count(Pedido.id_pedido).label('total_pedidos'),
            )
            .join(Persona, Persona.id_persona == Cliente.id_persona)
            .join(Usuario, Usuario.id_usuario == Cliente.id_usuario)
            .outerjoin(Pedido, Pedido.id_cliente == Cliente.id_cliente)
            .group_by(
                Cliente.id_cliente,
                Usuario.id_usuario,
                Usuario.username,
                Usuario.estado,
                Persona.nombre,
                Persona.apellido_p,
                Persona.apellido_m,
                Persona.correo,
                Persona.telefono,
                Persona.direccion,
            )
            .order_by(Persona.nombre.asc(), Persona.apellido_p.asc())
        )

        if q:
            term = f"%{q}%"
            query = query.filter(or_(
                Persona.nombre.ilike(term),
                Persona.apellido_p.ilike(term),
                Persona.apellido_m.ilike(term),
                Persona.correo.ilike(term),
                Persona.telefono.ilike(term),
                Usuario.username.ilike(term),
            ))

        if estado in {'activo', 'inactivo'}:
            query = query.filter(Usuario.estado.is_(estado == 'activo'))

        clientes = []
        for row in query.all():
            nombre_completo = ' '.join(part for part in [row.nombre, row.apellido_p, row.apellido_m] if part)
            clientes.append({
                'id_cliente': row.id_cliente,
                'id_usuario': row.id_usuario,
                'username': row.username,
                'estado_bool': bool(row.estado_usuario),
                'estado_display': 'Activo' if row.estado_usuario else 'Inactivo',
                'nombre': row.nombre,
                'apellido_paterno': row.apellido_p,
                'apellido_materno': row.apellido_m,
                'nombre_completo': nombre_completo,
                'correo': row.correo,
                'telefono': row.telefono,
                'direccion': row.direccion,
                'total_pedidos': int(row.total_pedidos or 0),
            })

        return clientes, None
    except Exception as e:
        current_app.logger.error(f"Error al obtener clientes: {str(e)}")
        return None, str(e)


def obtener_cliente(id_cliente):
    try:
        row = (
            db.session.query(
                Cliente.id_cliente.label('id_cliente'),
                Usuario.id_usuario.label('id_usuario'),
                Usuario.username.label('username'),
                Usuario.estado.label('estado_usuario'),
                Persona.nombre.label('nombre'),
                Persona.apellido_p.label('apellido_p'),
                Persona.apellido_m.label('apellido_m'),
                Persona.correo.label('correo'),
                Persona.telefono.label('telefono'),
                Persona.direccion.label('direccion'),
                func.count(Pedido.id_pedido).label('total_pedidos'),
            )
            .join(Persona, Persona.id_persona == Cliente.id_persona)
            .join(Usuario, Usuario.id_usuario == Cliente.id_usuario)
            .outerjoin(Pedido, Pedido.id_cliente == Cliente.id_cliente)
            .filter(Cliente.id_cliente == id_cliente)
            .group_by(
                Cliente.id_cliente,
                Usuario.id_usuario,
                Usuario.username,
                Usuario.estado,
                Persona.nombre,
                Persona.apellido_p,
                Persona.apellido_m,
                Persona.correo,
                Persona.telefono,
                Persona.direccion,
            )
            .first()
        )

        if not row:
            return None, 'Cliente no encontrado'

        pedidos = (
            Pedido.query
            .filter(Pedido.id_cliente == id_cliente)
            .order_by(Pedido.fecha.desc())
            .all()
        )

        pedidos_data = [
            {
                'id_pedido': pedido.id_pedido,
                'fecha': pedido.fecha,
                'fecha_entrega': pedido.fecha_entrega,
                'estado': pedido.estado,
                'total': float(pedido.total or 0),
                'metodo_pago': pedido.meta_pedido.metodo_pago if pedido.meta_pedido else 'N/D',
            }
            for pedido in pedidos
        ]

        nombre_completo = ' '.join(part for part in [row.nombre, row.apellido_p, row.apellido_m] if part)
        return {
            'id_cliente': row.id_cliente,
            'id_usuario': row.id_usuario,
            'username': row.username,
            'estado_bool': bool(row.estado_usuario),
            'estado_display': 'Activo' if row.estado_usuario else 'Inactivo',
            'nombre': row.nombre,
            'apellido_paterno': row.apellido_p,
            'apellido_materno': row.apellido_m,
            'nombre_completo': nombre_completo,
            'correo': row.correo,
            'telefono': row.telefono,
            'direccion': row.direccion,
            'total_pedidos': int(row.total_pedidos or 0),
            'pedidos': pedidos_data,
        }, None
    except Exception as e:
        current_app.logger.error(f"Error al obtener cliente: {str(e)}")
        return None, str(e)


def validar_datos_cliente(id_usuario, id_persona, username, correo, telefono):
    usuario_existente = Usuario.query.filter(
        Usuario.id_usuario != (id_usuario or 0),
        Usuario.username == username,
    ).first()

    persona_existente = Persona.query.filter(
        Persona.id_persona != (id_persona or 0),
        or_(
            Persona.correo == correo,
            Persona.telefono == telefono,
        )
    ).first()

    if usuario_existente:
        return False, 'El nombre de usuario ya está en uso.'

    if persona_existente:
        if persona_existente.correo == correo:
            return False, 'El correo electrónico ya está registrado.'
        if persona_existente.telefono == telefono:
            return False, 'El número de teléfono ya está registrado.'

    return True, None


def crear_cliente_admin(form, id_usuario_actor=None):
    try:
        password_hash = generate_password_hash(form.contrasena.data)

        db.session.execute(text("""
            CALL sp_crearCliente(
                :nombre, :ap_p, :ap_m,
                :telefono, :correo, :direccion,
                :username, :password
            )
        """), {
            'nombre': form.nombre.data,
            'ap_p': form.apellido_p.data,
            'ap_m': form.apellido_m.data,
            'telefono': form.telefono.data,
            'correo': form.correo.data,
            'direccion': form.direccion.data,
            'username': form.username.data,
            'password': password_hash,
        })

        usuario_creado = Usuario.query.filter_by(username=form.username.data).first()
        cliente_creado = Cliente.query.filter_by(id_usuario=usuario_creado.id_usuario).first() if usuario_creado else None

        registrar_evento(
            modulo='clientes',
            entidad='Cliente',
            accion='Crear cliente',
            id_usuario=id_usuario_actor,
            id_entidad=cliente_creado.id_cliente if cliente_creado else None,
            estado_nuevo='Activo',
            descripcion=f"Se creó el cliente {form.nombre.data} {form.apellido_p.data}",
        )

        db.session.commit()
        return True, 'Cliente creado exitosamente'
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error al crear cliente: {str(e)}')
        return False, str(e)


def actualizar_cliente_admin(id_cliente, form, id_usuario_actor=None):
    try:
        cliente = Cliente.query.get(id_cliente)
        if not cliente:
            return False, 'Cliente no encontrado'

        usuario = cliente.usuario
        persona = cliente.persona
        if not usuario or not persona:
            return False, 'Cliente incompleto'

        username = (form.username.data or '').strip()
        correo = (form.correo.data or '').strip().lower()
        telefono = (form.telefono.data or '').strip()
        valido, mensaje = validar_datos_cliente(usuario.id_usuario, persona.id_persona, username, correo, telefono)
        if not valido:
            return False, mensaje

        usuario.username = username
        if form.contrasena.data:
            usuario.contrasena = generate_password_hash(form.contrasena.data)

        persona.nombre = form.nombre.data.strip()
        persona.apellido_p = form.apellido_p.data.strip()
        persona.apellido_m = (form.apellido_m.data or '').strip() or None
        persona.telefono = telefono
        persona.correo = correo
        persona.direccion = (form.direccion.data or '').strip() or None

        registrar_evento(
            modulo='clientes',
            entidad='Cliente',
            accion='Actualizar cliente',
            id_usuario=id_usuario_actor,
            id_entidad=cliente.id_cliente,
            estado_anterior='Activo' if usuario.estado else 'Inactivo',
            estado_nuevo='Activo' if usuario.estado else 'Inactivo',
            descripcion=f"Se actualizó el cliente {persona.nombre} {persona.apellido_p}",
        )

        db.session.commit()
        return True, 'Cliente actualizado correctamente'
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error al actualizar cliente: {str(e)}')
        return False, str(e)


def eliminar_cliente(id_cliente, id_usuario_actor=None):
    try:
        cliente = Cliente.query.get(id_cliente)
        if not cliente:
            return False, 'Cliente no encontrado'

        if cliente.usuario:
            cliente.usuario.estado = False
            registrar_evento(
                modulo='clientes',
                entidad='Cliente',
                accion='Desactivar cliente',
                id_usuario=id_usuario_actor,
                id_entidad=cliente.id_cliente,
                estado_anterior='Activo',
                estado_nuevo='Inactivo',
                descripcion=f"Se desactivó el cliente {cliente.usuario.username}",
            )
            db.session.commit()
            return True, 'Cliente desactivado correctamente'

        return False, 'No fue posible desactivar el cliente'
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error al desactivar cliente: {str(e)}')
        return False, str(e)


def activar_cliente(id_cliente, id_usuario_actor=None):
    try:
        cliente = Cliente.query.get(id_cliente)
        if not cliente:
            return False, 'Cliente no encontrado'

        if cliente.usuario:
            cliente.usuario.estado = True
            registrar_evento(
                modulo='clientes',
                entidad='Cliente',
                accion='Activar cliente',
                id_usuario=id_usuario_actor,
                id_entidad=cliente.id_cliente,
                estado_anterior='Inactivo',
                estado_nuevo='Activo',
                descripcion=f"Se activó el cliente {cliente.usuario.username}",
            )
            db.session.commit()
            return True, 'Cliente activado correctamente'

        return False, 'No fue posible activar el cliente'
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error al activar cliente: {str(e)}')
        return False, str(e)
