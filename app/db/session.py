from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


# pool_pre_ping=True verifica la conexión antes de usarla, reconectando automáticamente
# tras caídas del servidor de base de datos.
engine = create_engine(get_settings().sqlalchemy_database_url, pool_pre_ping=True)
# expire_on_commit=False mantiene los objetos accesibles después del commit sin
# necesidad de una consulta adicional a la BD para re-leer sus atributos.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
