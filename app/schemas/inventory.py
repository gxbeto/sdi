from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema

from app.core.comprobante import COMPROBANTE_EXAMPLE, COMPROBANTE_PATTERN


# Cantidades operativas. El sistema admite fracciones (hasta 3 decimales), por eso
# se publican como number/decimal, nunca como integer ni como string.
Cantidad = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=3, examples=[10]),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema(
        {
            "type": "number",
            "format": "decimal",
            "minimum": 0,
            "multipleOf": 0.001,
            "example": 10,
        }
    ),
]
CantidadPositiva = Annotated[
    Decimal,
    Field(gt=0, max_digits=14, decimal_places=3, examples=[2]),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema(
        {
            "type": "number",
            "format": "decimal",
            "exclusiveMinimum": 0,
            "multipleOf": 0.001,
            "example": 2,
        }
    ),
]
Precio = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=2, examples=[32000]),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema(
        {
            "type": "number",
            "format": "decimal",
            "minimum": 0,
            "multipleOf": 0.01,
            "example": 32000,
        }
    ),
]
Impuesto = Annotated[
    Decimal,
    Field(ge=0, le=100, max_digits=5, decimal_places=2, examples=[10]),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema(
        {
            "type": "number",
            "format": "decimal",
            "minimum": 0,
            "maximum": 100,
            "multipleOf": 0.01,
            "example": 10,
        }
    ),
]


# documento_ref: documento EXTERNO recibido desde Ventas o Compras. Trazabilidad externa.
DOCUMENTO_REF_PATTERN = r"^[A-Z]{2,3}-\d{3}-\d{6}$"
DOCUMENTO_REF_EXAMPLE = "FV-001-000123"
DOCUMENTO_REF_DESCRIPTION = (
    "Documento externo recibido desde Ventas o Compras. Se usa para trazabilidad externa. "
    "Ejemplos: FV-001-000123, OC-001-000555."
)
COMPROBANTE_DESCRIPTION = (
    "Comprobante interno generado por el módulo Stock para identificar la operación "
    "dentro del sistema. Incluye dígito verificador para validación de entrada."
)

# Documento externo recibido en los requests (Ventas/Compras).
DocumentoRefIn = Annotated[
    str,
    Field(
        max_length=14,
        pattern=DOCUMENTO_REF_PATTERN,
        description=DOCUMENTO_REF_DESCRIPTION,
        examples=[DOCUMENTO_REF_EXAMPLE],
    ),
]
# Documento externo devuelto en las respuestas.
DocumentoRefOut = Annotated[
    str,
    Field(
        pattern=DOCUMENTO_REF_PATTERN,
        description=DOCUMENTO_REF_DESCRIPTION,
        examples=[DOCUMENTO_REF_EXAMPLE],
    ),
]
# Comprobante interno generado por Stock, devuelto en las respuestas.
ComprobanteOut = Annotated[
    str,
    Field(
        pattern=COMPROBANTE_PATTERN,
        description=COMPROBANTE_DESCRIPTION,
        examples=[COMPROBANTE_EXAMPLE],
    ),
]


class ErrorResponse(BaseModel):
    estado: str = Field(default="ERROR", examples=["ERROR"])
    codigo: str = Field(examples=["CODIGO_ERROR"])
    mensaje: str = Field(examples=["Descripcion clara del error."])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "estado": "ERROR",
                "codigo": "CODIGO_ERROR",
                "mensaje": "Descripcion clara del error.",
            }
        }
    )


class HealthOut(BaseModel):
    status: str = Field(examples=["ok"])

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


class ProductoCreate(BaseModel):
    codigo: str = Field(min_length=1, max_length=50, examples=["INF-006"])
    nombre: str = Field(min_length=1, max_length=150, examples=["Teclado Satellite AK-910 USB / Negro"])
    descripcion: str | None = None
    categoria: str | None = Field(default=None, examples=["Informatica"])
    unidad_medida: str = Field(default="UNIDAD", min_length=1, max_length=30)
    impuesto: Impuesto = Decimal("0.00")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "codigo": "INF-006",
                "nombre": "Teclado Satellite AK-910 USB / Negro",
                "descripcion": "Teclado USB con cable, color negro",
                "categoria": "Informatica",
                "unidad_medida": "UNIDAD",
                "impuesto": 10,
            }
        }
    )


class ProductoOut(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    descripcion: str | None
    categoria: str | None
    unidad_medida: str
    impuesto: Impuesto
    activo: bool

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "producto_id": 1,
                "codigo": "INF-006",
                "nombre": "Teclado Satellite AK-910 USB / Negro",
                "descripcion": "Teclado USB con cable, color negro",
                "categoria": "Informatica",
                "unidad_medida": "UNIDAD",
                "impuesto": 10,
                "activo": True,
            }
        },
    )


class ProductoCreated(BaseModel):
    producto_id: int
    codigo: str
    estado: str = "CREADO"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "producto_id": 1,
                "codigo": "INF-006",
                "estado": "CREADO",
            }
        }
    )


class StockOut(BaseModel):
    producto_id: int
    cantidad_total: Cantidad
    cantidad_reservada: Cantidad
    cantidad_disponible: Cantidad

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "producto_id": 1,
                "cantidad_total": 10,
                "cantidad_reservada": 2,
                "cantidad_disponible": 8,
            }
        },
    )


class ReservaItemIn(BaseModel):
    producto_id: int
    cantidad: CantidadPositiva

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "producto_id": 1,
                "cantidad": 2,
            }
        }
    )


class ReservaCreate(BaseModel):
    documento_ref: DocumentoRefIn
    items: list[ReservaItemIn] = Field(min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "documento_ref": "FV-001-000123",
                "items": [{"producto_id": 1, "cantidad": 2}],
            }
        }
    )


class ReservaItemOut(BaseModel):
    reserva_id: int
    producto_id: int
    cantidad_reservada: Cantidad
    cantidad_disponible: Cantidad

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reserva_id": 101,
                "producto_id": 1,
                "cantidad_reservada": 2,
                "cantidad_disponible": 8,
            }
        }
    )


class ReservaCreateOut(BaseModel):
    estado: str
    documento_ref: DocumentoRefOut
    comprobante: ComprobanteOut
    reservas: list[ReservaItemOut]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "estado": "RESERVADO",
                "documento_ref": "FV-001-000123",
                "comprobante": "STK-001-000001-6",
                "reservas": [
                    {
                        "reserva_id": 101,
                        "producto_id": 1,
                        "cantidad_reservada": 2,
                        "cantidad_disponible": 8,
                    }
                ],
            }
        }
    )


class ConfirmarReservaIn(BaseModel):
    documento_ref: DocumentoRefIn | None = Field(default=None)
    precio_venta: Precio | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "documento_ref": "FV-001-000123",
                "precio_venta": 45760,
            }
        }
    )


class ConfirmarReservaOut(BaseModel):
    estado: str
    reserva_id: int
    producto_id: int
    documento_ref: DocumentoRefOut
    comprobante: ComprobanteOut
    cantidad_descontada: Cantidad
    stock_total_actual: Cantidad
    cantidad_reservada_actual: Cantidad
    cantidad_disponible_actual: Cantidad

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "estado": "CONFIRMADA",
                "reserva_id": 101,
                "producto_id": 1,
                "documento_ref": "FV-001-000123",
                "comprobante": "STK-001-000002-4",
                "cantidad_descontada": 2,
                "stock_total_actual": 8,
                "cantidad_reservada_actual": 0,
                "cantidad_disponible_actual": 8,
            }
        }
    )


class LiberarReservaIn(BaseModel):
    motivo_liberacion: str = Field(min_length=1, max_length=200, examples=["Cancelacion de venta"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "motivo_liberacion": "Cancelacion de venta",
            }
        }
    )


class LiberarReservaOut(BaseModel):
    estado: str
    reserva_id: int
    comprobante: ComprobanteOut
    cantidad_liberada: Cantidad

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "estado": "LIBERADA",
                "reserva_id": 101,
                "comprobante": "STK-001-000003-2",
                "cantidad_liberada": 2,
            }
        }
    )


class CompraEventoIn(BaseModel):
    mensaje_id: str = Field(min_length=1, max_length=100, examples=["CMP-2026-0001"])
    referencia_compra: DocumentoRefIn
    producto_id: int
    cantidad: CantidadPositiva
    precio_compra: Precio
    proveedor_ref: str | None = Field(default=None, max_length=80)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mensaje_id": "CMP-2026-0001",
                "referencia_compra": "OC-001-000555",
                "producto_id": 1,
                "cantidad": 10,
                "precio_compra": 32000,
                "proveedor_ref": "PROV-001",
            }
        }
    )


class CompraEventoOut(BaseModel):
    mensaje_id: str
    estado_procesamiento: str
    producto_id: int
    documento_ref: DocumentoRefOut | None = None
    comprobante: ComprobanteOut | None = None
    stock_total_actual: Cantidad | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mensaje_id": "CMP-2026-0001",
                "estado_procesamiento": "PROCESADO",
                "producto_id": 1,
                "documento_ref": "OC-001-000555",
                "comprobante": "STK-001-000004-0",
                "stock_total_actual": 18,
            }
        }
    )


class VentaItemIn(BaseModel):
    producto_id: int
    cantidad: CantidadPositiva
    precio_venta: Precio

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "producto_id": 1,
                "cantidad": 2,
                "precio_venta": 45760,
            }
        }
    )


class VentaConfirmarIn(BaseModel):
    documento_ref: DocumentoRefIn
    items: list[VentaItemIn] = Field(min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "documento_ref": "FV-001-000123",
                "items": [{"producto_id": 1, "cantidad": 2, "precio_venta": 45760}],
            }
        }
    )


class VentaConfirmarOut(BaseModel):
    estado: str
    documento_ref: DocumentoRefOut
    comprobante: ComprobanteOut

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "estado": "CONFIRMADA",
                "documento_ref": "FV-001-000123",
                "comprobante": "STK-001-000005-7",
            }
        }
    )


class MovimientoOut(BaseModel):
    movimiento_id: int
    producto_id: int
    reserva_id: int | None
    tipo_movimiento: str
    origen: str
    documento_ref: DocumentoRefOut | None = None
    comprobante: ComprobanteOut
    cantidad: Cantidad
    stock_anterior: Cantidad
    stock_posterior: Cantidad
    observacion: str | None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "movimiento_id": 50,
                "producto_id": 1,
                "reserva_id": 101,
                "tipo_movimiento": "VENTA",
                "origen": "VENTAS",
                "documento_ref": "FV-001-000123",
                "comprobante": "STK-001-000001-6",
                "cantidad": 2,
                "stock_anterior": 10,
                "stock_posterior": 8,
                "observacion": "Confirmacion de venta desde reserva",
            }
        },
    )


class PrecioResumenOut(BaseModel):
    precio_compra: Precio | None = None
    precio_venta: Precio | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "precio_compra": 32000,
                "precio_venta": 45760,
            }
        }
    )


class ProductoConsultaOut(BaseModel):
    """
    Respuesta agrupada de la consulta flexible GET /productos/{producto_id}.

    Cada bloque se incluye solo si fue solicitado en el parámetro `include`.
    Los bloques no solicitados se omiten de la respuesta.
    """
    producto: ProductoOut | None = None
    stock: StockOut | None = None
    precios: PrecioResumenOut | None = None
    movimientos: list[MovimientoOut] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "producto": {
                    "producto_id": 1,
                    "codigo": "INF-006",
                    "nombre": "Teclado Satellite AK-910 USB / Negro",
                    "descripcion": "Teclado USB con cable, color negro",
                    "categoria": "Informatica",
                    "unidad_medida": "UNIDAD",
                    "impuesto": 10,
                    "activo": True,
                },
                "stock": {
                    "producto_id": 1,
                    "cantidad_total": 10,
                    "cantidad_reservada": 2,
                    "cantidad_disponible": 8,
                },
                "precios": {
                    "precio_compra": 32000,
                    "precio_venta": 45760,
                },
            }
        }
    )
