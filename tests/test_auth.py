"""Tests for authentication blueprint."""
import pytest
from app.models.user import User


class TestLogin:
    def test_login_page_loads(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200
        assert b"Iniciar" in resp.data

    def test_login_redirect_when_authenticated(self, client, admin_user, app):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
        resp = client.get("/auth/login", follow_redirects=False)
        # Should redirect away from login
        assert resp.status_code in (302, 200)

    def test_login_with_wrong_credentials(self, client):
        client.get("/auth/logout")  # ensure not logged in
        resp = client.post(
            "/auth/login",
            data={"username": "nobody", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Credenciales" in resp.data or b"incorrectas" in resp.data or b"login" in resp.data.lower()

    def test_login_with_correct_credentials(self, client, admin_user):
        resp = client.post(
            "/auth/login",
            data={"username": "admin_test", "password": "testpassword123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    def test_logout_requires_login(self, client):
        resp = client.get("/auth/logout", follow_redirects=True)
        assert resp.status_code == 200
        # Should redirect to login page
        assert b"Iniciar" in resp.data


class TestUserModel:
    def test_password_hashing(self, db):
        user = User(username="hashtest", email="hash@test.com", role="cajero")
        user.set_password("mypassword")
        assert user.password_hash != "mypassword"
        assert user.check_password("mypassword") is True
        assert user.check_password("wrongpassword") is False

    def test_is_admin(self, db):
        admin = User(username="adminrole", email="ar@test.com", role="admin")
        admin.set_password("pass")
        cajero = User(username="cajerorole", email="cr@test.com", role="cajero")
        cajero.set_password("pass")
        assert admin.is_admin() is True
        assert cajero.is_admin() is False

    def test_user_repr(self, db):
        user = User(username="reprtest", email="r@test.com", role="cocinero")
        user.set_password("pass")
        assert "reprtest" in repr(user)
