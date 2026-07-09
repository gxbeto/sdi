"""Catálogo oficial de productos del sistema y reglas comerciales.

Este módulo no depende de nada externo: lo importan los tests, el seed y la
simulación (incluso en producción, donde no hay dependencias de desarrollo).
"""
from decimal import Decimal

# (codigo, categoria, nombre, unidad_medida, precio)
# El precio es el precio de compra de catálogo; se registra vía evento de compra.
CATALOGO = [
    # Informatica
    ("INF-001", "Informatica", "Processador Intel Core i5-12400 2.5GHz LGA 1700 18MB", "UNIDAD", "1300000"),
    ("INF-002", "Informatica", "Processador AMD Ryzen 7 5700G 3.8GHz AM4 20MB", "UNIDAD", "1274000"),
    ("INF-003", "Informatica", "Processador AMD Ryzen Threadripper Pro 9975WX Socket STR5 / 4.0GHZ / 160MB", "UNIDAD", "32500000"),
    ("INF-004", "Informatica", "Cpu Xeon Gold 6134..3.2GHZ SR3AR", "UNIDAD", "7000000"),
    ("INF-005", "Informatica", "Processador AMD Ryzen 9 9950X3D2 4.3GHz AM5 208MB", "UNIDAD", "6860000"),
    ("INF-006", "Informatica", "Teclado Satellite AK-910 USB / Negro", "UNIDAD", "32000"),
    ("INF-007", "Informatica", "Cable HDMI 1.5", "UNIDAD", "10000"),
    ("INF-008", "Informatica", "Mineradora Bitmain Antminer S21+ de 225 TH/s", "UNIDAD", "20020000"),
    ("INF-009", "Informatica", "Memória Keepdata DDR3 8GB 1600MHz KD16N11/8G", "UNIDAD", "167300"),
    ("INF-010", "Informatica", "Memória Kingston Fury Beast DDR4 16GB 3200MHz", "UNIDAD", "931000"),
    ("INF-011", "Informatica", "Placa de Vídeo Biostar Extreme Gaming GeForce RTX2060 Super 8GB GDDR6 PCI-Express", "UNIDAD", "1869000"),
    ("INF-012", "Informatica", "Placa de Vídeo Asus TUF Gaming GeForce RTX5070 OC 12GB GDDR7 PCI-Express", "UNIDAD", "5600000"),
    # Celulares
    ("CEL-001", "Celulares", "Celular Apple iPhone 17 256GB", "UNIDAD", "5880000"),
    ("CEL-002", "Celulares", "Celular Xiaomi Redmi Note 15 Dual Chip 256GB 4G Global", "UNIDAD", "1253000"),
    ("CEL-003", "Celulares", "Celular Xiaomi 17 Ultra Dual Chip 1TB 5G Global", "UNIDAD", "9751000"),
    ("CEL-004", "Celulares", "Celular Apple iPhone 17 Pro Max 2TB", "UNIDAD", "13734000"),
    # Perfumes
    ("PER-001", "Perfumes", "Sistelle Perfume Tester Sanderling Shine Blooming Edp Femenino 100ML", "UNIDAD", "70000000"),
    ("PER-002", "Perfumes", "P.Boadicea The Victorious Resplendent 100ML", "UNIDAD", "9170000"),
    ("PER-003", "Perfumes", "Spirit Dubai Oud Edp 50ML", "UNIDAD", "5000000"),
    ("PER-004", "Perfumes", "PerfumeMonella Vagabonda Belle Edt 100ML - Feminino", "UNIDAD", "210000"),
    # Salud
    ("SAL-001", "Salud", "Balanza Comercial Quanta QTBD250 40KG", "UNIDAD", "35000"),
    ("SAL-002", "Salud", "Balanza Comercial Satellite AB-21001 40KG", "UNIDAD", "120000"),
    ("SAL-003", "Salud", "Balanza de Peso Corporal Quanta QTBCB200 180KG", "UNIDAD", "60000"),
    ("SAL-004", "Salud", "Medidor de Presion More Fitness MF-641ND", "UNIDAD", "110000"),
    ("SAL-005", "Salud", "Medidor de Presion More Fitness MF-333", "UNIDAD", "70000"),
]

CATALOGO_POR_CODIGO = {item[0]: item for item in CATALOGO}

# Reglas comerciales del catálogo:
# - Todos los productos tributan 10 % de impuesto.
# - El precio de venta es el precio de compra con 30 % de margen, y sobre ese
#   resultado se recarga el impuesto: venta = compra * 1.30 * 1.10.
IMPUESTO_PORCENTAJE = Decimal("10")
MARGEN_VENTA = Decimal("1.30")


def precio_venta_catalogo(precio_compra: str) -> str:
    recargo_impuesto = 1 + IMPUESTO_PORCENTAJE / 100
    venta = Decimal(precio_compra) * MARGEN_VENTA * recargo_impuesto
    return str(venta.quantize(Decimal("0.01")))
