import os
from decimal import Decimal

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


# Catálogo oficial de productos del sistema: (codigo, categoria, nombre, unidad_medida, precio).
# El precio se registra vía evento de compra, que es la vía de ingreso de precios al módulo Stock.
CATALOGO = [
    # Informatica
    ("INF-001", "Informatica", "Processador Intel Core i5-12400 2.5GHz LGA 1700 18MB", "UNIDAD", "1300000"),
    ("INF-002", "Informatica", "Processador AMD Ryzen 7 5700G 3.8GHz AM4 20MB", "UNIDAD", "1274000"),
    ("INF-003", "Informatica", "Processador AMD Ryzen Threadripper Pro 9975WX Socket STR5 / 4.0GHZ / 160MB", "UNIDAD", "32500000"),
    ("INF-004", "Informatica", "Cpu Xeon Gold 6134..3.2GHZ SR3AR", "UNIDAD", "7000000"),
    ("INF-005", "Informatica", "Processador AMD Ryzen 9 9950X3D2 4.3GHz AM5 208MB", "UNIDAD", "6860000"),
    ("INF-006", "Informatica", "Teclado Satellite AK-910 USB / Negro", "UNIDAD", "32000"),
    ("INF-007", "Informatica", "Cable HDMI 1.5", "UNIDAD", "10000"),
    ("INF-008", "Informatica", "Mineradora Bitmain Antminer S21+ de 225 TH/s", "UNIDAD", "20020000"),
    ("INF-009", "Informatica", "Memória Keepdata DDR3 8GB 1600MHz KD16N11/8G", "UNIDAD", "167300"),
    ("INF-010", "Informatica", "Memória Kingston Fury Beast DDR4 16GB 3200MHz", "UNIDAD", "931000"),
    ("INF-011", "Informatica", "Placa de Vídeo Biostar Extreme Gaming GeForce RTX2060 Super 8GB GDDR6 PCI-Express", "UNIDAD", "1869000"),
    ("INF-012", "Informatica", "Placa de Vídeo Asus TUF Gaming GeForce RTX5070 OC 12GB GDDR7 PCI-Express", "UNIDAD", "5600000"),
    # Celulares
    ("CEL-001", "Celulares", "Celular Apple iPhone 17 256GB", "UNIDAD", "5880000"),
    ("CEL-002", "Celulares", "Celular Xiaomi Redmi Note 15 Dual Chip 256GB 4G Global", "UNIDAD", "1253000"),
    ("CEL-003", "Celulares", "Celular Xiaomi 17 Ultra Dual Chip 1TB 5G Global", "UNIDAD", "9751000"),
    ("CEL-004", "Celulares", "Celular Apple iPhone 17 Pro Max 2TB", "UNIDAD", "13734000"),
    # Perfumes
    ("PER-001", "Perfumes", "Sistelle Perfume Tester Sanderling Shine Blooming Edp Femenino 100ML", "UNIDAD", "70000000"),
    ("PER-002", "Perfumes", "P.Boadicea The Victorious Resplendent 100ML", "UNIDAD", "9170000"),
    ("PER-003", "Perfumes", "Spirit Dubai Oud Edp 50ML", "UNIDAD", "5000000"),
    ("PER-004", "Perfumes", "PerfumeMonella Vagabonda Belle Edt 100ML - Feminino", "UNIDAD", "210000"),
    # Salud
    ("SAL-001", "Salud", "Balanza Comercial Quanta QTBD250 40KG", "UNIDAD", "35000"),
    ("SAL-002", "Salud", "Balanza Comercial Satellite AB-21001 40KG", "UNIDAD", "120000"),
    ("SAL-003", "Salud", "Balanza de Peso Corporal Quanta QTBCB200 180KG", "UNIDAD", "60000"),
    ("SAL-004", "Salud", "Medidor de Presion More Fitness MF-641ND", "UNIDAD", "110000"),
    ("SAL-005", "Salud", "Medidor de Presion More Fitness MF-333", "UNIDAD", "70000"),
]

CATALOGO_POR_CODIGO = {item[0]: item for item in CATALOGO}

# Reglas comerciales del catálogo:
# - Todos los productos tributan 10 % de impuesto.
# - El precio de venta es el precio de compra con 30 % de margen, y sobre ese
#   resultado se recarga el impuesto: venta = compra * 1.30 * 1.10.
IMPUESTO_PORCENTAJE = Decimal("10")
MARGEN_VENTA = Decimal("1.30")


def precio_venta_catalogo(precio_compra: str) -> str:
    recargo_impuesto = 1 + IMPUESTO_PORCENTAJE / 100
    venta = Decimal(precio_compra) * MARGEN_VENTA * recargo_impuesto
    return str(venta.quantize(Decimal("0.01")))


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
