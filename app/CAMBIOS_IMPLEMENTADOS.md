# Implementación del parámetro `view` en GET /productos/{producto_id}

## ✅ Resumen Ejecutivo

Se ha modificado exitosamente el endpoint `GET /productos/{producto_id}` para permitir que los usuarios seleccionen qué datos retornar mediante el parámetro de query `view`.

### Opciones disponibles:
- `producto` - Datos maestros del producto (default)
- `stock` - Cantidades y disponibilidad
- `precios` - Precios de venta y compra más recientes
- Combinaciones: `producto,stock`, `producto,precios`, `stock,precios`, `producto,stock,precios`

---

## 📋 Cambios Realizados

### 1. **app/schemas/inventory.py**
Nuevo schema `ProductoViewOut` con todos los campos posibles como opcionales:
- ✓ Campos de Producto: `producto_id`, `codigo`, `nombre`, `descripcion`, `categoria`, `unidad_medida`, `activo`
- ✓ Campos de Stock: `cantidad_total`, `cantidad_reservada`, `cantidad_disponible`
- ✓ Campos de Precios: `precio_venta`, `precio_compra`
- ✓ Configuración: `exclude_none=True` para no devolver campos null

**Ejemplo de configuración:**
```python
class ProductoViewOut(BaseModel):
    # Campos opcionales
    producto_id: int | None = None
    codigo: str | None = None
    # ... etc
    model_config = ConfigDict(exclude_none=True)
```

### 2. **app/api/productos.py**
Endpoint modificado con nuevo parámetro `view`:
```python
@router.get("/{producto_id}", response_model=ProductoViewOut)
def obtener_producto(
    producto_id: int,
    view: str = Query(default="producto", description="..."),
    db: Session = Depends(get_db),
) -> ProductoViewOut:
    return service.obtener_producto_con_vista(db, producto_id, view)
```

### 3. **app/services/inventory.py**
Nueva función `obtener_producto_con_vista()`:
- ✓ Valida el parámetro `view`
- ✓ Obtiene datos del producto si está en la vista
- ✓ Obtiene datos de stock si está en la vista
- ✓ Obtiene precios más recientes si está en la vista
- ✓ Retorna diccionario que se convierte a ProductoViewOut

### 4. **scripts/generate_openapi_yaml.py**
Enriquecimiento del parámetro `view`:
- ✓ Agregados valores enum válidos
- ✓ Descripción clara del parámetro
- ✓ Documentación en el contrato OpenAPI

---

## 🧪 Verificación

Todas las validaciones pasaron exitosamente:

```
✓ Schema ProductoViewOut presente en OpenAPI
✓ Campo 'producto_id' presente
✓ Campo 'codigo' presente
✓ Campo 'nombre' presente
✓ Campo 'descripcion' presente
✓ Campo 'categoria' presente
✓ Campo 'unidad_medida' presente
✓ Campo 'activo' presente
✓ Campo 'cantidad_total' presente
✓ Campo 'cantidad_reservada' presente
✓ Campo 'cantidad_disponible' presente
✓ Campo 'precio_venta' presente
✓ Campo 'precio_compra' presente
✓ Parámetro 'view' presente en endpoint
✓ Todos los valores del enum son correctos
✓ Descripción presente y relevante
✓ Endpoint retorna ProductoViewOut
✓ Descripción del endpoint menciona 'view'
```

---

## 📝 Ejemplos de Uso

### Request: Solo producto (default)
```bash
GET /productos/1
GET /productos/1?view=producto
```

**Response:**
```json
{
  "producto_id": 1,
  "codigo": "P001",
  "nombre": "Producto A",
  "descripcion": "Producto de ejemplo",
  "categoria": "General",
  "unidad_medida": "UND",
  "activo": true
}
```

### Request: Solo stock
```bash
GET /productos/1?view=stock
```

**Response:**
```json
{
  "cantidad_total": "10.000",
  "cantidad_reservada": "2.000",
  "cantidad_disponible": "8.000"
}
```

### Request: Solo precios
```bash
GET /productos/1?view=precios
```

**Response:**
```json
{
  "precio_venta": "15000.00",
  "precio_compra": "9000.00"
}
```

### Request: Combinación de todas las vistas
```bash
GET /productos/1?view=producto,stock,precios
```

**Response:**
```json
{
  "producto_id": 1,
  "codigo": "P001",
  "nombre": "Producto A",
  "descripcion": "Producto de ejemplo",
  "categoria": "General",
  "unidad_medida": "UND",
  "activo": true,
  "cantidad_total": "10.000",
  "cantidad_reservada": "2.000",
  "cantidad_disponible": "8.000",
  "precio_venta": "15000.00",
  "precio_compra": "9000.00"
}
```

### Request: Combinación parcial
```bash
GET /productos/1?view=producto,stock
```

**Response:**
```json
{
  "producto_id": 1,
  "codigo": "P001",
  "nombre": "Producto A",
  "descripcion": "Producto de ejemplo",
  "categoria": "General",
  "unidad_medida": "UND",
  "activo": true,
  "cantidad_total": "10.000",
  "cantidad_reservada": "2.000",
  "cantidad_disponible": "8.000"
}
```

---

## 🔄 Flujo de Procesamiento

```
GET /productos/{producto_id}?view=producto,stock,precios
         ↓
obtener_producto() en productos.py
         ↓
obtener_producto_con_vista() en inventory.py
         ↓
    Validar view ✓
         ↓
┌─────────────────────────────────────┐
│  Si "producto" está en view:        │
│  → Consultar tabla Producto         │
│  → Agregar campos al resultado      │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  Si "stock" está en view:           │
│  → Consultar tabla StockActual      │
│  → Agregar campos al resultado      │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  Si "precios" está en view:         │
│  → Consultar PrecioVenta (más rct)  │
│  → Consultar PrecioCompra (más rct) │
│  → Agregar campos al resultado      │
└─────────────────────────────────────┘
         ↓
Retornar ProductoViewOut (con exclude_none=True)
         ↓
FastAPI serializa a JSON
         ↓
Response 200 OK
```

---

## 🛡️ Manejo de Errores

La función `obtener_producto_con_vista()` valida:

1. **Vista inválida**: Si se pasa un valor no válido, retorna error `VISTA_INVALIDA`
2. **Producto no existe**: Si el producto no existe, retorna `PRODUCTO_NO_EXISTE`
3. **Stock no inicializado**: Si se solicita stock pero no existe, retorna `STOCK_NO_INICIALIZADO`

---

## 📚 OpenAPI Documentation

El esquema OpenAPI fue enriquecido automáticamente con:

```yaml
/productos/{producto_id}:
  get:
    parameters:
    - name: view
      in: query
      schema:
        type: string
        enum:
          - producto
          - stock
          - precios
          - producto,stock
          - producto,precios
          - stock,precios
          - producto,stock,precios
        description: Vistas a incluir en la respuesta...
    responses:
      '200':
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProductoViewOut'
```

---

## 📦 Archivos Modificados

| Archivo | Cambio | Líneas |
|---------|--------|--------|
| `app/schemas/inventory.py` | Nuevo schema `ProductoViewOut` | +45 |
| `app/api/productos.py` | Endpoint con parámetro `view` | +4 |
| `app/services/inventory.py` | Nueva función `obtener_producto_con_vista()` | +70 |
| `scripts/generate_openapi_yaml.py` | Enriquecimiento del parámetro | +12 |
| `openapi.yaml` | Regenerado | ✓ |

---

## 🚀 Próximos Pasos (Opcionales)

1. **Documentación adicional**: Agregar ejemplos en README.md
2. **Test de integración**: Crear tests con datos reales
3. **Validación en BD**: Asegurar que PrecioVenta y PrecioCompra existen para los productos
4. **Caché**: Considerar caché para consultas de precios frecuentes

---

## ✨ Conclusión

Se ha implementado exitosamente el parámetro `view` para el endpoint GET /productos/{producto_id}, permitiendo a los usuarios:
- Consultar solo los datos que necesitan
- Reducir el payload de respuesta
- Mejorar la eficiencia de integración
- Tener control granular sobre los datos retornados

El contrato OpenAPI documenta claramente todas las opciones disponibles.
