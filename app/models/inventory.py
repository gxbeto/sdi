from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Producto(Base):
    __tablename__ = "productos"

    producto_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(String(100))
    unidad_medida: Mapped[str] = mapped_column(String(30), nullable=False, default="UNIDAD")
    impuesto: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))

    stock: Mapped["StockActual"] = relationship(back_populates="producto", uselist=False)

    __table_args__ = (
        CheckConstraint("trim(codigo) <> ''", name="chk_producto_codigo_no_vacio"),
        CheckConstraint("trim(nombre) <> ''", name="chk_producto_nombre_no_vacio"),
        CheckConstraint("impuesto >= 0 AND impuesto <= 100", name="chk_producto_impuesto_rango"),
        Index("idx_productos_nombre", "nombre"),
    )


class StockActual(Base):
    __tablename__ = "stock_actual"

    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.producto_id"), primary_key=True)
    cantidad_total: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    cantidad_reservada: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    # persisted=True: la BD almacena el valor calculado en disco; las lecturas no recalculan.
    cantidad_disponible: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        Computed("cantidad_total - cantidad_reservada", persisted=True),
    )
    fecha_ultima_actualizacion: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_by: Mapped[str | None] = mapped_column(String(80))

    producto: Mapped[Producto] = relationship(back_populates="stock")

    __table_args__ = (
        CheckConstraint("cantidad_total >= 0", name="chk_stock_total_no_negativo"),
        CheckConstraint("cantidad_reservada >= 0", name="chk_stock_reservado_no_negativo"),
        CheckConstraint("cantidad_reservada <= cantidad_total", name="chk_stock_reserva_no_mayor_total"),
        Index("idx_stock_disponible", "producto_id", "cantidad_disponible"),
    )


class ReservaStock(Base):
    __tablename__ = "reservas_stock"

    reserva_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.producto_id"), nullable=False)
    # documento_ref: documento externo (Ventas/Compras). comprobante: interno de Stock.
    documento_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    comprobante: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad_reservada: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    estado_reserva: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")
    fecha_reserva: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    fecha_confirmacion: Mapped[object | None] = mapped_column(DateTime)
    fecha_liberacion: Mapped[object | None] = mapped_column(DateTime)
    motivo_liberacion: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        CheckConstraint("cantidad_reservada > 0", name="chk_reserva_cantidad_positiva"),
        CheckConstraint("estado_reserva IN ('PENDIENTE','CONFIRMADA','LIBERADA')", name="chk_reserva_estado"),
        CheckConstraint("trim(documento_ref) <> ''", name="chk_reserva_doc_no_vacio"),
        Index("idx_reservas_producto_estado", "producto_id", "estado_reserva"),
        Index("idx_reservas_documento", "documento_ref"),
        Index("idx_reservas_comprobante", "comprobante"),
        Index("idx_reservas_fecha", "fecha_reserva"),
    )


class MovimientoStock(Base):
    __tablename__ = "movimientos_stock"

    movimiento_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.producto_id"), nullable=False)
    reserva_id: Mapped[int | None] = mapped_column(ForeignKey("reservas_stock.reserva_id"))
    tipo_movimiento: Mapped[str] = mapped_column(String(30), nullable=False)
    origen: Mapped[str] = mapped_column(String(30), nullable=False)
    # documento_ref: documento externo que originó el movimiento (opcional en ajustes internos).
    documento_ref: Mapped[str | None] = mapped_column(String(80))
    # comprobante: comprobante interno de Stock que identifica la operación.
    comprobante: Mapped[str] = mapped_column(String(20), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    stock_anterior: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    stock_posterior: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    fecha_movimiento: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    observacion: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        CheckConstraint("cantidad > 0", name="chk_mov_cantidad_positiva"),
        CheckConstraint("tipo_movimiento IN ('COMPRA','RESERVA','VENTA','LIBERACION_RESERVA','AJUSTE')", name="chk_mov_tipo"),
        CheckConstraint("origen IN ('COMPRAS','VENTAS','STOCK','SISTEMA')", name="chk_mov_origen"),
        CheckConstraint("trim(comprobante) <> ''", name="chk_mov_comprobante_no_vacio"),
        Index("idx_movimientos_producto_fecha", "producto_id", "fecha_movimiento"),
        Index("idx_movimientos_documento", "documento_ref"),
        Index("idx_movimientos_comprobante", "comprobante"),
        Index("idx_movimientos_tipo_fecha", "tipo_movimiento", "fecha_movimiento"),
    )


class PrecioCompra(Base):
    __tablename__ = "precios_compra"

    precio_compra_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.producto_id"), nullable=False)
    fecha_precio: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    precio_compra: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="PYG")
    documento_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    comprobante: Mapped[str | None] = mapped_column(String(20))
    proveedor_ref: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        CheckConstraint("precio_compra >= 0", name="chk_precio_compra_positivo"),
        Index("idx_precios_compra_producto_fecha_precio", "producto_id", "fecha_precio", "precio_compra"),
    )


class PrecioVenta(Base):
    __tablename__ = "precios_venta"

    precio_venta_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.producto_id"), nullable=False)
    fecha_precio: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="PYG")
    documento_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    comprobante: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint("precio_venta >= 0", name="chk_precio_venta_positivo"),
        Index("idx_precios_venta_producto_fecha_precio", "producto_id", "fecha_precio", "precio_venta"),
    )


class ColaComprasLog(Base):
    __tablename__ = "cola_compras_log"

    evento_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Clave de idempotencia: el UNIQUE en mensaje_id impide procesar el mismo evento dos veces.
    mensaje_id: Mapped[str] = mapped_column(String(100), nullable=False)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.producto_id"))
    referencia_compra: Mapped[str] = mapped_column(String(80), nullable=False)
    comprobante: Mapped[str | None] = mapped_column(String(20))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    precio_compra: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_evento: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    estado_procesamiento: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")
    error_detalle: Mapped[str | None] = mapped_column(Text)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fecha_procesamiento: Mapped[object | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("mensaje_id", name="uq_cola_compras_log_mensaje_id"),
        CheckConstraint("estado_procesamiento IN ('PENDIENTE','PROCESADO','ERROR')", name="chk_cola_estado"),
        CheckConstraint("cantidad > 0", name="chk_cola_cantidad_positiva"),
        CheckConstraint("precio_compra >= 0", name="chk_cola_precio_no_negativo"),
        Index("idx_cola_estado_fecha", "estado_procesamiento", "fecha_evento"),
    )


class SecuenciaComprobante(Base):
    """Contador de correlativos para comprobantes internos de Stock, por serie."""

    __tablename__ = "secuencia_comprobante"

    serie: Mapped[str] = mapped_column(String(3), primary_key=True)
    ultimo_numero: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
