import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_login import LoginManager, current_user  # Solo flask_login
from sqlalchemy import and_, or_

from config import DevelopmentConfig
from models import db, Usuario, Caja as CajaModel, MovimientoCaja, Pedido, Compra
from modules.auth import auth
from modules.alertas import alertas, init_alertas
from modules.categorias import categorias
from modules.cuenta import cuenta
from modules.ingredientes import ingredientes
from modules.dashboard import dashboard
from modules.recetas import recetas
from modules.compras import compras
from modules.caja import caja
from modules.ventas import ventas
from modules.pedidos import pedidos
from modules.produccion import produccion
from modules.proveedores import proveedores
from modules.productos import productos
from modules.inventario import inventario
from modules.tienda import tienda

from modules.usuarios import usuarios

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()  # Inicializar LoginManager
CLOSE_MARKER_DESC = '__CIERRE_CAJA__'
CAJA_HORA_INICIO = 8
CAJA_MINUTO_INICIO = 10
CAJA_HORA_CIERRE = 22
CAJA_MINUTO_CIERRE = 0


class SafeRotatingFileHandler(RotatingFileHandler):
    """Avoid noisy traceback when log file rollover collides with Windows file locks."""

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 32:
                return
            raise


def _asegurar_colecciones_mongo(mongo_db):
    if mongo_db is None:
        return

    colecciones_objetivo = [
        'calificaciones',
        'estadisticasVentas',
        'historialActividad',
        'logs',
        'reporteCompras',
        'reporteProduccion',
        'reporteVentas',
    ]

    existentes = set(mongo_db.list_collection_names())
    for nombre in colecciones_objetivo:
        if nombre not in existentes:
            mongo_db.create_collection(nombre)


def _monto_egreso(valor):
    return abs(float(valor or 0))


def _ya_hubo_apertura_hoy(fecha_ref):
    inicio = datetime.combine(fecha_ref, datetime.min.time())
    fin = inicio + timedelta(days=1)
    return (
        CajaModel.query
        .filter(CajaModel.fecha >= inicio, CajaModel.fecha < fin)
        .count() > 0
    )


def _ya_hubo_cierre_hoy(fecha_ref):
    inicio = datetime.combine(fecha_ref, datetime.min.time())
    fin = inicio + timedelta(days=1)
    return (
        MovimientoCaja.query
        .filter(
            MovimientoCaja.descripcion == CLOSE_MARKER_DESC,
            MovimientoCaja.fecha >= inicio,
            MovimientoCaja.fecha < fin,
        )
        .count() > 0
    )


def _resolver_usuario_autocaja():
    if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'id_rol', None) in [1, 3]:
        return current_user

    ultimo_usuario = (
        CajaModel.query
        .order_by(CajaModel.fecha.desc())
        .first()
    )
    if ultimo_usuario and ultimo_usuario.usuario and ultimo_usuario.usuario.id_rol in [1, 3]:
        return ultimo_usuario.usuario

    return Usuario.query.filter(Usuario.id_rol.in_([1, 3])).order_by(Usuario.id_usuario.asc()).first()


def _auto_abrir_caja_si_corresponde():
    ahora = datetime.now()
    hora_apertura = ahora.replace(hour=CAJA_HORA_INICIO, minute=CAJA_MINUTO_INICIO, second=0, microsecond=0)
    if ahora < hora_apertura:
        return False

    if _ya_hubo_apertura_hoy(ahora.date()):
        return False

    caja_abierta = CajaModel.query.filter_by(estado='Abierta').order_by(CajaModel.fecha.desc()).first()
    if caja_abierta:
        return False

    usuario_autocaja = _resolver_usuario_autocaja()
    if not usuario_autocaja:
        return False

    ultima_caja_cerrada = CajaModel.query.filter_by(estado='Cerrada').order_by(CajaModel.fecha.desc()).first()
    monto_inicial = float(ultima_caja_cerrada.monto_final or 0) if ultima_caja_cerrada else 0.0

    nueva_caja = CajaModel(
        fecha=hora_apertura,
        monto_inicial=max(0.0, monto_inicial),
        estado='Abierta',
        id_usuario=usuario_autocaja.id_usuario,
    )
    db.session.add(nueva_caja)
    db.session.commit()
    return True


def _auto_cerrar_caja_si_corresponde():
    ahora = datetime.now()
    hora_cierre = ahora.replace(hour=CAJA_HORA_CIERRE, minute=CAJA_MINUTO_CIERRE, second=0, microsecond=0)
    if ahora < hora_cierre:
        return False

    if _ya_hubo_cierre_hoy(ahora.date()):
        return False

    caja_abierta = CajaModel.query.filter_by(estado='Abierta').order_by(CajaModel.fecha.desc()).first()
    if not caja_abierta:
        return False

    inicio = max(caja_abierta.fecha, datetime.combine(ahora.date(), datetime.min.time()))
    fin = hora_cierre if hora_cierre > inicio else ahora

    total_efectivo = 0.0
    pedidos = (
        Pedido.query
        .filter(
            Pedido.estado == 'Completado',
            or_(
                and_(Pedido.fecha_entrega.isnot(None), Pedido.fecha_entrega >= inicio, Pedido.fecha_entrega < fin),
                and_(Pedido.fecha_entrega.is_(None), Pedido.fecha >= inicio, Pedido.fecha < fin),
            )
        )
        .all()
    )

    for pedido in pedidos:
        metodo_pago = pedido.meta_pedido.metodo_pago if pedido.meta_pedido else 'Efectivo'
        if metodo_pago == 'Efectivo':
            total_efectivo += float(pedido.total or 0)

    compras_efectivo = (
        Compra.query
        .filter(
            Compra.estado == 'Completada',
            Compra.metodo_pago == 'Efectivo',
            or_(
                and_(Compra.fecha_entrega.isnot(None), Compra.fecha_entrega >= inicio, Compra.fecha_entrega < fin),
                and_(Compra.fecha_entrega.is_(None), Compra.fecha >= inicio, Compra.fecha < fin),
            )
        )
        .all()
    )

    total_egresos = sum(_monto_egreso(compra.total) for compra in compras_efectivo)
    efectivo_sistema = float(caja_abierta.monto_inicial or 0) + total_efectivo - total_egresos

    caja_abierta.monto_final = max(0.0, float(efectivo_sistema))
    caja_abierta.estado = 'Cerrada'

    db.session.add(MovimientoCaja(
        fecha=fin,
        tipo='Ingreso',
        monto=0,
        descripcion=CLOSE_MARKER_DESC,
        id_caja=caja_abierta.id_caja,
    ))
    db.session.commit()
    return True

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)
    app.config.setdefault('MONGO_URI', 'mongodb://localhost:27017/fondaGourmet')
    
    # Configuración adicional
    app.config['REMEMBER_COOKIE_DURATION'] = 30 * 24 * 3600  # 30 días
    
    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    # Configurar LoginManager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'  # Vista para login
    login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'
    
    # User loader para flask_login
    @login_manager.user_loader
    def load_user(user_id):
        """Carga el usuario desde la base de datos"""
        try:
            return Usuario.query.get(int(user_id))
        except Exception as e:
            app.logger.error(f"Error loading user {user_id}: {str(e)}")
            return None

    # Inicializar Mongo para bitácora y cachés no relacionales.
    app.mongo = None
    if MongoClient is not None:
        try:
            mongo_client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=2500)
            default_db = mongo_client.get_default_database()
            app.mongo = default_db if default_db is not None else mongo_client.get_database('fondaGourmet')
            mongo_client.admin.command('ping')
            _asegurar_colecciones_mongo(app.mongo)
        except Exception as mongo_error:
            app.logger.warning(f"MongoDB no disponible: {mongo_error}")
    else:
        app.logger.warning("pymongo no está instalado; bitácora Mongo desactivada.")

    @app.after_request
    def registrar_bitacora_http(response):
        if app.mongo is None:
            return response

        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return response

        if request.endpoint in {'static', 'alertas.marcar_vistas'}:
            return response

        try:
            app.mongo.bitacora_acciones.insert_one({
                'fecha': datetime.utcnow(),
                'modulo': (request.blueprint or 'sistema'),
                'endpoint': (request.endpoint or ''),
                'ruta': request.path,
                'metodo': request.method,
                'status_code': int(response.status_code),
                'usuario': {
                    'id_usuario': int(current_user.id_usuario) if getattr(current_user, 'is_authenticated', False) else None,
                    'username': getattr(current_user, 'username', None),
                    'rol': int(current_user.id_rol) if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'id_rol', None) else None,
                },
                'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
                'query': request.query_string.decode('utf-8', errors='ignore') if request.query_string else None,
            })
        except Exception as bitacora_error:
            app.logger.warning(f"No se pudo guardar evento en bitácora Mongo: {bitacora_error}")

        return response

    @app.before_request
    def aplicar_autocierre_caja():
        if request.endpoint == 'static':
            return None
        try:
            autoabierta = _auto_abrir_caja_si_corresponde()
            autocerrada = _auto_cerrar_caja_si_corresponde()
            hoy_key = datetime.now().strftime('%Y-%m-%d')
            usuario_puede_ver_alertas_caja = bool(
                getattr(current_user, 'is_authenticated', False)
                and getattr(current_user, 'id_rol', None) in [1, 3]
            )

            if usuario_puede_ver_alertas_caja and autoabierta and session.get('alerta_caja_apertura_810') != hoy_key:
                flash('La caja se abrió automáticamente a las 08:10 porque no se había iniciado.', 'info')
                session['alerta_caja_apertura_810'] = hoy_key

            if autocerrada and session.get('alerta_caja_cierre_2200') != hoy_key:
                flash('La caja se cerró automáticamente a las 22:00 por fin de turno.', 'info')
                session['alerta_caja_cierre_2200'] = hoy_key

            if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'id_rol', None) in [1, 3]:
                ahora = datetime.now()
                hora_inicio_alerta = ahora.replace(hour=CAJA_HORA_INICIO, minute=CAJA_MINUTO_INICIO, second=0, microsecond=0)
                hora_cierre = ahora.replace(hour=CAJA_HORA_CIERRE, minute=CAJA_MINUTO_CIERRE, second=0, microsecond=0)
                if hora_inicio_alerta <= ahora < hora_cierre:
                    caja_abierta = CajaModel.query.filter_by(estado='Abierta').order_by(CajaModel.fecha.desc()).first()
                    if not caja_abierta and session.get('alerta_caja_inicio_810') != hoy_key:
                        flash('Aún no se ha iniciado caja. Inicia con contraseña y monto inicial.', 'warning')
                        session['alerta_caja_inicio_810'] = hoy_key
        except Exception as cierre_error:
            db.session.rollback()
            app.logger.warning(f"No se pudo ejecutar autocierre de caja: {cierre_error}")
        return None

    @app.context_processor
    def inject_turno_caja():
        ahora = datetime.now()
        cierre = ahora.replace(hour=CAJA_HORA_CIERRE, minute=CAJA_MINUTO_CIERRE, second=0, microsecond=0)
        restante_segundos = max(0, int((cierre - ahora).total_seconds()))

        caja_abierta = CajaModel.query.filter_by(estado='Abierta').order_by(CajaModel.fecha.desc()).first()
        inicio_programado_txt = f'{CAJA_HORA_INICIO:02d}:{CAJA_MINUTO_INICIO:02d}'
        inicio_real_txt = caja_abierta.fecha.strftime('%H:%M') if caja_abierta else 'Pendiente'

        return {
            'turno_inicio_txt': inicio_programado_txt,
            'turno_inicio_real_txt': inicio_real_txt,
            'turno_cierre_txt': f'{CAJA_HORA_CIERRE:02d}:{CAJA_MINUTO_CIERRE:02d}',
            'turno_restante_segundos': restante_segundos,
            'mostrar_turno_caja': bool(getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'id_rol', None) in [1, 3]),
        }
    
    @app.context_processor
    def inject_customer_ratings():
        """Inject customer ratings into all templates for navbar display"""
        calificaciones_cliente = []
        promedio_calificaciones = None
        
        if current_user.is_authenticated and current_user.id_rol == 4 and getattr(current_user, 'cliente', None):
            mongo_db = getattr(app, 'mongo', None)
            if mongo_db is not None:
                try:
                    ids_pedido = [
                        row[0]
                        for row in (
                            db.session.query(Pedido.id_pedido)
                            .filter(Pedido.id_cliente == current_user.cliente.id_cliente)
                            .all()
                        )
                    ]

                    if ids_pedido:
                        ids_variantes = list({*ids_pedido, *[str(pid) for pid in ids_pedido]})
                        docs = list(
                            mongo_db.calificaciones_servicio.find(
                                {'idVenta': {'$in': ids_variantes}},
                                {'_id': 0, 'idVenta': 1, 'calificacion': 1, 'comentario': 1, 'productos': 1, 'fecha': 1, 'cliente': 1}
                            )
                        )
                        docs.sort(key=lambda d: d.get('fecha') or '', reverse=True)
                        calificaciones_cliente = docs
                        
                        # Calculate average rating
                        if calificaciones_cliente:
                            promedio = sum(c.get('calificacion', 0) for c in calificaciones_cliente) / len(calificaciones_cliente)
                            promedio_calificaciones = promedio
                except Exception as e:
                    app.logger.warning(f"Error loading customer ratings: {e}")
        
        return {
            'calificaciones_cliente': calificaciones_cliente,
            'promedio_calificaciones': promedio_calificaciones
        }
    
    # Registrar blueprints
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(alertas, url_prefix='/alertas')
    app.register_blueprint(cuenta, url_prefix='/cuenta')
    app.register_blueprint(categorias, url_prefix='/categorias')
    app.register_blueprint(dashboard, url_prefix='/dashboard')
    app.register_blueprint(recetas, url_prefix='/recetas')
    app.register_blueprint(caja, url_prefix='/caja')
    app.register_blueprint(ventas, url_prefix='/ventas')
    app.register_blueprint(produccion, url_prefix='/produccion')
    app.register_blueprint(compras, url_prefix='/compras')
    app.register_blueprint(tienda, url_prefix='/tienda')
    app.register_blueprint(usuarios, url_prefix='/usuarios')
    app.register_blueprint(productos, url_prefix='/productos')
    app.register_blueprint(inventario, url_prefix='/inventario')
    app.register_blueprint(proveedores, url_prefix='/proveedores')
    app.register_blueprint(ingredientes, url_prefix='/ingredientes')
    app.register_blueprint(pedidos, url_prefix='/pedidos')

    init_alertas(app)
    
    # Configurar logging
    os.makedirs('logs', exist_ok=True)

    if not any(isinstance(h, SafeRotatingFileHandler) for h in app.logger.handlers):
        file_handler = SafeRotatingFileHandler('logs/app.log', maxBytes=10000, backupCount=3, delay=True)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)

    @app.route('/favicon.ico')
    def favicon():
        return '', 204
    
    # 🚨 Errores
    @app.errorhandler(404)
    def not_found(error):
        if request.path == '/favicon.ico':
            return '', 204
        app.logger.warning(f'404: {request.url}')
        return render_template('404.html'), 404
    
    # 🏠 Home
    @app.route("/")
    def index():
        return redirect(url_for('tienda.index'))
    
    @app.route("/redirigir")
    def redirigir():
        if current_user.is_authenticated:
            return redirect(url_for('auth.redireccionar_por_rol', user=current_user))
        else:
            return redirect(url_for('auth.login'))
    
    return app

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)