"""
Generación y validación de comprobantes internos del módulo Stock.

Un comprobante interno identifica una operación generada por Stock (reserva,
confirmación, liberación, entrada por compra o salida por venta). Su formato es:

    STK-<serie:3>-<numero:6>-<dv:1>      Ej.: STK-001-000001-6

- STK: prefijo fijo del módulo Stock.
- serie: agrupador de 3 dígitos (por defecto 001).
- numero: correlativo de 6 dígitos dentro de la serie.
- dv: dígito verificador (algoritmo de Luhn sobre los 9 dígitos serie+numero).

El dígito verificador permite validar de entrada si un comprobante es "oficial"
(bien formado) sin necesidad de consultar la base de datos.
"""
import re

PREFIJO = "STK"
SERIE_DEFECTO = "001"

# Patrón contractual del comprobante interno, incluyendo el dígito verificador.
COMPROBANTE_PATTERN = r"^STK-\d{3}-\d{6}-\d$"
COMPROBANTE_EXAMPLE = "STK-001-000001-6"

_COMPROBANTE_RE = re.compile(COMPROBANTE_PATTERN)


def digito_verificador(digitos: str) -> int:
    """Calcula el dígito verificador (Luhn / mod 10) sobre una cadena de dígitos."""
    total = 0
    # Luhn: se recorre de derecha a izquierda duplicando posiciones alternas.
    for posicion, caracter in enumerate(reversed(digitos)):
        valor = int(caracter)
        if posicion % 2 == 0:
            valor *= 2
            if valor > 9:
                valor -= 9
        total += valor
    return (10 - (total % 10)) % 10


def formatear_comprobante(numero: int, serie: str = SERIE_DEFECTO) -> str:
    """Construye un comprobante interno oficial a partir de serie y correlativo."""
    serie_norm = f"{int(serie):03d}"
    numero_norm = f"{int(numero):06d}"
    dv = digito_verificador(serie_norm + numero_norm)
    return f"{PREFIJO}-{serie_norm}-{numero_norm}-{dv}"


def es_comprobante_valido(comprobante: str) -> bool:
    """Valida formato y dígito verificador de un comprobante interno."""
    if not isinstance(comprobante, str) or not _COMPROBANTE_RE.match(comprobante):
        return False
    _, serie, numero, dv = comprobante.split("-")
    return digito_verificador(serie + numero) == int(dv)
