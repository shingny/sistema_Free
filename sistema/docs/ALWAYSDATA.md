# Despliegue en Alwaysdata (Django + MySQL/MariaDB)

Esta guía deja el sistema funcionando con la base de datos de Alwaysdata y,
opcionalmente, con la aplicación alojada allí.

> Si la aplicación se despliega en Render, usa [RENDER.md](RENDER.md) para el
> Web Service. Esta guía sigue siendo válida para crear/migrar la base y para
> el hosting opcional en Alwaysdata.

## Datos de la base

> En este proyecto, los valores reales de host y base ya están en
> `.env` (ignorado por Git). Esta guía usa `TU_CUENTA` como
> marcador para poder publicarse sin exponer la cuenta.

| Dato | Valor |
| --- | --- |
| Host | `mysql-TU_CUENTA.alwaysdata.net` |
| Base | `TU_CUENTA_TU_BASE` |
| Usuario | lo completas en `.env` |
| Contraseña | la completas en `.env` |
| Puerto | `3306` |

El usuario y la contraseña **no** se guardan en el repositorio. Van en
`.env` (ignorado por Git).

## 1. Preparar el entorno local

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Abre `.env` (ya existe con el host y la base reales) y completa:

```dotenv
DB_USER=tu_usuario
DB_PASSWORD=tu_contraseña
SECRET_KEY=una_clave_larga_y_aleatoria
```

> Si prefieres empezar de cero, usa `.env.example` como plantilla.

Si vas a conectarte desde tu casa u oficina, activa el **acceso remoto** de la
base en el panel de Alwaysdata y autoriza tu IP:

1. Alwaysdata → **Bases de datos** → **MySQL/MariaDB**.
2. Abre `TU_CUENTA_TU_BASE`.
3. Activa **Acceso remoto** y añade tu IP pública.

Sin ese paso, la conexión desde tu equipo dará `Can't connect to MySQL server`.

## 2. Comprobar la conexión

```powershell
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --check
```

Debe mostrar el servidor, la base, el charset `utf8mb4` y el número de tablas.

> Para levantar `runserver` en tu PC, `.env` ya trae `DEBUG=1` y
> `SECURE_SSL_REDIRECT=0`, así que la app funciona contra la base en la nube.
> Si prefieres un entorno local sin conexión, pon `DB_ENGINE=sqlite` en `.env`.

## 3. Actualizar y respaldar SQLite

Antes de exportar, asegúrate de que la base local tenga el esquema actual:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe scripts\backup_sqlite.py
```

El respaldo queda en `backups/` (ignorado por Git).

## 4. Crear el esquema en MySQL

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

`config/settings.py` lee `.env` por defecto (o el archivo indicado en
`ENV_FILE`, si lo defines).

## 5. Copiar los datos

Primero simula la copia:

```powershell
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --dry-run
```

Luego ejecuta la copia real:

```powershell
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --yes
```

El script:

- conserva los IDs originales;
- copia usuarios, roles, permisos, productos, ventas, caja, mesas y auditoría;
- copia `django_content_type` y `auth_permission` para que las relaciones sigan
  siendo válidas;
- **no** copia `django_migrations` ni `django_session`;
- vacía las tablas destino antes de insertar.

Después completa permisos/roles por si faltara algo:

```powershell
.\.venv\Scripts\python.exe manage.py inicializar
```

### Si no puedes activar el acceso remoto

Requiere haber subido el proyecto y creado el entorno virtual (paso 7).
Sube `db.sqlite3` por SFTP a `/home/TU_CUENTA/www/brase/db.sqlite3`, entra por
SSH y ejecuta el script **desde el servidor**:

```bash
cd /home/TU_CUENTA/www/brase
source .venv/bin/activate
python scripts/migrar_sqlite_a_mysql.py --sqlite db.sqlite3 --env .env --yes
rm db.sqlite3
```

Desde el propio Alwaysdata la conexión a MySQL es local y no depende del acceso
remoto. Borra `db.sqlite3` del servidor al terminar.

### Imágenes de productos

El proyecto versiona la carpeta `media/` (imágenes de productos y logo), así que
al clonar el repositorio las imágenes llegan con el código. Si despliegas el
código sin esa carpeta, cópiala por SFTP/rsync al `media/` del servidor.

El script de datos copia las rutas de las imágenes en la base, pero no los
archivos. Si la aplicación sigue ejecutándose en tu PC y solo la base está en
Alwaysdata, no necesitas copiar la carpeta.

## 6. Archivos estáticos

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

WhiteNoise sirve `/static/` desde `staticfiles/`. Las imágenes de productos
(`/media/`) se atienden con la ruta de producción de Django incluida en
`config/urls.py`. Para una pollería pequeña es suficiente; si el tráfico crece,
mueve `media/` a un sitio de archivos estáticos de Alwaysdata.

## 7. Publicar la aplicación en Alwaysdata (opcional)

1. Sube el proyecto por SFTP/SSH o clónalo con Git en, por ejemplo:
   `/home/TU_CUENTA/www/brase`.
2. Crea el entorno virtual e instala dependencias:

   ```bash
   cd /home/TU_CUENTA/www/brase
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Crea `.env` en el servidor con los datos de producción. Puedes copiar
   `.env.example` y completar `DB_USER`, `DB_PASSWORD` y
   `SECRET_KEY`.
4. Ejecuta las migraciones y `collectstatic`:

   ```bash
   python manage.py migrate
   python manage.py inicializar
   python manage.py collectstatic --noinput
   ```

5. En Alwaysdata → **Web > Sites > Añadir un sitio**:
   - Tipo: **Python WSGI**.
   - Dirección: `tu-cuenta.alwaysdata.net` (o tu dominio).
   - Ruta de la aplicación: `/home/TU_CUENTA/www/brase/config/wsgi.py`.
   - Directorio de trabajo: `/home/TU_CUENTA/www/brase`.
   - Entorno virtual: `/home/TU_CUENTA/www/brase/.venv`.
   - Versión de Python: 3.12 o 3.13.
   - Variables de entorno:
     - `DJANGO_SETTINGS_MODULE=config.settings`
     - `ENV_FILE=/home/TU_CUENTA/www/brase/.env`

6. Activa HTTPS con Let's Encrypt en Alwaysdata. En `.env` de producción deja:

   ```dotenv
   DEBUG=0
   SECURE_SSL_REDIRECT=1
   USAR_PROXY_SSL=1
   ALLOWED_HOSTS=tu-cuenta.alwaysdata.net
   CSRF_TRUSTED_ORIGINS=https://tu-cuenta.alwaysdata.net
   ```

7. Los errores del sitio se ven en:
   `/home/TU_CUENTA/admin/logs/uwsgi/[id].log`.

## Problemas frecuentes

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `Can't connect to MySQL server` | Acceso remoto desactivado o IP no autorizada | Actívalo en Alwaysdata y añade tu IP |
| `Access denied for user` | Usuario/contraseña incorrectos | Revisa `DB_USER` y `DB_PASSWORD` |
| `Unknown database` | Nombre de base incorrecto | Usa `TU_CUENTA_TU_BASE` |
| `DisallowedHost` | Dominio no autorizado | Añádelo a `ALLOWED_HOSTS` |
| `CSRF verification failed` | Dominio no confiable | Añade `https://...` a `CSRF_TRUSTED_ORIGINS` |
| Bucle de redirección a HTTPS | Proxy no reconocido | Deja `USAR_PROXY_SSL=1`; si persiste, pon `SECURE_SSL_REDIRECT=0` y fuerza HTTPS desde Alwaysdata |
| `/static/` da 404 | No se ejecutó `collectstatic` | Ejecuta `manage.py collectstatic` |
| Las imágenes no cargan | `media/` no está accesible | Revisa la ruta de media o usa un sitio estático |

## Copias de seguridad

- Alwaysdata realiza copias de la base; aun así, puedes exportar con:

  ```bash
  python manage.py dumpdata --natural-foreign --indent 2 > respaldo.json
  ```

- No subas `db.sqlite3`, `backups/`, `respaldo.json` ni `.env*` al repositorio.
