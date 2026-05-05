"""Auth blueprint routes – login, logout, user management."""
import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from ...extensions import db
from ...models.user import User
from . import auth_bp

logger = logging.getLogger(__name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not username or not password:
            flash("Usuario y contraseña son requeridos.", "danger")
            return render_template("auth/login.html")

        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            logger.info("User %s logged in", username)
            next_page = request.args.get("next", "")
            # Validate next_page to prevent open redirect attacks
            if next_page and (next_page.startswith("/") and not next_page.startswith("//")):
                return redirect(next_page)
            return redirect(url_for("dashboard.index"))

        flash("Credenciales incorrectas. Intenta de nuevo.", "danger")
        logger.warning("Failed login attempt for username: %s", username)

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logger.info("User %s logged out", current_user.username)
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/usuarios")
@login_required
def users():
    if not current_user.is_admin():
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard.index"))
    all_users = User.query.order_by(User.username).all()
    return render_template("auth/users.html", users=all_users)


@auth_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
def create_user():
    if not current_user.is_admin():
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "cajero")

        if not all([username, email, password]):
            flash("Todos los campos son requeridos.", "danger")
            return render_template("auth/create_user.html")

        if User.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe.", "danger")
            return render_template("auth/create_user.html")

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Usuario {username} creado correctamente.", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/create_user.html")


@auth_bp.route("/usuarios/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    if not current_user.is_admin():
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard.index"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes desactivar tu propia cuenta.", "warning")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        state = "activado" if user.is_active else "desactivado"
        flash(f"Usuario {user.username} {state}.", "success")
    return redirect(url_for("auth.users"))
