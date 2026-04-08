from datetime import datetime
from flask import current_app, has_app_context


def registrar_evento(
    modulo,
    entidad,
    accion,
    id_usuario=None,
    id_entidad=None,
    estado_anterior=None,
    estado_nuevo=None,
    descripcion=None,
):
    """Registra eventos operativos en MongoDB sin interrumpir el flujo principal."""
    try:
        mongo_db = getattr(current_app, 'mongo', None) if has_app_context() else None
        if mongo_db is None:
            return

        mongo_db.bitacora_acciones.insert_one({
            'fecha': datetime.utcnow(),
            'modulo': modulo,
            'entidad': entidad,
            'accion': accion,
            'id_entidad': id_entidad,
            'estado_anterior': estado_anterior,
            'estado_nuevo': estado_nuevo,
            'descripcion': descripcion,
            'usuario': {
                'id_usuario': id_usuario,
            },
            'origen': 'manual',
        })
    except Exception as e:
        # La bitácora no debe romper transacciones de negocio.
        if has_app_context():
            current_app.logger.warning(f"No se pudo registrar evento en bitácora: {str(e)}")
