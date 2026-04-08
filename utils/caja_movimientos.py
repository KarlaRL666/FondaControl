from datetime import datetime

from models import db, Caja, MovimientoCaja


def registrar_ingreso_caja(monto, referencia, fecha=None):
    """Registra un ingreso en la caja abierta evitando duplicados por referencia."""
    try:
        caja_abierta = Caja.query.filter_by(estado='Abierta').order_by(Caja.fecha.desc()).first()
        if not caja_abierta:
            return False, 'No hay caja abierta'

        monto = float(monto or 0)
        if monto <= 0:
            return False, 'Monto inválido'

        existe = (
            MovimientoCaja.query
            .filter_by(
                id_caja=caja_abierta.id_caja,
                tipo='Ingreso',
                descripcion=referencia,
            )
            .first()
        )
        if existe:
            return True, 'Ingreso ya registrado'

        mov = MovimientoCaja(
            fecha=fecha or datetime.now(),
            tipo='Ingreso',
            monto=monto,
            descripcion=referencia,
            id_caja=caja_abierta.id_caja,
        )
        db.session.add(mov)
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        return False, str(e)
