import os
from sqlalchemy import create_engine

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None


def _load_env_file(path):
    if not os.path.exists(path):
        return

    with open(path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file(os.path.join(os.path.dirname(__file__), '.env_config'))


def _get_bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'si'}


def _resolve_mail_password():
    encrypted = os.getenv('MAIL_PASSWORD_ENCRYPTED')
    key = os.getenv('MAIL_PASSWORD_KEY')

    if encrypted and key and Fernet is not None:
        try:
            return Fernet(key.encode('utf-8')).decrypt(encrypted.encode('utf-8')).decode('utf-8')
        except Exception:
            print('Aviso: No se pudo descifrar MAIL_PASSWORD_ENCRYPTED. Revisa MAIL_PASSWORD_KEY.')

    raw_password = os.getenv('MAIL_PASSWORD')
    if raw_password:
        return raw_password.replace(' ', '').strip()
    return None

class Config(object):
    SECRET_KEY = 'Clave_Secreta'
    SESSION_COOKIE_SECURE = False
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024  # 3MB max upload size
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = _get_bool_env('MAIL_USE_TLS', True)
    MAIL_USE_SSL = _get_bool_env('MAIL_USE_SSL', False)
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = _resolve_mail_password()
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER') or MAIL_USERNAME
    TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '1x00000000000000000000AA')
    TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '1x0000000000000000000000000000000AA')
    TURNSTILE_VERIFY_URL = os.getenv('TURNSTILE_VERIFY_URL', 'https://challenges.cloudflare.com/turnstile/v0/siteverify')
    LOGIN_CAPTCHA_ENABLED = _get_bool_env('LOGIN_CAPTCHA_ENABLED', True)
    LOGIN_2FA_ENABLED = _get_bool_env('LOGIN_2FA_ENABLED', True)
    LOGIN_2FA_CODE_TTL = int(os.getenv('LOGIN_2FA_CODE_TTL', 300))
    RESET_PASSWORD_TOKEN_MAX_AGE = int(os.getenv('RESET_PASSWORD_TOKEN_MAX_AGE', 1800))



class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:karlamtz233@localhost/fonda'
    #SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://paulo:23010@localhost/fonda'
    #SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:23010@localhost/fonda'
    SQLALCHEMY_TRACK_MODIFICATIONS = False