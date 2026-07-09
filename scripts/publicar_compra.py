"""Publica un evento de compra en la cola RabbitMQ para probar el consumer.

Uso (con el venv activo, desde la raíz del proyecto):
    python scripts/publicar_compra.py --producto-id 1 --cantidad 5 --precio 32000
    python scripts/publicar_compra.py --mensaje-id CMP-MQ-0001 ...   # id explícito para probar idempotencia

Lee RABBITMQ_URL y RABBITMQ_COMPRAS_QUEUE del .env del proyecto (igual que el
consumer). El mensaje replica el schema CompraEventoIn que el consumer valida.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

import pika

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica un evento de compra en la cola de RabbitMQ.")
    parser.add_argument("--producto-id", type=int, required=True)
    parser.add_argument("--cantidad", default="5")
    parser.add_argument("--precio", default="32000")
    parser.add_argument("--referencia", default="OC-001-000900", help="Documento externo (OC-...).")
    parser.add_argument(
        "--mensaje-id",
        default=None,
        help="Clave de idempotencia. Por defecto se genera una única; repetirla debe dar DUPLICADO.",
    )
    args = parser.parse_args()

    mensaje = {
        "mensaje_id": args.mensaje_id or f"CMP-MQ-{uuid.uuid4().hex[:8].upper()}",
        "referencia_compra": args.referencia,
        "producto_id": args.producto_id,
        "cantidad": args.cantidad,
        "precio_compra": args.precio,
    }

    settings = get_settings()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.rabbitmq_compras_queue, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=settings.rabbitmq_compras_queue,
        body=json.dumps(mensaje),
        # delivery_mode=2: mensaje persistente, sobrevive reinicios del broker.
        properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
    )
    connection.close()
    print(f"Publicado en '{settings.rabbitmq_compras_queue}': {json.dumps(mensaje)}")


if __name__ == "__main__":
    main()
