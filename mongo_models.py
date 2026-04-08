
import datetime

from models import DetalleVenta, Venta, db


SNAPSHOT_RETENTION_DAYS = 90
SNAPSHOT_RETENTION_SECONDS = SNAPSHOT_RETENTION_DAYS * 24 * 60 * 60


def _ensure_resumen_ventas_ttl_index(app):
    index_name = "fecha_ttl_90d"
    index_info = app.mongo.resumen_ventas.index_information()

    legacy_index = index_info.get("fecha_1")
    if legacy_index and "expireAfterSeconds" not in legacy_index:
        app.mongo.resumen_ventas.drop_index("fecha_1")

    app.mongo.resumen_ventas.create_index(
        [("fecha", 1)],
        name=index_name,
        expireAfterSeconds=SNAPSHOT_RETENTION_SECONDS,
    )


def guardar_log(app, action, descripcion, id_usuario, ip):
    app.mongo.logs_seguridad.insert_one({
        "fecha": datetime.datetime.utcnow(),
        "accion": action,
        "descripcion": descripcion,
        "id_usuario": id_usuario,
        "ip": ip,
    })


def guardar_ticket(app, venta, detalles):
    app.mongo.tickets.insert_one({
        "id_venta": venta.id_venta,
        "fecha": venta.fecha.strftime("%Y-%m-%d %H:%M:%S"),
        "total": float(venta.total or 0),
        "id_usuario": venta.id_usuario,
        "detalles": [
            {
                "id_producto": detalle.id_producto,
                "cantidad": float(detalle.cantidad or 0),
                "precio_unitario": float(detalle.precio_unitario or 0),
            }
            for detalle in detalles
        ],
    })


def actualizar_dashboard(app):
    _ensure_resumen_ventas_ttl_index(app)

    productos_mas_vendidos_query = (
        db.session.query(
            DetalleVenta.id_producto,
            db.func.sum(DetalleVenta.cantidad).label("cantidad_total"),
        )
        .group_by(DetalleVenta.id_producto)
        .order_by(db.desc("cantidad_total"))
        .limit(5)
        .all()
    )

    resumen_ventas = {
        "fecha": datetime.datetime.utcnow(),
        "total_ventas": Venta.query.count(),
        "total_ingresos": float(db.session.query(db.func.sum(Venta.total)).scalar() or 0.0),
        "productos_mas_vendidos": [
            {
                "id_producto": row.id_producto,
                "cantidad_total": float(row.cantidad_total or 0),
            }
            for row in productos_mas_vendidos_query
        ],
    }

    app.mongo.resumen_ventas.insert_one(dict(resumen_ventas))
    app.mongo.dashboard_cache.replace_one({}, resumen_ventas, upsert=True)
    