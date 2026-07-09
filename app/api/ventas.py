from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import responses
from app.db.session import get_db
from app.schemas.inventory import VentaConfirmarIn, VentaConfirmarOut
from app.services import inventory as service

router = APIRouter(prefix="/ventas", tags=["ventas"])


@router.post(
    "/confirmar",
    summary="Confirmar venta completa desde reservas pendientes",
    description="Confirma una venta con multiples items usando reservas pendientes del mismo documento, descuenta stock en una unica transaccion y registra movimientos y precios de venta.",
    response_model=VentaConfirmarOut,
    responses={
        200: responses.VENTA_CONFIRMADA_OK,
        409: responses.RESERVA_NO_COINCIDE,
        422: responses.VALIDATION_ERROR,
    },
)
def confirmar_venta(payload: VentaConfirmarIn, db: Session = Depends(get_db)) -> VentaConfirmarOut:
    comprobante = service.confirmar_venta(db, payload)
    return VentaConfirmarOut(
        estado="CONFIRMADA",
        documento_ref=payload.documento_ref,
        comprobante=comprobante,
    )
