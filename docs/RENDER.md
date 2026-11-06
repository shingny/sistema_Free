# Despliegue en Render (Web Service) + MySQL en Alwaysdata

Arquitectura:

- **Aplicación:** Render Web Service (Python + Gunicorn).
- **Base de datos:** MySQL/MariaDB de Alwaysdata.
- **Estáticos:** WhiteNoise (`collectstatic` en el build).
- **Media:** imágenes versionadas en `media/` y servidas por URL en `/media/...`.

Archivos ya preparados:

- `build.sh`: instala dependencias y ejecuta `collectstatic`.
- `.python-version`: fija Python 3.12.6 (Django 5.2 no soporta 3.14).
- `config/settings.py`: agrega automáticamente `RENDER_EXTERNAL_HOSTNAME` a
  `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.
- `config/urls.py`: sirve `/media/` en producción (para una pollería pequeña).

## 1. Subir el proyecto a GitHub

Sigue [GITHUB.md](GITHUB.md). El repositorio puede ser público; no subas
`.env`, `.env.alwaysdata`, `db.sqlite3` ni `backups/`. Las imágenes de `media/`
**sí** se versionan.

## 2. Crear el Project y el Web Service en Render

Todo se hace desde el dashboard, **sin Blueprint**.

1. Render Dashboard → **New** → **Project**.
   - Project name: `brase-polleria`.
   - Environment name: `production`.
2. Dentro del proyecto `brase-polleria` / `production` → **New** → **Web Service**.
3. Conecta el repositorio y completa:
   - **Name:** `brase-polleria` (único en tu workspace).
   - **Language / Runtime:** **Python 3**.
   - **Region:** **Frankfurt** (la más cercana a Alwaysdata).
   - **Branch:** `main`.
   - **Instance Type:** **Free** (o **Starter** si no quieres cold starts).
4. **Build Command:**

   ```bash
   bash build.sh
   ```

5. **Start Command:**

   ```bash
   python manage.py migrate --noinput && python manage.py inicializar && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120
   ```

6. **Health Check Path:** `/ingresar/`.
7. En **Environment** agrega las variables de la sección 3.
8. **Create Web Service**.

> Si ya tienes un Web Service creado, muévelo con **••• → Move →
> brase-polleria / production**.
>
> El plan **Free** (0.1 CPU / 512 MB) alcanza para el monolito. Se duerme tras
> ~15 min sin tráfico y el primer acceso tarda ~1 min. Un workspace Hobby admite
> hasta 2 entornos por proyecto (por si luego quieres `staging`).

## 3. Variables de entorno en Render

| Variable | Valor |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings` |
| `DEBUG` | `0` |
| `SECRET_KEY` | generada por Render o una propia de 50+ caracteres |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` (Render agrega su hostname solo) |
| `DB_ENGINE` | `mysql` |
| `DB_HOST` | `mysql-TU_CUENTA.alwaysdata.net` |
| `DB_NAME` | `TU_CUENTA_TU_BASE` |
| `DB_USER` | tu usuario de Alwaysdata |
| `DB_PASSWORD` | tu contraseña de Alwaysdata |
| `DB_PORT` | `3306` |
| `DB_CONN_MAX_AGE` | `60` |
| `USAR_PROXY_SSL` | `1` |
| `USAR_X_FORWARDED_HOST` | `1` |
| `USAR_X_FORWARDED_FOR` | `1` |

`RENDER_EXTERNAL_HOSTNAME` lo define Render automáticamente; no lo agregues a
mano. El proyecto lo usa para `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.

## 4. Permitir la conexión desde Render a Alwaysdata

En Alwaysdata, la base debe aceptar conexiones desde Render:

1. Alwaysdata → **Bases de datos** → **MySQL/MariaDB** → tu base. Si el
   **acceso remoto** está desactivado, actívalo.
2. Render Dashboard → tu servicio → **Connect** → pestaña **Outbound**.
3. Copia los rangos IPv4 de salida de la región del servicio.
4. Alwaysdata → **Bases de datos** → **MySQL/MariaDB** → tu usuario.
5. Si tienes una **restricción por IP**, agrega los rangos de Render. Alwaysdata
   solo admite IPv4 y máscaras de red; si solo permite una IP, usa las
   **IPs de salida dedicadas** de Render (plan de pago) y autoriza esa IP.
6. Si no tienes restricción por IP, no hace falta cambiar nada.

> Alwaysdata permite hasta 40 conexiones simultáneas por usuario en Public
> Cloud. Un Web Service de Render con pocos workers está muy por debajo.

## 5. Migrar los datos

La base de Alwaysdata debe tener el esquema y los datos antes de usar la app.

Desde tu PC (con acceso remoto habilitado), sigue
[ALWAYSDATA.md](ALWAYSDATA.md), pasos 1 a 5:

```powershell
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --env .env.alwaysdata --check
.\.venv\Scripts\python.exe scripts\backup_sqlite.py
$env:ENV_FILE=".env.alwaysdata"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe scripts\migrar_sqlite_a_mysql.py --env .env.alwaysdata --yes
.\.venv\Scripts\python.exe manage.py inicializar
```

Si no puedes habilitar el acceso remoto, sube `db.sqlite3` por SFTP a
Alwaysdata, ejecuta el script desde su SSH y bórralo al terminar (ver la sección
“Si no puedes activar el acceso remoto” en ALWAYSDATA.md).

El `startCommand` de Render vuelve a ejecutar `migrate` e `inicializar` en cada
arranque; son idempotentes y no borran datos.

> Las imágenes ya viajan en `media/` (versionado), así que no dependen de la
> copia de la base.

> Haz la copia de datos **antes de abrir la app a los usuarios**: el script
> reemplaza el contenido de las tablas destino.

## 6. Medios (imágenes de productos)

Plan elegido: las imágenes de productos y el logo viven en la carpeta `media/`
del repositorio. Viajan con el código y se sirven por URL en `/media/...`, sin
depender de un disco persistente de Render.

- `media/` ya **no** está en `.gitignore`: haz `git add media` y commit.
- En cada deploy, Render recibe `media/` con el resto del código y Django sirve
  `/media/<path>` (ver `config/urls.py`).
- Para cambiar una imagen: reemplaza el archivo en `media/` (o usa el panel del
  dueño y copia el archivo generado), haz commit y push. Render redepliega.
- Las imágenes que se suban **en caliente** desde el panel en Render se guardan
  en el contenedor y se pierden en el siguiente deploy. Si quieres conservarlas,
  descárgalas y agrégalas al repositorio, o pasa a una de las opciones de abajo.

### Cómo agregar imágenes nuevas

Opción 1, desde el panel del dueño (`Catálogo → Productos`): sube la imagen,
copia el archivo creado en `media/productos/` a tu repo local, `git add media` y
`git push`.

Opción 2, por carpeta: deja las fotos en la carpeta `imagenes/` del repositorio
(nombre = nombre del producto) y ejecuta:

```powershell
.\.venv\Scripts\python.exe manage.py cargar_imagenes_productos
git add media
git commit -m "Actualizar imágenes de productos"
git push
```

Opcional, si más adelante quieres subida persistente:

1. **Render Disk (de pago):** añade un disco con mount path `/var/data`, define
   `MEDIA_ROOT=/var/data/media` y antepone `mkdir -p /var/data/media` al
   `startCommand`. Sube las imágenes al disco con SCP.
2. **Almacenamiento externo (S3, Cloudinary, etc.):** requiere integrar
   `django-storages` o el SDK correspondiente.

## 7. Dominio propio

1. Render → tu servicio → **Settings** → **Custom Domains** → añade el dominio.
2. En Render, agrega las variables **antes** de verificar el dominio:
   - `ALLOWED_HOSTS=localhost,127.0.0.1,tu-dominio.com,www.tu-dominio.com`
   - `CSRF_TRUSTED_ORIGINS=https://tu-dominio.com,https://www.tu-dominio.com`
3. Render emite el certificado TLS automáticamente.
4. `SECURE_SSL_REDIRECT=1` (por defecto con `DEBUG=0`) redirige a HTTPS.

> Render usa uno de los dominios verificados como `Host` en sus health checks.
> Si el dominio no está en `ALLOWED_HOSTS`, el health check puede fallar.

## 8. Problemas frecuentes

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `Can't connect to MySQL server` | Alwaysdata bloquea la IP de Render | Autoriza los rangos Outbound de Render |
| `Access denied for user` | Usuario/contraseña o permisos | Revisa `DB_USER`, `DB_PASSWORD` y permisos del usuario |
| `Unknown database` | Nombre de base incorrecto | Revisa `DB_NAME` |
| `DisallowedHost` | Hostname no autorizado | Revisa `ALLOWED_HOSTS`; Render agrega el suyo |
| `CSRF verification failed` | Origen no confiable | Define `CSRF_TRUSTED_ORIGINS` con `https://...` |
| `502 Bad Gateway` | Gunicorn no arrancó | Revisa los logs de Render y el `startCommand` |
| `/static/` da 404 | `collectstatic` no corrió | Revisa el build (`bash build.sh`) |
| Imágenes desaparecen | Filesystem efímero | Usa Render Disk o almacenamiento externo |
| `MySQL server has gone away` | Conexión inactiva | Deja `DB_CONN_MAX_AGE=60` y `CONN_HEALTH_CHECKS` |

## 9. Flujo de despliegue

1. `git push` a GitHub.
2. En Render: **New → Project** (`brase-polleria` / `production`) y dentro
   **New → Web Service**.
3. Render reconstruye con `bash build.sh`.
4. Render arranca con `migrate` + `inicializar` + `gunicorn`.
5. El health check consulta `/ingresar/`.
6. La app queda disponible en `https://TU-SERVICIO.onrender.com`.

No necesitas ejecutar `collectstatic` a mano en Render: lo hace el build.
