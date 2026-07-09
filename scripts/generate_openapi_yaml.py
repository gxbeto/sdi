from pathlib import Path
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


class _NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}

# Política numérica contractual publicada como extensión global x-numeric-policy.
# Las cantidades, precios e impuestos se exponen como number/decimal (no string, no integer).
NUMERIC_POLICY = {
    "description": "Política contractual para cantidades, precios e impuestos.",
    "rules": {
        "quantities": {
            "type": "number",
            "precision": "Hasta 3 decimales.",
            "inputRule": "Las cantidades operativas de entrada deben ser mayores que cero.",
            "outputRule": "Los saldos y cantidades calculadas deben ser mayores o iguales que cero.",
        },
        "prices": {
            "type": "number",
            "precision": "Hasta 2 decimales.",
            "rule": "Los precios deben ser mayores o iguales que cero.",
        },
        "tax": {
            "type": "number",
            "precision": "Hasta 2 decimales.",
            "rule": "El impuesto debe estar entre 0 y 100.",
        },
    },
}


OPERATION_ID_BY_METHOD_AND_PATH = {
    ("get", "/health"): "verificarDisponibilidad",
    ("post", "/productos"): "crearProducto",
    ("get", "/productos"): "listarProductos",
    ("get", "/productos/{producto_id}"): "obtenerProducto",
    ("get", "/stock/{producto_id}"): "obtenerStock",
    ("get", "/stock/movimientos"): "listarMovimientosStock",
    ("post", "/stock/reservas"): "crearReserva",
    ("post", "/stock/reservas/{reserva_id}/confirmar"): "confirmarReserva",
    ("post", "/stock/reservas/{reserva_id}/liberar"): "liberarReserva",
    ("post", "/compras/eventos"): "procesarEventoCompra",
    ("post", "/ventas/confirmar"): "confirmarVenta",
}

INTERNAL_OPERATIONS = {
    ("post", "/stock/reservas/{reserva_id}/confirmar"),
    ("post", "/stock/reservas/{reserva_id}/liberar"),
}

INTERNAL_OPERATION_NOTICE = (
    "Operación de uso interno. Solo debe ser invocada por módulos internos "
    "del ecosistema SDI, principalmente Ventas o procesos administrativos "
    "autorizados. No forma parte del contrato público para integradores externos."
)

# Identificadores que deben ser positivos en el contrato.
POSITIVE_INTEGER_FIELDS = {
    "producto_id",
    "reserva_id",
    "movimiento_id",
    "precio_compra_id",
    "precio_venta_id",
    "evento_id",
}

def _set_component_property_enum(
    schema: dict[str, Any],
    component_name: str,
    property_name: str,
    enum_values: list[str],
    description: str | None = None,
    default: str | None = None,
) -> None:
    """Agrega enum a una propiedad ya generada dentro de components.schemas."""
    components = schema.get("components", {}).get("schemas", {})
    component = components.get(component_name)

    if not isinstance(component, dict):
        return

    properties = component.get("properties", {})
    prop = properties.get(property_name)

    if not isinstance(prop, dict):
        return

    prop.clear()
    prop["type"] = "string"
    prop["enum"] = enum_values
    prop["title"] = property_name.replace("_", " ").title()

    if description:
        prop["description"] = description

    if default is not None:
        prop["default"] = default


def _set_query_parameter_enum(
    schema: dict[str, Any],
    parameter_name: str,
    enum_values: list[str],
    description: str | None = None,
) -> None:
    """Agrega enum a parámetros query generados como string libre."""
    paths = schema.get("paths", {})

    if not isinstance(paths, dict):
        return

    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            for parameter in operation.get("parameters", []):
                if not isinstance(parameter, dict):
                    continue

                if parameter.get("name") != parameter_name:
                    continue

                parameter_schema = parameter.setdefault("schema", {})
                parameter_schema.clear()
                parameter_schema["type"] = "string"
                parameter_schema["enum"] = enum_values
                parameter_schema["title"] = parameter_name.replace("_", " ").title()

                if description:
                    parameter["description"] = description


def _normalize_product_list_query_parameters(schema: dict[str, Any]) -> None:
    """Genera parámetros opcionales compatibles con Swagger Editor."""
    operation = schema.get("paths", {}).get("/productos", {}).get("get")
    if not isinstance(operation, dict):
        return

    definitions = {
        "filtro": {
            "schema": {
                "type": "string",
                "minLength": 1,
                "maxLength": 50,
            },
            "description": (
                "Código exacto del producto. Escriba cualquier código, por ejemplo INF-006."
            ),
        },
        "activo": {
            "schema": {
                "type": "boolean",
            },
            "description": (
                "Estado del producto. Use true para activos y false para inactivos."
            ),
        },
    }

    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue

        definition = definitions.get(parameter.get("name"))
        if not definition:
            continue

        parameter["required"] = False
        parameter["schema"] = definition["schema"]
        parameter["description"] = definition["description"]
        parameter.pop("example", None)
        parameter.pop("examples", None)


def _enrich_contract_enums(schema: dict[str, Any]) -> None:
    """
    Fortalece el contrato OpenAPI sin tocar la estructura de BD ni servicios.

    Convierte strings libres en enums documentales para que los consumidores
    conozcan los valores válidos esperados por el contrato.
    """
    codigo_error_values = [
        "VALIDACION_ERROR",
        "PRODUCTO_NO_EXISTE",
        "PRODUCTO_INACTIVO",
        "PRODUCTO_CODIGO_DUPLICADO",
        "STOCK_NO_INICIALIZADO",
        "STOCK_INSUFICIENTE",
        "RESERVA_NO_EXISTE",
        "RESERVA_NO_PENDIENTE",
        "RESERVA_NO_COINCIDE",
        "NO_AUTENTICADO",
        "ACCESO_DENEGADO",
        "ERROR_INTERNO",
        "ERROR_NO_CONTROLADO",
        "MENSAJE_DUPLICADO",
        "REPLAY_NO_COINCIDE",
        "OPERACION_YA_PROCESADA",
        "OPERACION_EN_PROCESO",
        "CONFLICTO_CONCURRENCIA",
        "DOCUMENTO_YA_PROCESADO",
        "DOCUMENTO_YA_TIENE_RESERVA",
        "RESERVA_YA_CONFIRMADA",
        "RESERVA_YA_LIBERADA",
    ]

    unidad_medida_values = [
        "UNIDAD",
        "CAJA",
        "KG",
        "LITRO",
        "METRO",
    ]

    tipo_movimiento_values = [
        "COMPRA",
        "RESERVA",
        "VENTA",
        "LIBERACION_RESERVA",
        "AJUSTE",
    ]

    origen_movimiento_values = [
        "COMPRAS",
        "VENTAS",
        "STOCK",
        "SISTEMA",
    ]

    estado_procesamiento_values = [
        "PENDIENTE",
        "PROCESADO",
        "ERROR",
    ]

    _set_component_property_enum(
        schema,
        "ErrorResponse",
        "estado",
        ["ERROR"],
        "Estado fijo para respuestas de error.",
        "ERROR",
    )
    _set_component_property_enum(
        schema,
        "ErrorResponse",
        "codigo",
        codigo_error_values,
        "Código técnico de error devuelto por la API.",
    )

    _set_component_property_enum(
        schema,
        "ProductoCreate",
        "unidad_medida",
        unidad_medida_values,
        "Unidad de medida utilizada para registrar y mover stock.",
        "UNIDAD",
    )
    _set_component_property_enum(
        schema,
        "ProductoOut",
        "unidad_medida",
        unidad_medida_values,
        "Unidad de medida utilizada para registrar y mover stock.",
    )
    _set_component_property_enum(
        schema,
        "ProductoCreated",
        "estado",
        ["CREADO"],
        "Estado devuelto cuando el producto fue creado.",
        "CREADO",
    )

    _set_component_property_enum(
        schema,
        "ReservaCreateOut",
        "estado",
        ["RESERVADO"],
        "Estado devuelto cuando la reserva fue creada.",
        "RESERVADO",
    )
    _set_component_property_enum(
        schema,
        "ConfirmarReservaOut",
        "estado",
        ["CONFIRMADA"],
        "Estado devuelto cuando la reserva fue confirmada.",
        "CONFIRMADA",
    )
    _set_component_property_enum(
        schema,
        "LiberarReservaOut",
        "estado",
        ["LIBERADA"],
        "Estado devuelto cuando la reserva fue liberada.",
        "LIBERADA",
    )

    _set_component_property_enum(
        schema,
        "MovimientoOut",
        "tipo_movimiento",
        tipo_movimiento_values,
        "Tipo de operación que generó el movimiento de stock.",
    )
    _set_component_property_enum(
        schema,
        "MovimientoOut",
        "origen",
        origen_movimiento_values,
        "Módulo o sistema que originó el movimiento.",
    )
    _set_query_parameter_enum(
        schema,
        "tipo_movimiento",
        tipo_movimiento_values,
        "Tipo de movimiento de stock usado como filtro de consulta.",
    )

    _set_component_property_enum(
        schema,
        "CompraEventoOut",
        "estado_procesamiento",
        estado_procesamiento_values,
        "Estado del procesamiento del evento recibido desde Compras.",
    )

    _set_component_property_enum(
        schema,
        "VentaConfirmarOut",
        "estado",
        ["CONFIRMADA"],
        "Estado devuelto cuando la venta fue confirmada.",
        "CONFIRMADA",
    )


def _remove_currency_references(node: object) -> None:
    """
    Elimina del contrato toda referencia a moneda.

    Se usa porque, en la definición actual del sistema, el contrato de
    servicios no debe exponer ni pedir moneda.
    """
    if isinstance(node, dict):
        # Elimina parámetros de operación con name=moneda/currency.
        if isinstance(node.get("parameters"), list):
            node["parameters"] = [
                parameter
                for parameter in node["parameters"]
                if not (
                    isinstance(parameter, dict)
                    and str(parameter.get("name", "")).lower() in {"moneda", "currency"}
                )
            ]

        # Elimina propiedades schema y claves de ejemplos llamadas moneda/currency.
        for key in list(node.keys()):
            normalized_key = str(key).lower()

            if normalized_key in {"moneda", "currency"}:
                del node[key]
                continue

            if key == "required" and isinstance(node[key], list):
                node[key] = [
                    item for item in node[key] if item not in {"moneda", "currency"}
                ]
                continue

            _remove_currency_references(node[key])

        components = node.get("components")
        if isinstance(components, dict):
            schemas = components.get("schemas")
            if isinstance(schemas, dict):
                schemas.pop("Moneda", None)
                schemas.pop("Currency", None)

    elif isinstance(node, list):
        for item in node:
            _remove_currency_references(item)


def _set_stable_operation_ids(schema: dict[str, Any]) -> None:
    """
    Reemplaza operationId generados internamente por nombres estables y humanos.

    Esto mejora el contrato para SDKs y clientes generados automáticamente,
    evitando nombres largos dependientes del framework como
    confirmar_reserva_stock_reservas__reserva_id__confirmar_post.
    """
    paths = schema.get("paths", {})

    if not isinstance(paths, dict):
        return

    used_operation_ids: set[str] = set()

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            operation_id = OPERATION_ID_BY_METHOD_AND_PATH.get((method_name, path))

            if not operation_id:
                continue

            if operation_id in used_operation_ids:
                raise ValueError(f"operationId duplicado en contrato OpenAPI: {operation_id}")

            operation["operationId"] = operation_id
            used_operation_ids.add(operation_id)



def _mark_internal_operations(schema: dict[str, Any]) -> None:
    """
    Marca las operaciones internas con x-internal sin eliminarlas del contrato.

    Estas operaciones siguen documentadas (no se remueven), pero se señalan como
    de uso interno para que los integradores externos sepan que no forman parte
    del contrato público.
    """
    paths = schema.get("paths", {})

    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            if (method_name, path) in INTERNAL_OPERATIONS:
                operation["x-internal"] = True
                current = (operation.get("description") or "").strip()
                if INTERNAL_OPERATION_NOTICE not in current:
                    operation["description"] = (
                        f"{current}\n\n{INTERNAL_OPERATION_NOTICE}" if current else INTERNAL_OPERATION_NOTICE
                    )



def _append_description(node: dict[str, Any], text: str) -> None:
    current = (node.get("description") or "").strip()
    if not current:
        node["description"] = text
    elif text not in current:
        node["description"] = f"{current} {text}"


def _apply_positive_integer_schema(node: dict[str, Any]) -> None:
    """Aplica mínimo positivo a identificadores enteros."""
    if isinstance(node.get("anyOf"), list):
        for item in node["anyOf"]:
            if isinstance(item, dict) and item.get("type") == "integer":
                item["minimum"] = 1
        _append_description(node, "Debe ser un identificador entero positivo.")
        return

    if node.get("type") == "integer" or "type" not in node:
        node["type"] = "integer"
        node["minimum"] = 1
        _append_description(node, "Debe ser un identificador entero positivo.")


def _enrich_validation_constraints(schema: dict[str, Any]) -> None:
    """
    Completa restricciones de contrato que FastAPI no genera de forma suficiente.

    Reglas agregadas:
    - producto_id, reserva_id y demás identificadores técnicos: mínimo 1.

    documento_ref y comprobante ya definen su patrón/descripción desde los schemas
    Pydantic (DocumentoRefIn/Out y ComprobanteOut), por lo que no se reescriben aquí.
    Las cantidades y precios se publican como number/decimal desde los schemas.
    """
    components = schema.get("components", {}).get("schemas", {})
    if isinstance(components, dict):
        for component in components.values():
            if not isinstance(component, dict):
                continue

            properties = component.get("properties", {})
            if not isinstance(properties, dict):
                continue

            for property_name, property_schema in properties.items():
                if not isinstance(property_schema, dict):
                    continue

                if property_name in POSITIVE_INTEGER_FIELDS:
                    _apply_positive_integer_schema(property_schema)

    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            for parameter in operation.get("parameters", []):
                if not isinstance(parameter, dict):
                    continue

                parameter_name = parameter.get("name")
                parameter_schema = parameter.setdefault("schema", {})
                if not isinstance(parameter_schema, dict):
                    continue

                if parameter_name in POSITIVE_INTEGER_FIELDS:
                    _apply_positive_integer_schema(parameter_schema)



ERROR_RESPONSE_COMPONENTS = {
    "ValidationErrorResponse": {
        "description": "El request no cumple el contrato OpenAPI o las validaciones declaradas.",
        "codigo": "VALIDACION_ERROR",
        "mensaje": "campo: descripción clara de la validación incumplida.",
    },
    "UnauthorizedErrorResponse": {
        "description": "No autenticado. Falta credencial válida o el mecanismo de autenticación rechazó la solicitud.",
        "codigo": "NO_AUTENTICADO",
        "mensaje": "No se pudo autenticar la solicitud.",
    },
    "ForbiddenErrorResponse": {
        "description": "Acceso denegado. El consumidor no tiene permiso para ejecutar la operación solicitada.",
        "codigo": "ACCESO_DENEGADO",
        "mensaje": "No tiene permisos para ejecutar esta operación.",
    },
    "InternalServerErrorResponse": {
        "description": "Error interno controlado del servicio.",
        "codigo": "ERROR_INTERNO",
        "mensaje": "Ocurrió un error interno al procesar la operación.",
    },
    "DefaultErrorResponse": {
        "description": "Error no controlado o no clasificado por el contrato.",
        "codigo": "ERROR_NO_CONTROLADO",
        "mensaje": "Ocurrió un error no clasificado por el contrato.",
    },
}


def _build_error_response_component(description: str, codigo: str, mensaje: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                "example": {
                    "estado": "ERROR",
                    "codigo": codigo,
                    "mensaje": mensaje,
                },
            }
        },
    }


def _ensure_error_response_components(schema: dict[str, Any]) -> None:
    """Centraliza las respuestas de error reutilizables del contrato."""
    components = schema.setdefault("components", {})
    responses = components.setdefault("responses", {})

    for name, data in ERROR_RESPONSE_COMPONENTS.items():
        responses[name] = _build_error_response_component(
            data["description"],
            data["codigo"],
            data["mensaje"],
        )


def _normalize_operation_error_responses(schema: dict[str, Any]) -> None:
    """
    Normaliza la política de errores de todas las operaciones.

    - Reemplaza los 422 repetidos por una respuesta reutilizable.
    - Agrega 401 y 403 a operaciones no públicas.
    - Agrega 500 y default a todas las operaciones.
    - Mantiene 400/404/409 específicos ya generados por cada endpoint.
    """
    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            responses = operation.setdefault("responses", {})
            if not isinstance(responses, dict):
                continue

            responses["422"] = {"$ref": "#/components/responses/ValidationErrorResponse"}
            responses.setdefault("500", {"$ref": "#/components/responses/InternalServerErrorResponse"})
            responses.setdefault("default", {"$ref": "#/components/responses/DefaultErrorResponse"})

            # Health queda público. El resto de operaciones queda preparado para
            # el modelo de seguridad que se defina, sin depender de legados.
            if path != "/health":
                responses.setdefault("401", {"$ref": "#/components/responses/UnauthorizedErrorResponse"})
                responses.setdefault("403", {"$ref": "#/components/responses/ForbiddenErrorResponse"})


def _attach_error_policy(schema: dict[str, Any]) -> None:
    """Agrega una política de errores clara como extensión del contrato."""
    schema["x-error-policy"] = {
        "format": "Todas las respuestas de error usan el schema ErrorResponse.",
        "schema": {
            "estado": "ERROR",
            "codigo": "Código técnico estable definido por el contrato.",
            "mensaje": "Mensaje legible para diagnóstico funcional o técnico.",
        },
        "httpStatus": {
            "400": "Error funcional o regla de negocio inválida.",
            "401": "Solicitud no autenticada o credencial inválida.",
            "403": "Consumidor autenticado sin permiso para ejecutar la operación.",
            "404": "Recurso solicitado inexistente.",
            "409": "Conflicto de estado o concurrencia funcional.",
            "422": "Error de validación del contrato OpenAPI.",
            "500": "Error interno controlado del servicio.",
            "default": "Error no clasificado por el contrato.",
        },
    }


def _enrich_error_policy(schema: dict[str, Any]) -> None:
    """Aplica la política de errores normalizada al contrato OpenAPI."""
    _ensure_error_response_components(schema)
    _normalize_operation_error_responses(schema)
    _attach_error_policy(schema)



IDEMPOTENCY_RULES_BY_METHOD_AND_PATH = {
    ("post", "/compras/eventos"): {
        "keyField": "mensaje_id",
        "scope": "Evento de compra recibido desde Compras o reenviado desde RabbitMQ.",
        "replayBehavior": "Si llega el mismo mensaje_id con el mismo contenido, no se vuelve a incrementar stock; se devuelve el resultado ya procesado.",
        "payloadConflictBehavior": "Si llega el mismo mensaje_id con contenido diferente, se rechaza con 409 y código REPLAY_NO_COINCIDE.",
    },
    ("post", "/stock/reservas"): {
        "keyField": "documento_ref",
        "scope": "Documento externo de venta o pedido que solicita la reserva.",
        "replayBehavior": "Si llega el mismo documento_ref con los mismos ítems, no se duplica la reserva; se devuelve el estado ya registrado.",
        "payloadConflictBehavior": "Si llega el mismo documento_ref con ítems diferentes, se rechaza con 409 y código REPLAY_NO_COINCIDE.",
    },
    ("post", "/stock/reservas/{reserva_id}/confirmar"): {
        "keyField": "reserva_id",
        "scope": "Confirmación interna de una reserva específica.",
        "replayBehavior": "Si la reserva ya está CONFIRMADA, la repetición de la confirmación se trata como idempotente y devuelve el estado confirmado sin descontar stock nuevamente.",
        "payloadConflictBehavior": "Si la reserva está LIBERADA o no corresponde a la operación, se rechaza con 409.",
    },
    ("post", "/stock/reservas/{reserva_id}/liberar"): {
        "keyField": "reserva_id",
        "scope": "Liberación interna de una reserva específica.",
        "replayBehavior": "Si la reserva ya está LIBERADA, la repetición de la liberación se trata como idempotente y devuelve el estado liberado sin alterar stock nuevamente.",
        "payloadConflictBehavior": "Si la reserva está CONFIRMADA, se rechaza con 409.",
    },
    ("post", "/ventas/confirmar"): {
        "keyField": "documento_ref",
        "scope": "Documento externo de venta confirmado por el módulo de Ventas.",
        "replayBehavior": "Si llega el mismo documento_ref con los mismos ítems, no se duplica el descuento; se devuelve el resultado ya confirmado.",
        "payloadConflictBehavior": "Si llega el mismo documento_ref con contenido diferente, se rechaza con 409 y código REPLAY_NO_COINCIDE.",
    },
}

CONCURRENCY_OPERATIONS = {
    ("post", "/stock/reservas"),
    ("post", "/stock/reservas/{reserva_id}/confirmar"),
    ("post", "/stock/reservas/{reserva_id}/liberar"),
    ("post", "/ventas/confirmar"),
    ("post", "/compras/eventos"),
}

CONFLICT_CASES_BY_METHOD_AND_PATH = {
    ("post", "/compras/eventos"): {
        "mensajeDuplicado": {
            "summary": "Mensaje ya procesado",
            "value": {
                "estado": "ERROR",
                "codigo": "MENSAJE_DUPLICADO",
                "mensaje": "El mensaje CMP-2026-0001 ya fue procesado previamente.",
            },
        },
        "replayNoCoincide": {
            "summary": "Replay con contenido diferente",
            "value": {
                "estado": "ERROR",
                "codigo": "REPLAY_NO_COINCIDE",
                "mensaje": "El mensaje_id ya existe, pero el contenido recibido no coincide con el procesamiento original.",
            },
        },
        "operacionEnProceso": {
            "summary": "Operación en proceso",
            "value": {
                "estado": "ERROR",
                "codigo": "OPERACION_EN_PROCESO",
                "mensaje": "El evento de compra está siendo procesado. Reintente la consulta o el envío más tarde.",
            },
        },
    },
    ("post", "/stock/reservas"): {
        "stockInsuficiente": {
            "summary": "Stock insuficiente",
            "value": {
                "estado": "ERROR",
                "codigo": "STOCK_INSUFICIENTE",
                "mensaje": "Stock insuficiente para el producto 1: solicitado 2, disponible 1.",
            },
        },
        "documentoYaTieneReserva": {
            "summary": "Documento ya reservado",
            "value": {
                "estado": "ERROR",
                "codigo": "DOCUMENTO_YA_TIENE_RESERVA",
                "mensaje": "El documento FV-001-000123 ya posee una reserva registrada.",
            },
        },
        "replayNoCoincide": {
            "summary": "Replay con contenido diferente",
            "value": {
                "estado": "ERROR",
                "codigo": "REPLAY_NO_COINCIDE",
                "mensaje": "El documento_ref ya existe, pero los ítems recibidos no coinciden con la reserva original.",
            },
        },
        "conflictoConcurrencia": {
            "summary": "Conflicto de concurrencia",
            "value": {
                "estado": "ERROR",
                "codigo": "CONFLICTO_CONCURRENCIA",
                "mensaje": "La reserva no pudo completarse porque el stock fue modificado por otra operación concurrente.",
            },
        },
    },
    ("post", "/stock/reservas/{reserva_id}/confirmar"): {
        "operacionYaProcesada": {
            "summary": "Confirmación repetida",
            "value": {
                "estado": "ERROR",
                "codigo": "OPERACION_YA_PROCESADA",
                "mensaje": "La reserva 101 ya fue confirmada previamente.",
            },
        },
        "reservaYaLiberada": {
            "summary": "Reserva liberada previamente",
            "value": {
                "estado": "ERROR",
                "codigo": "RESERVA_YA_LIBERADA",
                "mensaje": "La reserva 101 ya fue liberada y no puede confirmarse.",
            },
        },
        "conflictoConcurrencia": {
            "summary": "Conflicto de concurrencia",
            "value": {
                "estado": "ERROR",
                "codigo": "CONFLICTO_CONCURRENCIA",
                "mensaje": "La reserva fue modificada por otra operación concurrente.",
            },
        },
    },
    ("post", "/stock/reservas/{reserva_id}/liberar"): {
        "operacionYaProcesada": {
            "summary": "Liberación repetida",
            "value": {
                "estado": "ERROR",
                "codigo": "OPERACION_YA_PROCESADA",
                "mensaje": "La reserva 101 ya fue liberada previamente.",
            },
        },
        "reservaYaConfirmada": {
            "summary": "Reserva confirmada previamente",
            "value": {
                "estado": "ERROR",
                "codigo": "RESERVA_YA_CONFIRMADA",
                "mensaje": "La reserva 101 ya fue confirmada y no puede liberarse.",
            },
        },
        "conflictoConcurrencia": {
            "summary": "Conflicto de concurrencia",
            "value": {
                "estado": "ERROR",
                "codigo": "CONFLICTO_CONCURRENCIA",
                "mensaje": "La reserva fue modificada por otra operación concurrente.",
            },
        },
    },
    ("post", "/ventas/confirmar"): {
        "documentoYaProcesado": {
            "summary": "Venta ya confirmada",
            "value": {
                "estado": "ERROR",
                "codigo": "DOCUMENTO_YA_PROCESADO",
                "mensaje": "El documento FV-001-000123 ya fue confirmado previamente.",
            },
        },
        "replayNoCoincide": {
            "summary": "Replay con contenido diferente",
            "value": {
                "estado": "ERROR",
                "codigo": "REPLAY_NO_COINCIDE",
                "mensaje": "El documento_ref ya existe, pero los ítems recibidos no coinciden con la confirmación original.",
            },
        },
        "reservaNoCoincide": {
            "summary": "No coincide con reserva pendiente",
            "value": {
                "estado": "ERROR",
                "codigo": "RESERVA_NO_COINCIDE",
                "mensaje": "No existe una reserva pendiente para el documento FV-001-000123, producto 1 y cantidad 2.",
            },
        },
        "conflictoConcurrencia": {
            "summary": "Conflicto de concurrencia",
            "value": {
                "estado": "ERROR",
                "codigo": "CONFLICTO_CONCURRENCIA",
                "mensaje": "La venta no pudo confirmarse porque alguna reserva fue modificada por otra operación concurrente.",
            },
        },
    },
}


def _merge_conflict_response(operation: dict[str, Any], cases: dict[str, Any]) -> None:
    """Agrega ejemplos formales de conflictos 409 sin perder el schema único de errores."""
    responses = operation.setdefault("responses", {})
    conflict_response = responses.setdefault("409", {})
    conflict_response["description"] = (
        "Conflicto funcional, replay no coincidente, operación ya procesada "
        "o conflicto de concurrencia."
    )
    conflict_response["content"] = {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
            "examples": cases,
        }
    }


def _enrich_idempotency_and_concurrency_policy(schema: dict[str, Any]) -> None:
    """
    Formaliza idempotencia, replay, procesamiento previo y concurrencia en el contrato.

    No implementa locks ni persistencia; solo expresa la regla contractual aprobada
    para que los consumidores sepan cómo reintentar y qué errores esperar.
    """
    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method_name, operation in path_item.items():
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            operation_key = (method_name, path)

            idempotency_rule = IDEMPOTENCY_RULES_BY_METHOD_AND_PATH.get(operation_key)
            if idempotency_rule:
                operation["x-idempotency"] = {
                    "enabled": True,
                    **idempotency_rule,
                    "sameRequestPolicy": "No debe duplicar movimientos, reservas ni descuentos ante reintentos equivalentes.",
                    "differentPayloadPolicy": "Debe responder 409 si la clave idempotente ya existe con contenido diferente.",
                }

                current_description = (operation.get("description") or "").strip()
                notice = (
                    "La operación debe tratar reintentos equivalentes de forma idempotente. "
                    f"Clave idempotente: {idempotency_rule['keyField']}."
                )
                if notice not in current_description:
                    operation["description"] = (
                        f"{current_description}\n\n{notice}" if current_description else notice
                    )

            if operation_key in CONCURRENCY_OPERATIONS:
                operation["x-concurrency"] = {
                    "strategy": "pessimistic-locking",
                    "conflictStatus": 409,
                    "conflictCode": "CONFLICTO_CONCURRENCIA",
                    "description": (
                        "Las operaciones que afectan stock deben ejecutarse en transacción "
                        "y proteger el saldo/reserva contra modificaciones concurrentes."
                    ),
                }

            conflict_cases = CONFLICT_CASES_BY_METHOD_AND_PATH.get(operation_key)
            if conflict_cases:
                _merge_conflict_response(operation, conflict_cases)

    schema["x-idempotency-policy"] = {
        "description": "Política contractual para reintentos, replay y procesamiento previo.",
        "rules": {
            "sameIdempotencyKeySamePayload": "Debe devolver el resultado ya conocido sin duplicar efectos.",
            "sameIdempotencyKeyDifferentPayload": "Debe responder 409 con código REPLAY_NO_COINCIDE.",
            "alreadyProcessed": "Debe quedar expresado como operación ya procesada o respuesta idempotente documentada.",
            "duplicateEffects": "No se deben duplicar reservas, movimientos, compras ni descuentos de stock.",
        },
    }

    schema["x-concurrency-policy"] = {
        "description": "Política contractual para conflictos de concurrencia en operaciones de stock.",
        "httpStatus": 409,
        "errorCode": "CONFLICTO_CONCURRENCIA",
        "rules": {
            "stockMutation": "Toda operación que modifique stock o reservas debe proteger el saldo contra concurrencia.",
            "reservationMutation": "Las confirmaciones y liberaciones repetidas o concurrentes deben tener resultado determinístico.",
            "retry": "El consumidor puede reintentar operaciones idempotentes usando la misma clave y el mismo contenido.",
        },
    }

def _attach_numeric_policy(schema: dict[str, Any]) -> None:
    """Publica la política numérica contractual como extensión global."""
    schema["x-numeric-policy"] = NUMERIC_POLICY


def _normalize_include_parameter(schema: dict[str, Any]) -> None:
    """
    Documenta el parámetro `include` de la consulta flexible como lista de valores
    permitidos separados por coma (style: form, explode: false), sin enumerar todas
    las combinaciones posibles.
    """
    operation = schema.get("paths", {}).get("/productos/{producto_id}", {}).get("get")
    if not isinstance(operation, dict):
        return

    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict) or parameter.get("name") != "include":
            continue
        parameter["style"] = "form"
        parameter["explode"] = False
        parameter["required"] = False
        parameter_schema = parameter.setdefault("schema", {})
        parameter_schema["type"] = "string"
        parameter_schema["default"] = "producto"
        parameter["description"] = (
            "Bloques a incluir en la respuesta agrupada, separados por coma. "
            "Valores permitidos: producto, stock, precios, movimientos. "
            "Opcional; si se omite se asume 'producto'. El orden no afecta el "
            "resultado y los duplicados se ignoran. Ej.: include=producto,stock,precios."
        )


def main() -> None:
    output_path = PROJECT_ROOT / "openapi.yaml"
    schema = app.openapi()
    schema["openapi"] = "3.2.0"

    _enrich_contract_enums(schema)
    _normalize_product_list_query_parameters(schema)
    _normalize_include_parameter(schema)
    _remove_currency_references(schema)
    _set_stable_operation_ids(schema)
    _mark_internal_operations(schema)
    _enrich_validation_constraints(schema)
    _enrich_error_policy(schema)
    _enrich_idempotency_and_concurrency_policy(schema)
    _attach_numeric_policy(schema)

    output_path.write_text(
        yaml.dump(
            schema,
            Dumper=_NoAliasSafeDumper,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    print(f"OpenAPI YAML generado en {output_path}")


if __name__ == "__main__":
    main()
