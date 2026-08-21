"""Prueba de conexión SQL (solo lectura) usando credenciales.env de esta carpeta."""
from pathlib import Path
import pyodbc

env_path = Path(__file__).with_name("credenciales.env")
raw = env_path.read_bytes()
if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
    text = raw.decode("utf-16")
else:
    text = raw.decode("utf-8-sig")

cfg = {}
for line in text.splitlines():
    line = line.strip().lstrip("\ufeff")
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    cfg[key.strip().replace("\x00", "")] = value.strip().replace("\x00", "")

usuario = cfg.get("USUARIO", "")
if not usuario:
    raise SystemExit(f"Falta USUARIO en credenciales.env. Claves leidas: {list(cfg.keys())}")
if not cfg.get("CONTRASENA"):
    raise SystemExit("Falta CONTRASENA en credenciales.env")

conn_str = (
    "DRIVER={SQL Server};"
    f"SERVER={cfg['SERVIDOR']};"
    f"DATABASE={cfg['BASE']};"
    f"UID={usuario};"
    f"PWD={cfg['CONTRASENA']};"
)

try:
    conn = pyodbc.connect(conn_str, timeout=15)
    cur = conn.cursor()
    vista = cfg["VISTA"]
    cur.execute(f"SELECT TOP 1 * FROM {vista}")
    cols = [c[0] for c in cur.description]
    row = cur.fetchone()
    conn.close()
    print("CONEXION_OK")
    print(f"VISTA={vista}")
    print(f"COLUMNAS={len(cols)}")
    print(f"HAY_DATOS={'SI' if row else 'NO'}")
except pyodbc.Error as exc:
    print("CONEXION_ERROR")
    msg = str(exc)
    if cfg["CONTRASENA"] in msg:
        msg = msg.replace(cfg["CONTRASENA"], "***")
    print(msg)
