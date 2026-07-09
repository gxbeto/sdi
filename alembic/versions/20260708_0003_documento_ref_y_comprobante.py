"""diferenciar documento_ref (externo) y comprobante interno de Stock

Revision ID: 20260708_0003
Revises: 20260608_0002
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260708_0003"
down_revision: str | None = "20260608_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- reservas_stock: el comprobante externo pasa a llamarse documento_ref ---
    op.alter_column("reservas_stock", "comprobante", new_column_name="documento_ref")
    op.add_column("reservas_stock", sa.Column("comprobante", sa.String(20), nullable=False, server_default=""))
    op.alter_column("reservas_stock", "comprobante", server_default=None)
    op.create_index("idx_reservas_comprobante", "reservas_stock", ["comprobante"])

    # --- movimientos_stock ---
    op.alter_column(
        "movimientos_stock",
        "comprobante",
        new_column_name="documento_ref",
        existing_type=sa.String(80),
        existing_nullable=False,
        nullable=True,
    )
    op.add_column("movimientos_stock", sa.Column("comprobante", sa.String(20), nullable=False, server_default=""))
    op.alter_column("movimientos_stock", "comprobante", server_default=None)
    op.drop_constraint("chk_mov_doc_no_vacio", "movimientos_stock", type_="check")
    op.create_check_constraint("chk_mov_comprobante_no_vacio", "movimientos_stock", "trim(comprobante) <> ''")
    op.create_index("idx_movimientos_comprobante", "movimientos_stock", ["comprobante"])

    # --- precios_compra / precios_venta ---
    for tabla in ("precios_compra", "precios_venta"):
        op.alter_column(tabla, "comprobante", new_column_name="documento_ref")
        op.add_column(tabla, sa.Column("comprobante", sa.String(20), nullable=True))

    # --- cola_compras_log ---
    op.add_column("cola_compras_log", sa.Column("comprobante", sa.String(20), nullable=True))

    # --- secuencia de comprobantes internos ---
    op.create_table(
        "secuencia_comprobante",
        sa.Column("serie", sa.String(3), primary_key=True),
        sa.Column("ultimo_numero", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO secuencia_comprobante (serie, ultimo_numero) VALUES ('001', 0)")


def downgrade() -> None:
    op.drop_table("secuencia_comprobante")

    op.drop_column("cola_compras_log", "comprobante")

    for tabla in ("precios_venta", "precios_compra"):
        op.drop_column(tabla, "comprobante")
        op.alter_column(tabla, "documento_ref", new_column_name="comprobante")

    op.drop_index("idx_movimientos_comprobante", "movimientos_stock")
    op.drop_constraint("chk_mov_comprobante_no_vacio", "movimientos_stock", type_="check")
    op.create_check_constraint("chk_mov_doc_no_vacio", "movimientos_stock", "trim(documento_ref) <> ''")
    op.drop_column("movimientos_stock", "comprobante")
    op.alter_column(
        "movimientos_stock",
        "documento_ref",
        new_column_name="comprobante",
        existing_type=sa.String(80),
        existing_nullable=True,
        nullable=False,
    )

    op.drop_index("idx_reservas_comprobante", "reservas_stock")
    op.drop_column("reservas_stock", "comprobante")
    op.alter_column("reservas_stock", "documento_ref", new_column_name="comprobante")
