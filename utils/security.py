from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

#1 - Administrador
#2 - Cocinero
#3 - Cajero
#4 - Cliente


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            
            # Verificar si el usuario está autenticado
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Verificar el rol del usuario
            if current_user.id_rol not in roles:
                flash('No tienes permiso para acceder a esta página.', 'danger')
                return redirect(url_for('auth.login'))

            return func(*args, **kwargs)
        return wrapper
    return decorator