from . import ingredientes
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from forms import RegistrarIngredienteForm, EditarIngredienteForm
from utils.security import role_required
from .services import (
    crear_ingrediente,
    obtener_ingredientes,
    filtrar_ingredientes,
    desactivar_ingrediente,
    activar_ingrediente,
    actualizar_ingrediente,
    obtener_ingrediente,
    sugerir_categoria_ingrediente_por_proveedor,
    obtener_categorias_ingrediente_por_proveedor,
)
from models import CategoriaIngrediente, Proveedor, MateriaPrima


@ingredientes.route('/', methods=['GET', 'POST'])
@login_required
@role_required(1, 2)
def index():
    filtro = request.args.get('filtro')

    if filtro:
        ingredientes_list, error = filtrar_ingredientes(filtro)
    else:
        ingredientes_list, error = obtener_ingredientes()

    if error:
        current_app.logger.error(f"Error: {error}")
        flash(error, 'danger')
        return redirect(url_for('dashboard.index'))

    return render_template(
        'ingredientes/index.html',
        ingredientes=ingredientes_list,
        name=current_user.username
    )

@ingredientes.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required(1)
def crear():
    form = RegistrarIngredienteForm()

    # cargar proveedor y categorías dependientes del proveedor seleccionado
    form.id_proveedor.choices = [(0, 'Selecciona un proveedor')] + [(p.id_proveedor, p.persona.nombre) for p in Proveedor.query.all()]

    proveedor_id = request.values.get('id_proveedor', type=int)
    form.id_categoria_ingrediente.choices = []

    if proveedor_id:
        categorias_permitidas = obtener_categorias_ingrediente_por_proveedor(proveedor_id)
        form.id_categoria_ingrediente.choices = [
            (c['id_categoria_ingrediente'], c['nombre']) for c in categorias_permitidas
        ]

    if request.method == 'GET' and proveedor_id:
        form.id_proveedor.data = proveedor_id
        categoria_sugerida = sugerir_categoria_ingrediente_por_proveedor(proveedor_id)
        if categoria_sugerida:
            form.id_categoria_ingrediente.data = categoria_sugerida

    if form.validate_on_submit():
        exito, msg = crear_ingrediente(form)

        if exito:
            flash(msg, 'success')
            return redirect(url_for('ingredientes.index'))
        else:
            flash(msg, 'danger')

    return render_template('ingredientes/crear.html', form=form)

@ingredientes.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(1)
def editar(id):
    form = EditarIngredienteForm()

    ingrediente, error = obtener_ingrediente(id)
    if error:
        flash(error, 'danger')
        return redirect(url_for('ingredientes.index'))

    # cargar selects
    form.id_categoria_ingrediente.choices = [
        (c.id_categoria_ingrediente, c.nombre) for c in CategoriaIngrediente.query.order_by(CategoriaIngrediente.nombre.asc()).all()
    ]
    form.id_proveedor.choices = [(0, 'Selecciona un proveedor')] + [(p.id_proveedor, p.persona.nombre) for p in Proveedor.query.all()]

    if request.method == 'GET':
        form.nombre.data = ingrediente.get('nombre')
        form.unidad_medida.data = ingrediente.get('unidad_medida')
        form.stock_actual.data = ingrediente.get('stock_actual')
        form.stock_minimo.data = ingrediente.get('stock_minimo')
        form.precio.data = ingrediente.get('precio')
        form.porcentaje_merma.data = ingrediente.get('porcentaje_merma')
        form.factor_conversion.data = ingrediente.get('factor_conversion')
        form.id_categoria_ingrediente.data = ingrediente.get('id_categoria_ingrediente')
        form.id_proveedor.data = ingrediente.get('id_proveedor')

    if request.method == 'POST' and form.validate_on_submit():
        exito, msg = actualizar_ingrediente(id, form)

        if exito:
            flash(msg, 'success')
            return redirect(url_for('ingredientes.index'))
        else:
            flash(msg, 'danger')

    return render_template('ingredientes/editar.html', form=form, ingrediente=ingrediente)

@ingredientes.route('/desactivar', methods=['POST'])
@login_required
@role_required(1)
def desactivar():
    id_ingrediente = request.form.get('id')

    exito, msg = desactivar_ingrediente(id_ingrediente)

    if exito:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')

    return redirect(url_for('ingredientes.index'))

@ingredientes.route('/activar', methods=['POST'])
@login_required
@role_required(1)
def activar():
    id_ingrediente = request.form.get('id')

    exito, msg = activar_ingrediente(id_ingrediente)

    if exito:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')

    return redirect(url_for('ingredientes.index'))

@ingredientes.route('/detalle/<int:id>')
@login_required
@role_required(1)
def detalle(id):
    ingrediente = MateriaPrima.query.get_or_404(id)
    return render_template('ingredientes/detalle.html', ingrediente=ingrediente)


@ingredientes.route('/sugerir-categoria/<int:id_proveedor>', methods=['GET'])
@login_required
@role_required(1)
def sugerir_categoria(id_proveedor):
    categoria_id = sugerir_categoria_ingrediente_por_proveedor(id_proveedor)
    return jsonify({'id_categoria_ingrediente': categoria_id})


@ingredientes.route('/categorias-por-proveedor/<int:id_proveedor>', methods=['GET'])
@login_required
@role_required(1)
def categorias_por_proveedor(id_proveedor):
    categorias = obtener_categorias_ingrediente_por_proveedor(id_proveedor)
    sugerida = sugerir_categoria_ingrediente_por_proveedor(id_proveedor)
    return jsonify({'categorias': categorias, 'id_categoria_ingrediente_sugerida': sugerida})
