from app.schemas.inventory import ErrorResponse


def error_response(code: str, message: str, description: str) -> dict:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {
                    "estado": "ERROR",
                    "codigo": code,
                    "mensaje": message,
                }
            }
        },
    }


VALIDATION_ERROR = error_response(
    "VALIDACION_ERROR",
    "items.0.cantidad: Debe ser mayor que 0.",
    "El request no cumple el schema esperado.",
)

PRODUCTO_NO_EXISTE = error_response(
    "PRODUCTO_NO_EXISTE",
    "El producto 1 no existe.",
    "El producto solicitado no existe.",
)

PRODUCTO_INACTIVO = error_response(
    "PRODUCTO_INACTIVO",
    "El producto 1 esta inactivo.",
    "El producto existe, pero no puede operar.",
)

PRODUCTO_CODIGO_DUPLICADO = error_response(
    "PRODUCTO_CODIGO_DUPLICADO",
    "Ya existe un producto con el codigo INF-006.",
    "Ya existe un producto con el mismo codigo.",
)

STOCK_NO_INICIALIZADO = error_response(
    "STOCK_NO_INICIALIZADO",
    "El producto 1 no tiene registro de stock inicial.",
    "El producto existe, pero falta su registro de stock.",
)

STOCK_INSUFICIENTE = error_response(
    "STOCK_INSUFICIENTE",
    "Stock insuficiente para el producto 1: solicitado 2, disponible 1.",
    "No hay stock disponible suficiente.",
)

RESERVA_NO_EXISTE = error_response(
    "RESERVA_NO_EXISTE",
    "La reserva 101 no existe.",
    "La reserva solicitada no existe.",
)

RESERVA_NO_PENDIENTE = error_response(
    "RESERVA_NO_PENDIENTE",
    "La reserva 101 esta en estado CONFIRMADA y no puede modificarse.",
    "La reserva ya fue confirmada o liberada.",
)

RESERVA_NO_COINCIDE = error_response(
    "RESERVA_NO_COINCIDE",
    "No existe una reserva pendiente para el documento FV-001-000123, producto 1 y cantidad 2.",
    "La venta no coincide con una reserva pendiente.",
)


PRODUCTO_CREATED_OK = {
    "description": "Producto creado.",
    "content": {
        "application/json": {
            "example": {"producto_id": 1, "codigo": "INF-006", "estado": "CREADO"}
        }
    },
}

PRODUCTO_OK = {
    "description": "Producto encontrado.",
    "content": {
        "application/json": {
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
        }
    },
}

_EJEMPLO_PRODUCTO = {
    "producto_id": 1,
    "codigo": "INF-006",
    "nombre": "Teclado Satellite AK-910 USB / Negro",
    "descripcion": "Teclado USB con cable, color negro",
    "categoria": "Informatica",
    "unidad_medida": "UNIDAD",
    "impuesto": 10,
    "activo": True,
}
_EJEMPLO_STOCK = {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8,
}
_EJEMPLO_MOVIMIENTO = {
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
    "observacion": "Confirmación de venta desde reserva",
}

PRODUCTO_CONSULTA_OK = {
    "description": "Producto consultado. Respuesta agrupada según los bloques de include.",
    "content": {
        "application/json": {
            "examples": {
                "producto": {
                    "summary": "include=producto",
                    "value": {"producto": _EJEMPLO_PRODUCTO},
                },
                "stock": {
                    "summary": "include=stock",
                    "value": {"stock": _EJEMPLO_STOCK},
                },
                "productoStockPrecios": {
                    "summary": "include=producto,stock,precios",
                    "value": {
                        "producto": _EJEMPLO_PRODUCTO,
                        "stock": _EJEMPLO_STOCK,
                        "precios": {"precio_compra": 32000, "precio_venta": 45760},
                    },
                },
                "stockMovimientos": {
                    "summary": "include=stock,movimientos&limite_movimientos=10",
                    "value": {"stock": _EJEMPLO_STOCK, "movimientos": [_EJEMPLO_MOVIMIENTO]},
                },
                "productoMovimientos": {
                    "summary": "include=producto,movimientos&limite_movimientos=10",
                    "value": {"producto": _EJEMPLO_PRODUCTO, "movimientos": [_EJEMPLO_MOVIMIENTO]},
                },
            }
        }
    },
}

PRODUCTOS_LIST_OK = {
    "description": "Lista de productos.",
    "content": {
        "application/json": {
            "example": [
                {
                    "producto_id": 1,
                    "codigo": "INF-006",
                    "nombre": "Teclado Satellite AK-910 USB / Negro",
                    "descripcion": "Teclado USB con cable, color negro",
                    "categoria": "Informatica",
                    "unidad_medida": "UNIDAD",
                    "impuesto": 10,
                    "activo": True,
                },
                {
                    "producto_id": 13,
                    "codigo": "CEL-001",
                    "nombre": "Celular Apple iPhone 17 256GB",
                    "descripcion": "Smartphone Apple, 256GB de almacenamiento",
                    "categoria": "Celulares",
                    "unidad_medida": "UNIDAD",
                    "impuesto": 10,
                    "activo": True,
                },
            ]
        }
    },
}

STOCK_OK = {
    "description": "Stock actual.",
    "content": {
        "application/json": {
            "example": {
                "producto_id": 1,
                "cantidad_total": 10,
                "cantidad_reservada": 2,
                "cantidad_disponible": 8,
            }
        }
    },
}

MOVIMIENTOS_LIST_OK = {
    "description": "Lista de movimientos.",
    "content": {"application/json": {"example": [_EJEMPLO_MOVIMIENTO]}},
}

RESERVA_CREATED_OK = {
    "description": "Reserva creada.",
    "content": {
        "application/json": {
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
    },
}

RESERVA_CONFIRMADA_OK = {
    "description": "Reserva confirmada.",
    "content": {
        "application/json": {
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
    },
}

RESERVA_LIBERADA_OK = {
    "description": "Reserva liberada.",
    "content": {
        "application/json": {
            "example": {
                "estado": "LIBERADA",
                "reserva_id": 101,
                "comprobante": "STK-001-000003-2",
                "cantidad_liberada": 2,
            }
        }
    },
}

COMPRA_EVENTO_OK = {
    "description": "Evento de compra procesado.",
    "content": {
        "application/json": {
            "example": {
                "mensaje_id": "CMP-2026-0001",
                "estado_procesamiento": "PROCESADO",
                "producto_id": 1,
                "documento_ref": "OC-001-000555",
                "comprobante": "STK-001-000004-0",
                "stock_total_actual": 18,
            }
        }
    },
}

VENTA_CONFIRMADA_OK = {
    "description": "Venta confirmada.",
    "content": {
        "application/json": {
            "example": {
                "estado": "CONFIRMADA",
                "documento_ref": "FV-001-000123",
                "comprobante": "STK-001-000005-7",
            }
        }
    },
}
