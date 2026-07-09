# SDI — Instalación en producción y desinstalación

Documentación de la prueba de concepto desplegada el **2026-07-09** en el servidor
`vmi3080844` (Ubuntu, Python 3.12.3), conviviendo con otros proyectos (ACADEMIK y AFC)
sin interferir con ellos.

---

## 1. Inventario: qué se instaló y dónde

| Componente | Ubicación / nombre | Descripción |
|---|---|---|
| Código de la aplicación | `/opt/sdi` | Clon de https://github.com/gxbeto/sdi (rama `main`), propiedad del usuario `sdi` |
| Entorno virtual Python | `/opt/sdi/.venv` | Dependencias de `requirements.txt` |
| Configuración | `/opt/sdi/.env` | Única fuente de configuración (BD, RabbitMQ). `chmod 600`. **No versionado** |
| Usuario de sistema | `sdi` | Usuario dedicado sin privilegios (patrón `akadmin`/`afc`) |
| Servicio de la API | `sdi.service` | uvicorn, 2 workers, socket Unix `/run/sdi/sdi.sock` |
| Servicio del consumer | `sdi-consumer.service` | Consumer de compras RabbitMQ (si se instaló el paso 6) |
| Sitio nginx | `/etc/nginx/sites-available/sdi` (+ symlink en `sites-enabled`) | Proxy del puerto **8181** al socket Unix |
| Base de datos | PostgreSQL local, base `sdi` | Owner: usuario `sdi_user` (solo tiene permisos sobre esta base) |
| Broker de mensajería | `rabbitmq-server` (paquete apt) | Cola `compras.stock` (si se instaló el paso 6) |
| Backups | `/opt/sdi/backups/` | `pg_dump` automáticos pre-deploy (retención 10) y manuales |
| Regla de firewall | `ufw allow 8181/tcp` | Acceso externo a la API (si ufw está activo) |
| Sudoers (opcional) | `/etc/sudoers.d/sdi` | Permiso del usuario `sdi` para reiniciar su servicio (si se creó) |

**Puertos**: la API se expone solo en el **8181** vía nginx (el 6000 original lo bloquean
los navegadores con `ERR_UNSAFE_PORT`). uvicorn no abre puertos TCP (usa socket Unix).

---

## 2. Instalación (resumen de lo ejecutado)

### 2.1 Base de datos

```bash
sudo -u postgres psql <<'SQL'
CREATE USER sdi_user WITH PASSWORD 'CONTRASEÑA_GENERADA';
CREATE DATABASE sdi OWNER sdi_user;
SQL
```

> El owner debe ser `sdi_user` **desde la creación**: si las tablas se crean con otro
> dueño, `pg_dump` y las migraciones fallan con `permission denied`.

### 2.2 Usuario, código y configuración

```bash
useradd -r -m -s /bin/bash sdi
cd /opt && git clone https://github.com/gxbeto/sdi.git && cd sdi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # editar: DB_USER=sdi_user, DB_PASSWORD=..., DB_HOST=127.0.0.1
chmod 600 .env
chown -R sdi:sdi /opt/sdi
```

### 2.3 Tablas (primera corrida del mantenimiento)

```bash
su - sdi -c 'cd /opt/sdi && .venv/bin/python scripts/mantenimiento.py'
```

Crea las 9 tablas vía Alembic. Corridas posteriores solo aplican migraciones pendientes.

### 2.4 Servicio systemd de la API

`/etc/systemd/system/sdi.service`:

```ini
[Unit]
Description=SDI - Sistema Distribuido de Inventario (FastAPI)
After=network.target postgresql.service

[Service]
Type=simple
User=sdi
Group=www-data
WorkingDirectory=/opt/sdi
Environment="PATH=/opt/sdi/.venv/bin"
RuntimeDirectory=sdi
RuntimeDirectoryMode=0755
ExecStartPre=/bin/rm -f /run/sdi/sdi.sock
ExecStart=/opt/sdi/.venv/bin/uvicorn app.main:app \
    --uds /run/sdi/sdi.sock \
    --workers 2 \
    --proxy-headers
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now sdi
```

### 2.5 Nginx (puerto 8181)

`/etc/nginx/sites-available/sdi`:

```nginx
server {
    listen 8181;
    server_name _;

    location / {
        proxy_pass http://unix:/run/sdi/sdi.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/sdi /etc/nginx/sites-enabled/sdi
nginx -t && systemctl reload nginx      # reload, no restart: no afecta otros sitios
ufw status | grep -q active && ufw allow 8181/tcp
```

### 2.6 RabbitMQ + consumer de compras (opcional)

```bash
apt install -y rabbitmq-server
systemctl enable --now rabbitmq-server
```

`/etc/systemd/system/sdi-consumer.service`:

```ini
[Unit]
Description=SDI - Consumer de compras (RabbitMQ)
After=network.target rabbitmq-server.service postgresql.service

[Service]
Type=simple
User=sdi
WorkingDirectory=/opt/sdi
ExecStart=/opt/sdi/.venv/bin/python -m app.consumers.compras_consumer
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now sdi-consumer
```

### 2.7 Verificación

```bash
curl http://127.0.0.1:8181/health        # → {"status":"ok"}
```

- Swagger: `http://IP:8181/docs` · Guía funcional: `http://IP:8181/documentacion`

---

## 3. Operación diaria

Todo se opera con la herramienta de mantenimiento, como root:

```bash
bash /opt/sdi/scripts/mantenimiento.sh
```

- **Opción 3 (deploy)**: git pull + dependencias + backup + migraciones + reinicio de
  API y consumer + verificación de salud. Es el único comando necesario tras cada push.
- Las variables `DB_*` heredadas de la sesión **se ignoran** (solo vale el `.env` del
  proyecto): otros proyectos del servidor no pueden desviar la conexión.
- `scripts/simulacion.py` **borra todos los datos** (pide confirmación). No usar en
  producción salvo que ese sea el objetivo.

---

## 4. Desinstalación completa

Orden recomendado: servicios → nginx → código y usuario → base de datos → extras.
Ningún paso afecta a ACADEMIK ni AFC (no comparten usuario, base, sockets ni puertos).

### 4.0 (Opcional) Conservar un respaldo final

```bash
sudo -u postgres pg_dump sdi | gzip > /root/sdi_final_$(date +%Y%m%d).sql.gz
```

### 4.1 Detener y eliminar los servicios

```bash
systemctl disable --now sdi
systemctl disable --now sdi-consumer 2>/dev/null || true
rm -f /etc/systemd/system/sdi.service /etc/systemd/system/sdi-consumer.service
systemctl daemon-reload
systemctl reset-failed
```

### 4.2 Quitar el sitio de nginx

```bash
rm -f /etc/nginx/sites-enabled/sdi /etc/nginx/sites-available/sdi
nginx -t && systemctl reload nginx      # reload: los otros sitios siguen sirviendo
```

### 4.3 Cerrar el puerto del firewall (si se abrió)

```bash
ufw delete allow 8181/tcp 2>/dev/null || true
```

### 4.4 Eliminar la base de datos y su usuario

```bash
sudo -u postgres psql <<'SQL'
DROP DATABASE IF EXISTS sdi WITH (FORCE);
DROP USER IF EXISTS sdi_user;
SQL
```

> `WITH (FORCE)` corta las conexiones abiertas. Si además se quiere borrar la base de
> pruebas local de desarrollo, repetir con `sdi_test` en la máquina de desarrollo.

### 4.5 Eliminar el código, los backups y el usuario de sistema

```bash
rm -rf /opt/sdi
userdel -r sdi 2>/dev/null || userdel sdi
rm -f /etc/sudoers.d/sdi                # solo si se creó (paso opcional de instalación)
```

### 4.6 RabbitMQ (solo si no lo usa nadie más)

**Verificar primero** que ningún otro proyecto lo use:

```bash
rabbitmqctl list_queues                 # si hay colas ajenas a compras.stock, NO desinstalar
```

- Para borrar **solo la cola de SDI** y conservar RabbitMQ:
  ```bash
  rabbitmqctl delete_queue compras.stock
  ```
- Para desinstalar RabbitMQ por completo (borra colas, usuarios y datos del broker):
  ```bash
  apt purge -y rabbitmq-server && apt autoremove -y
  rm -rf /var/lib/rabbitmq /etc/rabbitmq
  ```

### 4.7 Verificación de la desinstalación

```bash
systemctl list-units --all | grep -i sdi        # → sin resultados
ls /opt/sdi 2>&1                                # → No such file or directory
sudo -u postgres psql -lqt | grep sdi           # → sin resultados
ss -tlnp | grep 8181                            # → sin resultados
curl -m 3 http://127.0.0.1:8181/health          # → connection refused
id sdi 2>&1                                     # → no such user
```

El repositorio de GitHub (https://github.com/gxbeto/sdi) no se toca: el código fuente
sigue disponible para reinstalar la prueba de concepto cuando haga falta, repitiendo
la sección 2.

---

*Documento generado como parte de la prueba de concepto SDI — módulo Stock,
cátedra Programación de Aplicaciones en Red.*
