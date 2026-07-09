import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.comprobante import SERIE_DEFECTO, formatear_comprobante
from app.core.errors import AppError, conflict, not_found
from app.models.inventory import (
    ColaComprasLog,
    MovimientoStock,
    PrecioCompra,
    PrecioVenta,
    Producto,
    ReservaStock,
    SecuenciaComprobante,
    StockActual,
)
from app.schemas.inventory import CompraEventoIn, ProductoCreate, ReservaCreate, VentaConfirmarIn

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.utcnow()


def _generar_comprobante(db: Session, serie: str = SERIE_DEFECTO) -> str:
    """
    Genera un comprobante interno de Stock con dígito verificador.

    Usa un contador por serie protegido con bloqueo de fila para garantizar
    correlativos únicos ante operaciones concurrentes.
    """
    fila = db.execute(
        select(SecuenciaComprobante).where(SecuenciaComprobante.serie == serie).with_for_update()
    ).scalar_one_or_none()
    if fila is None:
        fila = SecuenciaComprobante(serie=serie, ultimo_numero=0)
        db.add(fila)
        db.flush()
    fila.ultimo_numero += 1
    db.flush()
    return formatear_comprobante(fila.ultimo_numero, serie)


def _get_producto_activo(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise not_found("PRODUCTO_NO_EXISTE", f"El producto {producto_id} no existe.")
    if not producto.activo:
        raise AppError("PRODUCTO_INACTIVO", f"El producto {producto_id} esta inactivo.")
    return producto


def _lock_stock(db: Session, producto_id: int) -> StockActual:
    stock = db.execute(
        select(StockActual).where(StockActual.producto_id == producto_id).with_for_update()
    ).scalar_one_or_none()
    if stock is None:
        raise not_found(
            "STOCK_NO_INICIALIZADO",
            f"El producto {producto_id} no tiene registro de stock inicial.",
        )
    return stock


def _lock_reserva_pendiente(db: Session, reserva_id: int) -> ReservaStock:
    reserva = db.execute(
        select(ReservaStock).where(ReservaStock.reserva_id == reserva_id).with_for_update()
    ).scalar_one_or_none()
    if reserva is None:
        raise not_found("RESERVA_NO_EXISTE", f"La reserva {reserva_id} no existe.")
    if reserva.estado_reserva != "PENDIENTE":
        raise conflict(
            "RESERVA_NO_PENDIENTE",
            f"La reserva {reserva_id} esta en estado {reserva.estado_reserva} y no puede modificarse.",
        )
    return reserva


def _disponible(stock: StockActual) -> Decimal:
    return stock.cantidad_total - stock.cantidad_reservada


def _add_movimiento(
    db: Session,
    producto_id: int,
    tipo: str,
    origen: str,
    documento_ref: str | None,
    comprobante: str,
    cantidad: Decimal,
    stock_anterior: Decimal,
    stock_posterior: Decimal,
    observacion: str,
    created_by: str,
    reserva_id: int | None = None,
) -> MovimientoStock:
    movimiento = MovimientoStock(
        producto_id=producto_id,
        reserva_id=reserva_id,
        tipo_movimiento=tipo,
        origen=origen,
        documento_ref=documento_ref,
        comprobante=comprobante,
        cantidad=cantidad,
        stock_anterior=stock_anterior,
        stock_posterior=stock_posterior,
        observacion=observacion,
        created_by=created_by,
    )
    db.add(movimiento)
    return movimiento


def crear_producto(db: Session, payload: ProductoCreate) -> Producto:
    producto = Producto(
        codigo=payload.codigo.strip(),
        nombre=payload.nombre.strip(),
        descripcion=payload.descripcion,
        categoria=payload.categoria,
        unidad_medida=payload.unidad_medida.strip(),
        impuesto=payload.impuesto,
        created_by="STOCK",
        updated_by="STOCK",
    )
    db.add(producto)
    try:
        db.flush()
        db.add(StockActual(producto_id=producto.producto_id, updated_by="STOCK"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("PRODUCTO_CODIGO_DUPLICADO", f"Ya existe un producto con el codigo {producto.codigo}.") from exc
    db.refresh(producto)
    logger.info("Producto creado codigo=%s producto_id=%s origen=STOCK", producto.codigo, producto.producto_id)
    return producto


def listar_productos(db: Session, codigo: str | None, activo: bool | None) -> list[Producto]:
    stmt = select(Producto).order_by(Producto.producto_id)
    if codigo:
        stmt = stmt.where(Producto.codigo == codigo)
    if activo is not None:
        stmt = stmt.where(Producto.activo == activo)
    return list(db.execute(stmt).scalars())


def obtener_producto(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise not_found("PRODUCTO_NO_EXISTE", f"El producto {producto_id} no existe.")
    return producto


INCLUDE_BLOQUES_VALIDOS = {"producto", "stock", "precios", "movimientos"}


def _parsear_include(include: str) -> set[str]:
    """
    Normaliza el parámetro include: minúsculas, sin espacios, sin duplicados.

    Si no se informa, asume {'producto'}. Un valor no permitido produce 422.
    """
    bloques = {parte.strip().lower() for parte in include.split(",") if parte.strip()}
    if not bloques:
        return {"producto"}
    invalidos = bloques - INCLUDE_BLOQUES_VALIDOS
    if invalidos:
        raise AppError(
            "VALIDACION_ERROR",
            f"include: valores no permitidos {', '.join(sorted(invalidos))}. "
            f"Use: {', '.join(sorted(INCLUDE_BLOQUES_VALIDOS))}.",
            422,
        )
    return bloques


def obtener_producto_con_include(
    db: Session,
    producto_id: int,
    include: str,
    limite_movimientos: int = 10,
) -> dict:
    """
    Consulta flexible y agrupada de un producto.

    Devuelve un diccionario con los bloques solicitados en `include`
    (producto, stock, precios, movimientos). Los bloques no solicitados se omiten.
    El orden de los bloques no afecta el resultado y los duplicados se ignoran.
    """
    bloques = _parsear_include(include)

    # El producto siempre debe existir, se solicite o no su bloque.
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise not_found("PRODUCTO_NO_EXISTE", f"El producto {producto_id} no existe.")

    resultado: dict = {}

    if "producto" in bloques:
        resultado["producto"] = producto

    if "stock" in bloques:
        stock = db.get(StockActual, producto_id)
        if stock is None:
            raise not_found(
                "STOCK_NO_INICIALIZADO",
                f"El producto {producto_id} no tiene registro de stock inicial.",
            )
        resultado["stock"] = stock

    if "precios" in bloques:
        precio_venta_reciente = db.execute(
            select(PrecioVenta)
            .where(PrecioVenta.producto_id == producto_id)
            .order_by(PrecioVenta.fecha_precio.desc())
            .limit(1)
        ).scalar_one_or_none()
        precio_compra_reciente = db.execute(
            select(PrecioCompra)
            .where(PrecioCompra.producto_id == producto_id)
            .order_by(PrecioCompra.fecha_precio.desc())
            .limit(1)
        ).scalar_one_or_none()
        resultado["precios"] = {
            "precio_compra": precio_compra_reciente.precio_compra if precio_compra_reciente else None,
            "precio_venta": precio_venta_reciente.precio_venta if precio_venta_reciente else None,
        }

    if "movimientos" in bloques:
        movimientos = db.execute(
            select(MovimientoStock)
            .where(MovimientoStock.producto_id == producto_id)
            .order_by(MovimientoStock.fecha_movimiento.desc())
            .limit(limite_movimientos)
        ).scalars().all()
        resultado["movimientos"] = list(movimientos)

    return resultado


def obtener_stock(db: Session, producto_id: int) -> StockActual:
    if db.get(Producto, producto_id) is None:
        raise not_found("PRODUCTO_NO_EXISTE", f"El producto {producto_id} no existe.")
    stock = db.get(StockActual, producto_id)
    if stock is None:
        raise not_found(
            "STOCK_NO_INICIALIZADO",
            f"El producto {producto_id} no tiene registro de stock inicial.",
        )
    return stock


def procesar_compra(db: Session, payload: CompraEventoIn) -> tuple[str, Decimal | None, str | None]:
    existente = db.execute(
        select(ColaComprasLog).where(ColaComprasLog.mensaje_id == payload.mensaje_id)
    ).scalar_one_or_none()
    if existente and existente.estado_procesamiento == "PROCESADO":
        logger.warning("Mensaje duplicado mensaje_id=%s referencia=%s", payload.mensaje_id, payload.referencia_compra)
        return "DUPLICADO", None, existente.comprobante

    _get_producto_activo(db, payload.producto_id)
    stock = _lock_stock(db, payload.producto_id)
    comprobante = _generar_comprobante(db)
    stock_anterior = stock.cantidad_total
    stock.cantidad_total += payload.cantidad
    stock.fecha_ultima_actualizacion = _now()
    stock.updated_by = "COMPRAS"

    db.add(
        ColaComprasLog(
            mensaje_id=payload.mensaje_id,
            producto_id=payload.producto_id,
            referencia_compra=payload.referencia_compra,
            comprobante=comprobante,
            cantidad=payload.cantidad,
            precio_compra=payload.precio_compra,
            estado_procesamiento="PROCESADO",
            intentos=(existente.intentos + 1 if existente else 1),
            fecha_procesamiento=_now(),
        )
    )
    db.add(
        PrecioCompra(
            producto_id=payload.producto_id,
            precio_compra=payload.precio_compra,
            moneda="",
            documento_ref=payload.referencia_compra,
            comprobante=comprobante,
            proveedor_ref=payload.proveedor_ref,
        )
    )
    _add_movimiento(
        db,
        payload.producto_id,
        "COMPRA",
        "COMPRAS",
        payload.referencia_compra,
        comprobante,
        payload.cantidad,
        stock_anterior,
        stock.cantidad_total,
        "Compra procesada desde cola",
        "COMPRAS",
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Mensaje duplicado mensaje_id=%s referencia=%s", payload.mensaje_id, payload.referencia_compra)
        return "DUPLICADO", None, None
    logger.info("Compra procesada mensaje_id=%s producto_id=%s cantidad=%s", payload.mensaje_id, payload.producto_id, payload.cantidad)
    return "PROCESADO", stock.cantidad_total, comprobante


def crear_reservas(db: Session, payload: ReservaCreate) -> tuple[str, list[tuple[ReservaStock, Decimal]]]:
    resultados: list[tuple[ReservaStock, Decimal]] = []
    try:
        # Un comprobante interno por operación de reserva, compartido por todos los ítems.
        comprobante = _generar_comprobante(db)
        for item in payload.items:
            _get_producto_activo(db, item.producto_id)
            stock = _lock_stock(db, item.producto_id)
            cantidad_disponible = _disponible(stock)
            if cantidad_disponible < item.cantidad:
                logger.warning(
                    "Stock insuficiente documento_ref=%s producto_id=%s solicitado=%s disponible=%s",
                    payload.documento_ref,
                    item.producto_id,
                    item.cantidad,
                    cantidad_disponible,
                )
                raise conflict(
                    "STOCK_INSUFICIENTE",
                    f"Stock insuficiente para el producto {item.producto_id}: solicitado {item.cantidad}, disponible {cantidad_disponible}.",
                )
            stock_anterior = stock.cantidad_total
            stock.cantidad_reservada += item.cantidad
            stock.fecha_ultima_actualizacion = _now()
            stock.updated_by = "VENTAS"
            reserva = ReservaStock(
                producto_id=item.producto_id,
                documento_ref=payload.documento_ref,
                comprobante=comprobante,
                cantidad_reservada=item.cantidad,
                estado_reserva="PENDIENTE",
                created_by="VENTAS",
                updated_by="VENTAS",
            )
            db.add(reserva)
            db.flush()
            _add_movimiento(
                db,
                item.producto_id,
                "RESERVA",
                "VENTAS",
                payload.documento_ref,
                comprobante,
                item.cantidad,
                stock_anterior,
                stock.cantidad_total,
                "Reserva previa a confirmacion de venta",
                "VENTAS",
                reserva.reserva_id,
            )
            resultados.append((reserva, _disponible(stock)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Reserva creada documento_ref=%s comprobante=%s items=%s", payload.documento_ref, comprobante, len(resultados))
    return comprobante, resultados


def confirmar_reserva(
    db: Session,
    reserva_id: int,
    documento_ref: str | None,
    precio_venta: Decimal | None,
) -> tuple[ReservaStock, StockActual, str, str]:
    reserva = _lock_reserva_pendiente(db, reserva_id)
    stock = _lock_stock(db, reserva.producto_id)
    comprobante = _generar_comprobante(db)
    stock_anterior = stock.cantidad_total
    stock.cantidad_total -= reserva.cantidad_reservada
    stock.cantidad_reservada -= reserva.cantidad_reservada
    stock.fecha_ultima_actualizacion = _now()
    stock.updated_by = "VENTAS"
    reserva.estado_reserva = "CONFIRMADA"
    reserva.fecha_confirmacion = _now()
    reserva.updated_by = "VENTAS"
    doc = documento_ref or reserva.documento_ref
    _add_movimiento(
        db,
        reserva.producto_id,
        "VENTA",
        "VENTAS",
        doc,
        comprobante,
        reserva.cantidad_reservada,
        stock_anterior,
        stock.cantidad_total,
        "Confirmacion de venta desde reserva",
        "VENTAS",
        reserva.reserva_id,
    )
    if precio_venta is not None:
        db.add(PrecioVenta(producto_id=reserva.producto_id, precio_venta=precio_venta, moneda="", documento_ref=doc, comprobante=comprobante))
    db.commit()
    logger.info("Venta confirmada documento_ref=%s comprobante=%s reserva_id=%s producto_id=%s", doc, comprobante, reserva_id, reserva.producto_id)
    return reserva, stock, comprobante, doc


def liberar_reserva(db: Session, reserva_id: int, motivo: str) -> tuple[ReservaStock, Decimal, str]:
    reserva = _lock_reserva_pendiente(db, reserva_id)
    stock = _lock_stock(db, reserva.producto_id)
    comprobante = _generar_comprobante(db)
    stock_anterior = stock.cantidad_total
    stock.cantidad_reservada -= reserva.cantidad_reservada
    stock.fecha_ultima_actualizacion = _now()
    stock.updated_by = "VENTAS"
    reserva.estado_reserva = "LIBERADA"
    reserva.fecha_liberacion = _now()
    reserva.motivo_liberacion = motivo
    reserva.updated_by = "VENTAS"
    _add_movimiento(
        db,
        reserva.producto_id,
        "LIBERACION_RESERVA",
        "VENTAS",
        reserva.documento_ref,
        comprobante,
        reserva.cantidad_reservada,
        stock_anterior,
        stock.cantidad_total,
        "Liberacion de reserva",
        "VENTAS",
        reserva.reserva_id,
    )
    db.commit()
    logger.info("Reserva liberada documento_ref=%s comprobante=%s reserva_id=%s motivo=%s", reserva.documento_ref, comprobante, reserva_id, motivo)
    return reserva, reserva.cantidad_reservada, comprobante


def confirmar_venta(db: Session, payload: VentaConfirmarIn) -> str:
    reservas = db.execute(
        select(ReservaStock)
        .where(ReservaStock.documento_ref == payload.documento_ref, ReservaStock.estado_reserva == "PENDIENTE")
        .with_for_update()
    ).scalars().all()
    por_producto = {reserva.producto_id: reserva for reserva in reservas}
    try:
        # Un comprobante interno por operación de confirmación de venta.
        comprobante = _generar_comprobante(db)
        for item in payload.items:
            reserva = por_producto.get(item.producto_id)
            if reserva is None or reserva.cantidad_reservada != item.cantidad:
                raise conflict(
                    "RESERVA_NO_COINCIDE",
                    f"No existe una reserva pendiente para el documento {payload.documento_ref}, producto {item.producto_id} y cantidad {item.cantidad}.",
                )
            stock = _lock_stock(db, item.producto_id)
            stock_anterior = stock.cantidad_total
            stock.cantidad_total -= reserva.cantidad_reservada
            stock.cantidad_reservada -= reserva.cantidad_reservada
            stock.fecha_ultima_actualizacion = _now()
            stock.updated_by = "VENTAS"
            reserva.estado_reserva = "CONFIRMADA"
            reserva.fecha_confirmacion = _now()
            reserva.updated_by = "VENTAS"
            _add_movimiento(
                db,
                item.producto_id,
                "VENTA",
                "VENTAS",
                payload.documento_ref,
                comprobante,
                item.cantidad,
                stock_anterior,
                stock.cantidad_total,
                "Confirmacion de venta completa",
                "VENTAS",
                reserva.reserva_id,
            )
            db.add(
                PrecioVenta(
                    producto_id=item.producto_id,
                    precio_venta=item.precio_venta,
                    moneda="",
                    documento_ref=payload.documento_ref,
                    comprobante=comprobante,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Venta completa confirmada documento_ref=%s comprobante=%s items=%s", payload.documento_ref, comprobante, len(payload.items))
    return comprobante


def listar_movimientos(
    db: Session,
    producto_id: int | None,
    documento_ref: str | None,
    tipo_movimiento: str | None,
) -> list[MovimientoStock]:
    stmt = select(MovimientoStock).order_by(MovimientoStock.fecha_movimiento.desc())
    if producto_id is not None:
        stmt = stmt.where(MovimientoStock.producto_id == producto_id)
    if documento_ref:
        stmt = stmt.where(MovimientoStock.documento_ref == documento_ref)
    if tipo_movimiento:
        stmt = stmt.where(MovimientoStock.tipo_movimiento == tipo_movimiento)
    return list(db.execute(stmt).scalars())
