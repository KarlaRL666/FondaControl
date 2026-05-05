"""FondaControl – Application Factory."""
import logging
import os
from flask import Flask
from .config import config_by_name
from .extensions import db, login_manager, csrf, migrate


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application."""
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_by_name.get(config_name, config_by_name["default"]))

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _apply_security_headers(app)

    return app


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _configure_logging(app: Flask) -> None:
    """Set up application logging."""
    log_level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    )
    app.logger.setLevel(log_level)


def _init_extensions(app: Flask) -> None:
    """Bind Flask extensions to the application."""
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # Create tables for SQLite (testing) automatically
    if app.config.get("TESTING"):
        with app.app_context():
            db.create_all()


def _register_blueprints(app: Flask) -> None:
    """Register all application blueprints."""
    from .blueprints.auth import auth_bp
    from .blueprints.pos import pos_bp
    from .blueprints.inventory import inventory_bp
    from .blueprints.dashboard import dashboard_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(pos_bp, url_prefix="/pos")
    app.register_blueprint(inventory_bp, url_prefix="/inventario")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    # Root redirect to dashboard
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {"now": datetime.utcnow()}


def _register_error_handlers(app: Flask) -> None:
    """Register HTTP error handlers."""
    from flask import render_template

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error("Server error: %s", e)
        return render_template("errors/500.html"), 500


def _apply_security_headers(app: Flask) -> None:
    """Add security-related response headers to every response."""
    from flask import request

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
