import json
import logging

import pika
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.schemas.inventory import CompraEventoIn
from app.services.inventory import procesar_compra

configure_logging()
logger = logging.getLogger(__name__)


def _callback(channel, method, _properties, body: bytes) -> None:
    db = SessionLocal()
    try:
        payload = CompraEventoIn.model_validate(json.loads(body.decode("utf-8")))
        estado, _, _ = procesar_compra(db, payload)
        logger.info("Mensaje RabbitMQ confirmado mensaje_id=%s estado=%s", payload.mensaje_id, estado)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except (json.JSONDecodeError, ValidationError) as exc:
        # Mensajes con formato inválido se descartan (ack) para no bloquear la cola
        # con mensajes que nunca podrán procesarse correctamente.
        logger.error("Mensaje de compra inválido (-ack): %s", exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        # Errores transitorios (BD caída, timeout) usan nack+requeue para reintentar.
        logger.exception("Error procesando mensaje de compra (reintentando): %s", exc)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        db.close()


def main() -> None:
    settings = get_settings() # Se obtiene la configuración dentro de main() para evitar cargarla al importar el módulo, lo que es útil para pruebas unitarias.
    params = pika.URLParameters(settings.rabbitmq_url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()  # Se declara la cola aquí para asegurar que exista antes de consumir, aunque en producción se asume que ya está creada por la infraestructura.
    channel.queue_declare(queue=settings.rabbitmq_compras_queue, durable=True)

    # prefetch_count=1 garantiza procesamiento secuencial: el worker no recibe otro
    # mensaje hasta confirmar el actual, previniendo actualizaciones concurrentes de stock.
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=settings.rabbitmq_compras_queue, on_message_callback=_callback)
    logger.info("Consumer compras escuchando queue=%s", settings.rabbitmq_compras_queue)
    channel.start_consuming()   # El proceso se mantiene activo esperando mensajes; se detiene con Ctrl+C o señal de terminación del contenedor.


if __name__ == "__main__":
    main()


