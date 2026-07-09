import os

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
create_engine = sqlalchemy.create_engine
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.comprobante import es_comprobante_valido
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import inventory  # noqa: F401

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL") or TestClient is None,
    reason="Set TEST_DATABASE_URL and install test dependencies to run integration tests.",
)


# El catálogo oficial y las reglas comerciales viven en scripts/catalogo.py
# (módulo sin dependencias de test, compartido con seed y simulación).
from scripts.catalogo import (  # noqa: E402,F401
    CATALOGO,
    CATALOGO_POR_CODIGO,
    IMPUESTO_PORCENTAJE,
    MARGEN_VENTA,
    precio_venta_catalogo,
)


# La limpieza de tablas se hace al INICIO de cada test (no al final): así cada test
# arranca aislado (con contadores reiniciados, porque las tablas se recrean) y, al
# terminar la corrida, los datos del último test ejecutado quedan registrados en la
# base de pruebas para su inspección (en la suite completa, la simulación de
# tests/test_simulacion.py).
@pytest.fixture()
def client():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def crear_producto(client, codigo: str) -> int:
    codigo, categoria, nombre, unidad, _precio = CATALOGO_POR_CODIGO[codigo]
    respuesta = client.post(
        "/productos",
        json={
            "codigo": codigo,
            "nombre": nombre,
            "categoria": categoria,
            "unidad_medida": unidad,
            "impuesto": str(IMPUESTO_PORCENTAJE),
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["producto_id"]


def test_compra_reserva_confirmacion_y_duplicado(client):
    """Flujo completo con un producto real del catálogo: Teclado Satellite AK-910.

    Compra 10 unidades a 32.000 (precio de catálogo), reserva 2 para la venta
    FV-001-000123 y confirma la venta a 45.760 (32.000 * 1.30 de margen * 1.10
    de impuesto).
    """
    producto_id = crear_producto(client, "INF-006")

    compra = client.post(
        "/compras/eventos",
        json={
            "mensaje_id": "CMP-2026-0001",
            "referencia_compra": "OC-001-000555",
            "producto_id": producto_id,
            "cantidad": "10",
            "precio_compra": "32000",
        },
    )
    assert compra.status_code == 200
    assert compra.json()["estado_procesamiento"] == "PROCESADO"
    # El proceso de Stock genera un comprobante interno válido.
    assert es_comprobante_valido(compra.json()["comprobante"])
    assert compra.json()["documento_ref"] == "OC-001-000555"

    duplicada = client.post(
        "/compras/eventos",
        json={
            "mensaje_id": "CMP-2026-0001",
            "referencia_compra": "OC-001-000555",
            "producto_id": producto_id,
            "cantidad": "10",
            "precio_compra": "32000",
        },
    )
    assert duplicada.status_code == 200
    assert duplicada.json()["estado_procesamiento"] == "DUPLICADO"

    reserva = client.post(
        "/stock/reservas",
        json={"documento_ref": "FV-001-000123", "items": [{"producto_id": producto_id, "cantidad": "2"}]},
    )
    assert reserva.status_code == 201
    assert reserva.json()["documento_ref"] == "FV-001-000123"
    assert es_comprobante_valido(reserva.json()["comprobante"])
    reserva_id = reserva.json()["reservas"][0]["reserva_id"]

    confirmacion = client.post(
        f"/stock/reservas/{reserva_id}/confirmar",
        json={"documento_ref": "FV-001-000123", "precio_venta": precio_venta_catalogo("32000")},
    )
    assert confirmacion.status_code == 200
    assert confirmacion.json()["estado"] == "CONFIRMADA"
    assert confirmacion.json()["stock_total_actual"] == 8.0
    assert es_comprobante_valido(confirmacion.json()["comprobante"])


def test_reserva_sin_stock_falla(client):
    """Un producto recién creado (Cable HDMI 1.5) no tiene stock: la reserva debe fallar."""
    producto_id = crear_producto(client, "INF-007")

    reserva = client.post(
        "/stock/reservas",
        json={"documento_ref": "FV-001-000200", "items": [{"producto_id": producto_id, "cantidad": "1"}]},
    )
    assert reserva.status_code == 409
    assert reserva.json()["codigo"] == "STOCK_INSUFICIENTE"


def test_codigo_duplicado_rechazado(client):
    """No se puede registrar dos veces el mismo código de catálogo."""
    crear_producto(client, "CEL-001")

    repetido = client.post(
        "/productos",
        json={
            "codigo": "CEL-001",
            "nombre": "Celular Apple iPhone 17 256GB",
            "categoria": "Celulares",
        },
    )
    assert repetido.status_code == 409
    assert repetido.json()["codigo"] == "PRODUCTO_CODIGO_DUPLICADO"


def test_registro_catalogo_completo(client):
    """Registra el catálogo completo (25 productos en 4 categorías) con su precio.

    Por cada producto ejecuta el ciclo operativo completo:
    - alta del producto (codigo, nombre, categoria, unidad, impuesto 10 %),
    - compra de 10 unidades al precio de catálogo (queda precio_compra),
    - reserva de 2 unidades y confirmación de la venta a compra * 1.30 de
      margen * 1.10 de impuesto (quedan la reserva CONFIRMADA, el movimiento
      VENTA y precio_venta).

    Al finalizar cada producto queda con stock 8 (10 compradas - 2 vendidas).
    Está definido último a propósito, para que la base de pruebas termine la
    corrida con el catálogo completo cargado.
    """
    for indice, (codigo, categoria, nombre, unidad, precio) in enumerate(CATALOGO, start=1):
        producto_id = crear_producto(client, codigo)

        compra = client.post(
            "/compras/eventos",
            json={
                "mensaje_id": f"CMP-CATALOGO-{indice:04d}",
                "referencia_compra": f"OC-001-{indice:06d}",
                "producto_id": producto_id,
                "cantidad": "10",
                "precio_compra": precio,
            },
        )
        assert compra.status_code == 200, compra.text
        assert compra.json()["estado_procesamiento"] == "PROCESADO"

        reserva = client.post(
            "/stock/reservas",
            json={
                "documento_ref": f"FV-001-{indice:06d}",
                "items": [{"producto_id": producto_id, "cantidad": "2"}],
            },
        )
        assert reserva.status_code == 201, reserva.text
        reserva_id = reserva.json()["reservas"][0]["reserva_id"]

        venta = client.post(
            f"/stock/reservas/{reserva_id}/confirmar",
            json={"documento_ref": f"FV-001-{indice:06d}", "precio_venta": precio_venta_catalogo(precio)},
        )
        assert venta.status_code == 200, venta.text
        assert venta.json()["estado"] == "CONFIRMADA"
        assert venta.json()["stock_total_actual"] == 8.0

    listado = client.get("/productos")
    assert listado.status_code == 200
    productos = listado.json()
    assert len(productos) == len(CATALOGO)

    registrados = {p["codigo"]: p for p in productos}
    for codigo, categoria, nombre, unidad, _precio in CATALOGO:
        assert codigo in registrados
        assert registrados[codigo]["nombre"] == nombre
        assert registrados[codigo]["categoria"] == categoria
        assert registrados[codigo]["unidad_medida"] == unidad
        assert registrados[codigo]["impuesto"] == 10.0
        assert registrados[codigo]["activo"] is True

    categorias = {p["categoria"] for p in productos}
    assert categorias == {"Informatica", "Celulares", "Perfumes", "Salud"}

    # Verificación puntual de precio, stock y movimientos con la consulta flexible.
    teclado = registrados["INF-006"]
    consulta = client.get(
        f"/productos/{teclado['producto_id']}",
        params={"include": "producto,stock,precios,movimientos"},
    )
    assert consulta.status_code == 200
    cuerpo = consulta.json()
    assert cuerpo["producto"]["nombre"] == "Teclado Satellite AK-910 USB / Negro"
    assert cuerpo["producto"]["impuesto"] == 10.0
    assert cuerpo["stock"]["cantidad_total"] == 8.0
    assert cuerpo["stock"]["cantidad_reservada"] == 0.0
    assert cuerpo["precios"]["precio_compra"] == 32000.0
    # 32000 * 1.30 (margen) * 1.10 (impuesto) = 45760
    assert cuerpo["precios"]["precio_venta"] == 45760.0
    tipos = {m["tipo_movimiento"] for m in cuerpo["movimientos"]}
    assert tipos == {"COMPRA", "RESERVA", "VENTA"}
