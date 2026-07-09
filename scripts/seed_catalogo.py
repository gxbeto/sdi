"""Registra el catálogo oficial de productos contra la API en ejecución.

Uso:
    python scripts/seed_catalogo.py [URL_BASE]

Por defecto usa http://127.0.0.1:8000. Para cada producto ejecuta el ciclo
operativo completo:
1. Alta en /productos.
2. Evento de compra de 10 unidades al precio de catálogo (registra precio_compra).
3. Reserva de 2 unidades y confirmación de la venta a compra * 1.30 de margen
   * 1.10 de impuesto (registra la reserva CONFIRMADA, el movimiento VENTA y
   precio_venta).

Todos los productos se dan de alta con impuesto del 10 %.

Cada producto termina con stock 8 (10 compradas - 2 vendidas).
El script es idempotente: los códigos ya existentes se omiten, los eventos de
compra repetidos se marcan como DUPLICADO sin duplicar stock, y la venta se
salta si el producto ya registra un movimiento VENTA.
"""
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


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

    with httpx.Client(base_url=base_url, timeout=30) as client:
        for indice, (codigo, categoria, nombre, unidad, precio) in enumerate(CATALOGO, start=1):
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
            if alta.status_code == 201:
                producto_id = alta.json()["producto_id"]
                print(f"CREADO   {codigo} -> producto_id={producto_id}")
            elif alta.status_code == 409:
                existente = client.get("/productos", params={"filtro": codigo})
                existente.raise_for_status()
                producto_id = existente.json()[0]["producto_id"]
                print(f"EXISTE   {codigo} -> producto_id={producto_id}")
            else:
                print(f"ERROR    {codigo}: {alta.status_code} {alta.text}")
                continue

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
            if compra.status_code == 200:
                print(f"  compra {compra.json()['estado_procesamiento']} precio={precio}")
            else:
                print(f"  compra ERROR: {compra.status_code} {compra.text}")
                continue

            # Idempotencia de la venta: si el producto ya tiene un movimiento VENTA,
            # no se vuelve a reservar ni a vender.
            consulta = client.get(
                f"/productos/{producto_id}",
                params={"include": "movimientos", "limite_movimientos": 50},
            )
            consulta.raise_for_status()
            movimientos = consulta.json().get("movimientos") or []
            if any(m["tipo_movimiento"] == "VENTA" for m in movimientos):
                print("  venta ya registrada, se omite")
                continue

            reserva = client.post(
                "/stock/reservas",
                json={
                    "documento_ref": f"FV-001-{indice:06d}",
                    "items": [{"producto_id": producto_id, "cantidad": "2"}],
                },
            )
            if reserva.status_code != 201:
                print(f"  reserva ERROR: {reserva.status_code} {reserva.text}")
                continue
            reserva_id = reserva.json()["reservas"][0]["reserva_id"]

            precio_venta = precio_venta_catalogo(precio)
            venta = client.post(
                f"/stock/reservas/{reserva_id}/confirmar",
                json={"documento_ref": f"FV-001-{indice:06d}", "precio_venta": precio_venta},
            )
            if venta.status_code == 200:
                print(f"  venta CONFIRMADA precio={precio_venta} stock={venta.json()['stock_total_actual']}")
            else:
                print(f"  venta ERROR: {venta.status_code} {venta.text}")


if __name__ == "__main__":
    main()
