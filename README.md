# SDI — Sistema Distribuido de Inventario

API REST del módulo **Stock** para integración entre módulos de un ERP (Ventas, Compras y servicios administrativos), construida con **FastAPI**, **PostgreSQL**, **SQLAlchemy** y **Alembic**, con procesamiento de eventos de compra vía **RabbitMQ**.

## Características

- **Catálogo de productos** con categorías, unidad de medida e impuesto, y stock inicializado automáticamente.
- **Reservas de stock** con ciclo de vida completo: pendiente → confirmada (venta) o liberada.
- **Comprobantes internos verificables**: cada operación genera un comprobante `STK-001-nnnnnn-d` con dígito verificador, además de la trazabilidad del documento externo (`FV-...`, `OC-...`).
- **Compras idempotentes**: los eventos de compra se procesan una sola vez (clave `mensaje_id`); los reintentos no duplican stock.
- **Consulta flexible**: `GET /productos/{id}?include=producto,stock,precios,movimientos` devuelve solo los bloques solicitados.
- **Contrato OpenAPI 3.2 documentado** con políticas de errores, idempotencia y concurrencia ([openapi.yaml](openapi.yaml)).

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/productos` | Crear producto (inicializa stock en cero) |
| `GET` | `/productos` | Listar productos con filtros |
| `GET` | `/productos/{id}` | Consulta flexible (producto, stock, precios, movimientos) |
| `GET` | `/stock/{id}` | Stock actual de un producto |
| `GET` | `/stock/movimientos` | Historial de movimientos |
| `POST` | `/stock/reservas` | Reservar stock para un documento de venta |
| `POST` | `/stock/reservas/{id}/confirmar` | Confirmar reserva (interno) |
| `POST` | `/stock/reservas/{id}/liberar` | Liberar reserva (interno) |
| `POST` | `/ventas/confirmar` | Confirmar venta completa de un documento |
| `POST` | `/compras/eventos` | Procesar evento de compra (idempotente) |

## Ejecución local

Requisitos: Python 3.12+, PostgreSQL en ejecución (RabbitMQ solo para el consumer real de compras).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env              # editar con los datos de tu PostgreSQL local
alembic upgrade head                # crea las tablas
uvicorn app.main:app --reload
```

Swagger queda disponible en `http://127.0.0.1:8000/docs`.

> **Configuración**: toda la configuración sale del archivo `.env` (ver plantilla en [.env.example](.env.example)). No hay valores por defecto: si falta una clave, la aplicación no arranca. El `.env` nunca se versiona.

## Datos de ejemplo y simulación

Con el servidor levantado:

```powershell
python scripts/seed_catalogo.py     # carga el catálogo oficial (25 productos, 4 categorías)
python scripts/simulacion.py        # simulación completa: reset + compras y ventas aleatorias
```

La simulación compra los 25 productos con cantidades aleatorias (los más caros son más escasos), agrupa compras y ventas en documentos de 1 a 3 artículos, aplica un margen del 30 % más 10 % de impuesto al precio de venta, y verifica la consistencia final del stock. Use `--seed N` para corridas reproducibles.

## Pruebas

```powershell
pytest                              # unitarias (sin base de datos)

# integración + simulación contra una base de pruebas local:
$env:TEST_DATABASE_URL="postgresql+psycopg://USUARIO:PASSWORD@127.0.0.1:5432/sdi_test"
pytest
```

La base `sdi_test` debe existir (basta `CREATE DATABASE sdi_test;`). Las tablas se recrean al inicio de cada test y la corrida deja los datos del último test disponibles para inspección.

## Despliegue y mantenimiento en producción

Instalación inicial en el servidor:

```bash
git clone https://github.com/gxbeto/sdi.git && cd sdi
python -m venv .venv && source .venv/bin/activate
cp .env.example .env                # editar con la base de producción
pip install -r requirements.txt
python scripts/mantenimiento.py     # primera vez: crea todas las tablas
```

Cada actualización posterior es un solo comando:

```bash
python scripts/mantenimiento.py --reiniciar "systemctl restart sdi"
```

El programa baja los cambios de git, actualiza dependencias, aplica las migraciones pendientes de Alembic y reinicia el servicio. Ante cualquier error se detiene sin ejecutar los pasos siguientes.

## Integración por cola (RabbitMQ)

Además del endpoint REST, el módulo de Compras puede publicar eventos en la cola **`compras.stock`** (AMQP, durable, mensajes JSON persistentes con el mismo schema `CompraEventoIn`). El consumer de Stock aplica la misma lógica e idempotencia que `POST /compras/eventos`: un `mensaje_id` repetido se marca `DUPLICADO` y no duplica stock. La guía completa para publicadores (conexión, formato, semántica de reintentos) está en la sección *"Compras por cola (RabbitMQ)"* de la [documentación de servicios](docs/sdi_documentacion_servicios.html), servida en producción en `/documentacion`.

```powershell
python -m app.consumers.compras_consumer      # correr el consumer (requiere RabbitMQ)
python scripts/publicar_compra.py --producto-id 1 --cantidad 5 --precio 32000   # publicar un evento de prueba
```

Sin RabbitMQ, el mismo procesamiento puede probarse con `POST /compras/eventos`.

## Formato de errores

Todas las respuestas de error usan el mismo esquema:

```json
{
  "estado": "ERROR",
  "codigo": "STOCK_INSUFICIENTE",
  "mensaje": "Stock insuficiente para el producto 1: solicitado 2, disponible 1."
}
```

Códigos principales: `VALIDACION_ERROR`, `PRODUCTO_NO_EXISTE`, `PRODUCTO_INACTIVO`, `PRODUCTO_CODIGO_DUPLICADO`, `STOCK_NO_INICIALIZADO`, `STOCK_INSUFICIENTE`, `RESERVA_NO_EXISTE`, `RESERVA_NO_PENDIENTE`, `RESERVA_NO_COINCIDE`. El detalle completo, incluidas las políticas de idempotencia y concurrencia (replay, duplicados, conflictos 409), está en el [contrato OpenAPI](openapi.yaml).

## Documentación

- [Instalación en producción y desinstalación](docs/instalacion_produccion.md)
- [Contrato de servicios (OpenAPI 3.2)](docs/sdi_contrato_servicios_version_2.yaml)
- [Flujos de compras y ventas](docs/vista_previa_flujos_profesionales.html) (diagramas Mermaid en [docs/](docs/))
- Releases del sistema en [docs/](docs/)

---

Proyecto de la cátedra *Programación de Aplicaciones en Red*.
