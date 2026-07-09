"""Programa de mantenimiento para actualizar SDI en el servidor de producción.

Uso (desde la raíz del proyecto, con el venv del servidor):
    python scripts/mantenimiento.py [--rama main] [--forzar] [--sin-deps]
                                    [--reiniciar "comando"]

Qué hace, en orden:
1. Baja los cambios del repositorio git (git fetch + git pull --ff-only de la
   rama indicada). Con --forzar descarta cambios locales del servidor y deja
   el código exactamente como está en el remoto (git reset --hard).
2. Instala/actualiza las dependencias de requirements.txt (omitir con --sin-deps).
3. Aplica los cambios de estructura de base de datos con Alembic
   (alembic upgrade head). La primera vez crea todas las tablas desde cero;
   las siguientes solo aplica las migraciones pendientes. La conexión sale
   del .env del servidor.
4. Si se indica --reiniciar, ejecuta ese comando para reiniciar el servicio
   (por ejemplo: --reiniciar "systemctl restart sdi").

Instalación inicial en el servidor (una sola vez):
    git clone <URL_DEL_REPOSITORIO> sdi && cd sdi
    python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\\Scripts\\activate
    cp .env.example .env   # editar con la base y credenciales de producción
    pip install -r requirements.txt
    python scripts/mantenimiento.py    # crea las tablas y deja todo al día

El script es idempotente: si no hay cambios ni migraciones pendientes, no
modifica nada. Ante cualquier error se detiene con código de salida distinto
de cero, sin ejecutar los pasos siguientes.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def log(mensaje: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {mensaje}", flush=True)


def ejecutar(comando: list[str], descripcion: str) -> str:
    log(f"-> {descripcion}: {' '.join(comando)}")
    resultado = subprocess.run(
        comando,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    salida = (resultado.stdout or "").strip()
    if salida:
        print(salida)
    if resultado.returncode != 0:
        error = (resultado.stderr or "").strip()
        if error:
            print(error, file=sys.stderr)
        log(f"ERROR en '{descripcion}' (código {resultado.returncode}). Mantenimiento abortado.")
        sys.exit(resultado.returncode)
    return salida


def commit_actual() -> str:
    return ejecutar(["git", "rev-parse", "--short", "HEAD"], "commit actual")


def main() -> None:
    parser = argparse.ArgumentParser(description="Actualiza SDI desde git y aplica migraciones.")
    parser.add_argument("--rama", default="main", help="Rama a desplegar (default: main).")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Descarta cambios locales y deja el código igual al remoto (git reset --hard).",
    )
    parser.add_argument("--sin-deps", action="store_true", help="No reinstalar dependencias.")
    parser.add_argument(
        "--reiniciar",
        default=None,
        metavar="COMANDO",
        help='Comando para reiniciar el servicio al final (ej.: "systemctl restart sdi").',
    )
    args = parser.parse_args()

    log(f"Mantenimiento SDI iniciado en {PROJECT_ROOT}")

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

    # 3) Estructura de base de datos: la primera vez crea las tablas,
    #    luego aplica solo las migraciones pendientes.
    ejecutar([sys.executable, "-m", "alembic", "upgrade", "head"], "aplicar migraciones de BD")

    # 4) Reinicio del servicio (opcional).
    if args.reiniciar:
        ejecutar(args.reiniciar.split(), "reiniciar el servicio")
    else:
        log("Recordatorio: reiniciar el servicio para tomar el nuevo código (o usar --reiniciar).")

    log("Mantenimiento finalizado correctamente.")


if __name__ == "__main__":
    main()
