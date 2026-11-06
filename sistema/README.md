# Sistema Integral de Gestión para Pollería — BRASÉ

Paneles de dueño, caja y cocina: autenticación, usuarios, roles y permisos
(RBAC), productos, categorías, configuración, auditoría, dashboard,
apertura/cierre de caja, POS para llevar y salón, mesas, pagos, pedidos, envío a
cocina e historial.

**Stack:** Python 3.11+ / Django 5, HTML, CSS y JavaScript. La base de datos es
MySQL/MariaDB (Alwaysdata) mediante **PyMySQL**; SQLite queda como alternativa
local sin conexión. Los archivos estáticos se sirven con **WhiteNoise**. La
aplicación web está preparada para desplegarse en **Render** con Gunicorn.

> El código vive en la carpeta `sistema/` del repositorio. Entra ahí antes de
> ejecutar los comandos: `cd sistema`.

## Puesta en marcha local

La base se define en `.env` (MySQL de Alwaysdata por defecto, o SQLite si pones
`DB_ENGINE=sqlite`).

```powershell
cd sistema
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py inicializar
.\.venv\Scripts\python.exe manage.py runserver
```

Abre http://127.0.0.1:8000 e inicia sesión con la cuenta del dueño.

El dueño local de prueba es `dueno` / `Polleria-Local-2026!`. **Cambia esa
contraseña antes de usar el sistema en producción.**

La migración `ventas.0002_datos_iniciales` crea la **Caja principal** y los
métodos de pago iniciales (Efectivo, Tarjeta, Transferencia y Yape/Plin). La
migración `ventas.0004_mesas_iniciales` crea las mesas 1 a 6.

Paneles disponibles:

- `/panel/` — dueño/administrador.
- `/caja/` — cajero y supervisión.
- `/cocina/` — jefe de cocina y cocinero.
- `/mesero/` — mesero.
- `/pedido/` — pedido por internet del cliente (fase posterior).

## Base de datos en Alwaysdata (MySQL/MariaDB)

El proyecto ya está preparado para Alwaysdata. Los datos de conexión van en
`.env` (ignorado por Git); la plantilla pública `.env.example` usa marcadores de
posición.

Pasos resumidos:

```powershell
# 1. Completa en .env DB_USER, DB_PASSWORD y SECRET_KEY
# 2. Instala dependencias
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Comprueba la conexión
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --check

# 4. Crea el esquema en MySQL
.\.venv\Scripts\python.exe manage.py migrate

# 5. Copia los datos de SQLite (conserva IDs y relaciones)
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --yes
.\.venv\Scripts\python.exe manage.py inicializar
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

La guía completa, incluido el despliegue WSGI en Alwaysdata, está en
[docs/ALWAYSDATA.md](docs/ALWAYSDATA.md).

## Despliegue web en Render

La app se despliega como **Web Service monolítico** dentro de un **Project** de
Render y usa la base MySQL de Alwaysdata. Se configura desde el dashboard, sin
Blueprint:

- `build.sh` instala dependencias y ejecuta `collectstatic`.
- `gunicorn` arranca `config.wsgi:application`.
- `RENDER_EXTERNAL_HOSTNAME` se agrega automáticamente a `ALLOWED_HOSTS` y
  `CSRF_TRUSTED_ORIGINS`.
- Las imágenes de `media/` se sirven por URL en `/media/...`.

Guía completa: [docs/RENDER.md](docs/RENDER.md).

## Pruebas

Las pruebas usan SQLite para no crear una base de prueba en Alwaysdata:

```powershell
$env:DB_ENGINE="sqlite"
.\.venv\Scripts\python.exe manage.py test
```

La suite completa incluye validaciones, RBAC, caja, ventas, cocina, mesas y
pedidos de salón. Total: **162 pruebas**.

GitHub Actions ejecuta las pruebas con SQLite en cada push o pull request
(`.github/workflows/tests.yml`), sin necesidad de una base MySQL.

## Documentación

- [Sprint 1](docs/SPRINT_1.md): panel administrativo, seguridad, usuarios, roles, productos y auditoría.
- [Sprint 2](docs/SPRINT_2.md): caja, turnos, POS, pagos, pedidos, historial, cierre y dashboard de ventas.
- [Fase 2](docs/FASE_2.md): mesas, pedidos de salón, envío a cocina y panel `/cocina/`.
- [Estado del sistema](docs/ESTADO_SISTEMA.md): estado actual, paneles, datos locales, verificación y siguiente fase.
- [Alwaysdata](docs/ALWAYSDATA.md): base de datos, migración y despliegue.
- [Render](docs/RENDER.md): Web Service, variables de entorno, IPs y medios.
- [GitHub](docs/GITHUB.md): repositorio público, primer commit y verificación de secretos.

## Producción (resumen)

- `DEBUG=0`, `SECRET_KEY` propia y `ALLOWED_HOSTS` con el dominio real.
- `CSRF_TRUSTED_ORIGINS=https://tu-dominio` y HTTPS con Let's Encrypt/Render.
- `USAR_PROXY_SSL=1` detrás del proxy de Render o Alwaysdata.
- `python manage.py collectstatic --noinput` para WhiteNoise (Render lo hace en `build.sh`).
- `gunicorn config.wsgi:application` como servidor WSGI en Render.
- `python manage.py migrate --noinput` e `inicializar` al arrancar.
- Las imágenes de productos y el logo viven en `media/` (versionado) y se sirven por URL en `/media/...`.
- Para asignar fotos por nombre, déjalas en `imagenes/` y ejecuta `manage.py cargar_imagenes_productos`.
- Si prefieres no versionarlas, usa un disco persistente de Render (`MEDIA_ROOT=/var/data/media`) o almacenamiento externo.
- Copias de seguridad de la base y de `media/`.
- Nunca subir `.env`, `db.sqlite3` ni `backups/`.
