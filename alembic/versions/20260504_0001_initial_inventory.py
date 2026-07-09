"""initial inventory schema

Revision ID: 20260504_0001
Revises:
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "productos",
        sa.Column("producto_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("categoria", sa.String(100)),
        sa.Column("unidad_medida", sa.String(30), nullable=False, server_default="UNIDAD"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("created_by", sa.String(80)),
        sa.Column("updated_by", sa.String(80)),
        sa.CheckConstraint("trim(codigo) <> ''", name="chk_producto_codigo_no_vacio"),
        sa.CheckConstraint("trim(nombre) <> ''", name="chk_producto_nombre_no_vacio"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index("idx_productos_nombre", "productos", ["nombre"])

    op.create_table(
        "stock_actual",
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id"), primary_key=True),
        sa.Column("cantidad_total", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("cantidad_reservada", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("cantidad_disponible", sa.Numeric(14, 3), sa.Computed("cantidad_total - cantidad_reservada", persisted=True)),
        sa.Column("fecha_ultima_actualizacion", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_by", sa.String(80)),
        sa.CheckConstraint("cantidad_total >= 0", name="chk_stock_total_no_negativo"),
        sa.CheckConstraint("cantidad_reservada >= 0", name="chk_stock_reservado_no_negativo"),
        sa.CheckConstraint("cantidad_reservada <= cantidad_total", name="chk_stock_reserva_no_mayor_total"),
    )
    op.create_index("idx_stock_disponible", "stock_actual", ["producto_id", "cantidad_disponible"])

    op.create_table(
        "reservas_stock",
        sa.Column("reserva_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id"), nullable=False),
        sa.Column("comprobante", sa.String(80), nullable=False),
        sa.Column("cantidad_reservada", sa.Numeric(14, 3), nullable=False),
        sa.Column("estado_reserva", sa.String(20), nullable=False, server_default="PENDIENTE"),
        sa.Column("fecha_reserva", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("fecha_confirmacion", sa.DateTime()),
        sa.Column("fecha_liberacion", sa.DateTime()),
        sa.Column("motivo_liberacion", sa.String(200)),
        sa.Column("created_by", sa.String(80)),
        sa.Column("updated_by", sa.String(80)),
        sa.CheckConstraint("cantidad_reservada > 0", name="chk_reserva_cantidad_positiva"),
        sa.CheckConstraint("estado_reserva IN ('PENDIENTE','CONFIRMADA','LIBERADA')", name="chk_reserva_estado"),
        sa.CheckConstraint("trim(comprobante) <> ''", name="chk_reserva_doc_no_vacio"),
    )
    op.create_index("idx_reservas_producto_estado", "reservas_stock", ["producto_id", "estado_reserva"])
    op.create_index("idx_reservas_documento", "reservas_stock", ["comprobante"])
    op.create_index("idx_reservas_fecha", "reservas_stock", ["fecha_reserva"])

    op.create_table(
        "movimientos_stock",
        sa.Column("movimiento_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id"), nullable=False),
        sa.Column("reserva_id", sa.BigInteger(), sa.ForeignKey("reservas_stock.reserva_id")),
        sa.Column("tipo_movimiento", sa.String(30), nullable=False),
        sa.Column("origen", sa.String(30), nullable=False),
        sa.Column("comprobante", sa.String(80), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("stock_anterior", sa.Numeric(14, 3), nullable=False),
        sa.Column("stock_posterior", sa.Numeric(14, 3), nullable=False),
        sa.Column("fecha_movimiento", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("observacion", sa.Text()),
        sa.Column("created_by", sa.String(80)),
        sa.CheckConstraint("cantidad > 0", name="chk_mov_cantidad_positiva"),
        sa.CheckConstraint("tipo_movimiento IN ('COMPRA','RESERVA','VENTA','LIBERACION_RESERVA','AJUSTE')", name="chk_mov_tipo"),
        sa.CheckConstraint("origen IN ('COMPRAS','VENTAS','STOCK','SISTEMA')", name="chk_mov_origen"),
        sa.CheckConstraint("trim(comprobante) <> ''", name="chk_mov_doc_no_vacio"),
    )
    op.create_index("idx_movimientos_producto_fecha", "movimientos_stock", ["producto_id", "fecha_movimiento"])
    op.create_index("idx_movimientos_documento", "movimientos_stock", ["comprobante"])
    op.create_index("idx_movimientos_tipo_fecha", "movimientos_stock", ["tipo_movimiento", "fecha_movimiento"])

    op.create_table(
        "precios_compra",
        sa.Column("precio_compra_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id"), nullable=False),
        sa.Column("fecha_precio", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("precio_compra", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="PYG"),
        sa.Column("comprobante", sa.String(80), nullable=False),
        sa.Column("proveedor_ref", sa.String(80)),
        sa.CheckConstraint("precio_compra >= 0", name="chk_precio_compra_positivo"),
    )
    op.create_index("idx_precios_compra_producto_fecha_precio", "precios_compra", ["producto_id", "fecha_precio", "precio_compra"])

    op.create_table(
        "precios_venta",
        sa.Column("precio_venta_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id"), nullable=False),
        sa.Column("fecha_precio", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("precio_venta", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="PYG"),
        sa.Column("comprobante", sa.String(80), nullable=False),
        sa.CheckConstraint("precio_venta >= 0", name="chk_precio_venta_positivo"),
    )
    op.create_index("idx_precios_venta_producto_fecha_precio", "precios_venta", ["producto_id", "fecha_precio", "precio_venta"])

    op.create_table(
        "cola_compras_log",
        sa.Column("evento_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("mensaje_id", sa.String(100), nullable=False),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("productos.producto_id")),
        sa.Column("referencia_compra", sa.String(80), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("precio_compra", sa.Numeric(14, 2), nullable=False),
        sa.Column("fecha_evento", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("estado_procesamiento", sa.String(20), nullable=False, server_default="PENDIENTE"),
        sa.Column("error_detalle", sa.Text()),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fecha_procesamiento", sa.DateTime()),
        sa.CheckConstraint("estado_procesamiento IN ('PENDIENTE','PROCESADO','ERROR')", name="chk_cola_estado"),
        sa.CheckConstraint("cantidad > 0", name="chk_cola_cantidad_positiva"),
        sa.CheckConstraint("precio_compra >= 0", name="chk_cola_precio_no_negativo"),
        sa.UniqueConstraint("mensaje_id", name="uq_cola_compras_log_mensaje_id"),
    )
    op.create_index("idx_cola_estado_fecha", "cola_compras_log", ["estado_procesamiento", "fecha_evento"])


def downgrade() -> None:
    op.drop_table("cola_compras_log")
    op.drop_table("precios_venta")
    op.drop_table("precios_compra")
    op.drop_table("movimientos_stock")
    op.drop_table("reservas_stock")
    op.drop_table("stock_actual")
    op.drop_table("productos")
