"""Crea una copia de seguridad de db.sqlite3 antes de migrar a MySQL."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ORIGEN = BASE_DIR / "db.sqlite3"
DESTINO_DIR = BASE_DIR / "backups"


def main() -> int:
    if not ORIGEN.exists():
        print(f"No existe la base SQLite: {ORIGEN}")
        return 1

    DESTINO_DIR.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = DESTINO_DIR / f"db_{marca}.sqlite3"
    shutil.copy2(ORIGEN, destino)
    print(f"Respaldo creado: {destino}")
    print(f"Tamaño: {destino.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
