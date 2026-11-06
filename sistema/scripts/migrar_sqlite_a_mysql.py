"""Copia los datos de db.sqlite3 a una base MySQL/MariaDB ya migrada.

Uso típico:

    python scripts/migrar_sqlite_a_mysql.py --check
    python scripts/migrar_sqlite_a_mysql.py --dry-run
    python scripts/migrar_sqlite_a_mysql.py --yes

Antes de ejecutarlo, la base destino debe tener el esquema creado:

    python manage.py migrate

El script:
- conserva los IDs originales;
- copia content types, permisos, roles, usuarios y datos de negocio;
- no copia django_migrations ni django_session;
- vacía las tablas destino antes de insertar (pide confirmación).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_POR_DEFECTO = BASE_DIR / "db.sqlite3"
EXCLUIR = {"django_migrations", "django_session", "django_admin_log", "sqlite_sequence"}


def cargar_env(ruta: Path) -> None:
    """Carga un archivo .env. Las variables del archivo tienen prioridad."""
    if not ruta.exists():
        print(f"Aviso: no existe {ruta}; se usarán las variables del sistema.")
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ[clave.strip()] = valor.strip().strip('"').strip("'")


def q_mysql(nombre: str) -> str:
    return "`" + nombre.replace("`", "``") + "`"


def q_sqlite(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def tablas_sqlite(conn: sqlite3.Connection) -> list[str]:
    filas = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [f[0] for f in filas if f[0] not in EXCLUIR]


def columnas_sqlite(conn: sqlite3.Connection, tabla: str) -> list[str]:
    return [f[1] for f in conn.execute(f"PRAGMA table_info({q_sqlite(tabla)})").fetchall()]


def contar_sqlite(conn: sqlite3.Connection, tabla: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {q_sqlite(tabla)}").fetchone()[0]


def conectar_mysql():
    try:
        import pymysql
    except ImportError:
        print("Falta PyMySQL. Instala con: pip install -r requirements.txt")
        return None

    host = os.environ.get("DB_HOST", "")
    nombre = os.environ.get("DB_NAME", "")
    usuario = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASSWORD", "")
    puerto = int(os.environ.get("DB_PORT") or "3306")

    if not all([host, nombre, usuario]):
        print("Faltan DB_HOST, DB_NAME o DB_USER. Revisa tu archivo .env.")
        return None
    if password in ("", "TU_PASSWORD", "cambia-esta-clave"):
        print("Aviso: DB_PASSWORD parece un marcador de posición. Completa tu contraseña.")

    try:
        return pymysql.connect(
            host=host,
            port=puerto,
            user=usuario,
            password=password,
            database=nombre,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=15,
        )
    except Exception as exc:  # noqa: BLE001 - mensaje amigable para el usuario
        print(f"No se pudo conectar a MySQL ({usuario}@{host}:{puerto}/{nombre}).")
        print(f"Detalle: {exc}")
        print("Revisa el usuario, la contraseña, los permisos del usuario y el acceso remoto.")
        return None


def comprobar_mysql(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT VERSION() AS version, DATABASE() AS base, "
            "@@character_set_database AS charset"
        )
        fila = cur.fetchone()
        cur.execute("SHOW TABLES")
        total = len(cur.fetchall())
    print("Conexión MySQL correcta.")
    print(f"  Servidor: {fila[0]}")
    print(f"  Base:     {fila[1]}")
    print(f"  Charset:  {fila[2]}")
    print(f"  Tablas:   {total}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra datos de SQLite a MySQL.")
    parser.add_argument("--env", type=Path, default=Path(os.environ.get("ENV_FILE", BASE_DIR / ".env")))
    parser.add_argument("--sqlite", type=Path, default=SQLITE_POR_DEFECTO)
    parser.add_argument("--check", action="store_true", help="Solo comprueba la conexión MySQL.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra tablas y filas sin escribir.")
    parser.add_argument("--yes", action="store_true", help="No pide confirmación (peligroso).")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    ruta_env = args.env if args.env.is_absolute() else BASE_DIR / args.env
    cargar_env(ruta_env)

    if args.check:
        mysql_conn = conectar_mysql()
        if mysql_conn is None:
            return 1
        resultado = comprobar_mysql(mysql_conn)
        mysql_conn.close()
        return resultado

    ruta_sqlite = args.sqlite if args.sqlite.is_absolute() else BASE_DIR / args.sqlite
    if not ruta_sqlite.exists():
        print(f"No existe la base SQLite: {ruta_sqlite}")
        return 1

    sqlite_conn = sqlite3.connect(ruta_sqlite)
    tablas = tablas_sqlite(sqlite_conn)
    if not tablas:
        print("No se encontraron tablas de datos en SQLite.")
        return 1

    print(f"Origen: {ruta_sqlite}")
    print(f"Destino: {os.environ.get('DB_USER', '?')}@{os.environ.get('DB_HOST', '?')}"
          f":{os.environ.get('DB_PORT', '3306')}/{os.environ.get('DB_NAME', '?')}")
    print(f"Tablas a copiar: {len(tablas)}")

    if args.dry_run:
        total = 0
        for tabla in tablas:
            n = contar_sqlite(sqlite_conn, tabla)
            total += n
            print(f"  {tabla:<40} {n:>8} filas")
        print(f"  {'TOTAL':<40} {total:>8} filas")
        return 0

    mysql_conn = conectar_mysql()
    if mysql_conn is None:
        return 1

    with mysql_conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        destino = {fila[0] for fila in cur.fetchall()}

    faltantes = [t for t in tablas if t not in destino]
    if faltantes:
        print("Faltan tablas en MySQL. Ejecuta primero:")
        print("  python manage.py migrate")
        for t in faltantes:
            print(f"  - {t}")
        return 1

    # Verifica que las columnas coincidan antes de borrar nada.
    with mysql_conn.cursor() as cur:
        for tabla in tablas:
            cur.execute(f"SHOW COLUMNS FROM {q_mysql(tabla)}")
            cols_mysql = {fila[0] for fila in cur.fetchall()}
            cols_sqlite = columnas_sqlite(sqlite_conn, tabla)
            faltan = [c for c in cols_sqlite if c not in cols_mysql]
            if faltan:
                print(f"La tabla {tabla} no coincide: faltan columnas {faltan}")
                return 1

    if not args.yes:
        destino_nombre = os.environ.get("DB_NAME", "")
        print("\nATENCIÓN: se borrarán los datos actuales de la base destino.")
        print(f"Escribe {destino_nombre} para continuar:")
        if input("> ").strip() != destino_nombre:
            print("Cancelado.")
            return 1

    total = 0
    try:
        with mysql_conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for tabla in tablas:
                cur.execute(f"DELETE FROM {q_mysql(tabla)}")
            # Evita sesiones antiguas que apunten a usuarios recopiados.
            for extra in ("django_session", "django_admin_log"):
                if extra in destino:
                    cur.execute(f"DELETE FROM {q_mysql(extra)}")

            for tabla in tablas:
                cols = columnas_sqlite(sqlite_conn, tabla)
                cols_sql = ", ".join(q_mysql(c) for c in cols)
                marcadores = ", ".join(["%s"] * len(cols))
                insert = f"INSERT INTO {q_mysql(tabla)} ({cols_sql}) VALUES ({marcadores})"
                filas = sqlite_conn.execute(f"SELECT * FROM {q_sqlite(tabla)}")
                n_tabla = 0
                while True:
                    lote = filas.fetchmany(args.batch_size)
                    if not lote:
                        break
                    lote = [
                        tuple(bytes(v) if isinstance(v, memoryview) else v for v in fila)
                        for fila in lote
                    ]
                    cur.executemany(insert, lote)
                    n_tabla += len(lote)
                total += n_tabla
                print(f"  {tabla:<40} {n_tabla:>8} filas")

            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        mysql_conn.commit()
    except Exception as exc:  # noqa: BLE001 - se informa y se intenta restaurar
        mysql_conn.rollback()
        try:
            with mysql_conn.cursor() as cur:
                cur.execute("SET FOREIGN_KEY_CHECKS=1")
        except Exception:
            pass
        mysql_conn.close()
        print(f"\nError durante la migración: {exc}")
        print("No se completó la copia. Revisa el error y vuelve a intentarlo.")
        return 1

    mysql_conn.close()
    print(f"\nMigración completada: {total:,} filas copiadas.")
    print("Siguiente paso: ejecuta `python manage.py inicializar`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
