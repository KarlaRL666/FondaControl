from . import proveedores
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from forms import RegistroProveedorForm, EditarProveedorForm
from utils.security import role_required
from .services import (
    crear_proveedor, ver_proveedores, desactivar_proveedor,
    activar_proveedor, obtener_proveedor, actualizar_proveedor
)
from models import db, Proveedor, Persona
from datetime import datetime

@proveedores.route('/', methods=['GET'])
@login_required
@role_required(1)
def index():
    resultados, error = ver_proveedores()
    if error:
        current_app.logger.error(f"Error al obtener proveedores: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('dashboard.index'))
    return render_template('proveedores/index.html', proveedores=resultados, name=current_user.username)

@proveedores.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required(1)
def crear():
    form = RegistroProveedorForm()

    if form.validate_on_submit():
        exito, error = crear_proveedor(form)

        if exito:
            current_app.logger.info(f"Proveedor creado: {form.nombre.data}")   
            flash('Proveedor creado correctamente', 'success')
            return redirect(url_for('proveedores.index'))
        else:
            current_app.logger.error(f"Error al crear proveedor: {str(error)}")
            flash(error, 'danger')

    return render_template('proveedores/crear.html', form=form)



@proveedores.route('/desactivar', methods=['POST'])
@login_required
@role_required(1)
def desactivar():
    id_proveedor = request.form.get('id_proveedor')

    exito, error = desactivar_proveedor(id_proveedor)

    if exito:
        current_app.logger.info(f"Proveedor desactivado: ID {id_proveedor}")
        flash('Proveedor desactivado', 'success')
    else:
        current_app.logger.error(f"Error al desactivar proveedor: {str(error)}")
        flash(error, 'danger')

    return redirect(url_for('proveedores.index'))

@proveedores.route('/activar', methods=['POST'])
@login_required
@role_required(1)
def activar():
    id_proveedor = request.form.get('id_proveedor')

    exito, error = activar_proveedor(id_proveedor)

    if exito:
        current_app.logger.info(f"Proveedor activado: ID {id_proveedor}")
        flash('Proveedor activado', 'success')
    else:
        current_app.logger.error(f"Error al activar proveedor: {str(error)}")
        flash(error, 'danger')

    return redirect(url_for('proveedores.index'))

@proveedores.route('/detalles')
@login_required
@role_required(1)
def detalles():
    id_proveedor = request.args.get('id_proveedor') 
    proveedor, error = obtener_proveedor(id_proveedor)

    if error:
        current_app.logger.error(f"Error al obtener detalles del proveedor: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('proveedores.index'))

    return render_template('proveedores/detalles.html', proveedor=proveedor)

@proveedores.route('/editar', methods=['GET', 'POST'])
@login_required
@role_required(1)
def editar():
    form = EditarProveedorForm()
    
    id_proveedor = request.args.get('id_proveedor') or request.form.get('id_proveedor')
    if not id_proveedor:
        flash('No se recibió el proveedor a editar.', 'warning')
        return redirect(url_for('proveedores.index'))

    proveedor, error = obtener_proveedor(id_proveedor)
    if error:
        current_app.logger.error(f"Error al obtener proveedor para edición: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('proveedores.index'))
     
    if request.method == 'GET':
        form.nombre.data = proveedor.get('nombre')
        form.apellido_p.data = proveedor.get('apellido_paterno')
        form.apellido_m.data = proveedor.get('apellido_materno')
        form.telefono.data = proveedor.get('telefono')
        form.correo.data = proveedor.get('correo')
        form.direccion.data = proveedor.get('direccion')
        form.id_categoria_proveedor.data = proveedor.get('id_categoria_proveedor')

    if request.method == 'POST' and form.validate_on_submit():
        exito, error = actualizar_proveedor(id_proveedor, form)

        if exito:
            current_app.logger.info(f"Proveedor actualizado: {form.nombre.data}")
            flash('Proveedor actualizado correctamente', 'success')
            return redirect(url_for('proveedores.index'))

        current_app.logger.error(f"Error al actualizar proveedor: {str(error)}")
        flash(error, 'danger')
    
    return render_template('proveedores/editar.html', form=form, proveedor=proveedor)
