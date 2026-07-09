from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación, leída del archivo .env (o variables de entorno).

    Sin valores por defecto a propósito: si falta una clave en el .env, la
    aplicación falla al arrancar en lugar de conectarse a un destino no deseado.
    """

    app_name: str
    db_engine: str
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    # database_url es un override opcional: si se define, reemplaza a los campos db_*.
    database_url: str | None = None
    rabbitmq_url: str
    rabbitmq_compras_queue: str
    log_level: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        driver = "postgresql+psycopg" if self.db_engine == "postgresql" else self.db_engine
        return f"{driver}://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


# lru_cache convierte get_settings en un singleton: el archivo .env se lee
# una sola vez al arrancar, no en cada petición HTTP.
@lru_cache
def get_settings() -> Settings:
    return Settings()
