"""Pruebas unitarias sin base de datos del contrato y utilidades de Stock."""
import pytest

from app.core.comprobante import (
    digito_verificador,
    es_comprobante_valido,
    formatear_comprobante,
)
from app.core.errors import AppError
from app.services.inventory import _parsear_include


def test_comprobante_formato_y_digito_verificador():
    c = formatear_comprobante(1)
    assert c == "STK-001-000001-6"
    assert es_comprobante_valido(c)


def test_comprobante_detecta_digito_invalido():
    # Mismo comprobante con dígito verificador incorrecto.
    assert not es_comprobante_valido("STK-001-000001-0")
    # Formato inválido.
    assert not es_comprobante_valido("FV-001-000123")
    assert not es_comprobante_valido("STK-001-000001")


def test_comprobante_correlativos_distintos():
    assert formatear_comprobante(1) != formatear_comprobante(2)


def test_digito_verificador_es_un_digito():
    for n in range(1, 1000):
        dv = digito_verificador(f"001{n:06d}")
        assert 0 <= dv <= 9


def test_include_default_producto():
    assert _parsear_include("") == {"producto"}
    assert _parsear_include("producto") == {"producto"}


def test_include_dedup_y_orden_indiferente():
    assert _parsear_include("producto,producto,stock") == {"producto", "stock"}
    assert _parsear_include("stock,producto") == _parsear_include("producto,stock")


def test_include_valor_invalido_es_422():
    with pytest.raises(AppError) as exc:
        _parsear_include("producto,inexistente")
    assert exc.value.code == "VALIDACION_ERROR"
    assert exc.value.status_code == 422
