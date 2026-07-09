from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import responses
from app.db.session import get_db
from app.schemas.inventory import (
    ConfirmarReservaIn,
    ConfirmarReservaOut,
    LiberarReservaIn,
    LiberarReservaOut,
    MovimientoOut,
    ReservaCreate,
    ReservaCreateOut,
    ReservaItemOut,
    StockOut,
)
from app.services import inventory as service

router = APIRouter(prefix="/stock", tags=["stock"])


# /movimientos debe declararse antes de /{producto_id} para que FastAPI no
# interprete "movimientos" como un entero en el parámetro de ruta.
@router.get(
    "/movimientos",
    summary="Consultar historial de movimientos de stock",
    description="Devuelve la trazabilidad de compras, reservas, ventas, liberaciones y ajustes. Permite filtrar por producto, documento de referencia y tipo de movimiento.",
    response_model=list[MovimientoOut],
    responses={200: responses.MOVIMIENTOS_LIST_OK, 422: responses.VALIDATION_ERROR},
)
def listar_movimientos(
    producto_id: int | None = None,
    documento_ref: str | None = None,
    tipo_movimiento: str | None = None,
    db: Session = Depends(get_db),
) -> list[MovimientoOut]:
    return service.listar_movimientos(db, producto_id, documento_ref, tipo_movimiento)


@router.get(
    "/{producto_id}",
    summary="Consultar stock actual de un producto",
    description="Devuelve las cantidades total, reservada y disponible del producto indicado.",
    response_model=StockOut,
    responses={
        200: responses.STOCK_OK,
        404: responses.PRODUCTO_NO_EXISTE,
        422: responses.VALIDATION_ERROR,
    },
)
def obtener_stock(producto_id: int, db: Session = Depends(get_db)) -> StockOut:
    return service.obtener_stock(db, producto_id)


@router.post(
    "/reservas",
    summary="Crear reserva de stock para uno o mas productos",
    description="Valida productos activos y stock disponible, bloquea las filas de stock involucradas, incrementa la cantidad reservada y registra movimientos de tipo RESERVA.",
    response_model=ReservaCreateOut,
    status_code=201,
    responses={
        201: responses.RESERVA_CREATED_OK,
        400: responses.PRODUCTO_INACTIVO,
        404: responses.PRODUCTO_NO_EXISTE,
        409: responses.STOCK_INSUFICIENTE,
        422: responses.VALIDATION_ERROR,
    },
)
def crear_reserva(payload: ReservaCreate, db: Session = Depends(get_db)) -> ReservaCreateOut:
    comprobante, reservas = service.crear_reservas(db, payload)
    return ReservaCreateOut(
        estado="RESERVADO",
        documento_ref=payload.documento_ref,
        comprobante=comprobante,
        reservas=[
            ReservaItemOut(
                reserva_id=reserva.reserva_id,
                producto_id=reserva.producto_id,
                cantidad_reservada=reserva.cantidad_reservada,
                cantidad_disponible=cantidad_disponible,
            )
            for reserva, cantidad_disponible in reservas
        ],
    )


@router.post(
    "/reservas/{reserva_id}/confirmar",
    summary="Confirmar reserva y descontar stock definitivo",
    description="Confirma una reserva pendiente, descuenta cantidad_total y cantidad_reservada, registra movimiento de VENTA y opcionalmente precio de venta.",
    response_model=ConfirmarReservaOut,
    responses={
        200: responses.RESERVA_CONFIRMADA_OK,
        404: responses.RESERVA_NO_EXISTE,
        409: responses.RESERVA_NO_PENDIENTE,
        422: responses.VALIDATION_ERROR,
    },
)
def confirmar_reserva(
    reserva_id: int,
    payload: ConfirmarReservaIn,
    db: Session = Depends(get_db),
) -> ConfirmarReservaOut:
    reserva, stock, comprobante, documento_ref = service.confirmar_reserva(
        db,
        reserva_id,
        payload.documento_ref,
        payload.precio_venta,
    )
    return ConfirmarReservaOut(
        estado="CONFIRMADA",
        reserva_id=reserva.reserva_id,
        producto_id=reserva.producto_id,
        documento_ref=documento_ref,
        comprobante=comprobante,
        cantidad_descontada=reserva.cantidad_reservada,
        stock_total_actual=stock.cantidad_total,
        cantidad_reservada_actual=stock.cantidad_reservada,
        cantidad_disponible_actual=stock.cantidad_total - stock.cantidad_reservada,
    )


@router.post(
    "/reservas/{reserva_id}/liberar",
    summary="Liberar reserva pendiente y devolver disponibilidad",
    description="Libera una reserva pendiente cuando la venta no se concreta, reduce cantidad_reservada y registra movimiento de LIBERACION_RESERVA.",
    response_model=LiberarReservaOut,
    responses={
        200: responses.RESERVA_LIBERADA_OK,
        404: responses.RESERVA_NO_EXISTE,
        409: responses.RESERVA_NO_PENDIENTE,
        422: responses.VALIDATION_ERROR,
    },
)
def liberar_reserva(
    reserva_id: int,
    payload: LiberarReservaIn,
    db: Session = Depends(get_db),
) -> LiberarReservaOut:
    reserva, cantidad, comprobante = service.liberar_reserva(db, reserva_id, payload.motivo_liberacion)
    return LiberarReservaOut(
        estado="LIBERADA",
        reserva_id=reserva.reserva_id,
        comprobante=comprobante,
        cantidad_liberada=cantidad,
    )
