# 🔐 CONFIGURACIÓN DE SEGURIDAD PARA FLASK
# Buffet Management System - Security Configuration

import os
from datetime import timedelta
from pathlib import Path

# ============================================
# ENTORNO
# ============================================

class Config:
    """Configuración base"""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'CHANGE_ME_IN_PRODUCTION_VERY_IMPORTANT')
    DEBUG = False
    TESTING = False
    
    # ============================================
    # SESIÓN Y COOKIES (A07 - Autenticación Débil)
    # ============================================
    
    # Tiempo de expiración: 10 minutos
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=10)
    SESSION_COOKIE_SECURE = True  # Solo HTTPS
    SESSION_COOKIE_HTTPONLY = True  # No acceso JavaScript
    SESSION_COOKIE_SAMESITE = 'Strict'  # Previene CSRF
    SESSION_COOKIE_NAME = '__session_id'  # No predecible
    SESSION_REFRESH_EACH_REQUEST = True  # Reseta timeout
    
    # ============================================
    # CONTRASEÑAS (A07 - Autenticación Débil)
    # ============================================
    
    # Validación contraseña
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_DIGITS = True  # Requiere número
    PASSWORD_REQUIRE_UPPERCASE = True  # Requiere mayúscula
    PASSWORD_REQUIRE_LOWERCASE = True  # Requiere minúscula
    PASSWORD_REQUIRE_SPECIAL = True  # Requiere caracteres especiales !@#$%^&*
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # Bcrypt hashing
    BCRYPT_LOG_ROUNDS = 12  # Más alto = más seguro pero lento
    
    # 2FA
    OTP_EXPIRATION_SECONDS = 600  # 10 minutos
    OTP_LENGTH = 6
    
    # Intenta fallidos
    MAX_LOGIN_ATTEMPTS = 3
    LOGIN_LOCKOUT_MINUTES = 15
    
    # ============================================
    # CSRF (A10 - CSRF/SSRF)
    # ============================================
    
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_TIME_LIMIT = None  # Sin tiempo límite
    WTF_CSRF_SSL_STRICT = True
    
    # ============================================
    # CORS (A10 - CSRF/SSRF)
    # ============================================
    
    CORS_ORIGINS = [
        os.getenv('APP_DOMAIN', 'http://localhost:5000'),
    ]
    CORS_ALLOW_HEADERS = [
        'Content-Type',
        'Authorization',
        'X-Requested-With',
    ]
    CORS_EXPOSE_HEADERS = [
        'Content-Range',
        'X-Content-Range',
    ]
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_MAX_AGE = 3600
    
    # ============================================
    # BASE DE DATOS (A03 - Inyección, A05 - Config)
    # ============================================
    
    # SQLAlchemy - Prevenir SQL Injection
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Usuario BD NO ROOT
    # Conexión template:
    # mysql://app_user:secure_pass@localhost/buffet_db
    # SQL Server: mssql+pyodbc://app_user:secure_pass@servername/buffet_db
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'mysql://buffet_app:your_secure_password@localhost/buffet_db'
    )
    
    # Timeout queries
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': 10,
        }
    }
    
    # ============================================
    # ARCHIVOS Y UPLOAD (A03 - Inyección)
    # ============================================
    
    # Directorio upload FUERA del web root
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        '..', 
        'uploads'
    )
    
    # Tamaño máximo archivo
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    
    # Extensiones permitidas
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    
    # MIME types permitidos
    ALLOWED_MIMETYPES = {
        'application/pdf',
        'image/jpeg',
        'image/png',
    }
    
    # ============================================
    # LOGGING Y AUDITORÍA (A09 - Logging)
    # ============================================
    
    # Archivo logs
    LOG_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..',
        'logs',
        'app.log'
    )
    
    # Máximo tamaño antes rotar
    LOG_MAX_BYTES = 100 * 1024 * 1024  # 100MB
    LOG_BACKUP_COUNT = 10  # Guardar 10 archivos rotados
    
    # Nivel logging
    LOG_LEVEL = 'INFO'

    # ============================================
    # RATE LIMITING
    # ============================================
    
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "100/hour"
    RATELIMIT_LOGIN = "10/minute"  # 10 intentos por minuto
    RATELIMIT_API = "1000/hour"
    
    # ============================================
    # HEADERS DE SEGURIDAD (A05 - Config Incorrecta)
    # ============================================
    
    # Estos se añaden en un middleware
    SECURITY_HEADERS = {
        # Previene hacer iframe de la app
        'X-Frame-Options': 'DENY',
        
        # Previene MIME sniffing
        'X-Content-Type-Options': 'nosniff',
        
        # Habilita XSS protection en navegadores
        'X-XSS-Protection': '1; mode=block',
        
        # Content Security Policy
        'Content-Security-Policy': (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
        
        # Referrer policy
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        
        # Feature policy (permissions)
        'Permissions-Policy': (
            'geolocation=(), '
            'microphone=(), '
            'camera=(),'
            'payment=()'
        ),
    }
    
    # HSTS - Force HTTPS
    HSTS_ENABLED = True
    HSTS_MAX_AGE = 31536000  # 1 año
    HSTS_INCLUDE_SUBDOMAINS = True
    HSTS_PRELOAD = True
    
    # ============================================
    # JWT (si se usa API con tokens)
    # ============================================
    
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'CHANGE_ME_JWT_SECRET')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=10)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'
    
    # ============================================
    # EMAIL (para 2FA, recuperación contraseña)
    # ============================================
    
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', True)
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@buffet.com')
    
    # ============================================
    # CAPTCHA (reCAPTCHA v3)
    # ============================================
    
    RECAPTCHA_ENABLED = True
    RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')
    RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY')
    RECAPTCHA_SCORE_THRESHOLD = 0.5
    

class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    TESTING = False
    WTF_CSRF_ENABLED = False  # Desabilitar CSRF solo en desarrollo
    SESSION_COOKIE_SECURE = False  # Permitir http en desarrollo
    SQLALCHEMY_ECHO = True  # Ver queries SQL
    LOG_LEVEL = 'DEBUG'
    

class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    

class ProductionConfig(Config):
    """Configuración para producción"""
    # Todas las opciones seguras están por defecto
    DEBUG = False
    TESTING = False
    
    # Validar que SECRET_KEY esté en .env
    @property
    def SECRET_KEY(self):
        secret = os.getenv('SECRET_KEY')
        if not secret or secret == 'CHANGE_ME_IN_PRODUCTION_VERY_IMPORTANT':
            raise ValueError(
                'SECRET_KEY no configurado en variables entorno. '
                'Esto es CRÍTICO para seguridad.'
            )
        return secret


# Seleccionar configuración según entorno
config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Obtener configuración según FLASK_ENV"""
    env = os.getenv('FLASK_ENV', 'development')
    return config_by_name.get(env, config_by_name['default'])
