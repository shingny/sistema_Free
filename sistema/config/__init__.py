"""Compatibilidad con MySQL usando PyMySQL.

Django importa ``MySQLdb`` para su backend MySQL. PyMySQL expone la misma
interfaz, así que lo registramos con ese nombre. Si el proyecto corre con
SQLite y PyMySQL no está instalado, Django sigue funcionando.
"""
try:
    import pymysql
except ImportError:  # pragma: no cover - solo aplica si falta la dependencia
    pymysql = None
else:
    pymysql.install_as_MySQLdb()
