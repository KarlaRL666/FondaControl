#!/usr/bin/env python
"""Migration script para agregar cantidad_producida a DetalleProduccion"""
from app import app
from models import db
from sqlalchemy import text

def migrate():
    with app.app_context():
        inspector = db.inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('detalle_produccion')]
        
        print("Columnas en detalle_produccion:")
        print(cols)
        
        if 'cantidad_producida' not in cols:
            print("\nAgregando cantidad_producida...")
            db.session.execute(text(
                "ALTER TABLE detalle_produccion ADD COLUMN cantidad_producida FLOAT DEFAULT 0"
            ))
            db.session.commit()
            print("✓ Columna agregada")
        else:
            print("\n✓ Columna cantidad_producida ya existe")

if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"✗ Error: {e}")
