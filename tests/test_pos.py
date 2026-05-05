"""Tests for POS blueprint endpoints."""
import json
import pytest
from app.models.product import Product, Category
from app.models.sale import Sale
from decimal import Decimal


def login(client, username, password):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


class TestPOSBlueprint:
    def test_pos_index_requires_login(self, client):
        resp = client.get("/pos/")
        assert resp.status_code in (302, 308)

    def test_pos_index_loads_when_authenticated(self, client, admin_user):
        login(client, "admin_test", "testpassword123")
        resp = client.get("/pos/")
        assert resp.status_code == 200

    def test_create_sale(self, client, admin_user, db):
        login(client, "admin_test", "testpassword123")
        resp = client.post(
            "/pos/ventas",
            data=json.dumps({"table_number": "5"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert "folio" in data
        assert data["folio"].startswith("VTA-")

    def test_get_sale(self, client, admin_user, db):
        login(client, "admin_test", "testpassword123")
        # Create a sale first
        resp = client.post(
            "/pos/ventas",
            data=json.dumps({}),
            content_type="application/json",
        )
        sale_id = resp.get_json()["id"]

        get_resp = client.get(f"/pos/ventas/{sale_id}")
        assert get_resp.status_code == 200
        sale_data = get_resp.get_json()
        assert sale_data["id"] == sale_id

    def test_add_item_to_sale(self, client, admin_user, db):
        login(client, "admin_test", "testpassword123")

        # Create a product
        cat = Category(name="POSCat")
        db.session.add(cat)
        db.session.flush()
        product = Product(
            name="Arroz", price=Decimal("25.00"), category_id=cat.id
        )
        db.session.add(product)
        db.session.commit()

        # Create sale
        sale_resp = client.post(
            "/pos/ventas",
            data=json.dumps({}),
            content_type="application/json",
        )
        sale_id = sale_resp.get_json()["id"]

        # Add item
        item_resp = client.post(
            f"/pos/ventas/{sale_id}/items",
            data=json.dumps({"product_id": product.id, "quantity": 2}),
            content_type="application/json",
        )
        assert item_resp.status_code == 200
        assert item_resp.get_json()["items_count"] == 1

    def test_pay_sale(self, client, admin_user, db):
        login(client, "admin_test", "testpassword123")

        cat = Category(name="PayCat")
        db.session.add(cat)
        db.session.flush()
        product = Product(name="Sopa Pay", price=Decimal("30.00"), category_id=cat.id)
        db.session.add(product)
        db.session.commit()

        sale_resp = client.post(
            "/pos/ventas",
            data=json.dumps({}),
            content_type="application/json",
        )
        sale_id = sale_resp.get_json()["id"]

        client.post(
            f"/pos/ventas/{sale_id}/items",
            data=json.dumps({"product_id": product.id, "quantity": 1}),
            content_type="application/json",
        )

        pay_resp = client.post(
            f"/pos/ventas/{sale_id}/pagar",
            data=json.dumps({"payment_method": "efectivo", "amount_paid": 50.0}),
            content_type="application/json",
        )
        assert pay_resp.status_code == 200
        pay_data = pay_resp.get_json()
        assert pay_data["change"] == pytest.approx(20.0, rel=1e-3)

    def test_history_page(self, client, admin_user):
        login(client, "admin_test", "testpassword123")
        resp = client.get("/pos/historial")
        assert resp.status_code == 200
