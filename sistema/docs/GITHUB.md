# Publicar el proyecto en GitHub

El repositorio será público. Antes de subirlo, comprueba que no haya secretos ni
datos reales.

> Estructura del repositorio:
> - Raíz del repo (donde vive `.git`):
>   `D:\polleria sistema\sistema\PANEL ADMINISTRATIVO DEL DUEÑO`
> - Código del proyecto: `...\PANEL ADMINISTRATIVO DEL DUEÑO\sistema`
>
> Los comandos de **Git** (`git add`, `git commit`, `git push`) se ejecutan en la
> raíz del repo. Los comandos de **Django** (`manage.py`, `pip`, tests) se
> ejecutan dentro de `sistema`. En Render, configura **Root Directory = `sistema`**.

## 1. Archivos que NO deben subirse

Estos ya están en `.gitignore`:

- `.env` (contraseñas y `SECRET_KEY`);
- `db.sqlite3` y `backups/`;
- `staticfiles/` (se genera con `collectstatic`);
- `.venv/`, `__pycache__/`, `*.pyc`.

Sí se versiona:

- `media/` (imágenes de productos y logo). Viajan con el repositorio y se
  sirven por URL en `/media/...`.

Comprueba antes del primer commit:

```powershell
git status --short
git check-ignore -v .env db.sqlite3 backups
```

Si `git status` muestra `.env`, `db.sqlite3` o `backups/`, no hagas commit: revisa
`.gitignore`. En cambio, las imágenes de `media/` sí deben aparecer.

## 2. Inicializar Git y primer commit

```powershell
git init
git add .
git status
git commit -m "Sistema de pollería BRASÉ con Django, MySQL y despliegue en Render"
git branch -M main
```

Revisa `git status` antes del commit. Debe aparecer el código, las plantillas,
los tests, `requirements.txt`, `.env.example` y la
documentación; **no** los archivos ignorados.

## 3. Crear el repositorio público y subir

En GitHub:

1. **New repository**.
2. Nombre, por ejemplo `brase-polleria`.
3. Visibilidad: **Public**.
4. No marques “Add a README”, `.gitignore` ni licencia (ya existen en local).

Luego:

```powershell
git remote add origin https://github.com/TU_USUARIO/brase-polleria.git
git push -u origin main
```

## 4. Verificación posterior

- Abre el repositorio en el navegador.
- Confirma que no aparecen `.env`, `db.sqlite3` ni `backups/`.
- Confirma que las imágenes de `media/` sí están en el repositorio.
- Revisa que `README.md` y `docs/ALWAYSDATA.md` se vean bien.
- En **Actions** debe ejecutarse el workflow de pruebas (SQLite, sin MySQL).

## 5. Si subiste un secreto por error

1. Cambia inmediatamente la contraseña de la base y genera una nueva
   `SECRET_KEY`.
2. Elimina el archivo del historial con `git filter-repo` o BFG.
3. Fuerza el push y avisa a cualquier colaborador.
4. No basta con borrar el archivo en un commit nuevo: el historial conserva el
   contenido.

## 6. Licencia

El repositorio es público, pero una licencia es una decisión legal del autor.
Si quieres permitir reutilización, añade `LICENSE` (MIT, Apache-2.0, etc.). Si
no, el código queda “todos los derechos reservados” por defecto.

## 7. Despliegue

Render puede construir y desplegar directamente desde este repositorio. Crea el
proyecto y el Web Service en el dashboard (sin Blueprint); los comandos y
variables están en [RENDER.md](RENDER.md).
