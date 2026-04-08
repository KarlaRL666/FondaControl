"""estado pagado en pedidos

Revision ID: e24a9b7c11f2
Revises: c2e7a4b9f1d3
Create Date: 2026-04-14 00:10:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e24a9b7c11f2'
down_revision = 'c2e7a4b9f1d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pedidos', schema=None) as batch_op:
        batch_op.drop_constraint('check_estado_pedido', type_='check')
        batch_op.create_check_constraint(
            'check_estado_pedido',
            "estado IN ('Pendiente', 'En Proceso', 'Producido', 'Completado', 'Pagado', 'Cancelado')",
        )

    op.execute(
        """
        UPDATE pedidos p
        SET p.estado = 'Pagado'
        WHERE p.estado = 'Completado'
          AND EXISTS (
              SELECT 1
              FROM movimientos_caja m
              WHERE m.tipo = 'Ingreso'
                AND m.descripcion = CONCAT('Pedido #', p.id_pedido)
          )
        """
    )


def downgrade():
    op.execute("UPDATE pedidos SET estado = 'Completado' WHERE estado = 'Pagado'")

    with op.batch_alter_table('pedidos', schema=None) as batch_op:
        batch_op.drop_constraint('check_estado_pedido', type_='check')
        batch_op.create_check_constraint(
            'check_estado_pedido',
            "estado IN ('Pendiente', 'En Proceso', 'Producido', 'Completado', 'Cancelado')",
        )
