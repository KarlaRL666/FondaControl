from . import usuarios
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from forms import RegistroUsuarioForm, EditarUsuarioForm
from utils.security import role_required
from .services import (
    crear_usuario, ver_usuarios, desactivar_usuario,
    activar_usuario, obtener_usuario, actualizar_usuario,
    obtener_roles, obtener_roles_nombres
)
from models import db, Usuario, Persona
from datetime import datetime

@usuarios.route('/', methods=['GET'])
@login_required
@role_required(1)
def index():
    resultados, error = ver_usuarios()
    if error:
        current_app.logger.error(f"Error al obtener usuarios: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('dashboard.index'))
    return render_template('usuarios/index.html', usuarios=resultados, name=current_user.username)

@usuarios.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required(1)
def crear():
    form = RegistroUsuarioForm()

    roles, error = obtener_roles_nombres()
    if error:
        current_app.logger.error(f"Error al obtener roles: {str(error)}")
        flash(error, 'danger')
        roles = []

    if form.validate_on_submit():
        exito, error = crear_usuario(form)

        if exito:
            current_app.logger.info(f"Usuario creado: {form.username.data}")   
            flash('Usuario creado correctamente', 'success')
            return redirect(url_for('usuarios.index'))
        else:
            current_app.logger.error(f"Error al crear usuario: {str(error)}")
            flash(error, 'danger')

    return render_template('usuarios/crear.html', form=form)



@usuarios.route('/desactivar', methods=['POST'])
@login_required
@role_required(1)
def desactivar():
    id_usuario = request.form.get('id_usuario')

    exito, error = desactivar_usuario(id_usuario)

    if exito:
        current_app.logger.info(f"Usuario desactivado: ID {id_usuario}")
        flash('Usuario desactivado', 'success')
    else:
        current_app.logger.error(f"Error al desactivar usuario: {str(error)}")
        flash(error, 'danger')

    return redirect(url_for('usuarios.index'))

@usuarios.route('/activar', methods=['POST'])
@login_required
@role_required(1)
def activar():
    id_usuario = request.form.get('id_usuario')

    exito, error = activar_usuario(id_usuario)

    if exito:
        current_app.logger.info(f"Usuario activado: ID {id_usuario}")
        flash('Usuario activado', 'success')
    else:
        current_app.logger.error(f"Error al activar usuario: {str(error)}")
        flash(error, 'danger')

    return redirect(url_for('usuarios.index'))

@usuarios.route('/detalles')
@login_required
@role_required(1)
def detalles():
    id_usuario = request.args.get('id_usuario') 
    usuario, error = obtener_usuario(id_usuario)

    if error:
        current_app.logger.error(f"Error al obtener detalles del usuario: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('usuarios.index'))

    return render_template('usuarios/detalles.html', usuario=usuario)

@usuarios.route('/editar', methods=['GET', 'POST'])
@login_required
@role_required(1)
def editar():
    form = EditarUsuarioForm()
    
    id_usuario = request.args.get('id_usuario') or request.form.get('id_usuario')
    if not id_usuario:
        flash('No se recibió el usuario a editar.', 'warning')
        return redirect(url_for('usuarios.index'))

    usuario, error = obtener_usuario(id_usuario)
    if error:
        current_app.logger.error(f"Error al obtener usuario para edición: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('usuarios.index'))
    
    roles, _ = obtener_roles_nombres()
    form.rol.choices = [(r, r) for r in roles]
   
    if request.method == 'GET':
        form.nombre.data = usuario.get('nombre')
        form.apellido_p.data = usuario.get('apellido_paterno')
        form.apellido_m.data = usuario.get('apellido_materno')
        form.telefono.data = usuario.get('telefono')
        form.correo.data = usuario.get('correo')
        form.direccion.data = usuario.get('direccion')
        form.username.data = usuario.get('username')
        form.rol.data = usuario.get('rol_nombre')

    if request.method == 'POST' and form.validate_on_submit():
        exito, error = actualizar_usuario(id_usuario, form)

        if exito:
            current_app.logger.info(f"Usuario actualizado: {form.username.data}")
            flash('Usuario actualizado correctamente', 'success')
            return redirect(url_for('usuarios.index'))

        current_app.logger.error(f"Error al actualizar usuario: {str(error)}")
        flash(error, 'danger')
    
    return render_template('usuarios/editar.html', form=form, usuario=usuario)
