from . import productos
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from forms import CrearProductoForm, EditarProductoForm
from utils.security import role_required
from .services import (
    crear_producto, obtener_productos, desactivar_producto,
    activar_producto, obtener_producto, actualizar_producto, buscar_productos, obtener_categorias
)


@productos.route('/', methods=['GET'])
@login_required
@role_required(1, 2, 3)
def index():
    """Listar todos los productos"""
    categorias, error = obtener_categorias()
    if error:
        current_app.logger.error(f"Error al obtener categorías: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('dashboard.index'))
    
    resultados, error = obtener_productos()
    if error:
        current_app.logger.error(f"Error al obtener productos: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('dashboard.index'))

    productos_stock_bajo = [
        producto for producto in resultados
        if float(producto.get('stock_actual') or 0) <= float(producto.get('stock_minimo') or 0)
    ]
    
    return render_template(
        'productos/index.html',
        productos=resultados,
        productos_stock_bajo=productos_stock_bajo,
        name=current_user.username,
        categorias=categorias,
    )


@productos.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required(1)
def crear():
    """Crear un nuevo producto"""
    form = CrearProductoForm()
    categorias, error = obtener_categorias()
    if error:
        current_app.logger.error(f"Error al obtener categorías: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('productos.index'))
    form.id_categoria_platillo.choices = [(cat.id_categoria_platillo, cat.nombre) for cat in categorias]
    if form.validate_on_submit():
        resultado = crear_producto(form)
        exito, error, id_producto_nuevo = resultado
        
        if exito:
            current_app.logger.info(f"Producto creado: {form.nombre.data}")
            flash('Producto creado correctamente. Ahora crea su receta.', 'success')
            return redirect(url_for('recetas.crear', id_producto=id_producto_nuevo))
        else:
            current_app.logger.error(f"Error al crear producto: {str(error)}")
            flash(error, 'danger')
    
    return render_template('productos/crear.html', form=form)


@productos.route('/editar', methods=['GET', 'POST'])
@login_required
@role_required(1)
def editar():
    """Editar un producto existente"""
    form = EditarProductoForm()
    
    id_producto = request.args.get('id_producto') or request.form.get('id_producto')
    if not id_producto:
        flash('No se recibió el producto a editar.', 'warning')
        return redirect(url_for('productos.index'))
    
    producto, error = obtener_producto(id_producto)
    if error:
        current_app.logger.error(f"Error al obtener producto para edición: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('productos.index'))
    
    if request.method == 'GET':
        form.nombre.data = producto.get('nombre')
        form.descripcion.data = producto.get('descripcion')
        form.precio.data = producto.get('precio')
        form.stock_actual.data = producto.get('stock_actual')
        form.stock_minimo.data = producto.get('stock_minimo')
        form.id_categoria_platillo.data = producto.get('id_categoria_platillo')
        form.imagen.data = producto.get('imagen')
    
    if request.method == 'POST' and form.validate_on_submit():
        exito, error = actualizar_producto(id_producto, form)
        
        if exito:
            current_app.logger.info(f"Producto actualizado: {form.nombre.data}")
            flash('Producto actualizado correctamente', 'success')
            return redirect(url_for('productos.index'))
        else:
            current_app.logger.error(f"Error al actualizar producto: {str(error)}")
            flash(error, 'danger')
    
    return render_template('productos/editar.html', form=form, producto=producto)


@productos.route('/desactivar', methods=['POST'])
@login_required
@role_required(1)
def desactivar():
    """Desactivar un producto"""
    id_producto = request.form.get('id_producto')
    
    exito, error = desactivar_producto(id_producto)
    
    if exito:
        current_app.logger.info(f"Producto desactivado: ID {id_producto}")
        flash('Producto desactivado', 'success')
    else:
        current_app.logger.error(f"Error al desactivar producto: {str(error)}")
        flash(error, 'danger')
    
    return redirect(url_for('productos.index'))


@productos.route('/activar', methods=['POST'])
@login_required
@role_required(1)
def activar():
    """Activar un producto"""
    id_producto = request.form.get('id_producto')
    
    exito, error = activar_producto(id_producto)
    
    if exito:
        current_app.logger.info(f"Producto activado: ID {id_producto}")
        flash('Producto activado', 'success')
    else:
        current_app.logger.error(f"Error al activar producto: {str(error)}")
        flash(error, 'danger')
    
    return redirect(url_for('productos.index'))


@productos.route('/detalles')
@login_required
@role_required(1, 2)
def detalles():
    """Ver detalles de un producto"""
    id_producto = request.args.get('id_producto')
    producto, error = obtener_producto(id_producto)
    
    if error:
        current_app.logger.error(f"Error al obtener detalles del producto: {str(error)}")
        flash(error, 'danger')
        return redirect(url_for('productos.index'))
    
    return render_template('productos/detalles.html', producto=producto)
