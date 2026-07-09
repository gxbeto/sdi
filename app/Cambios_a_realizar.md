Necesito corregir correctamente el proyecto SDI Stock, especialmente el generador OpenAPI, 
la consulta flexible de productos y el manejo de comprobantes internos.

Contexto general:
- El archivo openapi.yaml no debe editarse manualmente como fuente principal.
- El contrato OpenAPI debe generarse desde el código y desde scripts/generate_openapi_yaml.py.
- Fue rechazada la propuesta de exponer cantidades y precios como string decimal.
- La decisión aprobada es usar type: number para cantidades, precios e impuestos.
- No usar type: integer para cantidades ni precios, porque el sistema puede manejar cantidades fraccionadas.
- No volver a convertir cantidades ni precios a string.
- Se decidió implementar consulta flexible con include.
- Se decidió usar respuesta agrupada.
- Se decidió diferenciar documento_ref y comprobante:
  - documento_ref: documento externo recibido desde Ventas o Compras.
  - comprobante: comprobante interno generado por Stock.
- El sistema sí va a generar comprobantes internos en los procesos de Stock.

Objetivos principales:
1. Corregir scripts/generate_openapi_yaml.py para dejar de convertir cantidades y precios a string.
2. Mantener cantidades, precios e impuesto como number.
3. Agregar consulta flexible:
   GET /productos/{producto_id}?include=producto,stock,precios
4. Usar respuesta agrupada para la consulta flexible.
5. Incorporar correctamente comprobante como documento interno generado por Stock.
6. Mantener documento_ref como documento externo recibido desde Ventas o Compras.

============================================================
1. CORREGIR MODELO NUMÉRICO DEL CONTRATO
============================================================

Modificar scripts/generate_openapi_yaml.py.

Eliminar o reemplazar toda lógica que convierta decimales a string, incluyendo funciones, comentarios y reglas relacionadas con:

- string decimal
- pattern decimal para cantidades/precios
- _apply_decimal_string_schema
- _stringify_decimal_value
- _stringify_decimal_examples
- DECIMAL_FIELD_RULES orientado a string
- cualquier regla que fuerce type: string para cantidad, precio o impuesto

Nueva política:

Campos de cantidad:
- cantidad
- cantidad_total
- cantidad_reservada
- cantidad_disponible
- cantidad_descontada
- cantidad_liberada
- stock_total_actual
- cantidad_reservada_actual
- cantidad_disponible_actual
- stock_anterior
- stock_posterior

Reglas para cantidades:
- type: number
- format: decimal, si el generador lo permite sin conflicto
- multipleOf: 0.001
- cantidades de entrada: exclusiveMinimum: 0
- cantidades de salida o saldos: minimum: 0

Campos de precio:
- precio_compra
- precio_venta

Reglas para precios:
- type: number
- format: decimal, si corresponde
- minimum: 0
- multipleOf: 0.01

Campo impuesto:
- impuesto
- type: number
- format: decimal, si corresponde
- minimum: 0
- maximum: 100
- multipleOf: 0.01

Los ejemplos numéricos deben quedar como números JSON, no como strings.

Correcto:
{
  "cantidad": 2,
  "cantidad_total": 10,
  "precio_venta": 15000,
  "impuesto": 10.1
}

Incorrecto:
{
  "cantidad": "2.000",
  "precio_venta": "15000.00"
}

No usar integer para cantidades ni precios.

============================================================
2. AGREGAR POLÍTICA NUMÉRICA GLOBAL AL OPENAPI
============================================================

Agregar al OpenAPI generado una extensión global:

x-numeric-policy:
  description: Política contractual para cantidades, precios e impuestos.
  rules:
    quantities:
      type: number
      precision: Hasta 3 decimales.
      inputRule: Las cantidades operativas de entrada deben ser mayores que cero.
      outputRule: Los saldos y cantidades calculadas deben ser mayores o iguales que cero.
    prices:
      type: number
      precision: Hasta 2 decimales.
      rule: Los precios deben ser mayores o iguales que cero.
    tax:
      type: number
      precision: Hasta 2 decimales.
      rule: El impuesto debe estar entre 0 y 100.

============================================================
3. IMPLEMENTAR CONSULTA FLEXIBLE DE PRODUCTOS
============================================================

Modificar GET /productos/{producto_id} para soportar el parámetro query include.

Ejemplo principal aprobado:

GET /productos/1?include=producto,stock,precios

El parámetro include debe permitir combinar estos bloques:

- producto
- stock
- precios
- movimientos

Ejemplos válidos:

GET /productos/1?include=producto
GET /productos/1?include=stock
GET /productos/1?include=precios
GET /productos/1?include=movimientos
GET /productos/1?include=producto,stock
GET /productos/1?include=producto,precios
GET /productos/1?include=stock,precios
GET /productos/1?include=stock,movimientos
GET /productos/1?include=producto,movimientos
GET /productos/1?include=producto,stock,precios
GET /productos/1?include=producto,stock,precios,movimientos

Reglas:
- include es opcional.
- Si no se informa include, debe asumir include=producto.
- No documentar todas las combinaciones como enum separado.
- Documentar include como una lista de valores permitidos separados por coma.
- En OpenAPI usar style: form y explode: false para representar include=producto,stock,precios.
- Si se recibe un valor no permitido, responder 422 usando ErrorResponse con código VALIDACION_ERROR.
- El orden de los bloques en include no debe afectar el resultado.
- Evitar duplicados. Ejemplo: include=producto,producto,stock debe tratarse como producto,stock.

============================================================
4. AGREGAR PARÁMETRO PARA MOVIMIENTOS
============================================================

Cuando include contiene movimientos, permitir el parámetro:

limite_movimientos:
  type: integer
  minimum: 1
  maximum: 50
  default: 10

Reglas:
- Los movimientos deben devolverse ordenados desde el más reciente al más antiguo.
- Orden: fecha_movimiento descendente.
- Cantidad por defecto: 10.
- Cantidad máxima: 50.
- Si include no contiene movimientos, limite_movimientos no debe afectar la respuesta.
- No eliminar GET /stock/movimientos.
- GET /stock/movimientos debe seguir existiendo para consultas específicas de historial.

============================================================
5. USAR RESPUESTA AGRUPADA
============================================================

GET /productos/{producto_id} debe devolver una respuesta agrupada, no plana.

Crear o ajustar el schema:

ProductoConsultaOut:
  type: object
  properties:
    producto:
      nullable: true
      $ref: '#/components/schemas/ProductoOut'
    stock:
      nullable: true
      $ref: '#/components/schemas/StockOut'
    precios:
      nullable: true
      $ref: '#/components/schemas/PrecioResumenOut'
    movimientos:
      type: array
      items:
        $ref: '#/components/schemas/MovimientoOut'

Reglas:
- Si include contiene producto, llenar producto.
- Si include no contiene producto, producto debe omitirse o venir como null, según el estilo usado en el proyecto. Preferir omitir campos no solicitados si FastAPI/Pydantic lo permite.
- Si include contiene stock, llenar stock.
- Si include contiene precios, llenar precios.
- Si include contiene movimientos, llenar movimientos.
- Si include no contiene movimientos, movimientos debe omitirse o venir como lista vacía, pero se prefiere omitirlo.
- La respuesta no debe mezclar todos los campos en la raíz.

Ejemplo:

GET /productos/1?include=producto,stock,precios

Respuesta esperada:

{
  "producto": {
    "producto_id": 1,
    "codigo": "P001",
    "nombre": "Producto A",
    "descripcion": "Producto de ejemplo",
    "categoria": "General",
    "unidad_medida": "UNIDAD",
    "impuesto": 10.1,
    "activo": true
  },
  "stock": {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8
  },
  "precios": {
    "precio_compra": 9200,
    "precio_venta": 15230
  }
}

Ejemplo:

GET /productos/1?include=stock,movimientos&limite_movimientos=10

Respuesta esperada:

{
  "stock": {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8
  },
  "movimientos": [
    {
      "movimiento_id": 50,
      "producto_id": 1,
      "reserva_id": 101,
      "tipo_movimiento": "VENTA",
      "origen": "VENTAS",
      "documento_ref": "FV-001-000123",
      "comprobante": "STK-001-000001",
      "cantidad": 2,
      "stock_anterior": 10,
      "stock_posterior": 8,
      "observacion": "Confirmación de venta desde reserva"
    }
  ]
}

============================================================
6. CREAR O AJUSTAR PRECIORESUMENOUT
============================================================

Crear PrecioResumenOut si no existe.

PrecioResumenOut:
  type: object
  properties:
    precio_compra:
      type: number
      minimum: 0
      multipleOf: 0.01
      nullable: true
    precio_venta:
      type: number
      minimum: 0
      multipleOf: 0.01
      nullable: true

Reglas:
- precio_compra puede ser null si todavía no existe precio de compra registrado.
- precio_venta puede ser null si todavía no existe precio de venta registrado.
- No usar moneda.
- No agregar campo moneda.

============================================================
7. DIFERENCIAR DOCUMENTO_REF Y COMPROBANTE
============================================================

Aplicar esta convención en schemas, ejemplos y documentación:

documento_ref:
- Documento externo recibido desde Ventas o Compras.
- Ejemplos:
  - FV-001-000123
  - OC-001-000555
- Se usa para trazabilidad externa.
- Debe mantenerse en reservas, ventas, compras y movimientos cuando corresponda.

comprobante:
- Comprobante interno generado por Stock.
- Debe ser generado por el módulo Stock en los procesos que crean movimientos o confirman operaciones.
- Ejemplo sugerido:
  - STK-001-000001
- Se usa para trazabilidad interna del módulo Stock.
- No debe reemplazar documento_ref.
- Puede convivir con documento_ref.

Formato sugerido para comprobante:

^[A-Z]{3}-\d{3}-\d{6}$

Ejemplo:

STK-001-000001

Agregar descripción:

"Comprobante interno generado por el módulo Stock para identificar la operación dentro del sistema."

Agregar ejemplos donde corresponda.

============================================================
8. INCORPORAR COMPROBANTE EN LOS PROCESOS
============================================================

Actualizar los schemas de salida y movimientos para incluir comprobante cuando corresponda.

Procesos que deben generar o devolver comprobante:

POST /stock/reservas
- Recibe documento_ref externo.
- Genera comprobante interno de reserva o movimiento de stock.
- La respuesta debe incluir documento_ref y comprobante.

Ejemplo:

{
  "estado": "RESERVADO",
  "documento_ref": "FV-001-000123",
  "comprobante": "STK-001-000001",
  "reservas": []
}

POST /stock/reservas/{reserva_id}/confirmar
- Recibe o utiliza documento_ref externo.
- Genera o reutiliza comprobante interno asociado a la confirmación.
- La respuesta debe incluir comprobante.

POST /stock/reservas/{reserva_id}/liberar
- Genera comprobante interno de liberación.
- La respuesta debe incluir comprobante.

POST /compras/eventos
- Recibe referencia_compra o documento_ref externo de Compras.
- Genera comprobante interno de entrada de Stock.
- La respuesta debe incluir comprobante.

POST /ventas/confirmar
- Recibe factura_id o documento_ref externo de Ventas.
- Genera comprobante interno de salida de Stock.
- La respuesta debe incluir documento_ref y comprobante.

GET /stock/movimientos
- MovimientoOut debe incluir documento_ref y comprobante.
- documento_ref identifica el documento externo.
- comprobante identifica la operación interna de Stock.

============================================================
9. NO ELIMINAR ENDPOINTS EXISTENTES
============================================================

No eliminar estos endpoints:

- GET /stock/{producto_id}
- GET /stock/movimientos
- POST /stock/reservas
- POST /stock/reservas/{reserva_id}/confirmar
- POST /stock/reservas/{reserva_id}/liberar
- POST /compras/eventos
- POST /ventas/confirmar

La consulta flexible de producto es una comodidad para consumidores, no reemplaza los endpoints específicos.

============================================================
10. MANTENER LO YA APROBADO
============================================================

Conservar:

- operationId estables.
- política normalizada de errores.
- respuestas 401, 403, 422, 500 y default.
- enums de unidad_medida, tipo_movimiento, origen y estado_procesamiento.
- política de idempotencia.
- política de concurrencia.
- endpoints internos marcados con x-internal cuando corresponda.
- documentación externa externalDocs.
- metadata de info, servers, contact, license y termsOfService.

============================================================
11. VALIDACIONES ESPERADAS EN OPENAPI
============================================================

Después de modificar el código, ejecutar:

python scripts/generate_openapi_yaml.py

Luego verificar en openapi.yaml:

- Ningún campo de cantidad debe quedar como type: string.
- Ningún campo de precio debe quedar como type: string.
- Ningún campo de cantidad o precio debe quedar como type: integer.
- cantidad debe quedar como type: number y exclusiveMinimum: 0.
- cantidades de salida deben quedar como type: number y minimum: 0.
- precios deben quedar como type: number, minimum: 0 y multipleOf: 0.01.
- impuesto debe quedar como type: number, minimum: 0, maximum: 100 y multipleOf: 0.01.
- GET /productos/{producto_id} debe tener include como parámetro combinable.
- GET /productos/{producto_id} debe tener limite_movimientos.
- GET /productos/{producto_id} debe devolver ProductoConsultaOut.
- ProductoConsultaOut debe estar agrupado por producto, stock, precios y movimientos.
- MovimientoOut debe incluir documento_ref y comprobante.
- Las respuestas de procesos de Stock deben devolver comprobante cuando generen una operación interna.
- documento_ref no debe ser reemplazado por comprobante.
- comprobante no debe usarse para representar documentos externos de Ventas o Compras.

============================================================
12. EJEMPLOS QUE DEBEN FIGURAR EN EL CONTRATO
============================================================

Agregar ejemplos para GET /productos/{producto_id}:

1. include=producto

GET /productos/1?include=producto

{
  "producto": {
    "producto_id": 1,
    "codigo": "P001",
    "nombre": "Producto A",
    "descripcion": "Producto de ejemplo",
    "categoria": "General",
    "unidad_medida": "UNIDAD",
    "impuesto": 10.1,
    "activo": true
  }
}

2. include=stock

GET /productos/1?include=stock

{
  "stock": {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8
  }
}

3. include=producto,stock,precios

GET /productos/1?include=producto,stock,precios

{
  "producto": {
    "producto_id": 1,
    "codigo": "P001",
    "nombre": "Producto A",
    "descripcion": "Producto de ejemplo",
    "categoria": "General",
    "unidad_medida": "UNIDAD",
    "impuesto": 10.1,
    "activo": true
  },
  "stock": {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8
  },
  "precios": {
    "precio_compra": 9200,
    "precio_venta": 15230
  }
}

4. include=stock,movimientos

GET /productos/1?include=stock,movimientos&limite_movimientos=10

{
  "stock": {
    "producto_id": 1,
    "cantidad_total": 10,
    "cantidad_reservada": 2,
    "cantidad_disponible": 8
  },
  "movimientos": [
    {
      "movimiento_id": 50,
      "producto_id": 1,
      "reserva_id": 101,
      "tipo_movimiento": "VENTA",
      "origen": "VENTAS",
      "documento_ref": "FV-001-000123",
      "comprobante": "STK-001-000001",
      "cantidad": 2,
      "stock_anterior": 10,
      "stock_posterior": 8,
      "observacion": "Confirmación de venta desde reserva"
    }
  ]
}

5. include=producto,movimientos

GET /productos/1?include=producto,movimientos&limite_movimientos=10

{
  "producto": {
    "producto_id": 1,
    "codigo": "P001",
    "nombre": "Producto A",
    "descripcion": "Producto de ejemplo",
    "categoria": "General",
    "unidad_medida": "UNIDAD",
    "impuesto": 10.1,
    "activo": true
  },
  "movimientos": [
    {
      "movimiento_id": 50,
      "producto_id": 1,
      "reserva_id": 101,
      "tipo_movimiento": "VENTA",
      "origen": "VENTAS",
      "documento_ref": "FV-001-000123",
      "comprobante": "STK-001-000001",
      "cantidad": 2,
      "stock_anterior": 10,
      "stock_posterior": 8,
      "observacion": "Confirmación de venta desde reserva"
    }
  ]
}

============================================================
13. ENTREGABLES
============================================================

Devolver:

1. Archivos modificados completos o bloques exactos a reemplazar.
2. Lista de funciones eliminadas del generador.
3. Lista de funciones nuevas agregadas al generador.
4. Schemas creados o modificados.
5. Cómo quedó documentado GET /productos/{producto_id}.
6. Cómo quedó documentado documento_ref.
7. Cómo quedó documentado comprobante.
8. Cómo validar que openapi.yaml fue generado correctamente.
9. Comandos para ejecutar pruebas o validación básica.

No entregar una solución parcial. Revisar que el contrato generado sea coherente de punta a punta.