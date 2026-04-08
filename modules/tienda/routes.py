from . import tienda
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Producto, Carrito, DetalleCarrito, Pedido, CategoriaPlatillo
from forms import ContactoForm
from utils.security import role_required
from datetime import datetime
import smtplib
from email.message import EmailMessage
from .services import (
    obtener_menu, 
    agregar_producto_carrito, 
    obtener_carrito, 
    obtener_o_crear_carrito,
    reducir_cantidad_carrito,
    agregar_cantidad_carrito,
    finalizar_pedido, 
    obtener_categorias,
    obtener_categorias_ingrediente,
    obtener_materias_primas
)

CONTACTO_EMAIL_DESTINO = 'karlalizbethmtzl@gmail.com'
CONTACTO_TELEFONO_DESTINO = '+524779197919'
CONTACTO_TELEFONO_MOSTRAR = '+52 477 919 7919'


def _build_index_context(contacto_form=None):
    if contacto_form is None:
        contacto_form = ContactoForm()

    contacto_form.contacto_destino_email.data = CONTACTO_EMAIL_DESTINO
    contacto_form.contacto_destino_telefono.data = CONTACTO_TELEFONO_DESTINO

    productos, error = obtener_menu()
    if error:
        current_app.logger.error(f"Error al cargar productos para inicio tienda: {error}")
        productos = []

    categorias, error = obtener_categorias()
    if error:
        current_app.logger.error(f"Error al cargar categorías para inicio tienda: {error}")
        categorias = []

    productos_destacados = productos[:6] if productos else []

    calificaciones_cliente = []
    mongo_db = getattr(current_app, 'mongo', None)
    if mongo_db is not None:
        try:
            docs = list(
                mongo_db.calificaciones_servicio.find(
                    {},
                    {'_id': 0, 'idVenta': 1, 'calificacion': 1, 'comentario': 1, 'productos': 1, 'fecha': 1, 'cliente': 1}
                )
            )

            ids_venta = [d.get('idVenta') for d in docs if d.get('idVenta') is not None]
            ids_venta_int = []
            for vid in ids_venta:
                try:
                    ids_venta_int.append(int(vid))
                except (TypeError, ValueError):
                    continue

            pedidos_map = {}
            if ids_venta_int:
                pedidos_sql = Pedido.query.filter(Pedido.id_pedido.in_(ids_venta_int)).all()
                pedidos_map = {p.id_pedido: p for p in pedidos_sql}

            calificaciones_enriquecidas = []
            for d in docs:
                item = dict(d)
                id_venta = item.get('idVenta')
                try:
                    id_venta_int = int(id_venta)
                except (TypeError, ValueError):
                    id_venta_int = None

                cliente_nombre = item.get('cliente')
                pedido = pedidos_map.get(id_venta_int) if id_venta_int is not None else None
                if not cliente_nombre and pedido and pedido.cliente:
                    if pedido.cliente.persona:
                        nombre = (pedido.cliente.persona.nombre or '').strip()
                        ap = (pedido.cliente.persona.apellido_p or '').strip()
                        am = (pedido.cliente.persona.apellido_m or '').strip()
                        cliente_nombre = ' '.join(v for v in [nombre, ap, am] if v).strip()
                    elif pedido.cliente.usuario:
                        cliente_nombre = (pedido.cliente.usuario.username or '').strip()

                item['cliente'] = cliente_nombre or 'Cliente'
                calificaciones_enriquecidas.append(item)

            calificaciones_enriquecidas.sort(key=lambda d: d.get('fecha') or '', reverse=True)
            calificaciones_cliente = calificaciones_enriquecidas
        except Exception as mongo_error:
            current_app.logger.warning(f"No se pudieron cargar calificaciones de MongoDB: {mongo_error}")

    return {
        'productos': productos,
        'categorias': categorias,
        'calificaciones_cliente': calificaciones_cliente,
        'productos_destacados': productos_destacados,
        'contacto_form': contacto_form,
        'contacto_enviado': request.args.get('contacto_enviado'),
        'contacto_email': CONTACTO_EMAIL_DESTINO,
        'contacto_telefono': CONTACTO_TELEFONO_DESTINO,
        'contacto_telefono_mostrar': CONTACTO_TELEFONO_MOSTRAR,
    }


def _enviar_correo_contacto(nombre, email, telefono, asunto, mensaje, destino_email):
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = int(current_app.config.get('MAIL_PORT', 587))
    mail_username = current_app.config.get('MAIL_USERNAME')
    mail_password = current_app.config.get('MAIL_PASSWORD')
    mail_sender = current_app.config.get('MAIL_DEFAULT_SENDER') or mail_username
    mail_use_tls = bool(current_app.config.get('MAIL_USE_TLS', True))
    mail_use_ssl = bool(current_app.config.get('MAIL_USE_SSL', False))

    if not (mail_server and mail_port and mail_sender and mail_username and mail_password and destino_email):
        current_app.logger.warning(
            'SMTP no configurado: agrega MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD y MAIL_DEFAULT_SENDER en .env_config o variables de entorno.'
        )
        return False

    cuerpo = (
        'Nuevo mensaje desde el formulario de contacto de Casa Gourmet\n\n'
        f'Nombre: {nombre}\n'
        f'Email: {email}\n'
        f'Teléfono: {telefono or "No proporcionado"}\n'
        f'Asunto: {asunto}\n\n'
        'Mensaje:\n'
        f'{mensaje}\n'
    )

    msg = EmailMessage()
    msg['Subject'] = f'[Contacto Web] {asunto}'
    msg['From'] = mail_sender
    msg['To'] = destino_email
    msg['Reply-To'] = email
    msg.set_content(cuerpo)

    try:
        if mail_use_ssl:
            with smtplib.SMTP_SSL(mail_server, mail_port, timeout=15) as smtp:
                smtp.login(mail_username, mail_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(mail_server, mail_port, timeout=15) as smtp:
                smtp.ehlo()
                if mail_use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(mail_username, mail_password)
                smtp.send_message(msg)
        return True
    except Exception as smtp_error:
        current_app.logger.error(f'Error enviando correo de contacto por SMTP: {smtp_error}')
        return False

@tienda.route('/', methods=['GET', 'POST'])
def index():
    return render_template('tienda/index.html', **_build_index_context())

@tienda.route('/menu')
def menu():
    productos, error = obtener_menu()

    if error:
        current_app.logger.error(f"Error al cargar menú: {error}")
        flash("Error al cargar el menú", "danger")
        return redirect(url_for('index'))

    carrito_preview = None
    if current_user.is_authenticated and current_user.id_rol in [3, 4]:
        carrito_preview, carrito_error = obtener_carrito()
        if carrito_error:
            current_app.logger.warning(f"No se pudo cargar preview de carrito en menú: {carrito_error}")
            carrito_preview = {"productos": [], "total": 0}

    return render_template(
        'tienda/menu.html',
        productos=productos,
        carrito_preview=carrito_preview,
        name=current_user.username if current_user.is_authenticated else None
    )
    
@tienda.route('/carrito')
@login_required
@role_required(3, 4)
def carrito():
    carrito, error = obtener_carrito()

    if error:
        current_app.logger.error(f"Error al cargar carrito: {error}")
        flash("Error al cargar el carrito", "danger")
        return redirect(url_for('tienda.menu'))

    return render_template('tienda/carrito.html', carrito=carrito)

@tienda.route('/agregar/<int:id>', methods=['POST'])
def agregar_carrito(id):
    if not current_user.is_authenticated:
        flash('Debes iniciar sesión para agregar productos al carrito.', 'warning')
        return redirect(url_for('auth.login'))

    if current_user.id_rol not in [3, 4]:
        flash('No tienes permisos para agregar productos al carrito.', 'warning')
        return redirect(url_for('tienda.menu'))

    exito, mensaje = agregar_producto_carrito(id)

    if exito:
        current_app.logger.info(f"Producto agregado: {id}")
        flash(mensaje, "success")
    else:
        current_app.logger.error(f"Error carrito: {mensaje}")
        flash(mensaje, "danger")

    return redirect(url_for('tienda.menu'))


@tienda.route('/carrito/resumen-json', methods=['GET'])
@login_required
@role_required(3, 4)
def carrito_resumen_json():
    carrito, error = obtener_carrito()
    if error:
        return jsonify({'ok': False, 'message': error}), 400
    return jsonify({'ok': True, 'carrito': carrito})


@tienda.route('/agregar-json/<int:id>', methods=['POST'])
@login_required
@role_required(3, 4)
def agregar_carrito_json(id):
    exito, mensaje = agregar_producto_carrito(id)
    if not exito:
        return jsonify({'ok': False, 'message': mensaje}), 400

    carrito, error = obtener_carrito()
    if error:
        return jsonify({'ok': False, 'message': error}), 400

    return jsonify({'ok': True, 'message': mensaje, 'carrito': carrito})


@tienda.route('/carrito/cambiar-json/<int:id_producto>', methods=['POST'])
@login_required
@role_required(3, 4)
def cambiar_cantidad_menu_json(id_producto):
    data = request.get_json(silent=True) or {}
    accion = (data.get('accion') or '').strip().lower()

    carrito_obj, error = obtener_o_crear_carrito()
    if error or not carrito_obj:
        return jsonify({'ok': False, 'message': error or 'Carrito no disponible'}), 400

    detalle = DetalleCarrito.query.filter_by(
        id_carrito=carrito_obj.id_carrito,
        id_producto=id_producto,
    ).first()

    if accion == 'inc':
        exito, mensaje = agregar_producto_carrito(id_producto, cantidad=1)
        if not exito:
            return jsonify({'ok': False, 'message': mensaje}), 400
    elif accion in ('dec', 'remove'):
        if not detalle:
            return jsonify({'ok': False, 'message': 'Producto no encontrado en el carrito'}), 404

        if accion == 'remove':
            db.session.delete(detalle)
        else:
            if int(detalle.cantidad or 0) > 1:
                detalle.cantidad = int(detalle.cantidad or 0) - 1
                detalle.subtotal = float(detalle.cantidad or 0) * float(detalle.producto.precio or 0)
            else:
                db.session.delete(detalle)

        carrito_obj.total = sum(float(d.subtotal or 0) for d in carrito_obj.detalles)
        db.session.commit()
    else:
        return jsonify({'ok': False, 'message': 'Acción inválida'}), 400

    carrito, error = obtener_carrito()
    if error:
        return jsonify({'ok': False, 'message': error}), 400

    return jsonify({'ok': True, 'carrito': carrito})

@tienda.route('/reducir/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(3, 4)
def reducir_cantidad(id):
    exito, mensaje = reducir_cantidad_carrito(id)

    if exito:
        current_app.logger.info(f"Cantidad reducida del carrito: {id}")
        flash(mensaje, "success")
        return redirect(url_for('tienda.carrito'))
    else:
        current_app.logger.error(f"Error al reducir cantidad del carrito: {mensaje}")
        flash(mensaje, "danger")

    return redirect(url_for('tienda.carrito'))

@tienda.route('/aumentar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(3, 4)
def aumentar_cantidad(id):
    exito, mensaje = agregar_cantidad_carrito(id)

    if exito:
        current_app.logger.info(f"Cantidad aumentada del carrito: {id}")
        flash(mensaje, "success")
        return redirect(url_for('tienda.carrito'))
    else:
        current_app.logger.error(f"Error al aumentar cantidad del carrito: {mensaje}")
        flash(mensaje, "danger")

    return redirect(url_for('tienda.carrito'))

@tienda.route('/actualizar_cantidad/', methods=['POST'])
@login_required
@role_required(3, 4)
def actualizar_cantidad(id):
    accion = request.json.get('accion')

    detalle = DetalleCarrito.query.get(id)

    if not detalle:
        return {"ok": False}

    if accion == "sumar":
        detalle.cantidad += 1
        
    elif accion == "restar":
        detalle.cantidad -= 1
        if detalle.cantidad <= 0:
            db.session.delete(detalle)
            db.session.commit()
            return {"ok": True,
                    "eliminado": True,
                    "cantidad": 0,
                    "subtotal": 0}
        return {"ok": True,
                "eliminado": False,
                "cantidad": detalle.cantidad,
                "subtotal": detalle.subtotal}
        
    detalle.cantidad = max(detalle.cantidad, 0)
    detalle.subtotal = detalle.cantidad * detalle.producto.precio

    carrito = detalle.carrito
    carrito.total = sum(d.subtotal for d in carrito.detalles)

    db.session.commit()

    return {"ok": True}

@tienda.route('/finalizar', methods=['POST'])
@login_required
@role_required(3, 4)
def finalizar_compra():
    # Payment data is NOT collected here - will be captured at caja when order is ready for delivery
    origen = (request.form.get('origen') or '').strip().lower()
    fecha_requerida = request.form.get('fecha_requerida')
    exito, mensaje = finalizar_pedido(fecha_requerida=fecha_requerida)

    if not exito:
        flash(mensaje, "danger")
        if origen == 'menu':
            return redirect(url_for('tienda.menu'))
        return redirect(url_for('tienda.carrito'))

    flash(mensaje or "Pedido realizado con éxito 🧾", "success")
    # Si el mensaje indica que fue enviado a producción, redirigir a producción
    if 'producción' in (mensaje or '').lower():
        return redirect(url_for('produccion.index'))
    return redirect(url_for('pedidos.mis_pedidos'))


@tienda.route('/materias-primas')
def materias_primas():
    categorias, error = obtener_categorias_ingrediente()
    if error:
        current_app.logger.error(f"Error al cargar categorías: {error}")
        categorias = []
    
    categoria_id = request.args.get('categoria', type=int)
    
    materias, error = obtener_materias_primas(categoria_id)
    if error:
        current_app.logger.error(f"Error al cargar materias primas: {error}")
        materias = []
    
    return render_template(
        'tienda/materias_primas.html',
        categorias=categorias,
        materias_primas=materias,
        categoria_seleccionada=categoria_id
    )


@tienda.route('/contacto/enviar', methods=['POST'])
def enviar_contacto():
    """Handle contact form submission"""
    try:
        form = ContactoForm()

        if not form.validate_on_submit():
            primer_error = next((errores[0] for errores in form.errors.values() if errores), None)
            flash(primer_error or "Por favor corrige los campos del formulario de contacto.", "danger")
            return render_template('tienda/index.html', **_build_index_context(form))

        nombre = (form.nombre.data or '').strip()
        email = (form.email.data or '').strip()
        telefono = (form.telefono.data or '').strip()
        asunto = (form.asunto.data or '').strip()
        mensaje = (form.mensaje.data or '').strip()
        contacto_destino_email = (form.contacto_destino_email.data or '').strip() or CONTACTO_EMAIL_DESTINO
        contacto_destino_telefono = (form.contacto_destino_telefono.data or '').strip() or CONTACTO_TELEFONO_DESTINO
        
        # Log the contact message
        contact_log = (
            f"[CONTACTO] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"| Nombre: {nombre} | Email: {email} | Teléfono: {telefono} "
            f"| Asunto: {asunto} | Destino Email: {contacto_destino_email} "
            f"| Destino Teléfono: {contacto_destino_telefono} | Mensaje: {mensaje}"
        )
        current_app.logger.info(contact_log)
        
        # Try to save to MongoDB if available
        mongo_db = getattr(current_app, 'mongo', None)
        if mongo_db is not None:
            try:
                mongo_db.contactos.insert_one({
                    'nombre': nombre,
                    'email': email,
                    'telefono': telefono,
                    'asunto': asunto,
                    'mensaje': mensaje,
                    'contacto_destino_email': contacto_destino_email,
                    'contacto_destino_telefono': contacto_destino_telefono,
                    'fecha': datetime.now(),
                    'estado': 'Nuevo'
                })
            except Exception as mongo_error:
                current_app.logger.warning(f"No se pudo guardar en MongoDB: {mongo_error}")

        correo_enviado = _enviar_correo_contacto(
            nombre=nombre,
            email=email,
            telefono=telefono,
            asunto=asunto,
            mensaje=mensaje,
            destino_email=contacto_destino_email,
        )

        if correo_enviado:
            flash("¡Mensaje enviado correctamente! Te responderemos pronto.", "success")
            return redirect(url_for('tienda.index', contacto_enviado='1') + '#contacto')

        else:
            flash(
                "Recibimos tu mensaje, pero no se pudo enviar por correo en este momento. Se guardó para seguimiento.",
                "warning"
            )
            return redirect(url_for('tienda.index', contacto_enviado='0') + '#contacto')

        return redirect(url_for('tienda.index') + '#contacto')
    
    except Exception as e:
        current_app.logger.error(f"Error al procesar contacto: {e}")
        flash("Hubo un error al enviar tu mensaje. Intenta de nuevo.", "danger")
        return redirect(url_for('tienda.index') + '#contacto')
