"""User model with bcrypt password hashing."""
import bcrypt
from flask_login import UserMixin
from ..extensions import db, login_manager


class User(UserMixin, db.Model):
    """Application user (staff / admin)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="cajero")  # admin | cajero | cocinero
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relationships
    sales = db.relationship("Sale", backref="cashier", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store the password using bcrypt."""
        pw_bytes = password.encode("utf-8")
        self.password_hash = bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify a plaintext password against the stored hash."""
        return bcrypt.checkpw(
            password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<User {self.username!r} [{self.role}]>"


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))
