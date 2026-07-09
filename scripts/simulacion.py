"""Simulación de operación completa del módulo Stock con el catálogo oficial.

Uso (contra una API en ejecución):
    python scripts/simulacion.py [URL_BASE] [--seed N] [--db-url URL] [--no-reset]

Por defecto usa http://127.0.0.1:8000 y, antes de simular, BORRA TODOS los datos
y reinicia los contadores (TRUNCATE ... RESTART IDENTITY) de la base configurada
en .env (o la indicada con --db-url). El borrado pide confirmación explícita
(hay que escribir 'borrar'); use --sin-confirmar solo en automatizaciones y
--no-reset para simular sin borrar. NO ejecutar el reset contra producción.

Reglas de la simulación:
- Se compran los 25 productos del catálogo. La cantidad es aleatoria de 1 a 20,
  con escasez proporcional al precio: los productos más caros reciben un tope
  menor (el más caro compra 1-2 unidades; el más barato hasta 20).
- Cada documento externo de compra (OC-001-nnnnnn) agrupa de 1 a 3 artículos,
  hasta completar el catálogo. Cada artículo viaja como un evento de compra
  con su propio mensaje_id, compartiendo la referencia del documento.
- Las ventas siguen el mismo esquema: cada documento de venta (FV-001-nnnnnn)
  agrupa de 1 a 3 artículos. La cantidad vendida es aleatoria entre 1 y el
  stock disponible del producto. Cada venta se registra como reserva del
  documento y confirmación de la venta completa.
- Todos los productos tributan 10 % de impuesto, y el precio de venta es el
  precio de compra con 30 % de margen más el impuesto (compra * 1.30 * 1.10).

Al final se verifica que el stock de cada producto sea comprado - vendido y
que no queden cantidades reservadas.
"""
import argparse
import random
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_inventory_flow import (  # noqa: E402
    CATALOGO,
    IMPUESTO_PORCENTAJE,
    precio_venta_catalogo,
)

MAX_ARTICULOS_POR_DOCUMENTO = 3
CANTIDAD_MAXIMA_COMPRA = 20

# Tablas del módulo Stock, en cualquier orden: TRUNCATE ... CASCADE resuelve las FK.
TABLAS_STOCK = [
    "movimientos_stock",
    "precios_compra",
    "precios_venta",
    "cola_compras_log",
    "reservas_stock",
    "stock_actual",
    "productos",
    "secuencia_comprobante",
]


def reiniciar_datos(db_url: str | None = None) -> None:
    """Borra todos los datos del módulo y reinicia los contadores de identidad."""
    import sqlalchemy as sa

    if db_url is None:
        from app.core.config import get_settings

        db_url = get_settings().sqlalchemy_database_url

    engine = sa.create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(f"TRUNCATE TABLE {', '.join(TABLAS_STOCK)} RESTART IDENTITY CASCADE")
        )
    destino = db_url.rsplit("@", 1)[-1]
    print(f"Datos borrados y contadores reiniciados en {destino}")


def _maximo_a_comprar(precio: int, precios_ordenados: list[int]) -> int:
    """Tope de compra inversamente proporcional al precio: los caros son escasos."""
    posicion = precios_ordenados.index(precio) / max(len(precios_ordenados) - 1, 1)
    return max(1, round(CANTIDAD_MAXIMA_COMPRA - (CANTIDAD_MAXIMA_COMPRA - 1) * posicion))


def _agrupar_en_documentos(rng: random.Random, elementos: list) -> list[list]:
    """Parte la lista en grupos de 1 a MAX_ARTICULOS_POR_DOCUMENTO artículos."""
    grupos = []
    i = 0
    while i < len(elementos):
        tamano = rng.randint(1, MAX_ARTICULOS_POR_DOCUMENTO)
        grupos.append(elementos[i : i + tamano])
        i += tamano
    return grupos


def _verificar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise RuntimeError(mensaje)


def ejecutar_simulacion(client, rng: random.Random) -> dict:
    """Ejecuta la simulación completa. `client` puede ser httpx.Client o TestClient."""
    precios_ordenados = sorted(int(item[4]) for item in CATALOGO)
    resumen = {"productos": {}, "compras": [], "ventas": []}

    # 1) Alta del catálogo completo.
    ids: dict[str, int] = {}
    for codigo, categoria, nombre, unidad, _precio in CATALOGO:
        alta = client.post(
            "/productos",
            json={
                "codigo": codigo,
                "nombre": nombre,
                "categoria": categoria,
                "unidad_medida": unidad,
                "impuesto": str(IMPUESTO_PORCENTAJE),
            },
        )
        _verificar(alta.status_code == 201, f"alta {codigo}: {alta.status_code} {alta.text}")
        ids[codigo] = alta.json()["producto_id"]

    # 2) Compras: documentos externos OC con 1-3 artículos hasta cubrir el catálogo.
    pendientes_compra = list(CATALOGO)
    rng.shuffle(pendientes_compra)
    numero_mensaje = 0
    for numero_doc, grupo in enumerate(_agrupar_en_documentos(rng, pendientes_compra), start=1):
        referencia = f"OC-001-{numero_doc:06d}"
        articulos = []
        for codigo, _cat, _nom, _uni, precio in grupo:
            numero_mensaje += 1
            cantidad = rng.randint(1, _maximo_a_comprar(int(precio), precios_ordenados))
            compra = client.post(
                "/compras/eventos",
                json={
                    "mensaje_id": f"CMP-SIM-{numero_mensaje:04d}",
                    "referencia_compra": referencia,
                    "producto_id": ids[codigo],
                    "cantidad": str(cantidad),
                    "precio_compra": precio,
                },
            )
            _verificar(
                compra.status_code == 200
                and compra.json()["estado_procesamiento"] == "PROCESADO",
                f"compra {codigo}: {compra.status_code} {compra.text}",
            )
            resumen["productos"][codigo] = {"comprado": cantidad, "vendido": 0}
            articulos.append({"codigo": codigo, "cantidad": cantidad})
        resumen["compras"].append({"documento": referencia, "articulos": articulos})

    # 3) Ventas: documentos FV con 1-3 artículos, cantidad aleatoria hasta el disponible.
    pendientes_venta = list(CATALOGO)
    rng.shuffle(pendientes_venta)
    for numero_doc, grupo in enumerate(_agrupar_en_documentos(rng, pendientes_venta), start=1):
        documento = f"FV-001-{numero_doc:06d}"
        items = []
        for codigo, _cat, _nom, _uni, precio in grupo:
            disponible = resumen["productos"][codigo]["comprado"]
            items.append(
                {
                    "codigo": codigo,
                    "cantidad": rng.randint(1, disponible),
                    "precio": precio_venta_catalogo(precio),
                }
            )

        reserva = client.post(
            "/stock/reservas",
            json={
                "documento_ref": documento,
                "items": [
                    {"producto_id": ids[it["codigo"]], "cantidad": str(it["cantidad"])}
                    for it in items
                ],
            },
        )
        _verificar(reserva.status_code == 201, f"reserva {documento}: {reserva.status_code} {reserva.text}")

        venta = client.post(
            "/ventas/confirmar",
            json={
                "documento_ref": documento,
                "items": [
                    {
                        "producto_id": ids[it["codigo"]],
                        "cantidad": str(it["cantidad"]),
                        "precio_venta": it["precio"],
                    }
                    for it in items
                ],
            },
        )
        _verificar(
            venta.status_code == 200 and venta.json()["estado"] == "CONFIRMADA",
            f"venta {documento}: {venta.status_code} {venta.text}",
        )
        for it in items:
            resumen["productos"][it["codigo"]]["vendido"] = it["cantidad"]
        resumen["ventas"].append({"documento": documento, "articulos": items})

    # 4) Verificación final: stock = comprado - vendido y nada reservado.
    for codigo, datos in resumen["productos"].items():
        consulta = client.get(f"/productos/{ids[codigo]}", params={"include": "stock"})
        _verificar(consulta.status_code == 200, f"consulta {codigo}: {consulta.text}")
        stock = consulta.json()["stock"]
        esperado = datos["comprado"] - datos["vendido"]
        _verificar(
            stock["cantidad_total"] == float(esperado),
            f"stock {codigo}: esperado {esperado}, actual {stock['cantidad_total']}",
        )
        _verificar(
            stock["cantidad_reservada"] == 0.0,
            f"reservado {codigo}: debería ser 0, actual {stock['cantidad_reservada']}",
        )
        datos["stock_final"] = esperado

    return resumen


def imprimir_resumen(resumen: dict) -> None:
    print(f"\nCompras: {len(resumen['compras'])} documentos")
    for compra in resumen["compras"]:
        detalle = ", ".join(f"{a['codigo']} x{a['cantidad']}" for a in compra["articulos"])
        print(f"  {compra['documento']}: {detalle}")
    print(f"\nVentas: {len(resumen['ventas'])} documentos")
    for venta in resumen["ventas"]:
        detalle = ", ".join(f"{a['codigo']} x{a['cantidad']}" for a in venta["articulos"])
        print(f"  {venta['documento']}: {detalle}")
    print("\nStock final por producto:")
    for codigo in sorted(resumen["productos"]):
        d = resumen["productos"][codigo]
        print(f"  {codigo}: comprado={d['comprado']:>2} vendido={d['vendido']:>2} stock={d['stock_final']:>2}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulación de compras y ventas del catálogo.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", type=int, default=None, help="Semilla para reproducir la simulación.")
    parser.add_argument("--db-url", default=None, help="URL de BD para el reset (por defecto, la del .env).")
    parser.add_argument("--no-reset", action="store_true", help="No borrar los datos antes de simular.")
    parser.add_argument(
        "--sin-confirmar",
        action="store_true",
        help="No pedir confirmación antes del reset (para uso automatizado).",
    )
    args = parser.parse_args()

    if not args.no_reset:
        if not args.sin_confirmar:
            if args.db_url:
                destino = args.db_url.rsplit("@", 1)[-1]
            else:
                from app.core.config import get_settings

                destino = f"{get_settings().db_host}:{get_settings().db_port}/{get_settings().db_name}"
            print(f"ATENCIÓN: se van a BORRAR TODOS los datos de {destino}.")
            respuesta = input("Escriba 'borrar' para continuar (cualquier otra cosa cancela): ")
            if respuesta.strip().lower() != "borrar":
                print("Simulación cancelada. Use --no-reset para simular sin borrar.")
                sys.exit(1)
        reiniciar_datos(args.db_url)

    rng = random.Random(args.seed)
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        resumen = ejecutar_simulacion(client, rng)
    imprimir_resumen(resumen)


if __name__ == "__main__":
    main()
