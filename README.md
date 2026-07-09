# SDI

Backend de inventario con FastAPI, PostgreSQL, SQLAlchemy, Alembic y RabbitMQ.

## Ejecutar local sin Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger queda disponible en `http://127.0.0.1:8000/docs`.

## Generar OpenAPI YAML

```powershell
python scripts/generate_openapi_yaml.py
```

El archivo se genera como `openapi.yaml` en la raíz del proyecto.

## Requisitos locales

Instalar y tener corriendo:

- PostgreSQL
- RabbitMQ, solo si se va a usar el consumer real de compras

La configuración por defecto queda en `.env.example`:

```env
DB_ENGINE=postgresql
DB_NAME=sdi
DB_USER=postgres
DB_PASSWORD=cambiar_password
DB_HOST=127.0.0.1
DB_PORT=5432
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_COMPRAS_QUEUE=compras.stock
```

Si tu PostgreSQL usa otro usuario, password, puerto o nombre de base, cambia los valores `DB_*` en `.env`.

## Consumer de compras

```powershell
python -m app.consumers.compras_consumer
```

El consumer requiere RabbitMQ local. Si no querés instalar RabbitMQ todavía, podés probar compras con el endpoint simulador:

```http
POST /compras/eventos
```

## Pruebas

```powershell
pytest
```

Para ejecutar las pruebas de integración contra PostgreSQL local:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:cambiar_password@127.0.0.1:5432/sdi_test"
pytest
```

Crear previamente la base de pruebas si querés ejecutar integración separada:

```sql
CREATE DATABASE sdi_test OWNER postgres;
```

## Docker opcional

El archivo `docker-compose.yml` queda disponible solo como alternativa para quien prefiera levantar PostgreSQL y RabbitMQ en contenedores.

## Formato de errores

Todas las respuestas de error usan el mismo formato:

```json
{
  "estado": "ERROR",
  "codigo": "STOCK_INSUFICIENTE",
  "mensaje": "Stock insuficiente para el producto 1: solicitado 2.00, disponible 1.00."
}
```

Códigos principales:

- `VALIDACION_ERROR`: el request no cumple el schema.
- `PRODUCTO_NO_EXISTE`: el producto solicitado no existe.
- `PRODUCTO_INACTIVO`: el producto existe pero no puede operar.
- `PRODUCTO_CODIGO_DUPLICADO`: ya existe un producto con el mismo código.
- `STOCK_NO_INICIALIZADO`: el producto existe, pero falta su fila en `stock_actual`.
- `STOCK_INSUFICIENTE`: no hay disponible suficiente para reservar.
- `RESERVA_NO_EXISTE`: la reserva solicitada no existe.
- `RESERVA_NO_PENDIENTE`: la reserva ya fue confirmada o liberada.
- `RESERVA_NO_COINCIDE`: la venta no coincide con una reserva pendiente por documento, producto y cantidad.
