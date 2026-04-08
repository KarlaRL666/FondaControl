from sqlalchemy import inspect, text

from models import db


def asegurar_columnas(tabla, columnas):
    inspector = inspect(db.engine)
    existentes = {columna['name'] for columna in inspector.get_columns(tabla)}
    faltantes = [columna for columna in columnas if columna[0] not in existentes]

    if not faltantes:
        return False

    with db.engine.begin() as conexion:
        for nombre, definicion in faltantes:
            conexion.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}"))

    return True