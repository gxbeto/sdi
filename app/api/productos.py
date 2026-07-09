from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import responses
from app.db.session import get_db
from app.schemas.inventory import ProductoConsultaOut, ProductoCreate, ProductoCreated, ProductoOut
from app.services import inventory as service

router = APIRouter(prefix="/productos", tags=["productos"])


@router.post(
    "",
    summary="Crear producto e inicializar su stock en cero",
    description="Registra un producto activo en el catalogo e inserta automaticamente su fila en stock_actual con cantidades en cero.",
    response_model=ProductoCreated,
    status_code=201,
    responses={
        201: responses.PRODUCTO_CREATED_OK,
        409: responses.PRODUCTO_CODIGO_DUPLICADO,
        422: responses.VALIDATION_ERROR,
    },
)
def crear_producto(payload: ProductoCreate, db: Session = Depends(get_db)) -> ProductoCreated:
    producto = service.crear_producto(db, payload)
    return ProductoCreated(producto_id=producto.producto_id, codigo=producto.codigo)


@router.get(
    "/{producto_id}",
    summary="Consultar producto por identificador (consulta flexible agrupada)",
    description=(
        "Devuelve una respuesta agrupada con los bloques solicitados en el parámetro "
        "`include`: producto, stock, precios y/o movimientos (separados por coma). "
        "Si no se informa include, se asume `producto`. El orden no afecta el resultado "
        "y los duplicados se ignoran. Un valor no permitido responde 422 VALIDACION_ERROR. "
        "No reemplaza a GET /stock/{producto_id} ni a GET /stock/movimientos."
    ),
    response_model=ProductoConsultaOut,
    response_model_exclude_none=True,
    responses={
        200: responses.PRODUCTO_CONSULTA_OK,
        404: responses.PRODUCTO_NO_EXISTE,
        422: responses.VALIDATION_ERROR,
    },
)
def obtener_producto(
    producto_id: int,
    include: str = Query(
        default="producto",
        description=(
            "Bloques a incluir, separados por coma. Valores permitidos: "
            "producto, stock, precios, movimientos. Ej.: include=producto,stock,precios"
        ),
    ),
    limite_movimientos: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Cantidad máxima de movimientos (solo aplica si include contiene 'movimientos'). Orden: más recientes primero.",
    ),
    db: Session = Depends(get_db),
) -> ProductoConsultaOut:
    return service.obtener_producto_con_include(db, producto_id, include, limite_movimientos)


@router.get(
    "",
    summary="Listar productos con filtros opcionales",
    description="Lista productos del catalogo. Permite filtrar por codigo exacto y por estado activo/inactivo.",
    response_model=list[ProductoOut],
    responses={200: responses.PRODUCTOS_LIST_OK, 422: responses.VALIDATION_ERROR},
)
def listar_productos(
    filtro: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
        description="Código exacto del producto.",
        examples=["INF-006"],
    ),
    activo: bool | None = Query(
        default=None,
        description="Estado del producto. Use true para activos y false para inactivos.",
        examples=[True, False],
    ),
    db: Session = Depends(get_db),
) -> list[ProductoOut]:
    return service.listar_productos(db, filtro, activo)
