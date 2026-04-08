#!/usr/bin/env python
"""
Script para agregar campos de tarjeta a la tabla ventas.
Uso: python migrate_tarjeta_ventas.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db
from sqlalchemy import text

def migrate():
    with app.app_context():
        inspector = db.inspect(db.engine)
        ventas_columns = [col['name'] for col in inspector.get_columns('ventas')]
        
        print("Columnas actuales en tabla 'ventas':")
        print(ventas_columns)
        
        # Verificar si las columnas ya existen
        campos_a_agregar = {
            'tarjeta_titular': "VARCHAR(120)",
            'tarjeta_numero': "VARCHAR(4)",
            'tarjeta_vencimiento': "VARCHAR(5)"
        }
        
        for campo, tipo in campos_a_agregar.items():
            if campo not in ventas_columns:
                print(f"\nAgregando columna: {campo} ({tipo})")
                db.session.execute(text(f"ALTER TABLE ventas ADD COLUMN {campo} {tipo}"))
            else:
                print(f"\nColumna {campo} ya existe")
        
        db.session.commit()
        print("\n✓ Migración completada exitosamente")

if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"✗ Error durante migración: {e}")
        sys.exit(1)
