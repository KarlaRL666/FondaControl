from . import clientes
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from utils.security import role_required
from forms import RegistroClienteForm, EditarClienteForm
from .services import (
    obtener_clientes,
    obtener_cliente,
    crear_cliente_admin,
    actualizar_cliente_admin,
    eliminar_cliente,
    activar_cliente,
)


@clientes.route('/', methods=['GET'])
@login_required
@role_required(1)
def index():
    q = (request.args.get('q') or '').strip()
    estado = (request.args.get('estado') or 'all').strip().lower()

    clientes_list, error = obtener_clientes(q=q, estado=estado)
    if error:
        current_app.logger.error(f'Error al cargar clientes: {error}')
        flash('Error al cargar los clientes', 'danger')
        return redirect(url_for('dashboard.index'))

    total = len(clientes_list)
    activos = sum(1 for cliente in clientes_list if cliente['estado_bool'])
    inactivos = total - activos

    return render_template(
        'clientes/index.html',
        clientes=clientes_list,
        total=total,
        activos=activos,
        inactivos=inactivos,
        q=q,
        estado=estado,
    )


@clientes.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required(1)
def crear():
    form = RegistroClienteForm()

    if form.validate_on_submit():
        exito, mensaje = crear_cliente_admin(form, id_usuario_actor=current_user.id_usuario)
        flash(mensaje, 'success' if exito else 'danger')
        if exito:
            return redirect(url_for('clientes.index'))

    return render_template('clientes/crear.html', form=form)


@clientes.route('/ver/<int:id_cliente>', methods=['GET'])
@login_required
@role_required(1)
def ver(id_cliente):
    cliente, error = obtener_cliente(id_cliente)
    if error:
        flash(error, 'danger')
        return redirect(url_for('clientes.index'))

    return render_template('clientes/detalles.html', cliente=cliente)


@clientes.route('/editar/<int:id_cliente>', methods=['GET', 'POST'])
@login_required
@role_required(1)
def editar(id_cliente):
    form = EditarClienteForm()
    cliente, error = obtener_cliente(id_cliente)
    if error:
        flash(error, 'danger')
        return redirect(url_for('clientes.index'))

    if request.method == 'GET':
        form.nombre.data = cliente.get('nombre')
        form.apellido_p.data = cliente.get('apellido_paterno')
        form.apellido_m.data = cliente.get('apellido_materno')
        form.telefono.data = cliente.get('telefono')
        form.correo.data = cliente.get('correo')
        form.direccion.data = cliente.get('direccion')
        form.username.data = cliente.get('username')

    if form.validate_on_submit():
        exito, mensaje = actualizar_cliente_admin(id_cliente, form, id_usuario_actor=current_user.id_usuario)
        flash(mensaje, 'success' if exito else 'danger')
        if exito:
            return redirect(url_for('clientes.ver', id_cliente=id_cliente))

    return render_template('clientes/editar.html', form=form, cliente=cliente)


@clientes.route('/eliminar/<int:id_cliente>', methods=['POST'])
@login_required
@role_required(1)
def eliminar(id_cliente):
    exito, mensaje = eliminar_cliente(id_cliente, id_usuario_actor=current_user.id_usuario)
    flash(mensaje, 'success' if exito else 'danger')
    return redirect(url_for('clientes.index'))


@clientes.route('/activar/<int:id_cliente>', methods=['POST'])
@login_required
@role_required(1)
def activar(id_cliente):
    exito, mensaje = activar_cliente(id_cliente, id_usuario_actor=current_user.id_usuario)
    flash(mensaje, 'success' if exito else 'danger')
    return redirect(url_for('clientes.index'))