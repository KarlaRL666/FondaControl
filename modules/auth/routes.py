from . import auth
from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_required, login_user, logout_user, current_user
from models import db, Usuario, Persona
from forms import LoginForm, RegistroClienteForm, EditarPerfilForm, RecuperarPasswordForm, ResetPasswordForm, Verificar2FAForm
from modules.cuenta.services import crear_cliente, actualizar_mi_cuenta, ver_perfil, cargar_datos_usuario
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
import json
import time
import random
import smtplib
from email.message import EmailMessage


def _verificar_turnstile(token, remote_ip=None):
    if not current_app.config.get('LOGIN_CAPTCHA_ENABLED', True):
        return True, None

    if not token:
        return False, 'Completa el CAPTCHA antes de iniciar sesión.'

    secret_key = (current_app.config.get('TURNSTILE_SECRET_KEY') or '').strip()
    verify_url = (current_app.config.get('TURNSTILE_VERIFY_URL') or '').strip()
    is_test_key = secret_key.endswith('AA') and secret_key.startswith('1x0000000000000000000000000000000')
    if not current_app.debug and is_test_key:
        current_app.logger.warning('Turnstile usa clave de prueba fuera de DEBUG.')
        return False, 'CAPTCHA no está configurado para producción. Contacta al administrador.'

    if not secret_key or not verify_url:
        current_app.logger.warning('Turnstile no configurado correctamente: falta secret o verify URL.')
        return False, 'No se pudo validar el CAPTCHA. Contacta al administrador.'

    payload = {
        'secret': secret_key,
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    try:
        data = urlencode(payload).encode('utf-8')
        req = Request(verify_url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        with urlopen(req, timeout=7) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            result = json.loads(body or '{}')
    except Exception as exc:
        current_app.logger.warning(f'No se pudo validar Turnstile: {exc}')
        return False, 'No se pudo validar el CAPTCHA en este momento. Inténtalo nuevamente.'

    if result.get('success'):
        return True, None

    error_codes = result.get('error-codes') or []
    if error_codes:
        current_app.logger.warning(f'Turnstile rechazado: {error_codes}')
    return False, 'Validación CAPTCHA no aprobada. Inténtalo otra vez.'


def _enviar_correo(destino, asunto, cuerpo):
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = int(current_app.config.get('MAIL_PORT', 587))
    mail_username = current_app.config.get('MAIL_USERNAME')
    mail_password = current_app.config.get('MAIL_PASSWORD')
    mail_sender = current_app.config.get('MAIL_DEFAULT_SENDER') or mail_username
    mail_use_tls = bool(current_app.config.get('MAIL_USE_TLS', True))
    mail_use_ssl = bool(current_app.config.get('MAIL_USE_SSL', False))

    if not (mail_server and mail_port and mail_sender and mail_username and mail_password and destino):
        current_app.logger.warning('SMTP incompleto para envío de seguridad.')
        return False

    msg = EmailMessage()
    msg['Subject'] = asunto
    msg['From'] = mail_sender
    msg['To'] = destino
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
    except Exception as email_error:
        current_app.logger.error(f'Error enviando correo de seguridad: {email_error}')
        return False


def _buscar_usuario_por_correo(correo):
    persona = Persona.query.filter_by(correo=(correo or '').strip().lower()).first()
    if not persona:
        return None

    if persona.cliente and persona.cliente.usuario:
        return persona.cliente.usuario
    if persona.empleado and persona.empleado.usuario:
        return persona.empleado.usuario
    return None


def _security_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _clear_pending_2fa():
    session.pop('pending_2fa_user_id', None)
    session.pop('pending_2fa_remember', None)
    session.pop('pending_2fa_code_hash', None)
    session.pop('pending_2fa_exp', None)


def _clear_reset_2fa():
    session.pop('reset_2fa_user_id', None)
    session.pop('reset_2fa_code_hash', None)
    session.pop('reset_2fa_exp', None)


def _generar_codigo_2fa():
    return f"{random.randint(0, 999999):06d}"


def _enviar_codigo_2fa(usuario):
    correo_destino = None
    if usuario.cliente and usuario.cliente.persona:
        correo_destino = usuario.cliente.persona.correo
    elif usuario.empleado and usuario.empleado.persona:
        correo_destino = usuario.empleado.persona.correo

    if not correo_destino:
        return False

    codigo = _generar_codigo_2fa()
    ttl = int(current_app.config.get('LOGIN_2FA_CODE_TTL', 300))
    session['pending_2fa_code_hash'] = generate_password_hash(codigo)
    session['pending_2fa_exp'] = int(time.time()) + ttl

    asunto = 'Código de verificación 2FA - Casa Gourmet'
    cuerpo = (
        f'Hola {usuario.username},\n\n'
        f'Tu código de verificación es: {codigo}\n'
        f'Este código expira en {max(1, ttl // 60)} minuto(s).\n\n'
        'Si no solicitaste este acceso, ignora este mensaje.'
    )
    return _enviar_correo(correo_destino, asunto, cuerpo)


def _enviar_codigo_2fa_reset(usuario):
    correo_destino = None
    if usuario.cliente and usuario.cliente.persona:
        correo_destino = usuario.cliente.persona.correo
    elif usuario.empleado and usuario.empleado.persona:
        correo_destino = usuario.empleado.persona.correo

    if not correo_destino:
        return False

    codigo = _generar_codigo_2fa()
    ttl = int(current_app.config.get('LOGIN_2FA_CODE_TTL', 300))
    session['reset_2fa_code_hash'] = generate_password_hash(codigo)
    session['reset_2fa_exp'] = int(time.time()) + ttl

    asunto = 'Código de verificación para recuperar contraseña - Casa Gourmet'
    cuerpo = (
        f'Hola {usuario.username},\n\n'
        f'Tu código para recuperar contraseña es: {codigo}\n'
        f'Este código expira en {max(1, ttl // 60)} minuto(s).\n\n'
        'Si no solicitaste este cambio, ignora este mensaje.'
    )
    return _enviar_correo(correo_destino, asunto, cuerpo)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if request.method == 'POST':
        if not form.validate():
            for _, errors in form.errors.items():
                if errors:
                    flash(errors[0], 'warning')
                    break
            return render_template('auth/login.html', form=form)

        turnstile_token = (request.form.get('cf-turnstile-response') or '').strip()
        captcha_ok, captcha_error = _verificar_turnstile(turnstile_token, request.remote_addr)
        if not captcha_ok:
            flash(captcha_error, 'warning')
            return render_template('auth/login.html', form=form)

        remember = True if request.form.get('remember') else False
        
        # Buscar usuario
        user = Usuario.query.filter_by(username=form.username.data).first()
        
        # 1. CASO FALLIDO
        if not user or not user.check_password(form.contrasena.data):
            current_app.logger.warning(f"Intento de login fallido para usuario: {form.username.data}")
            flash("Usuario o contraseña incorrectos. Por favor, verifica tus credenciales.", "danger")
            return render_template('auth/login.html', form=form)
        
        # 2. CASO CUENTA INACTIVA
        if not user.estado:
            current_app.logger.warning(f"Intento de login para usuario inactivo: {form.username.data}")
            flash("Tu cuenta está inactiva. Por favor, contacta al administrador.", "warning")
            return render_template('auth/login.html', form=form)
        
        # 3. CASO EXITOSO
        current_app.logger.info(f"Credenciales correctas para usuario: {form.username.data}")

        login_user(user, remember=remember)
        flash(f'¡Bienvenido {user.username}!', 'success')
        return redirect_por_rol(user)

    return render_template('auth/login.html', form=form)


@auth.route('/2fa', methods=['GET', 'POST'])
def verificar_2fa():
    user_id = session.get('reset_2fa_user_id')
    if not user_id:
        flash('No hay recuperación de contraseña pendiente.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    form = Verificar2FAForm()
    if form.validate_on_submit():
        exp = int(session.get('reset_2fa_exp') or 0)
        code_hash = session.get('reset_2fa_code_hash') or ''
        now_ts = int(time.time())

        if not code_hash or now_ts > exp:
            _clear_reset_2fa()
            flash('El código expiró. Solicita recuperación nuevamente.', 'warning')
            return redirect(url_for('auth.forgot_password'))

        if not check_password_hash(code_hash, (form.codigo.data or '').strip()):
            flash('Código 2FA inválido.', 'danger')
            return render_template('auth/verify_2fa.html', form=form)

        user = Usuario.query.get(int(user_id))
        if not user or not user.estado:
            _clear_reset_2fa()
            flash('Usuario no disponible para recuperar contraseña.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        token = _security_serializer().dumps({'uid': user.id_usuario}, salt='password-reset')
        _clear_reset_2fa()
        flash('Código verificado. Ya puedes restablecer tu contraseña.', 'success')
        return redirect(url_for('auth.reset_password', token=token))

    return render_template('auth/verify_2fa.html', form=form)


@auth.route('/2fa/reenviar', methods=['POST'])
def reenviar_2fa():
    user_id = session.get('reset_2fa_user_id')
    if not user_id:
        flash('No hay recuperación pendiente.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    user = Usuario.query.get(int(user_id))
    if not user:
        _clear_reset_2fa()
        flash('Usuario no encontrado para reenviar código.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if _enviar_codigo_2fa_reset(user):
        flash('Te enviamos un nuevo código 2FA.', 'info')
    else:
        flash('No se pudo reenviar el código 2FA.', 'danger')
    return redirect(url_for('auth.verificar_2fa'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = RecuperarPasswordForm()
    if form.validate_on_submit():
        user = _buscar_usuario_por_correo(form.correo.data)
        if user and user.estado:
            _clear_reset_2fa()
            session['reset_2fa_user_id'] = user.id_usuario

            if _enviar_codigo_2fa_reset(user):
                flash('Te enviamos un código 2FA para recuperar tu contraseña.', 'info')
                return redirect(url_for('auth.verificar_2fa'))

            _clear_reset_2fa()

        flash('Si el correo existe en el sistema, te enviaremos instrucciones para recuperar contraseña.', 'info')
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html', form=form)


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    form = ResetPasswordForm()
    try:
        data = _security_serializer().loads(
            token,
            salt='password-reset',
            max_age=int(current_app.config.get('RESET_PASSWORD_TOKEN_MAX_AGE', 1800))
        )
        user_id = int(data.get('uid'))
    except SignatureExpired:
        flash('El enlace de recuperación expiró. Solicita uno nuevo.', 'warning')
        return redirect(url_for('auth.forgot_password'))
    except (BadSignature, ValueError, TypeError):
        flash('El enlace de recuperación es inválido.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = Usuario.query.get(user_id)
    if not user or not user.estado:
        flash('No se pudo restablecer contraseña para esta cuenta.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if form.validate_on_submit():
        user.contrasena = generate_password_hash(form.contrasena.data)
        db.session.commit()
        flash('Contraseña actualizada correctamente. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)

def redirect_por_rol(user):
    """Función auxiliar para redirigir según el rol del usuario"""
    if user.rol.nombre in ['Administrador']:
        return redirect(url_for('dashboard.index'))
    elif user.rol.nombre == 'Cajero':
        return redirect(url_for('pedidos.index'))
    elif user.rol.nombre == 'Cocinero':
        return redirect(url_for('produccion.index'))
    elif user.rol.nombre == 'Cliente':
        return redirect(url_for('tienda.menu'))
    else:
        return redirect(url_for('dashboard.index'))

@auth.route('/crearCuenta', methods=['GET', 'POST'])
def crearCuenta():
    form = RegistroClienteForm()
    if form.validate_on_submit():
        exito, error = crear_cliente(form)
        if exito:
            current_app.logger.info(f"Cuenta creada para cliente: {form.username.data}")
            flash('Cuenta creada exitosamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            current_app.logger.error(f"Error al crear cuenta: {str(error)}")
            flash(error, 'danger')

    return render_template('cuenta/crear.html', form=form)

@auth.route('/miPerfil')
@login_required
def mi_perfil():
    usuario, error = ver_perfil(current_user.id_usuario)
    if not usuario:
        current_app.logger.error("Usuario no encontrado en la base de datos.")
        flash("Error al cargar tu perfil. Por favor, intenta nuevamente.", "danger")
        return redirect(url_for('dashboard.index'))

    return render_template('cuenta/perfil.html', usuario=usuario)

@auth.route('/editarPerfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    usuario = current_user
    if not usuario:
        current_app.logger.error("Usuario no encontrado en la base de datos.")
        flash("Error al cargar tu perfil. Por favor, intenta nuevamente.", "danger")
        return redirect(url_for('dashboard.index'))
    
    form = EditarPerfilForm()

    datos_usuario, error = cargar_datos_usuario(usuario.id_usuario, form)
    if not datos_usuario:
        current_app.logger.error(f"Error al cargar datos del perfil: {str(error)}")
        flash("No fue posible cargar tus datos para edición.", "danger")
        return redirect(url_for('cuenta.perfil'))

    if request.method == 'GET':
        form.nombre.data = datos_usuario.get('nombre')
        form.apellido_p.data = datos_usuario.get('apellido_p')
        form.apellido_m.data = datos_usuario.get('apellido_m')
        form.telefono.data = datos_usuario.get('telefono')
        form.correo.data = datos_usuario.get('correo')
        form.direccion.data = datos_usuario.get('direccion')
        form.username.data = datos_usuario.get('username')
    
    if form.validate_on_submit():
        exito, error = actualizar_mi_cuenta(usuario.id_usuario, request.form)
        if exito:
            current_app.logger.info(f"Perfil actualizado para cliente: {form.username.data}")
            flash('Perfil actualizado correctamente.', 'success')
            return redirect(url_for('cuenta.perfil'))
        else:
            flash(error, 'danger')  

    return render_template('cuenta/editar.html', form=form, usuario=datos_usuario)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/redirigir')
@login_required
def redirigir():
    return redirect_por_rol(current_user)