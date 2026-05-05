"""Shared test fixtures."""
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(scope="session")
def app():
    """Create application for testing (SQLite in-memory)."""
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def db(app):
    """Provide the database for the session."""
    with app.app_context():
        yield _db


@pytest.fixture(scope="session")
def admin_user(db):
    """Create and return an admin user (once per session)."""
    existing = User.query.filter_by(username="admin_test").first()
    if existing:
        return existing
    user = User(username="admin_test", email="admin@test.com", role="admin")
    user.set_password("testpassword123")
    db.session.add(user)
    db.session.commit()
    return user
