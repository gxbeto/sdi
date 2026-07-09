"""Test de simulación: compras y ventas aleatorias del catálogo completo.

Reglas simuladas:
- Compra de los 25 productos con cantidad aleatoria de 1 a 20; los más caros
  son más escasos (tope de compra inversamente proporcional al precio).
- Cada documento de compra (OC) y de venta (FV) agrupa de 1 a 3 artículos.
- La cantidad vendida es aleatoria entre 1 y el stock disponible.

La base de pruebas se limpia y con contadores reiniciados al inicio (el fixture
recrea las tablas), y termina la corrida con los datos de la simulación cargados.
Use SIM_SEED para reproducir una corrida exacta.
"""
import os
import random

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from scripts.simulacion import MAX_ARTICULOS_POR_DOCUMENTO, ejecutar_simulacion
from tests.test_inventory_flow import CATALOGO, client  # noqa: F401  (fixture)

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL") or TestClient is None,
    reason="Set TEST_DATABASE_URL and install test dependencies to run integration tests.",
)


def test_simulacion_compras_y_ventas(client):  # noqa: F811
    rng = random.Random(int(os.getenv("SIM_SEED", "20260709")))
    resumen = ejecutar_simulacion(client, rng)

    # Se compraron y vendieron los 25 productos del catálogo.
    assert len(resumen["productos"]) == len(CATALOGO)

    precios = {item[0]: int(item[4]) for item in CATALOGO}
    for codigo, datos in resumen["productos"].items():
        assert 1 <= datos["comprado"] <= 20, codigo
        assert 1 <= datos["vendido"] <= datos["comprado"], codigo
        # ejecutar_simulacion ya verificó contra la API que el stock coincide.
        assert datos["stock_final"] == datos["comprado"] - datos["vendido"], codigo

    # Cada documento (compra y venta) agrupa de 1 a 3 artículos.
    for documento in resumen["compras"] + resumen["ventas"]:
        assert 1 <= len(documento["articulos"]) <= MAX_ARTICULOS_POR_DOCUMENTO

    # Los artículos comprados suman el catálogo completo, sin repetidos.
    comprados = [a["codigo"] for c in resumen["compras"] for a in c["articulos"]]
    assert sorted(comprados) == sorted(precios)
    vendidos = [a["codigo"] for v in resumen["ventas"] for a in v["articulos"]]
    assert sorted(vendidos) == sorted(precios)

    # Escasez: los 5 productos más caros se compran en menor cantidad promedio
    # que los 5 más baratos.
    orden_por_precio = sorted(precios, key=precios.get)
    baratos = [resumen["productos"][c]["comprado"] for c in orden_por_precio[:5]]
    caros = [resumen["productos"][c]["comprado"] for c in orden_por_precio[-5:]]
    assert sum(caros) / len(caros) < sum(baratos) / len(baratos)
