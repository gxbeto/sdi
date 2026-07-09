"""Programa de mantenimiento para actualizar SDI en el servidor de producción.

Uso (desde la raíz del proyecto, con el venv del servidor):
    python scripts/mantenimiento.py [--rama main] [--forzar] [--sin-deps]
                                    [--sin-backup] [--reiniciar "comando"]
                                    [--verificar-url URL]

Qué hace, en orden:
1. Baja los cambios del repositorio git (git fetch + git pull --ff-only de la
   rama indicada). Con --forzar descarta cambios locales del servidor y deja
   el código exactamente como está en el remoto (git reset --hard).
2. Instala/actualiza las dependencias de requirements.txt (omitir con --sin-deps).
3. Crea un backup de la base con pg_dump en backups/ antes de migrar
   (omitir con --sin-backup; si pg_dump no está instalado, avisa y continúa).
4. Aplica los cambios de estructura de base de datos con Alembic
   (alembic upgrade head). La primera vez crea todas las tablas desde cero;
   las siguientes solo aplica las migraciones pendientes.
5. Si se indica --reiniciar, ejecuta ese comando para reiniciar el servicio
   (por ejemplo: --reiniciar "systemctl restart sdi").
6. Si se indica --verificar-url, comprueba que el servicio responda 200 en esa
   URL tras el reinicio (por ejemplo: --verificar-url http://127.0.0.1:6000/health).

Aislamiento de configuración: toda la configuración sale EXCLUSIVAMENTE del
archivo .env de este proyecto. Las variables de entorno heredadas de la sesión
(DB_NAME, DB_HOST, DATABASE_URL, etc. — por ejemplo de otros proyectos que
conviven en el mismo servidor) se eliminan antes de ejecutar las migraciones,
para que nunca puedan desviar la conexión hacia otra base.

Instalación inicial en el servidor (una sola vez):
    git clone https://github.com/gxbeto/sdi.git && cd sdi
    python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\\Scripts\\activate
    cp .env.example .env   # editar con la base y credenciales de producción
    pip install -r requirements.txt
    python scripts/mantenimiento.py    # crea las tablas y deja todo al día

El script es idempotente: si no hay cambios ni migraciones pendientes, no
modifica nada. Ante cualquier error se detiene con código de salida distinto
de cero, sin ejecutar los pasos siguientes.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_ROOT / "backups"

# Claves de configuración de SDI: se eliminan del entorno heredado para que
# solo valga el .env del proyecto (otros proyectos del servidor pueden tener
# exportadas variables con los mismos nombres).
CLAVES_CONFIGURACION = [
    "APP_NAME",
    "DB_ENGINE",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "RABBITMQ_URL",
    "RABBITMQ_COMPRAS_QUEUE",
    "LOG_LEVEL",
]


def entorno_limpio() -> dict:
    entorno = os.environ.copy()
    for clave in CLAVES_CONFIGURACION:
        entorno.pop(clave, None)
    return entorno


def log(mensaje: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {mensaje}", flush=True)


def ejecutar(comando: list[str], descripcion: str, stdout_a_archivo: Path | None = None) -> str:
    log(f"-> {descripcion}: {' '.join(comando)}")
    destino = open(stdout_a_archivo, "wb") if stdout_a_archivo else subprocess.PIPE
    try:
        resultado = subprocess.run(
            comando,
            cwd=PROJECT_ROOT,
            stdout=destino,
            stderr=subprocess.PIPE,
            env=entorno_limpio(),
        )
    finally:
        if stdout_a_archivo:
            destino.close()
    salida = "" if stdout_a_archivo else (resultado.stdout or b"").decode(errors="replace").strip()
    if salida:
        print(salida)
    if resultado.returncode != 0:
        error = (resultado.stderr or b"").decode(errors="replace").strip()
        if error:
            print(error, file=sys.stderr)
        log(f"ERROR en '{descripcion}' (código {resultado.returncode}). Mantenimiento abortado.")
        sys.exit(resultado.returncode)
    return salida


def commit_actual() -> str:
    return ejecutar(["git", "rev-parse", "--short", "HEAD"], "commit actual")


def leer_env() -> dict:
    """Lee el .env del proyecto sin depender de librerías externas."""
    valores: dict[str, str] = {}
    archivo = PROJECT_ROOT / ".env"
    if not archivo.exists():
        log("ERROR: no existe el archivo .env del proyecto. Mantenimiento abortado.")
        sys.exit(1)
    # utf-8-sig tolera el BOM que agregan los editores de Windows.
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip()
    return valores


def hacer_backup() -> None:
    """Backup de la base con pg_dump antes de migrar. Aborta si el backup falla."""
    env = leer_env()
    if env.get("DB_ENGINE", "postgresql") != "postgresql" or "DB_NAME" not in env:
        log("Backup omitido: configuración de BD no compatible con pg_dump.")
        return

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        log("AVISO: pg_dump no está instalado; se continúa SIN backup previo.")
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    destino = BACKUP_DIR / f"pre-update_{datetime.now():%Y%m%d_%H%M%S}.sql"
    comando = [
        pg_dump,
        "-h", env.get("DB_HOST", "127.0.0.1"),
        "-p", env.get("DB_PORT", "5432"),
        "-U", env.get("DB_USER", "postgres"),
        env["DB_NAME"],
    ]
    os.environ["PGPASSWORD"] = env.get("DB_PASSWORD", "")
    try:
        ejecutar(comando, "backup previo de la base", stdout_a_archivo=destino)
    finally:
        os.environ.pop("PGPASSWORD", None)
    log(f"Backup creado: {destino}")

    # Retención: se conservan los últimos 10 backups pre-update.
    backups = sorted(BACKUP_DIR.glob("pre-update_*.sql"))
    for viejo in backups[:-10]:
        viejo.unlink()


def verificar_salud(url: str, intentos: int = 5, espera_segundos: int = 2) -> None:
    log(f"Verificando salud del servicio en {url} ...")
    ultimo_error = "sin respuesta"
    for _ in range(intentos):
        time.sleep(espera_segundos)
        try:
            with urllib.request.urlopen(url, timeout=5) as respuesta:
                if respuesta.status == 200:
                    log("Servicio saludable (HTTP 200).")
                    return
                ultimo_error = f"HTTP {respuesta.status}"
        except (urllib.error.URLError, OSError) as exc:
            ultimo_error = str(exc)
    log(f"ERROR: el servicio no respondió correctamente ({ultimo_error}).")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Actualiza SDI desde git y aplica migraciones.")
    parser.add_argument("--rama", default="main", help="Rama a desplegar (default: main).")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Descarta cambios locales y deja el código igual al remoto (git reset --hard).",
    )
    parser.add_argument("--sin-deps", action="store_true", help="No reinstalar dependencias.")
    parser.add_argument("--sin-backup", action="store_true", help="No hacer backup previo de la base.")
    parser.add_argument(
        "--reiniciar",
        default=None,
        metavar="COMANDO",
        help='Comando para reiniciar el servicio al final (ej.: "systemctl restart sdi").',
    )
    parser.add_argument(
        "--verificar-url",
        default=None,
        metavar="URL",
        help="URL de salud a comprobar tras el reinicio (ej.: http://127.0.0.1:6000/health).",
    )
    args = parser.parse_args()

    log(f"Mantenimiento SDI iniciado en {PROJECT_ROOT}")
    ignoradas = [c for c in CLAVES_CONFIGURACION if c in os.environ]
    if ignoradas:
        log(f"AVISO: se ignoran variables de entorno heredadas: {', '.join(ignoradas)} (solo vale el .env).")

    # 1) Bajar cambios del repositorio.
    version_anterior = commit_actual()
    ejecutar(["git", "fetch", "origin", args.rama], "bajar cambios del remoto")
    if args.forzar:
        ejecutar(["git", "reset", "--hard", f"origin/{args.rama}"], "forzar código igual al remoto")
    else:
        ejecutar(["git", "checkout", args.rama], "posicionarse en la rama")
        # --ff-only: si el servidor tiene commits locales que divergen, el pull
        # falla en lugar de crear merges en producción (usar --forzar en ese caso).
        ejecutar(["git", "pull", "--ff-only", "origin", args.rama], "actualizar el código")
    version_nueva = commit_actual()

    if version_anterior == version_nueva:
        log(f"Sin cambios de código (commit {version_nueva}).")
    else:
        log(f"Código actualizado: {version_anterior} -> {version_nueva}")

    # 2) Dependencias.
    if args.sin_deps:
        log("Instalación de dependencias omitida (--sin-deps).")
    else:
        ejecutar(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"],
            "instalar dependencias",
        )

    # 3) Backup previo de la base.
    if args.sin_backup:
        log("Backup previo omitido (--sin-backup).")
    else:
        hacer_backup()

    # 4) Estructura de base de datos: la primera vez crea las tablas,
    #    luego aplica solo las migraciones pendientes.
    ejecutar([sys.executable, "-m", "alembic", "upgrade", "head"], "aplicar migraciones de BD")

    # 5) Reinicio del servicio (opcional).
    if args.reiniciar:
        ejecutar(args.reiniciar.split(), "reiniciar el servicio")
    else:
        log("Recordatorio: reiniciar el servicio para tomar el nuevo código (o usar --reiniciar).")

    # 6) Verificación de salud (opcional).
    if args.verificar_url:
        verificar_salud(args.verificar_url)

    log("Mantenimiento finalizado correctamente.")


if __name__ == "__main__":
    main()
