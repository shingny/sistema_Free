# Carpeta de imágenes de productos

Coloca aquí las fotos de los productos con un nombre que coincida con el
producto (por ejemplo `pollo entero.png`, `chicha morada.png`). Luego ejecuta:

```powershell
.\.venv\Scripts\python.exe manage.py cargar_imagenes_productos
```

El comando copia las fotos a `media/productos/` y las asigna al producto cuyo
nombre coincide. Para que viajen con el despliegue, haz commit de `media/`:

```powershell
git add media
git commit -m "Actualizar imágenes de productos"
git push
```

Formatos admitidos: `.png`, `.jpg`, `.jpeg`, `.webp`. Tamaño máximo por imagen:
2 MB.

También puedes subir o cambiar imágenes desde el panel del dueño
(`Catálogo → Productos`); el archivo resultante queda en `media/` y se sirve en
`/media/...`.
