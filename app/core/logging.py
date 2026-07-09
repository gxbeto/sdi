import logging

from app.core.config import get_settings

# Configuración centralizada de logging para toda la aplicación, usando el nivel definido en settings.
def configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

