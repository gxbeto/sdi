from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.api import compras, productos, stock, ventas
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.schemas.inventory import HealthOut

configure_logging()

app = FastAPI(
    title="SDI - Servicio Distribuido de Inventario",
    summary="API de gestion de stock para integracion entre modulos ERP.",
    version="0.1.0",
    description="""
API REST del modulo de Stock del sistema SDI.

Permite administrar productos, consultar stock, crear reservas,
confirmar ventas, liberar reservas y procesar eventos de compra.

Esta API esta pensada para integracion entre sistemas internos:
- Modulo de Ventas
- Modulo de Compras
- Modulo de Stock
- Servicios administrativos internos

La primera version no incluye seguridad formal. El consumo debe realizarse
en ambiente controlado de red interna o infraestructura protegida.
""",
    terms_of_service="https://docs.sdi.local/terminos-api",
    contact={
        "name": "Equipo SDI - Sistema Distribuido de Inventario",
        "email": "gxbeto@gmail.com",
    },
    license_info={
        "name": "Uso de la catedra Programacion de Aplicaiciones en Red - Profesor Alfonso Fernandez",
    },
    servers=[
        {
            "url": "http://127.0.0.1:8000",
            "description": "Ambiente local de desarrollo",
        },
        {
            # Puerto 8181: los navegadores bloquean el 6000 (ERR_UNSAFE_PORT).
            "url": "http://158.220.111.78:8181",
            "description": "Ambiente de pruebas / integracion",
        },
    ],
    openapi_version="3.2.0",
)

original_openapi = app.openapi


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = original_openapi()
    schema["externalDocs"] = {
        "description": "Documentacion tecnica y funcional del modulo SDI Stock",
        "url": "http://158.220.111.78:8181/documentacion",
    }

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


def _validation_message(error: dict) -> str:
    location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
    error_type = error.get("type")
    context = error.get("ctx") or {}
    messages = {
        "string_too_short": f"Debe tener al menos {context.get('min_length')} caracter(es).",
        "string_too_long": f"Debe tener como máximo {context.get('max_length')} caracter(es).",
        "too_short": f"Debe contener al menos {context.get('min_length')} elemento(s).",
        "greater_than": f"Debe ser mayor que {context.get('gt')}.",
        "greater_than_equal": f"Debe ser mayor o igual que {context.get('ge')}.",
        "missing": "Campo obligatorio.",
        "decimal_max_digits": f"Debe tener como máximo {context.get('max_digits')} dígitos.",
        "decimal_max_places": f"Debe tener como máximo {context.get('decimal_places')} decimales.",
        "int_parsing": "Debe ser un número entero.",
        "decimal_parsing": "Debe ser un número decimal válido.",
        "string_pattern_mismatch": "No cumple el formato requerido.",
        "enum": "Valor fuera del catálogo permitido.",
    }
    detail = messages.get(error_type, error.get("msg", "Request inválido."))
    return f"{location}: {detail}" if location else detail


@app.exception_handler(AppError)
def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"estado": "ERROR", "codigo": exc.code, "mensaje": exc.message},
    )


@app.exception_handler(RequestValidationError)
def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    return JSONResponse(
        status_code=422,
        content={"estado": "ERROR", "codigo": "VALIDACION_ERROR", "mensaje": _validation_message(first_error)},
    )




@app.exception_handler(Exception)
def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "estado": "ERROR",
            "codigo": "ERROR_INTERNO",
            "mensaje": "Ocurrió un error interno al procesar la operación.",
        },
    )


@app.get(
    "/health",
    tags=["health"],
    summary="Verificar disponibilidad del servicio SDI",
    description="Retorna un estado simple para confirmar que la API esta levantada y responde requests HTTP.",
    response_model=HealthOut,
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
def health() -> HealthOut:
    return HealthOut(status="ok")


_DOCUMENTACION_HTML = Path(__file__).resolve().parents[1] / "docs" / "sdi_documentacion_servicios.html"


# Guía funcional de los servicios, enlazada desde /docs (descripción y externalDocs).
# include_in_schema=False: es una página de documentación, no parte del contrato.
@app.get("/documentacion", include_in_schema=False)
def documentacion() -> FileResponse:
    return FileResponse(_DOCUMENTACION_HTML, media_type="text/html; charset=utf-8")


app.include_router(productos.router)
app.include_router(stock.router)
app.include_router(compras.router)
app.include_router(ventas.router)
