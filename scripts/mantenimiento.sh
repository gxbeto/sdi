#!/bin/bash
# Herramienta de mantenimiento interactiva de SDI para el servidor de producción.
# Mismo estilo que las herramientas de ACADEMIK/AFC. Ejecutar como root:
#   bash /opt/sdi/scripts/mantenimiento.sh
#
# El deploy (opción 3) delega en scripts/mantenimiento.py, que hace:
# git pull + dependencias + backup pg_dump + migraciones Alembic, ignorando
# variables de entorno heredadas de otros proyectos (solo vale el .env).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_NAME="${APP_NAME:-SDI}"
APP_DIR="${APP_DIR:-/opt/sdi}"
APP_USER="${APP_USER:-sdi}"
SERVICE_NAME="${SERVICE_NAME:-sdi}"
DB_NAME="${DB_NAME:-sdi}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:6000/health}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

run_as_app_user() {
    su - "$APP_USER" -c "$1"
}

ensure_app_user_can_write_repo() {
    if ! su - "$APP_USER" -c "test -w '$APP_DIR/.git/objects'" >/dev/null 2>&1; then
        echo -e "${RED}Error de permisos del repositorio.${NC}"
        echo "El usuario $APP_USER no puede escribir en $APP_DIR/.git/objects"
        echo "Ejecute: chown -R $APP_USER:$APP_USER $APP_DIR"
        return 1
    fi
}

restart_app_and_verify() {
    systemctl restart "$SERVICE_NAME"
    echo -n "Esperando al servicio"
    for _ in 1 2 3 4 5; do
        sleep 2
        echo -n "."
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            echo -e " ${GREEN}OK — $HEALTH_URL responde 200${NC}"
            return 0
        fi
    done
    echo -e " ${RED}ERROR: el servicio no responde${NC}"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    return 1
}

show_menu() {
    echo ""
    echo "========================================"
    echo " ${APP_NAME} - Herramienta de Mantenimiento"
    echo "========================================"
    echo "1. Ver estado de la aplicacion"
    echo "2. Ver logs en vivo"
    echo "3. Actualizar aplicacion (deploy completo)"
    echo "4. Backup de la base de datos"
    echo "5. Restaurar backup de la base"
    echo "6. Reiniciar servicios"
    echo "7. Limpiar archivos temporales"
    echo "8. Salir"
    echo ""
}

status_app() {
    echo -e "${YELLOW}Estado de los servicios:${NC}\n"

    echo "Servicio $SERVICE_NAME:"
    systemctl status "$SERVICE_NAME" --no-pager | head -5 || true

    echo -e "\nNginx:"
    systemctl status nginx --no-pager | head -3 || true

    echo -e "\nPostgreSQL:"
    systemctl status postgresql --no-pager | head -3 || true

    echo -e "\nWorkers uvicorn:"
    pgrep -u "$APP_USER" -f uvicorn | wc -l | xargs echo "Procesos activos:"

    echo -e "\nSalud de la API:"
    curl -sf "$HEALTH_URL" && echo "" || echo -e "${RED}sin respuesta${NC}"

    echo -e "\nVersion desplegada:"
    git -C "$APP_DIR" log -1 --format="%h %s (%cr)" || true

    echo -e "\nUso de disco:"
    df -h / | tail -1
}

show_logs() {
    echo -e "${YELLOW}Logs de ${SERVICE_NAME} (Ctrl+C para salir):${NC}\n"
    journalctl -u "$SERVICE_NAME" -f --no-pager
}

deploy() {
    echo -e "${YELLOW}Deploy completo de ${APP_NAME}...${NC}\n"
    ensure_app_user_can_write_repo || return 1

    # mantenimiento.py hace: git pull + dependencias + backup pg_dump + migraciones,
    # con entorno limpio (ignora DB_* heredadas; solo vale el .env de $APP_DIR).
    echo -e "${BLUE}[1/3] Codigo, dependencias, backup y migraciones...${NC}"
    run_as_app_user "cd $APP_DIR && .venv/bin/python scripts/mantenimiento.py"

    echo -e "${BLUE}[2/3] Reiniciando servicio...${NC}"
    restart_app_and_verify

    echo -e "${BLUE}[3/3] Version desplegada:${NC}"
    git -C "$APP_DIR" log -1 --format="%h %s (%cr)"
    echo -e "${GREEN}Deploy finalizado${NC}"
}

backup_db() {
    local backup_file

    echo -e "${YELLOW}Creando backup de la base...${NC}\n"
    backup_file="$BACKUP_DIR/${SERVICE_NAME}_$DATE.sql"
    sudo -u postgres pg_dump "$DB_NAME" > "$backup_file"
    gzip "$backup_file"
    backup_file="$backup_file.gz"

    echo -e "${GREEN}Backup creado: $backup_file${NC}"
    ls -lh "$backup_file"

    echo -e "\n${YELLOW}Ultimos backups:${NC}"
    ls -lht "$BACKUP_DIR"/*.gz 2>/dev/null | head -5 || echo "(ninguno)"
}

restore_db() {
    local backup_num backup_file confirm

    echo -e "${YELLOW}Backups disponibles:${NC}\n"
    if ! ls "$BACKUP_DIR"/*.sql.gz >/dev/null 2>&1; then
        echo "No hay backups .sql.gz en $BACKUP_DIR"
        return
    fi
    ls -t "$BACKUP_DIR"/*.sql.gz | nl

    read -r -p "Numero de backup a restaurar (0 para cancelar): " backup_num
    if [ -z "${backup_num:-}" ] || [ "$backup_num" -eq 0 ]; then
        echo "Cancelado"
        return
    fi

    backup_file=$(ls -t "$BACKUP_DIR"/*.sql.gz | sed -n "${backup_num}p")
    if [ ! -f "$backup_file" ]; then
        echo -e "${RED}Backup no encontrado${NC}"
        return 1
    fi

    echo -e "${RED}Atencion: esto sobreescribe la base actual (${DB_NAME}).${NC}"
    read -r -p "Escriba 'si' para continuar: " confirm
    if [ "$confirm" != "si" ]; then
        echo "Cancelado"
        return
    fi

    sudo -u postgres pg_dump "$DB_NAME" > "$BACKUP_DIR/pre-restore_$DATE.sql"
    systemctl stop "$SERVICE_NAME"
    sudo -u postgres psql -c "DROP DATABASE $DB_NAME WITH (FORCE);"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER ${DB_NAME}_user;"
    gunzip -c "$backup_file" | sudo -u postgres psql "$DB_NAME"

    echo -e "${GREEN}Base restaurada${NC}"
    restart_app_and_verify
}

restart_services() {
    echo -e "${YELLOW}Reiniciando servicios...${NC}\n"
    restart_app_and_verify
    nginx -t && systemctl reload nginx
    echo -e "\n${YELLOW}Estado actual:${NC}"
    status_app
}

cleanup_temp() {
    echo -e "${YELLOW}Limpiando archivos temporales...${NC}\n"
    cd "$APP_DIR"

    du -sh . | xargs echo "Tamano antes:"
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "pre-update_*.sql" -mtime +30 -delete 2>/dev/null || true
    du -sh . | xargs echo "Tamano despues:"

    echo -e "${GREEN}Limpieza finalizada${NC}"
}

while true; do
    show_menu
    read -r -p "Seleccione una opcion (1-8): " option

    case "$option" in
        1) status_app ;;
        2) show_logs ;;
        3) deploy ;;
        4) backup_db ;;
        5) restore_db ;;
        6) restart_services ;;
        7) cleanup_temp ;;
        8) echo "Hasta luego"; exit 0 ;;
        *) echo -e "${RED}Opcion invalida${NC}" ;;
    esac

    read -r -p "Presione Enter para continuar..."
done
