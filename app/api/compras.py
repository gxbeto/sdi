from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import responses
from app.db.session import get_db
from app.schemas.inventory import CompraEventoIn, CompraEventoOut
from app.services import inventory as service

router = APIRouter(prefix="/compras", tags=["compras"])


# Endpoint dual: en producción lo invoca el consumer de RabbitMQ internamente;
# también está expuesto HTTP para pruebas manuales y reenvíos de mensajes fallidos.
@router.post(
    "/eventos",
    summary="Procesar evento de compra e incrementar stock",
    description=(
        "Procesa un evento de compra recibido por HTTP o reenviado desde RabbitMQ, evita duplicados por "
        "mensaje_id, incrementa stock y registra movimiento y precio de compra. "
        "Canal asincrono equivalente: publicar el mismo payload (JSON, delivery_mode 2) en la cola RabbitMQ "
        "'compras.stock' (exchange default, durable). El consumer de Stock aplica exactamente la misma logica "
        "e idempotencia. Detalle completo en /documentacion, seccion 'Compras por cola (RabbitMQ)'."
    ),
    response_model=CompraEventoOut,
    responses={
        200: responses.COMPRA_EVENTO_OK,
        400: responses.PRODUCTO_INACTIVO,
        404: responses.PRODUCTO_NO_EXISTE,
        422: responses.VALIDATION_ERROR,
    },
)
def procesar_evento_compra(payload: CompraEventoIn, db: Session = Depends(get_db)) -> CompraEventoOut:
    estado, stock_total, comprobante = service.procesar_compra(db, payload)
    return CompraEventoOut(
        mensaje_id=payload.mensaje_id,
        estado_procesamiento=estado,
        producto_id=payload.producto_id,
        documento_ref=payload.referencia_compra,
        comprobante=comprobante,
        stock_total_actual=stock_total,
    )
