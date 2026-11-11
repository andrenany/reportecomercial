# -*- coding: utf-8 -*-
"""
Consulta solo lectura a dbo.vw_FVivaldiWebSalud → consulta_facturacion.html

- Filtros (año, mes, programa, empresa, estado)
- Gráficos por año / programa / empresa
- Hoja calendario veterinarios (día de muestreo → empresas y programas)

fac_vtatotal está en UF; fac_uf = UF del día → venta_clp = UF × valor UF.
Usa credenciales.env. No modifica la base.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pyodbc

from chart_tools import CSS_CHART_TOOLS, JS_CHART_TOOLS

BASE_DIR = Path(__file__).resolve().parent
OUT_HTML = BASE_DIR / "consulta_facturacion.html"
VISTA = "dbo.vw_FVivaldiWebSalud"
VISTA_PLANILLA = "dbo.vw_atv_planilla_detalles"
EXPR_CLP = "(CAST(fac_vtatotal AS FLOAT) * CAST(ISNULL(fac_uf, 0) AS FLOAT))"


def cargar_credenciales() -> dict:
    env_path = BASE_DIR / "credenciales.env"
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
    faltantes = [k for k in ("SERVIDOR", "BASE", "USUARIO", "CONTRASENA") if not cfg.get(k)]
    if faltantes:
        raise SystemExit(f"Faltan en credenciales.env: {', '.join(faltantes)}")
    cfg["VISTA"] = cfg.get("VISTA") or VISTA
    return cfg


def conectar(cfg: dict):
    conn = pyodbc.connect(
        "DRIVER={SQL Server};"
        f"SERVER={cfg['SERVIDOR']};"
        f"DATABASE={cfg['BASE']};"
        f"UID={cfg['USUARIO']};"
        f"PWD={cfg['CONTRASENA']};",
        timeout=30,
    )
    conn.timeout = 300
    return conn


def serializar(valor):
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, str):
        return valor.strip()
    return valor


def consultar(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [{c: serializar(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def analizar(cur, vista: str) -> dict:
    if vista.lower() not in {VISTA.lower(), "dbo.vw_fvivaldiwebsalud"}:
        raise ValueError(f"Vista no permitida: {vista}")

    print("  · serie filtrable (año×mes×programa×empresa×estado)...")
    serie = consultar(
        cur,
        f"""
        SELECT
            YEAR(TRY_CONVERT(date, fecha_recepcion, 103)) AS anio,
            MONTH(TRY_CONVERT(date, fecha_recepcion, 103)) AS mes,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)') AS programa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(estado)), ''), '(sin estado)') AS estado,
            COUNT(*) AS n,
            SUM(CAST(fac_vtatotal AS FLOAT)) AS venta_uf,
            SUM({EXPR_CLP}) AS venta_clp
        FROM {vista}
        WHERE TRY_CONVERT(date, fecha_recepcion, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_recepcion, 103) >= '2020-01-01'
        GROUP BY
            YEAR(TRY_CONVERT(date, fecha_recepcion, 103)),
            MONTH(TRY_CONVERT(date, fecha_recepcion, 103)),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(estado)), ''), '(sin estado)')
        """,
    )

    print("  · calendario muestreo (vet x dia x sede x empresa x programa x centro)...")
    calendario = consultar(
        cur,
        f"""
        SELECT
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23) AS dia,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)') AS veterinario,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)') AS sede,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)') AS programa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)') AS centro,
            COUNT(*) AS n,
            SUM({EXPR_CLP}) AS venta_clp,
            SUM(CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(nombre_seccion,'')))) = 'COSTO OPERATIVO'
                     THEN CAST(fac_vtatotal AS FLOAT) ELSE 0 END) AS costo_operativo_uf,
            SUM(CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(nombre_seccion,'')))) = 'COSTO OPERATIVO'
                     THEN {EXPR_CLP} ELSE 0 END) AS costo_operativo_clp
        FROM {vista}
        WHERE TRY_CONVERT(date, fecha_muestreo, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_muestreo, 103) >= '2024-01-01'
        GROUP BY
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)')
        """,
    )

    print("  · índice de casos (caso → día de muestreo)...")
    casos = consultar(
        cur,
        f"""
        SELECT
            LTRIM(RTRIM(caso_adlab)) AS caso,
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23) AS dia,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)') AS veterinario,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)') AS sede,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)') AS programa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)') AS centro,
            COUNT(*) AS n,
            SUM({EXPR_CLP}) AS venta_clp,
            SUM(CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(nombre_seccion,'')))) = 'COSTO OPERATIVO'
                     THEN {EXPR_CLP} ELSE 0 END) AS costo_operativo_clp
        FROM {vista}
        WHERE TRY_CONVERT(date, fecha_muestreo, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_muestreo, 103) >= '2024-01-01'
          AND NULLIF(LTRIM(RTRIM(caso_adlab)), '') IS NOT NULL
        GROUP BY
            LTRIM(RTRIM(caso_adlab)),
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)')
        """,
    )

    print("  · casos → pre-factura y factura...")
    facturas = consultar(
        cur,
        f"""
        SELECT
            caso,
            prefactura,
            factura,
            estado,
            fecha,
            empresa
        FROM (
            SELECT
                LTRIM(RTRIM(caso_adlab)) AS caso,
                NULLIF(CASE
                    WHEN LTRIM(RTRIM(CAST(fac_id_facturacion AS varchar(40)))) IN ('0', '9999999998') THEN ''
                    ELSE LTRIM(RTRIM(CAST(fac_id_facturacion AS varchar(40))))
                END, '') AS prefactura,
                NULLIF(LTRIM(RTRIM(CAST(factura AS varchar(40)))), '') AS factura,
                ISNULL(NULLIF(LTRIM(RTRIM(estado)), ''), '(sin estado)') AS estado,
                CONVERT(char(10), COALESCE(
                    TRY_CONVERT(date, fac_fecha_facturacion),
                    TRY_CONVERT(date, fac_fecha_facturacion, 103)
                ), 23) AS fecha,
                ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '') AS empresa
            FROM {vista}
            WHERE NULLIF(LTRIM(RTRIM(caso_adlab)), '') IS NOT NULL
        ) t
        GROUP BY caso, prefactura, factura, estado, fecha, empresa
        """,
    )

    print("  · costos planilla (co_km y otros co)...")
    costos = consultar(
        cur,
        f"""
        SELECT
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23) AS dia,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)') AS veterinario,
            ISNULL(NULLIF(LTRIM(RTRIM(empresa_servicio)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(centro)), ''), '(sin centro)') AS centro,
            SUM(CAST(ISNULL(co_km, 0) AS float)) AS co_km,
            SUM(
                CAST(ISNULL(co_extra, 0) AS float)
                + CAST(ISNULL(co_veterinario, 0) AS float)
            ) AS co_uf,
            SUM(
                CAST(ISNULL(co_peaje, 0) AS float)
                + CAST(ISNULL(co_transbordador, 0) AS float)
                + CAST(ISNULL(co_taxi, 0) AS float)
                + CAST(ISNULL(co_pasaje, 0) AS float)
                + CAST(ISNULL(co_colacion, 0) AS float)
                + CAST(ISNULL(co_alojamiento, 0) AS float)
            ) AS co_otros
        FROM {VISTA_PLANILLA}
        WHERE TRY_CONVERT(date, fecha_muestreo, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_muestreo, 103) >= '2024-01-01'
        GROUP BY
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)'),
            ISNULL(NULLIF(LTRIM(RTRIM(empresa_servicio)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(centro)), ''), '(sin centro)')
        """,
    )

    print("  · KPIs globales...")
    kpis = consultar(
        cur,
        f"""
        SELECT
            COUNT(*) AS registros,
            COUNT(DISTINCT caso_adlab) AS casos,
            SUM(CASE WHEN LTRIM(RTRIM(ISNULL(estado,''))) = 'FACTURADO' THEN 1 ELSE 0 END) AS facturados,
            SUM(CAST(fac_vtatotal AS FLOAT)) AS venta_uf,
            SUM(CASE WHEN LTRIM(RTRIM(ISNULL(estado,''))) = 'FACTURADO'
                     THEN CAST(fac_vtatotal AS FLOAT) ELSE 0 END) AS venta_uf_facturada,
            SUM({EXPR_CLP}) AS venta_clp,
            SUM(CASE WHEN LTRIM(RTRIM(ISNULL(estado,''))) = 'FACTURADO'
                     THEN {EXPR_CLP} ELSE 0 END) AS venta_clp_facturada,
            CONVERT(varchar(10), MIN(TRY_CONVERT(date, fecha_recepcion, 103)), 103) AS fecha_min,
            CONVERT(varchar(10), MAX(TRY_CONVERT(date, fecha_recepcion, 103)), 103) AS fecha_max
        FROM {vista}
        """,
    )[0]

    return {"serie": serie, "calendario": calendario, "casos": casos, "facturas": facturas, "costos": costos, "kpis": kpis}


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADL · Consulta facturación</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<script src="auth.js"></script>
<style>
:root {{
  --adl-navy:#003E6D; --adl-orange:#F37021; --adl-teal:#0A8F9C;
  --adl-navy-soft:#1A5F8A; --adl-sky:#E8F1F7;
  --navy:#003E6D; --orange:#F37021; --teal:#0A8F9C;
  --ink:#0F2A40; --muted:#5B738B; --line:#D7E3EE; --bg:#EEF3F8; --panel:#fff;
  --ok:#2F9E71; --danger:#D64545;
  --shadow:0 12px 36px rgba(0,42,74,.08);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"IBM Plex Sans",system-ui,sans-serif; color:var(--ink);
  min-height:100vh;
  background:
    radial-gradient(900px 420px at -5% -10%, rgba(243,112,33,.16), transparent 55%),
    radial-gradient(800px 380px at 105% 0%, rgba(10,143,156,.14), transparent 50%),
    linear-gradient(180deg,#F7FAFC 0%, var(--bg) 40%, #E8EEF4 100%);
}}
.topnav {{
  display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;
  padding:12px 16px; margin-bottom:14px;
  background:linear-gradient(135deg,#fff 0%, var(--adl-sky) 100%);
  border:1px solid rgba(215,227,238,.9); border-radius:20px;
  box-shadow:var(--shadow);
  backdrop-filter:blur(8px);
}}
.brand-row {{ display:flex; align-items:center; gap:12px; }}
.brand-row img {{ height:54px; width:auto; display:block; }}
.brand-text {{ font-family:Manrope,sans-serif; font-weight:800; font-size:1.08rem; color:var(--navy); line-height:1.15; }}
.brand-text span {{ color:var(--orange); }}
.nav-links {{ display:flex; gap:8px; flex-wrap:wrap; }}
.nav-links a, .nav-links button {{
  text-decoration:none; color:var(--navy); border:1px solid var(--line); background:rgba(255,255,255,.75);
  padding:9px 14px; border-radius:999px; font:inherit; font-size:.85rem; font-weight:700; cursor:pointer;
}}
.nav-links a:hover {{ border-color:var(--orange); color:var(--orange); }}
.nav-links a.active {{
  background:linear-gradient(135deg, var(--navy), var(--adl-navy-soft));
  color:#fff; border-color:transparent;
}}
.chip {{ background:#fff; border:1px solid var(--line); }}
.wrap {{ max-width:none; width:100%; margin:0 auto; padding:18px 28px 56px; box-sizing:border-box; }}
.subhead {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:baseline; margin-bottom:12px; }}
.subhead h2 {{ margin:0; font-size:1.1rem; color:var(--navy); }}
.subhead p {{ margin:0; color:var(--teal); font-size:.85rem; font-weight:600; }}
.meta {{ color:var(--muted); font-size:.78rem; text-align:right; line-height:1.45; }}
.tabs {{ display:flex; gap:8px; margin:16px 0 12px; flex-wrap:wrap; }}
.tabs button {{
  border:1px solid var(--line); background:rgba(255,255,255,.85); color:var(--navy); border-radius:999px;
  padding:9px 16px; font:inherit; font-weight:700; cursor:pointer;
}}
.tabs button.active {{
  background:linear-gradient(135deg, var(--navy), var(--teal));
  color:#fff; border-color:transparent;
}}
.tab-pane {{ display:none; }}
.tab-pane.active {{ display:block; }}
.filters {{
  display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end;
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px;
  margin-bottom:14px; position:relative; z-index:30;
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.filters label.f {{ display:flex; flex-direction:column; gap:5px; font-size:.7rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); min-width:160px; flex:1; }}
.filters .hint-multi {{ width:100%; font-size:.72rem; color:var(--muted); margin:0; text-transform:none; letter-spacing:0; font-weight:400; }}
.kpis {{ display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-bottom:14px; }}
@media (max-width:1100px) {{ .kpis {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }} }}
.kpi {{
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px 16px 14px;
  border-left:4px solid var(--navy);
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.kpi.accent {{ border-left-color:var(--orange); }}
.kpi.ok {{ border-left-color:var(--ok); }}
.kpi .l {{ font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
.kpi .v {{ font-family:Manrope,sans-serif; font-size:1.38rem; font-weight:800; color:var(--navy); margin-top:6px; letter-spacing:-.02em; }}
.kpi .h {{ font-size:.76rem; color:var(--muted); margin-top:4px; }}
.grid {{ display:grid; grid-template-columns:1.35fr 1fr; gap:14px; }}
@media (max-width:980px) {{ .grid {{ grid-template-columns:1fr; }} }}
.panel {{
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px;
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.panel h3 {{ margin:0 0 4px; font-family:Manrope,sans-serif; font-size:1.02rem; color:var(--navy); }}
.panel .desc {{ margin:0 0 10px; color:var(--muted); font-size:.82rem; }}
.chart-wrap {{ position:relative; height:340px; }}
.chart-wrap.tall {{ height:400px; }}
.cal-controls {{ display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; margin-bottom:12px; }}
.cal-controls label {{ display:flex; flex-direction:column; gap:4px; font-size:.75rem; color:var(--muted); }}
.cal-controls select, .cal-controls input {{
  border:1px solid var(--line); border-radius:10px; padding:8px 10px; font:inherit; min-width:160px;
}}
.cal-wrap {{
  width:100%;
  overflow:hidden;
  background:#F7FAFC;
  border:1px solid var(--line);
  border-radius:14px;
  padding:12px;
}}
.cal-dow {{
  display:grid;
  grid-template-columns:repeat(7, minmax(0, 1fr));
  gap:8px;
  margin-bottom:8px;
}}
.cal-dow span {{
  text-align:center; font-size:.72rem; font-weight:600; color:var(--muted);
  text-transform:uppercase; padding:4px 0;
}}
.cal-grid {{
  display:grid;
  grid-template-columns:repeat(7, minmax(0, 1fr));
  gap:8px;
  align-items:stretch;
}}
.cal-day {{
  min-height:100px;
  max-height:140px;
  overflow:hidden;
  background:#fff;
  border:1px solid var(--line);
  border-radius:12px;
  padding:8px;
  font-size:.72rem;
  cursor:default;
}}
.cal-day.empty {{
  visibility:hidden;
  pointer-events:none;
  border:none;
  background:transparent;
  min-height:100px;
}}
.cal-day.clickable {{ cursor:pointer; transition: box-shadow .15s, border-color .15s, transform .12s; }}
.cal-day.clickable:hover {{ border-color:var(--adl-teal); box-shadow:0 4px 14px rgba(10,143,156,.18); transform:translateY(-1px); }}
.cal-day.selected {{ border-color:var(--orange); box-shadow:0 0 0 2px rgba(243,112,33,.25); }}
.cal-day .num {{ font-weight:700; color:var(--navy); margin-bottom:4px; }}
.cal-day .op {{ color:var(--muted); margin-bottom:3px; font-weight:600; }}
.cal-day .tag {{
  display:block; background:#E8F1F7; color:var(--navy); border-radius:6px; padding:2px 5px; margin:2px 0;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}}
.cal-day .tag.prog {{ background:#FFF1E6; color:#9A4A12; }}
.cal-day.has {{ border-color:var(--adl-teal); }}
.cal-day.today {{ outline:2px solid var(--orange); outline-offset:1px; }}
.cal-detail {{
  margin-top:14px; background:#fff; border:1px solid var(--line); border-radius:16px; padding:12px 14px;
}}
.cal-detail.highlight {{
  border-color:var(--orange);
  box-shadow:0 8px 24px rgba(243,112,33,.12);
}}
.cal-detail table {{ width:100%; border-collapse:collapse; font-size:.82rem; }}
.cal-detail th, .cal-detail td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
.cal-detail th {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; white-space:nowrap; }}
.cal-detail td {{ max-width:200px; }}
.cal-detail td.num, .cal-detail th.num {{ max-width:none; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.cal-detail tr.co-falta td {{ background:#FFF4E8; }}
.cal-detail td.co-alerta {{ max-width:none; color:#9A3412; font-weight:800; font-size:.72rem; letter-spacing:.02em; white-space:nowrap; }}
.cal-detail .scroll {{ max-height:360px; overflow:auto; }}
.caso-search {{
  width:100%; background:#F7FAFC; border:1px solid var(--line); border-radius:14px; padding:12px;
}}
.caso-search .lbl {{
  display:block; font-size:.7rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin-bottom:6px;
}}
.caso-search-row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.caso-search-row input {{
  flex:1; min-width:220px; border:1px solid var(--line); border-radius:12px; padding:10px 12px;
  font:inherit; font-weight:500; color:var(--ink); background:#fff;
}}
.caso-search-row button {{
  border:0; border-radius:999px; padding:10px 16px; font:inherit; font-weight:700; cursor:pointer;
  background:var(--navy); color:#fff;
}}
.caso-search-row button.ghost {{ background:#fff; color:var(--navy); border:1px solid var(--line); }}
.caso-hits {{ display:flex; flex-direction:column; gap:6px; max-height:240px; overflow:auto; margin-top:8px; }}
.caso-hits button.hit {{
  text-align:left; background:#fff; color:var(--ink); border:1px solid var(--line);
  border-radius:10px; padding:8px 10px; font:inherit; font-weight:500; cursor:pointer;
}}
.caso-hits button.hit:hover {{ border-color:var(--teal); }}
.caso-hits .msg {{ font-size:.82rem; color:var(--muted); }}
.caso-ficha {{
  display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:0 0 12px;
}}
@media (max-width:800px) {{ .caso-ficha {{ grid-template-columns:1fr 1fr; }} }}
.caso-ficha div {{ background:#F7FAFC; border:1px solid var(--line); border-radius:10px; padding:8px 10px; }}
.caso-ficha .k {{ font-size:.68rem; font-weight:700; text-transform:uppercase; color:var(--muted); }}
.caso-ficha .v {{ font-weight:700; color:var(--navy); margin-top:2px; word-break:break-word; }}
.fac-buscar {{ margin-bottom:10px; padding:10px 12px; }}
.fac-buscar h3 {{ font-size:.92rem; margin-bottom:2px; }}
.fac-buscar .desc {{ font-size:.75rem; margin:0 0 8px; }}
.fac-buscar .caso-search {{ padding:8px 10px; border-radius:10px; }}
.fac-buscar .caso-search .lbl {{ margin-bottom:4px; }}
.fac-buscar .caso-search-row {{ gap:6px; }}
.fac-buscar .caso-search-row input {{ padding:6px 10px; border-radius:8px; font-size:.82rem; min-width:160px; }}
.fac-buscar .caso-search-row button {{ padding:6px 12px; font-size:.78rem; }}
.fac-buscar .caso-hits {{ max-height:150px; margin-top:6px; gap:4px; }}
.fac-buscar .caso-hits button.hit {{ padding:5px 8px; font-size:.78rem; border-radius:8px; }}
.fac-caso-result {{ margin-top:6px; }}
.fac-caso-result table {{ width:100%; border-collapse:collapse; font-size:.78rem; }}
.fac-caso-result th, .fac-caso-result td {{ padding:4px 6px; border-bottom:1px solid var(--line); text-align:left; }}
.fac-caso-result th {{ color:var(--muted); font-size:.68rem; text-transform:uppercase; }}
.cal-detail tr.caso-hit td {{ background:#FFF6EF; }}
.rules-box {{
  background:#fff; border:1px solid var(--line); border-radius:16px; padding:16px 18px; margin-bottom:12px;
}}
.rules-box h3 {{ margin:0 0 8px; color:var(--navy); font-size:1rem; }}
.rules-box h4 {{ margin:14px 0 6px; color:var(--adl-teal); font-size:.9rem; }}
.rules-box ul {{ margin:0; padding-left:1.2rem; color:var(--muted); line-height:1.55; }}
.rules-box li {{ margin:4px 0; }}
.rules-box strong {{ color:var(--ink); }}
.rules-box .warn {{
  margin-top:12px; padding:10px 12px; border-radius:10px;
  background:#FFF1E6; border-left:4px solid var(--orange); color:#7A3E0B; font-size:.86rem;
}}
footer {{ text-align:center; color:var(--muted); font-size:.78rem; padding:16px; }}
{CSS_CHART_TOOLS}
</style>
</head>
<body>
<div class="wrap">
<div class="topnav">
  <div class="brand-row">
    <img src="logo_adl.png" alt="ADL" onerror="this.style.display='none'" />
    <div class="brand-text">Dashboard <span>Facturación</span></div>
  </div>
  <div class="nav-links">
    <a href="dashboard_facturacion.html">Unificado</a>
    <a href="dashboard_facturacion_excel.html">Solo facturación</a>
    <a class="active" href="consulta_facturacion.html">Consulta facturación</a>
    <a href="resumen_cantidad.html">Resumen cantidad</a>
    <a href="reglas.html">Reglas</a>
    <button type="button" class="chip" style="border-radius:999px;padding:9px 14px" onclick="adlLogout()">Salir</button>
  </div>
</div>
  <div class="subhead">
    <div>
      <h2>Consulta facturación</h2>
      <p>Vista SQL · vw_FVivaldiWebSalud · montos = UF × UF del día</p>
    </div>
    <div class="meta" id="meta"></div>
  </div>

  <div class="tabs">
    <button type="button" class="active" data-tab="analisis">Análisis</button>
    <button type="button" data-tab="calendario">Calendario veterinarios</button>
    <button type="button" data-tab="reglas-cal">Reglas calendario</button>
  </div>

  <div id="tab-analisis" class="tab-pane active">
    <div class="panel fac-buscar">
      <h3>Buscar caso</h3>
      <p class="desc">Pre-factura y factura del caso. Si no hay número, se muestra “—”.</p>
      <div class="caso-search">
        <span class="lbl">Caso</span>
        <div class="caso-search-row">
          <input id="fac-caso" type="search" placeholder="Ej. PM-157553, VI-27432 o solo el número" autocomplete="off">
          <button type="button" id="btn-buscar-fac-caso">Buscar</button>
          <button type="button" id="btn-limpiar-fac-caso" class="ghost">Limpiar</button>
        </div>
        <div id="fac-caso-hits" class="caso-hits"></div>
        <div id="fac-caso-result" class="fac-caso-result"></div>
      </div>
    </div>
    <div class="filters" id="filters">
      <p class="hint-multi">Filtros multi-selección. Vacío = todos. Serie desde 2020.</p>
      <label class="f">Año<div class="msel" id="f-anio" data-empty="Todos"></div></label>
      <label class="f">Mes<div class="msel" id="f-mes" data-empty="Todos"></div></label>
      <label class="f">Programa<div class="msel" id="f-programa" data-empty="Todos"></div></label>
      <label class="f">Empresa<div class="msel" id="f-empresa" data-empty="Todas"></div></label>
      <label class="f">Estado<div class="msel" id="f-estado" data-empty="Todos"></div></label>
    </div>
    <div class="kpis" id="kpis"></div>
    <div class="grid">
      <div class="panel">
        <h3>Por año</h3>
        <p class="desc">Venta $ (UF × UF día)</p>
        <div class="chart-wrap"><canvas id="cAnio"></canvas></div>
      </div>
      <div class="panel">
        <h3>Mensual</h3>
        <p class="desc">Evolución del filtro</p>
        <div class="chart-wrap"><canvas id="cMes"></canvas></div>
      </div>
    </div>
    <div class="grid" style="margin-top:12px">
      <div class="panel">
        <h3>Por programa</h3>
        <p class="desc">Top programas del filtro</p>
        <div class="chart-wrap tall"><canvas id="cProg"></canvas></div>
      </div>
      <div class="panel">
        <h3>Por empresa</h3>
        <p class="desc">Top 15 empresas</p>
        <div class="chart-wrap tall"><canvas id="cEmp"></canvas></div>
      </div>
    </div>
    <div class="grid" style="margin-top:12px">
      <div class="panel">
        <h3>Por estado</h3>
        <div class="chart-wrap"><canvas id="cEst"></canvas></div>
      </div>
      <div class="panel">
        <h3>Año × programa</h3>
        <p class="desc">Comparativo apilado</p>
        <div class="chart-wrap"><canvas id="cAnioProg"></canvas></div>
      </div>
    </div>
  </div>

  <div id="tab-calendario" class="tab-pane">
    <div class="panel" style="margin-bottom:12px">
      <h3>Día de muestreo</h3>
      <p class="desc">Empresas y programas por veterinario. Costo operativo = sección “Costo Operativo” (UF × UF del día). CO km y otros CO vienen de la planilla, cruzados por fecha, veterinario, empresa de servicio y centro.</p>
      <div class="filters" id="cal-filters" style="margin:10px 0 12px; box-shadow:none">
        <div class="caso-search">
          <span class="lbl">Buscar por caso</span>
          <div class="caso-search-row">
            <input id="cal-caso" type="search" placeholder="Ej. PM-170523, VI-30109 o solo el número" autocomplete="off">
            <button type="button" id="btn-buscar-caso">Buscar</button>
            <button type="button" id="btn-limpiar-caso" class="ghost">Limpiar</button>
          </div>
          <p class="hint-multi">Encuentra el día de muestreo del caso y muestra todo lo realizado ese día: veterinarios, sedes, empresas, centros y programas.</p>
          <div id="cal-caso-hits" class="caso-hits"></div>
        </div>
        <p class="hint-multi">Puedes marcar varios veterinarios, sedes y programas.</p>
        <label class="f">Veterinario<div class="msel" id="cal-vet" data-empty="Todos"></div></label>
        <label class="f">Cliente / empresa<div class="msel" id="cal-cliente" data-empty="Todos"></div></label>
        <label class="f">Sede<div class="msel" id="cal-sede" data-empty="Todas"></div></label>
        <label class="f">Programa<div class="msel" id="cal-programa" data-empty="Todos"></div></label>
        <label class="f">Año
          <select id="cal-anio" style="border:1px solid var(--line);border-radius:12px;padding:10px 12px;font:inherit"></select>
        </label>
        <label class="f">Mes
          <select id="cal-mes" style="border:1px solid var(--line);border-radius:12px;padding:10px 12px;font:inherit"></select>
        </label>
        <label class="f" style="min-width:220px">
          <span>&nbsp;</span>
          <label style="flex-direction:row;align-items:center;gap:8px;font-size:.82rem;color:var(--ink);padding-top:8px">
            <input type="checkbox" id="cal-ocultar-na" checked>
            Ocultar “No aplica” / “Cliente”
          </label>
        </label>
      </div>
      <div id="cal-kpis" class="kpis"></div>
      <div class="cal-wrap">
        <div class="cal-dow" id="cal-dow"></div>
        <div class="cal-grid" id="cal-grid"></div>
      </div>
      <div class="cal-detail" id="cal-day-box">
        <h3 id="cal-detail-title">Resumen del día</h3>
        <div id="cal-detail-body"><em style="color:var(--muted)">Sin día seleccionado. También puedes buscar un caso arriba.</em></div>
      </div>
      <div class="cal-detail" style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center">
          <div>
            <h3 id="cal-table-title" style="margin:0">Tabla del mes</h3>
            <p class="desc" id="cal-table-desc" style="margin:4px 0 0">Detalle filtrado del calendario</p>
          </div>
          <button type="button" class="chip" id="btn-excel-cal" style="border-radius:999px;padding:9px 14px;background:var(--ok);color:#fff;border-color:var(--ok)">Descargar Excel</button>
        </div>
        <div class="filters" style="margin:12px 0 0; box-shadow:none; padding:10px 12px">
          <p class="hint-multi">Puedes marcar varios años, meses, empresas y programas. Si no marcas año o mes, usa el del calendario. Si no marcas empresa o programa, usa el filtro de arriba.</p>
          <label class="f" style="min-width:140px">Años<div class="msel" id="cal-tabla-anio" data-empty="Año del calendario"></div></label>
          <label class="f" style="min-width:200px">Meses<div class="msel" id="cal-tabla-mes" data-empty="Mes del calendario"></div></label>
          <label class="f" style="min-width:220px;flex:1">Empresa<div class="msel" id="cal-tabla-empresa" data-empty="Todas / filtro de arriba"></div></label>
          <label class="f" style="min-width:220px;flex:1">Programa<div class="msel" id="cal-tabla-programa" data-empty="Todos / filtro de arriba"></div></label>
        </div>
        <div class="scroll" style="max-height:420px;overflow:auto;margin-top:10px">
          <table id="cal-table">
            <thead>
              <tr>
                <th>Día</th><th>Veterinario</th><th>Sede</th><th>Empresa</th><th>Centros</th><th>Programas</th><th>Casos</th>
                <th class="num">N</th><th class="num">Venta $</th><th class="num">Costo operativo $</th>
                <th class="num">CO km</th><th class="num">Aumentos UF</th><th class="num">Otros CO $</th>
                <th>Comentario</th>
              </tr>
            </thead>
            <tbody id="cal-tbody"></tbody>
            <tfoot id="cal-tfoot"></tfoot>
          </table>
        </div>
      </div>
      <div class="cal-detail" id="cal-resumen-box" style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
          <div>
            <h3 style="margin:0">Resumen por empresa y sede</h3>
            <p class="desc" id="cal-resumen-desc" style="margin:4px 0 0">Elige año, mes y programa. Días = fechas de muestreo distintas. Costo operativo en UF (sección Costo Operativo).</p>
          </div>
          <button type="button" class="chip" id="btn-excel-cal-resumen" style="border-radius:999px;padding:9px 14px;background:var(--ok);color:#fff;border-color:var(--ok)">Descargar Excel</button>
        </div>
        <div class="filters" style="margin:12px 0 0; box-shadow:none; padding:10px 12px">
          <p class="hint-multi">Puedes marcar varios años, meses y programas. Vacío = todos. También respeta veterinario, cliente y sede de arriba.</p>
          <label class="f" style="min-width:140px">Año<div class="msel" id="cal-resumen-anio" data-empty="Todos los años"></div></label>
          <label class="f" style="min-width:160px">Mes<div class="msel" id="cal-resumen-mes" data-empty="Todos los meses"></div></label>
          <label class="f" style="min-width:220px;flex:1.4">Programa<div class="msel" id="cal-resumen-programa" data-empty="Todos los programas"></div></label>
        </div>
        <div id="cal-resumen-kpis" class="kpis" style="margin-top:12px"></div>
        <div class="scroll" style="max-height:420px;overflow:auto;margin-top:10px">
          <table id="cal-resumen-table">
            <thead>
              <tr>
                <th>Empresa</th>
                <th>Sede</th>
                <th class="num">Días</th>
                <th class="num">Costo operativo UF</th>
                <th class="num">CO km</th>
                <th class="num">Aumentos UF</th>
                <th class="num">Otros CO $</th>
              </tr>
            </thead>
            <tbody id="cal-resumen-tbody"></tbody>
            <tfoot id="cal-resumen-tfoot"></tfoot>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-reglas-cal" class="tab-pane">
    <div class="rules-box">
      <h3>Reglas del calendario de veterinarios</h3>
      <p class="desc" style="margin:0 0 8px;color:var(--muted)">Fuente: vista SQL <strong>dbo.vw_FVivaldiWebSalud</strong> (solo lectura). Montos en pesos = UF × valor UF del día (<code>fac_vtatotal × fac_uf</code>).</p>

      <h4>Qué muestra el calendario</h4>
      <ul>
        <li>Se agrupa por <strong>fecha de muestreo</strong> (<code>fecha_muestreo</code>), no por fecha de recepción ni de factura.</li>
        <li>La grilla del mes muestra empresas, programas y el <strong>costo operativo facturado</strong> del día. No muestra CO km, aumentos UF ni otros CO: esos costos van solo en las tablas.</li>
        <li>Los indicadores de arriba son días con muestreo, registros, venta $ y costo operativo $. Datos desde <strong>2024 en adelante</strong>.</li>
      </ul>

      <h4>Costos</h4>
      <ul>
        <li><strong>Venta $</strong> = todas las filas del grupo: <code>fac_vtatotal × fac_uf</code> (UF de la línea × valor UF del día).</li>
        <li><strong>Costo operativo $</strong> = solo la sección <strong>“Costo Operativo”</strong>, en pesos (<code>fac_vtatotal × fac_uf</code>). Es lo facturado, no lo ingresado en la planilla.</li>
        <li><strong>Costo operativo UF</strong> = esa misma sección, en UF (<code>fac_vtatotal</code>, sin multiplicar por el valor UF del día). Se usa en el resumen por empresa y sede.</li>
        <li><strong>CO km</strong>, <strong>Aumentos UF</strong> y <strong>Otros CO $</strong> salen de <strong>dbo.vw_atv_planilla_detalles</strong>. El cruce es <strong>fecha de muestreo + veterinario + empresa de servicio + centro</strong> (<code>empresa_servicio</code> = <code>nombre_empresaservicios</code>, <code>centro</code> = <code>nombre_centro</code>).</li>
        <li><strong>CO km</strong> = <code>co_km</code>. Son kilómetros, sin signo peso.</li>
        <li><strong>Aumentos UF</strong> = <code>co_extra + co_veterinario</code>. Esos dos campos vienen en UF.</li>
        <li><strong>Otros CO $</strong> = <code>co_peaje + co_transbordador + co_taxi + co_pasaje + co_colacion + co_alojamiento</code>. Pesos tal como se ingresaron, sin multiplicar por la UF. No entran <code>ga_vehiculo</code>, <code>ga_consumo</code> ni el texto <code>otros</code>.</li>
        <li>El operativo es de la visita (día + veterinario + empresa + centro). Si esa visita tiene varios programas, van <strong>en la misma fila</strong> y el CO se muestra una sola vez.</li>
        <li>Si todos los <code>co_</code> de la visita están en 0, o no hay fila en la planilla, el comentario es <strong>OPERATIVO NO INGRESADO</strong>. No se marca cuando <strong>todos</strong> los programas de la fila son screening. Si hay screening mezclado con otro programa y ese otro no tiene costos, la alerta se mantiene.</li>
      </ul>

      <h4>Dónde se ven los costos</h4>
      <ul>
        <li><strong>Resumen del día:</strong> una fila por veterinario. Junta sedes, empresas, centros, programas y casos. El CO es la suma de cada visita de ese veterinario, contada una vez.</li>
        <li><strong>Detalle por centro:</strong> una fila por visita (día + veterinario + empresa + centro), con sus programas juntos.</li>
        <li><strong>Tabla del mes:</strong> lista los casos igual que el resumen del día. Puedes marcar varios años, meses, empresas y programas; el calendario de arriba sigue en un solo mes. Si no marcas año o mes, parte del año y mes del calendario. Si no marcas empresa o programa, usa el filtro de arriba.</li>
        <li>En esa tabla, los centros del <strong>mismo día y mismo veterinario</strong> se unen cuando el CO cargado es el mismo (mismos km, mismos aumentos UF y mismos otros CO). Los centros, empresas y programas quedan en la fila y ese CO se cuenta <strong>una vez</strong>. La venta $ y el costo operativo $ sí se suman. Si el CO es distinto, cada centro sigue en su fila.</li>
        <li>El Excel de la tabla del mes exporta ese mismo detalle, con casos, comentario y centros unidos.</li>
        <li><strong>Resumen por empresa y sede:</strong> días distintos de muestreo, costo operativo en UF, CO km, aumentos UF y otros CO. Se filtra por año, mes y programa, y respeta veterinario, cliente y sede de arriba.</li>
      </ul>

      <h4>Cómo se hace el match / cruce</h4>
      <ul>
        <li><strong>Día</strong> ← <code>fecha_muestreo</code> (formato día/mes/año de la vista).</li>
        <li><strong>Veterinario</strong> ← <code>nombre_veterinario</code> (se puede ocultar “No aplica” / “Cliente”).</li>
        <li><strong>Sede</strong> ← <code>nombre_lugaranalisis</code> (Puerto Montt / Aysén / Villarrica).</li>
        <li><strong>Empresa</strong> ← <code>nombre_empresaservicios</code> (no <code>nombre_empresa</code>).</li>
        <li><strong>Centro</strong> ← <code>nombre_centro</code>.</li>
        <li><strong>Programa</strong> ← <code>nombre_programa</code>.</li>
        <li>Los filtros del calendario (veterinario, cliente/empresa, sede, programa) son multi-selección: vacío = todos.</li>
        <li><strong>Buscar por caso</strong> usa <code>caso_adlab</code>. Cada caso tiene un día de muestreo. Al encontrarlo se lista <strong>todo lo realizado ese día</strong> (sin recortar por veterinario, cliente ni programa). La fila resaltada es la combinación del caso. Acepta el código completo (<code>PM-170523</code>) o solo el número.</li>
        <li>Al hacer clic en un día se abre el resumen de ese día. <strong>Buscar por caso</strong> lleva al día de muestreo del caso y resalta su visita.</li>
      </ul>

      <h4>Acceso PVE por sede</h4>
      <ul>
        <li><strong>pve</strong> entra a la vista PVE (calendario y reglas) y ve <strong>todas</strong> las sedes: Puerto Montt, Aysén y Villarrica.</li>
        <li><strong>pveaysen</strong> entra a la misma vista PVE y solo ve la sede <strong>Aysén</strong>. El calendario, el resumen del día, el detalle por centro, la tabla del mes, el resumen por empresa y la búsqueda por caso quedan recortados a Aysén. No puede cambiar la sede.</li>
        <li><strong>pvevillarrica</strong> entra a la misma vista PVE y solo ve la sede <strong>Villarrica</strong>, con el mismo recorte. No puede cambiar la sede.</li>
        <li>Al regenerar este reporte se envía un correo por sede con las visitas del mes, hasta hoy, marcadas <strong>OPERATIVO NO INGRESADO</strong>. El screening puro no entra. Cada sede recibe solo lo suyo. Los correos están en <code>alertas_correo.env</code> y no se publican. Si el listado no cambió, no se reenvía.</li>
      </ul>

      <h4>Qué NO incluye este calendario</h4>
      <ul>
        <li>No incluye días de <strong>vuelo</strong>.</li>
        <li>No incluye días de <strong>hospedaje</strong> como actividad. El monto <code>co_alojamiento</code> de la planilla sí entra en Otros CO $.</li>
        <li>No incluye <strong>puerto cerrado</strong>.</li>
        <li>No incluye días de <strong>muestreo de calidad</strong>.</li>
      </ul>
      <div class="warn">
        Este calendario refleja actividad de muestreo operativo registrada en FVivaldi (Web Salud).
        No lista días de vuelo, hospedaje, puerto cerrado ni muestreo de calidad.
        El monto de alojamiento ingresado en la planilla (<code>co_alojamiento</code>) sí queda dentro de Otros CO $.
      </div>
    </div>
  </div>
</div>
<footer>ADL Diagnostic Chile · Consulta facturación · FVivaldi Web Salud</footer>
<script>
const RAW = {data};
const MESES = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const MESES_L = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const DOW = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
const COLORS = ['#003E6D','#F37021','#0A8F9C','#2F9E71','#E9B949','#7B68A6','#D64545','#829AB1','#1A5F8A','#FF8A3D'];

const fmt = n => new Intl.NumberFormat('es-CL', {{ style:'currency', currency:'CLP', maximumFractionDigits:0 }}).format(Number(n)||0);
const fmtM = n => {{
  const x = Number(n)||0;
  if (Math.abs(x) >= 1e9) return '$' + (x/1e9).toFixed(2) + ' mil M';
  if (Math.abs(x) >= 1e6) return '$' + (x/1e6).toFixed(1) + ' M';
  return fmt(x);
}};
const fmtN = n => new Intl.NumberFormat('es-CL').format(Number(n)||0);
const fmtUf = n => new Intl.NumberFormat('es-CL', {{ maximumFractionDigits: 1 }}).format(Number(n)||0);
const fmtDec = fmtUf;
const fmtUf2 = n => new Intl.NumberFormat('es-CL', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}).format(Number(n)||0);
const uniqueSorted = arr => [...new Set(arr.filter(x => x !== null && x !== undefined && x !== ''))]
  .sort((a,b) => String(a).localeCompare(String(b), 'es', {{ numeric:true }}));
const sum = (rows, key='venta_clp') => rows.reduce((a,r) => a + (Number(r[key])||0), 0);

{JS_CHART_TOOLS}

document.getElementById('meta').innerHTML =
  `Servidor: ${{RAW.servidor}}<br>Base: ${{RAW.base}}<br>Vista: ${{RAW.vista}}<br>Generado: ${{RAW.generado}}`;

/* ---- tabs ---- */
document.querySelectorAll('.tabs button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});

const charts = {{}};
function destroyCharts() {{
  Object.keys(charts).forEach(k => {{ try {{ charts[k].destroy(); }} catch(e) {{}} delete charts[k]; }});
}}

function fillFilters() {{
  const rows = RAW.serie || [];
  fillMulti('f-anio', uniqueSorted(rows.map(r => r.anio)));
  fillMulti('f-mes', [1,2,3,4,5,6,7,8,9,10,11,12].map(String), null, Object.fromEntries([1,2,3,4,5,6,7,8,9,10,11,12].map(m => [String(m), MESES[m]])));
  fillMulti('f-programa', uniqueSorted(rows.map(r => r.programa)));
  fillMulti('f-empresa', uniqueSorted(rows.map(r => r.empresa)));
  fillMulti('f-estado', uniqueSorted(rows.map(r => r.estado)));
}}

function filteredSerie() {{
  const anios = selectedMulti('f-anio').map(Number);
  const meses = selectedMulti('f-mes').map(Number);
  const progs = new Set(selectedMulti('f-programa'));
  const emps = new Set(selectedMulti('f-empresa'));
  const ests = new Set(selectedMulti('f-estado'));
  return (RAW.serie || []).filter(r => {{
    if (anios.length && !anios.includes(Number(r.anio))) return false;
    if (meses.length && !meses.includes(Number(r.mes))) return false;
    if (progs.size && !progs.has(r.programa)) return false;
    if (emps.size && !emps.has(r.empresa)) return false;
    if (ests.size && !ests.has(r.estado)) return false;
    return true;
  }});
}}

function groupSum(rows, key) {{
  const m = new Map();
  rows.forEach(r => {{
    const k = r[key] ?? '(sin)';
    const cur = m.get(k) || {{ key:k, n:0, venta_clp:0, venta_uf:0 }};
    cur.n += Number(r.n)||0;
    cur.venta_clp += Number(r.venta_clp)||0;
    cur.venta_uf += Number(r.venta_uf)||0;
    m.set(k, cur);
  }});
  return [...m.values()];
}}

function renderAnalisis() {{
  destroyCharts();
  const rows = filteredSerie();
  const tot = sum(rows);
  const totUf = sum(rows, 'venta_uf');
  const n = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  const fact = rows.filter(r => String(r.estado).toUpperCase()==='FACTURADO');
  const items = [
    ['Registros (filtro)', fmtN(n), rows.length + ' grupos', ''],
    ['Venta $', fmtM(tot), fmtUf(totUf) + ' UF', 'accent'],
    ['Facturado $', fmtM(sum(fact)), fmtN(fact.reduce((a,r)=>a+(Number(r.n)||0),0)) + ' regs', 'ok'],
    ['Programas', uniqueSorted(rows.map(r=>r.programa)).length, 'en filtro', ''],
    ['Empresas', uniqueSorted(rows.map(r=>r.empresa)).length, 'en filtro', ''],
    ['Global fact. $', fmtM(RAW.kpis.venta_clp_facturada), 'sin filtro · toda la vista', ''],
  ];
  document.getElementById('kpis').innerHTML = items.map(([l,v,h,cls]) =>
    `<div class="kpi ${{cls}}"><div class="l">${{l}}</div><div class="v">${{v}}</div><div class="h">${{h}}</div></div>`
  ).join('');

  const porAnio = groupSum(rows, 'anio').sort((a,b)=>Number(a.key)-Number(b.key));
  charts.anio = new Chart(document.getElementById('cAnio'), {{
    type:'bar',
    data: {{
      labels: porAnio.map(x => String(x.key)),
      datasets:[{{ label:'Venta $', data: porAnio.map(x => x.venta_clp), backgroundColor:'#003E6D', borderRadius:8, maxBarThickness:48 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false, interaction: interactIndex,
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Por año', {{ conTotal:false }}), datalabels: dlMoney() }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const porMes = Array.from({{length:12}}, (_,i) => sum(rows.filter(r => Number(r.mes)===i+1)));
  charts.mes = new Chart(document.getElementById('cMes'), {{
    type:'bar',
    data: {{
      labels: MESES.slice(1),
      datasets:[{{ label:'Venta $', data: porMes, backgroundColor:'#F37021', borderRadius:6, maxBarThickness:36 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false, interaction: interactIndex,
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Mensual', {{ conTotal:false }}), datalabels: dlMoney({{ minRatio:0.04 }}) }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const porProg = groupSum(rows, 'programa').sort((a,b)=>b.venta_clp-a.venta_clp).slice(0,12);
  charts.prog = new Chart(document.getElementById('cProg'), {{
    type:'bar',
    data: {{
      labels: porProg.map(x => x.key),
      datasets:[{{ label:'Venta $', data: porProg.map(x => x.venta_clp), backgroundColor:'#0A8F9C', borderRadius:6, maxBarThickness:22 }}]
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false, interaction: interactIndex,
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Programa', {{ conTotal:false }}), datalabels: dlMoney({{ horiz:true }}) }},
      scales: {{
        x: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }},
        y: {{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});

  const porEmp = groupSum(rows, 'empresa').sort((a,b)=>b.venta_clp-a.venta_clp).slice(0,15);
  charts.emp = new Chart(document.getElementById('cEmp'), {{
    type:'bar',
    data: {{
      labels: porEmp.map(x => x.key),
      datasets:[{{ label:'Venta $', data: porEmp.map(x => x.venta_clp),
        backgroundColor: porEmp.map((_,i)=> i%2 ? 'rgba(243,112,33,.9)' : 'rgba(0,62,109,.88)'),
        borderRadius:6, maxBarThickness:18 }}]
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false, interaction: interactIndex,
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Empresa', {{ conTotal:false }}), datalabels: dlMoney({{ horiz:true }}) }},
      scales: {{
        x: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }},
        y: {{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});

  const porEst = groupSum(rows, 'estado').sort((a,b)=>b.n-a.n);
  charts.est = new Chart(document.getElementById('cEst'), {{
    type:'doughnut',
    data: {{
      labels: porEst.map(x => x.key),
      datasets:[{{ data: porEst.map(x => x.n), backgroundColor: COLORS, borderWidth:0 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{position:'bottom', labels:{{boxWidth:12, font:{{size:11}}}}}},
        tooltip: {{ callbacks: {{ label: c => `${{c.label}}: ${{fmtN(c.raw)}} · ${{fmtM(porEst[c.dataIndex]?.venta_clp||0)}}` }} }},
        datalabels: dlPiePct() }}
    }}
  }});

  const anios = uniqueSorted(rows.map(r => r.anio));
  const progs = uniqueSorted(rows.map(r => r.programa)).slice(0,8);
  charts.anioProg = new Chart(document.getElementById('cAnioProg'), {{
    type:'bar',
    data: {{
      labels: anios.map(String),
      datasets: progs.map((p,i) => ({{
        label: p,
        data: anios.map(y => sum(rows.filter(r => Number(r.anio)===Number(y) && r.programa===p))),
        backgroundColor: COLORS[i % COLORS.length],
        stack: 'a', maxBarThickness:40, borderRadius:3
      }}))
    }},
    options: {{
      responsive:true, maintainAspectRatio:false, interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom', labels:{{boxWidth:10, font:{{size:10}}}}}},
        tooltip: tipGrupo(() => 'Año × programa', {{ conTotal:true }}),
        datalabels: dlMoney({{ stacked:true, minRatio:0.07 }})
      }},
      scales: {{
        x: {{ stacked:true, ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ stacked:true, ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});
}}

/* ---- calendario veterinarios ---- */
let selectedDia = null;
let calTableRows = [];
let casoActivo = null;
let calTablaMesManual = false;
let calTablaAnioManual = false;

function calBaseRows() {{
  const ocultar = document.getElementById('cal-ocultar-na').checked;
  return (RAW.calendario || []).filter(r => {{
    if (!ocultar) return true;
    const v = String(r.veterinario||'').toLowerCase();
    return v !== 'no aplica' && v !== 'cliente' && v !== '(sin veterinario)';
  }});
}}

function fillCalFilters() {{
  const rows = calBaseRows();
  const prevV = selectedMulti('cal-vet');
  const prevC = selectedMulti('cal-cliente');
  const prevS = selectedMulti('cal-sede');
  const prevP = selectedMulti('cal-programa');
  fillMulti('cal-vet', uniqueSorted(rows.map(r => r.veterinario)), prevV.filter(v => rows.some(r => r.veterinario===v)));
  fillMulti('cal-cliente', uniqueSorted(rows.map(r => r.empresa)), prevC.filter(v => rows.some(r => r.empresa===v)));
  fillMulti('cal-sede', uniqueSorted(rows.map(r => r.sede)), prevS.filter(v => rows.some(r => r.sede===v)));
  fillMulti('cal-programa', uniqueSorted(rows.map(r => r.programa)), prevP.filter(v => rows.some(r => r.programa===v)));

  const anios = uniqueSorted(rows.map(r => String(r.dia||'').slice(0,4))).filter(Boolean);
  const selA = document.getElementById('cal-anio');
  const selM = document.getElementById('cal-mes');
  const prevA = selA.value, prevM = selM.value;
  selA.innerHTML = anios.map(a => `<option value="${{a}}">${{a}}</option>`).join('');
  selM.innerHTML = MESES_L.slice(1).map((m,i) => `<option value="${{i+1}}">${{m}}</option>`).join('');
  if (prevA && anios.includes(prevA)) selA.value = prevA;
  else if (anios.length) selA.value = anios[anios.length-1];
  if (prevM) selM.value = prevM;
  else selM.value = String(new Date().getMonth()+1);
  fillCalTableFiltros();
  fillCalResumenPeriodo();
}}

function mesesCalendario() {{
  const vals = ['1','2','3','4','5','6','7','8','9','10','11','12'];
  const labels = Object.fromEntries(vals.map(m => [m, MESES_L[Number(m)]]));
  return {{ vals, labels }};
}}

function aniosCalendario() {{
  return uniqueSorted(calBaseRows().map(r => String(r.dia || '').slice(0, 4))).filter(Boolean);
}}

function fillCalTableFiltros() {{
  const rows = calBaseRows();
  const {{ vals, labels }} = mesesCalendario();
  const anios = aniosCalendario();
  const empresas = uniqueSorted(rows.map(r => r.empresa));
  const programas = uniqueSorted(rows.map(r => r.programa));
  const prevE = selectedMulti('cal-tabla-empresa').filter(v => empresas.includes(v));
  const prevP = selectedMulti('cal-tabla-programa').filter(v => programas.includes(v));
  const mesCal = String(Number(document.getElementById('cal-mes').value) || 0);
  const anioCal = String(document.getElementById('cal-anio').value || '');
  const prevM = calTablaMesManual
    ? selectedMulti('cal-tabla-mes').filter(v => vals.includes(v))
    : (vals.includes(mesCal) ? [mesCal] : []);
  const prevA = calTablaAnioManual
    ? selectedMulti('cal-tabla-anio').filter(v => anios.includes(v))
    : (anios.includes(anioCal) ? [anioCal] : []);
  fillMulti('cal-tabla-anio', anios, prevA);
  fillMulti('cal-tabla-mes', vals, prevM, labels);
  fillMulti('cal-tabla-empresa', empresas, prevE);
  fillMulti('cal-tabla-programa', programas, prevP);
}}

function rowsTablaMes() {{
  const anios = new Set(selectedMulti('cal-tabla-anio'));
  const meses = new Set(selectedMulti('cal-tabla-mes').map(Number));
  const empresasTabla = selectedMulti('cal-tabla-empresa');
  const empresas = new Set(empresasTabla.length ? empresasTabla : selectedMulti('cal-cliente'));
  const progsTabla = selectedMulti('cal-tabla-programa');
  const progs = new Set(progsTabla.length ? progsTabla : selectedMulti('cal-programa'));
  const vets = new Set(selectedMulti('cal-vet'));
  const sedes = new Set(selectedMulti('cal-sede'));
  return calBaseRows().filter(r => {{
    const d = String(r.dia || '');
    if (anios.size && !anios.has(d.slice(0, 4))) return false;
    const m = Number(d.slice(5, 7));
    if (meses.size && !meses.has(m)) return false;
    if (vets.size && !vets.has(r.veterinario)) return false;
    if (empresas.size && !empresas.has(r.empresa)) return false;
    if (sedes.size && !sedes.has(r.sede)) return false;
    if (progs.size && !progs.has(r.programa)) return false;
    return true;
  }}).sort((a,b) => String(a.dia).localeCompare(String(b.dia))
    || String(a.veterinario).localeCompare(String(b.veterinario), 'es')
    || String(a.empresa).localeCompare(String(b.empresa), 'es')
    || String(a.centro||'').localeCompare(String(b.centro||''), 'es')
    || String(a.programa||'').localeCompare(String(b.programa||''), 'es'));
}}

function filteredCalRows() {{
  const anio = Number(document.getElementById('cal-anio').value);
  const mes = Number(document.getElementById('cal-mes').value);
  const vets = new Set(selectedMulti('cal-vet'));
  const clientes = new Set(selectedMulti('cal-cliente'));
  const sedes = new Set(selectedMulti('cal-sede'));
  const progs = new Set(selectedMulti('cal-programa'));
  const prefix = `${{anio}}-${{String(mes).padStart(2,'0')}}`;
  return calBaseRows().filter(r => {{
    if (!String(r.dia||'').startsWith(prefix)) return false;
    if (vets.size && !vets.has(r.veterinario)) return false;
    if (clientes.size && !clientes.has(r.empresa)) return false;
    if (sedes.size && !sedes.has(r.sede)) return false;
    if (progs.size && !progs.has(r.programa)) return false;
    return true;
  }});
}}

function renderCalendario() {{
  const anio = Number(document.getElementById('cal-anio').value);
  const mes = Number(document.getElementById('cal-mes').value);
  const rows = filteredCalRows();
  calTableRows = rows.slice().sort((a,b) => String(a.dia).localeCompare(String(b.dia))
    || String(a.veterinario).localeCompare(String(b.veterinario), 'es')
    || String(a.empresa).localeCompare(String(b.empresa), 'es')
    || String(a.centro||'').localeCompare(String(b.centro||''), 'es')
    || String(a.programa||'').localeCompare(String(b.programa||''), 'es'));

  const totVenta = sum(rows);
  const totOp = sum(rows, 'costo_operativo_clp');
  const nRegs = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  const dias = uniqueSorted(rows.map(r => r.dia)).length;
  document.getElementById('cal-kpis').innerHTML = [
    ['Días con muestreo', fmtN(dias), MESES_L[mes] + ' ' + anio, ''],
    ['Registros', fmtN(nRegs), uniqueSorted(rows.map(r=>r.veterinario)).length + ' veterinarios', ''],
    ['Venta $ del mes', fmtM(totVenta), 'UF × UF día', 'accent'],
    ['Costo operativo $', fmtM(totOp), 'sección Costo Operativo', 'ok'],
  ].map(([l,v,h,cls]) => `<div class="kpi ${{cls}}"><div class="l">${{l}}</div><div class="v">${{v}}</div><div class="h">${{h}}</div></div>`).join('');

  const byDay = new Map();
  rows.forEach(r => {{
    const d = r.dia;
    if (!byDay.has(d)) byDay.set(d, {{ empresas:new Map(), programas:new Map(), n:0, venta:0, costo:0 }});
    const o = byDay.get(d);
    o.n += Number(r.n)||0;
    o.venta += Number(r.venta_clp)||0;
    o.costo += Number(r.costo_operativo_clp)||0;
    o.empresas.set(r.empresa, (o.empresas.get(r.empresa)||0) + (Number(r.n)||0));
    o.programas.set(r.programa, (o.programas.get(r.programa)||0) + (Number(r.n)||0));
  }});

  const first = new Date(anio, mes-1, 1);
  let start = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(anio, mes, 0).getDate();
  const today = new Date().toISOString().slice(0,10);

  document.getElementById('cal-dow').innerHTML = DOW.map(d => `<span>${{d}}</span>`).join('');

  const grid = document.getElementById('cal-grid');
  let html = '';
  for (let i=0;i<start;i++) html += `<div class="cal-day empty" aria-hidden="true"></div>`;
  for (let day=1; day<=daysInMonth; day++) {{
    const iso = `${{anio}}-${{String(mes).padStart(2,'0')}}-${{String(day).padStart(2,'0')}}`;
    const info = byDay.get(iso);
    const cls = [
      'cal-day',
      info ? 'has clickable' : 'clickable',
      iso===today ? 'today' : '',
      selectedDia===iso ? 'selected' : ''
    ].filter(Boolean).join(' ');
    let body = '';
    if (info) {{
      const emps = [...info.empresas.entries()].sort((a,b)=>b[1]-a[1]).slice(0,2);
      const progs = [...info.programas.entries()].sort((a,b)=>b[1]-a[1]).slice(0,2);
      body = `<div class="op">${{fmtM(info.costo)}} op.</div>`
        + emps.map(([e]) => `<span class="tag" title="${{e}}">${{e}}</span>`).join('')
        + progs.map(([p]) => `<span class="tag prog" title="${{p}}">${{p}}</span>`).join('');
      if (info.empresas.size > 2) body += `<span class="tag">+${{info.empresas.size-2}} emp.</span>`;
    }} else {{
      body = `<div class="op" style="opacity:.45">Sin muestreo</div>`;
    }}
    html += `<div class="${{cls}}" data-dia="${{iso}}" role="button" tabindex="0"><div class="num">${{day}}</div>${{body}}</div>`;
  }}
  // completar última semana para que el grid quede rectangular
  const totalCells = start + daysInMonth;
  const pad = (7 - (totalCells % 7)) % 7;
  for (let i=0;i<pad;i++) html += `<div class="cal-day empty" aria-hidden="true"></div>`;
  grid.innerHTML = html;
  grid.querySelectorAll('.cal-day.clickable').forEach(el => {{
    const open = () => {{ casoActivo = null; showDiaDetalle(el.dataset.dia); }};
    el.addEventListener('click', open);
    el.addEventListener('keydown', (ev) => {{ if (ev.key === 'Enter' || ev.key === ' ') {{ ev.preventDefault(); open(); }} }});
  }});

  if (!calTablaAnioManual) {{
    fillMulti('cal-tabla-anio', aniosCalendario(), [String(anio)]);
  }}
  if (!calTablaMesManual) {{
    const pack = mesesCalendario();
    fillMulti('cal-tabla-mes', pack.vals, [String(mes)], pack.labels);
  }}
  renderCalTable();
  renderCalResumen();
  const prefixMes = `${{anio}}-${{String(mes).padStart(2,'0')}}`;
  if (casoActivo && String(casoActivo[0].dia || '').startsWith(prefixMes))
    showDiaDetalle(casoActivo[0].dia, false, casoActivo);
  else if (selectedDia && selectedDia.startsWith(prefixMes))
    showDiaDetalle(selectedDia, false);
}}

function textoCasos(ids) {{
  const list = [...new Set(ids || [])].sort((a, b) => String(a).localeCompare(String(b), 'es', {{ numeric: true }}));
  return list.join(', ');
}}

function firmaCo(c) {{
  const n = x => String(Math.round((Number(x) || 0) * 10000));
  return [n(c.co_km), n(c.co_uf), n(c.co_otros)].join('|');
}}
function agruparTablaMes(rows) {{
  const map = new Map();
  const order = [];
  (rows || []).forEach(r => {{
    const c = costoDeFila(r);
    const k = [r.dia, String(r.veterinario || '').trim().toUpperCase(), firmaCo(c)].join('\\t');
    let g = map.get(k);
    if (!g) {{
      g = {{
        dia: r.dia, veterinario: r.veterinario,
        sedes: [], empresas: [], centros: [], programas: [], casos: [],
        n: 0, venta_clp: 0, costo_operativo_clp: 0,
        co_km: Number(c.co_km) || 0, co_uf: Number(c.co_uf) || 0, co_otros: Number(c.co_otros) || 0
      }};
      map.set(k, g);
      order.push(g);
    }}
    g.sedes.push(r.sede);
    g.empresas.push(r.empresa);
    g.centros.push(r.centro || '');
    g.programas.push(r.programa);
    casosDeFila(r.dia, r).forEach(id => g.casos.push(id));
    g.n += Number(r.n) || 0;
    g.venta_clp += Number(r.venta_clp) || 0;
    g.costo_operativo_clp += Number(r.costo_operativo_clp) || 0;
  }});
  return order.map(g => ({{
    dia: g.dia, veterinario: g.veterinario,
    sede: unirLista(g.sedes), empresa: unirLista(g.empresas), centro: unirLista(g.centros),
    programa: unirLista(g.programas), casos: g.casos,
    n: g.n, venta_clp: g.venta_clp, costo_operativo_clp: g.costo_operativo_clp,
    co_km: g.co_km, co_uf: g.co_uf, co_otros: g.co_otros
  }}));
}}
function costosTablaMes(visitas) {{
  return (visitas || []).reduce((a, v) => {{
    a.km += Number(v.co_km) || 0;
    a.uf += Number(v.co_uf) || 0;
    a.otros += Number(v.co_otros) || 0;
    return a;
  }}, {{ km: 0, uf: 0, otros: 0 }});
}}

function renderCalTable() {{
  const rows = rowsTablaMes();
  calTableRows = rows;
  const visitas = agruparTablaMes(rows);
  const co = costosTablaMes(visitas);
  const anios = selectedMulti('cal-tabla-anio');
  const meses = selectedMulti('cal-tabla-mes');
  const empresas = selectedMulti('cal-tabla-empresa');
  const programas = selectedMulti('cal-tabla-programa');
  const anioTxt = !anios.length ? 'todos los años' : anios.join(', ');
  const mesTxt = !meses.length ? 'todos los meses'
    : meses.map(m => MESES_L[Number(m)] || m).join(', ');
  const empTxt = !empresas.length ? 'empresas del filtro de arriba' : empresas.length + ' empresa(s)';
  const progTxt = !programas.length ? 'programas del filtro de arriba' : programas.length + ' programa(s)';
  document.getElementById('cal-table-title').textContent = (anios.length > 1 || meses.length > 1) ? 'Tabla de los meses' : 'Tabla del mes';
  document.getElementById('cal-table-desc').textContent =
    `${{anioTxt}} · ${{mesTxt}} · ${{empTxt}} · ${{progTxt}} · ${{visitas.length}} visitas · costo operativo ${{fmtM(sum(rows, 'costo_operativo_clp'))}} · CO km ${{fmtDec(co.km)}} · aumentos ${{fmtUf2(co.uf)}} UF · otros CO ${{fmt(co.otros)}}`;
  document.getElementById('cal-tbody').innerHTML = visitas.map(v => `
    <tr${{faltaOperativo(v.co_km, v.co_uf, v.co_otros, v.programa) ? ' class="co-falta"' : ''}}>
      <td>${{v.dia||''}}</td>
      <td>${{v.veterinario||''}}</td>
      <td>${{v.sede||''}}</td>
      <td>${{v.empresa||''}}</td>
      <td>${{v.centro||''}}</td>
      <td>${{v.programa||''}}</td>
      <td>${{htmlCasos(v.casos)}}</td>
      <td class="num">${{fmtN(v.n)}}</td>
      <td class="num">${{fmt(v.venta_clp)}}</td>
      <td class="num">${{fmt(v.costo_operativo_clp)}}</td>
      <td class="num">${{fmtDec(v.co_km)}}</td>
      <td class="num">${{fmtUf2(v.co_uf)}}</td>
      <td class="num">${{fmt(v.co_otros)}}</td>
      ${{celdaAlertaCo(v.co_km, v.co_uf, v.co_otros, v.programa)}}
    </tr>`).join('') || `<tr><td colspan="14" style="color:var(--muted)">Sin datos para el filtro</td></tr>`;
  const totN = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  document.getElementById('cal-tfoot').innerHTML = rows.length ? `
    <tr style="font-weight:700;background:#F7FAFC">
      <td colspan="7">TOTAL</td>
      <td class="num">${{fmtN(totN)}}</td>
      <td class="num">${{fmt(sum(rows))}}</td>
      <td class="num">${{fmt(sum(rows, 'costo_operativo_clp'))}}</td>
      <td class="num">${{fmtDec(co.km)}}</td>
      <td class="num">${{fmtUf2(co.uf)}}</td>
      <td class="num">${{fmt(co.otros)}}</td>
      <td></td>
    </tr>` : '';
}}

function fillCalResumenPeriodo() {{
  const rows = calBaseRows();
  const anios = uniqueSorted(rows.map(r => String(r.dia||'').slice(0,4)).filter(a => /^\\d{{4}}$/.test(a)));
  const mesesVals = ['1','2','3','4','5','6','7','8','9','10','11','12'];
  const mesLabels = Object.fromEntries(mesesVals.map(m => [m, MESES_L[Number(m)]]));
  const prevA = selectedMulti('cal-resumen-anio').filter(v => anios.includes(v));
  const prevM = selectedMulti('cal-resumen-mes').filter(v => mesesVals.includes(v));
  const programas = uniqueSorted(rows.map(r => r.programa));
  const prevP = selectedMulti('cal-resumen-programa').filter(v => programas.includes(v));
  let preA = prevA, preM = prevM, preP = prevP;
  if (!preA.length && !preM.length && !preP.length) {{
    const anio = document.getElementById('cal-anio').value;
    const mes = String(Number(document.getElementById('cal-mes').value)||0);
    if (anios.includes(anio)) preA = [anio];
    else if (anios.length) preA = [anios[anios.length-1]];
    if (mesesVals.includes(mes)) preM = [mes];
    preP = selectedMulti('cal-programa').filter(v => programas.includes(v));
  }}
  fillMulti('cal-resumen-anio', anios, preA);
  fillMulti('cal-resumen-mes', mesesVals, preM, mesLabels);
  fillMulti('cal-resumen-programa', programas, preP);
}}

function filteredCalResumenRows() {{
  const anios = new Set(selectedMulti('cal-resumen-anio').map(Number));
  const meses = new Set(selectedMulti('cal-resumen-mes').map(Number));
  const vets = new Set(selectedMulti('cal-vet'));
  const clientes = new Set(selectedMulti('cal-cliente'));
  const sedes = new Set(selectedMulti('cal-sede'));
  const progs = new Set(selectedMulti('cal-resumen-programa'));
  return calBaseRows().filter(r => {{
    const d = String(r.dia||'');
    const y = Number(d.slice(0,4));
    const m = Number(d.slice(5,7));
    if (anios.size && !anios.has(y)) return false;
    if (meses.size && !meses.has(m)) return false;
    if (vets.size && !vets.has(r.veterinario)) return false;
    if (clientes.size && !clientes.has(r.empresa)) return false;
    if (sedes.size && !sedes.has(r.sede)) return false;
    if (progs.size && !progs.has(r.programa)) return false;
    return true;
  }});
}}

function calResumenAgg() {{
  const map = new Map();
  filteredCalResumenRows().forEach(r => {{
    const emp = r.empresa || '(sin empresa)';
    const sede = r.sede || '(sin sede)';
    const k = emp + '\\t' + sede;
    const cur = map.get(k) || {{ empresa: emp, sede: sede, dias: new Set(), uf: 0, visitas: new Set(), km: 0, aumentos: 0, otros: 0 }};
    if (r.dia) cur.dias.add(r.dia);
    cur.uf += Number(r.costo_operativo_uf)||0;
    const vk = claveCo(r.dia, r.veterinario, r.empresa, r.centro);
    if (!cur.visitas.has(vk)) {{
      cur.visitas.add(vk);
      const c = costoDeFila(r);
      cur.km += Number(c.co_km) || 0;
      cur.aumentos += Number(c.co_uf) || 0;
      cur.otros += Number(c.co_otros) || 0;
    }}
    map.set(k, cur);
  }});
  return [...map.values()]
    .map(x => ({{ empresa: x.empresa, sede: x.sede, dias: x.dias.size, uf: x.uf, km: x.km, aumentos: x.aumentos, otros: x.otros }}))
    .sort((a,b) => String(a.empresa).localeCompare(String(b.empresa), 'es')
      || String(a.sede).localeCompare(String(b.sede), 'es'));
}}

function labelMesesResumen() {{
  const anios = selectedMulti('cal-resumen-anio');
  const meses = selectedMulti('cal-resumen-mes');
  const progs = selectedMulti('cal-resumen-programa');
  const aTxt = !anios.length ? 'todos los años'
    : anios.length <= 3 ? anios.join(', ')
    : anios.length + ' años';
  const mTxt = !meses.length ? 'todos los meses'
    : meses.length <= 4 ? meses.map(m => MESES_L[Number(m)] || m).join(', ')
    : meses.length + ' meses';
  const pTxt = !progs.length ? 'todos los programas'
    : progs.length === 1 ? progs[0]
    : progs.length + ' programas';
  return aTxt + ' · ' + mTxt + ' · ' + pTxt;
}}

function renderCalResumen() {{
  const items = calResumenAgg();
  const totDias = items.reduce((a,x) => a + x.dias, 0);
  const totUf = items.reduce((a,x) => a + x.uf, 0);
  const mesesTxt = labelMesesResumen();
  const co = sumarCostos(filteredCalResumenRows());
  document.getElementById('cal-resumen-desc').textContent =
    `${{items.length}} combinaciones empresa × sede · ${{mesesTxt}} · respeta filtros de veterinario, cliente y sede · CO km y otros CO una vez por visita`;
  document.getElementById('cal-resumen-kpis').innerHTML = [
    ['Empresas × sede', fmtN(items.length), mesesTxt, ''],
    ['Días (suma)', fmtN(totDias), 'días de muestreo distintos por fila', ''],
    ['Costo operativo UF', fmtUf2(totUf), 'sección Costo Operativo', 'ok'],
    ['CO km', fmtDec(co.km), 'kilometraje, una vez por visita', ''],
    ['Aumentos UF', fmtUf2(co.uf), 'co_extra + co_veterinario', ''],
    ['Otros CO $', fmt(co.otros), 'peaje, pasajes, colación y alojamiento', ''],
  ].map(([l,v,h,cls]) => `<div class="kpi ${{cls}}"><div class="l">${{l}}</div><div class="v">${{v}}</div><div class="h">${{h}}</div></div>`).join('');
  document.getElementById('cal-resumen-tbody').innerHTML = items.map(x => `
    <tr>
      <td>${{x.empresa}}</td>
      <td>${{x.sede}}</td>
      <td class="num">${{fmtN(x.dias)}}</td>
      <td class="num">${{fmtUf2(x.uf)}}</td>
      <td class="num">${{fmtDec(x.km)}}</td>
      <td class="num">${{fmtUf2(x.aumentos)}}</td>
      <td class="num">${{fmt(x.otros)}}</td>
    </tr>`).join('') || `<tr><td colspan="7" style="color:var(--muted)">Sin datos para los meses y filtros elegidos</td></tr>`;
  document.getElementById('cal-resumen-tfoot').innerHTML = items.length ? `
    <tr style="font-weight:700;background:#F7FAFC">
      <td colspan="2">TOTAL</td>
      <td class="num">${{fmtN(totDias)}}</td>
      <td class="num">${{fmtUf2(totUf)}}</td>
      <td class="num">${{fmtDec(co.km)}}</td>
      <td class="num">${{fmtUf2(co.uf)}}</td>
      <td class="num">${{fmt(co.otros)}}</td>
    </tr>` : '';
}}

function csvCell(v) {{
  const s = String(v ?? '');
  return /[;"\\n]/.test(s) ? `"${{s.replace(/"/g,'""')}}"` : s;
}}

function downloadCalResumenExcel() {{
  const items = calResumenAgg();
  if (!items.length) {{ alert('No hay filas para exportar con los meses y filtros actuales.'); return; }}
  const lines = [['Empresa','Sede','Dias','Costo_Operativo_UF','CO_km','Aumentos_UF','Otros_CO'].join(';')];
  items.forEach(x => {{
    lines.push([csvCell(x.empresa), csvCell(x.sede), x.dias, (Number(x.uf)||0).toFixed(2).replace('.', ','), Math.round(Number(x.km)||0), (Number(x.aumentos)||0).toFixed(2).replace('.', ','), Math.round(Number(x.otros)||0)].join(';'));
  }});
  const totDias = items.reduce((a,x) => a + x.dias, 0);
  const totUf = items.reduce((a,x) => a + x.uf, 0);
  const co = sumarCostos(filteredCalResumenRows());
  lines.push(['TOTAL','', totDias, totUf.toFixed(2).replace('.', ','), Math.round(co.km), (Number(co.uf)||0).toFixed(2).replace('.', ','), Math.round(co.otros)].join(';'));
  const bom = '\\uFEFF';
  const blob = new Blob([bom + lines.join('\\r\\n')], {{ type: 'text/csv;charset=utf-8;' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'calendario_resumen_empresa_sede.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}}

function escHtml(s) {{
  return String(s ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}
function normCaso(s) {{
  return String(s || '').toUpperCase().split(' ').join('');
}}
function mismaLineaCaso(r, grupo) {{
  return (grupo || []).some(c =>
    r.veterinario === c.veterinario
    && r.sede === c.sede
    && r.empresa === c.empresa
    && (r.centro || '') === (c.centro || '')
    && r.programa === c.programa
  );
}}
function gruposPorCaso(rows) {{
  const map = new Map();
  rows.forEach(r => {{
    const k = normCaso(r.caso);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(r);
  }});
  return [...map.values()].sort((a, b) =>
    String(b[0].dia).localeCompare(String(a[0].dia))
    || String(a[0].caso).localeCompare(String(b[0].caso), 'es')
  );
}}
function buscarGruposCaso(q) {{
  const nq = normCaso(q);
  if (!nq || nq.length < 3) return {{ error: 'Escribe al menos 3 caracteres del caso.' }};
  const all = RAW.casos || [];
  let hits = all.filter(r => normCaso(r.caso) === nq);
  if (!hits.length && /^[0-9]+$/.test(nq)) {{
    hits = all.filter(r => normCaso(r.caso).split('-').pop() === nq);
  }}
  if (!hits.length) hits = all.filter(r => normCaso(r.caso).includes(nq));
  return {{ grupos: gruposPorCaso(hits) }};
}}
function abrirCaso(grupo) {{
  casoActivo = grupo;
  selectedDia = grupo[0].dia;
  const partes = String(grupo[0].dia || '').split('-');
  const selA = document.getElementById('cal-anio');
  const selM = document.getElementById('cal-mes');
  if ([...selA.options].some(o => o.value === partes[0])) selA.value = partes[0];
  selM.value = String(Number(partes[1] || 1));
  document.getElementById('cal-caso-hits').innerHTML = '';
  renderCalendario();
  document.getElementById('cal-day-box').scrollIntoView({{ behavior:'smooth', block:'nearest' }});
}}
function renderHitsCaso(grupos) {{
  const box = document.getElementById('cal-caso-hits');
  const show = grupos.slice(0, 30);
  const extra = grupos.length > show.length
    ? ` Mostrando los ${{show.length}} más recientes: afina el número.`
    : '';
  box.innerHTML = `<div class="msg">${{fmtN(grupos.length)}} casos coinciden.${{extra}} Elige uno.</div>`
    + show.map(g => {{
      const c = g[0];
      const centros = [...new Set(g.map(x => x.centro))].join(', ');
      return `<button type="button" class="hit"><strong>${{escHtml(c.caso)}}</strong> · ${{escHtml(c.dia)}} · ${{escHtml(c.empresa)}} · ${{escHtml(centros)}} · ${{escHtml(c.veterinario)}}</button>`;
    }}).join('');
  box.querySelectorAll('button.hit').forEach((btn, i) => {{
    btn.addEventListener('click', () => abrirCaso(show[i]));
  }});
}}
function buscarCaso() {{
  const q = document.getElementById('cal-caso').value;
  const res = buscarGruposCaso(q);
  const box = document.getElementById('cal-caso-hits');
  if (res.error) {{ box.innerHTML = `<div class="msg">${{res.error}}</div>`; return; }}
  if (!res.grupos.length) {{
    box.innerHTML = `<div class="msg">No hay un caso “${{escHtml(normCaso(q))}}” con muestreo desde 2024.</div>`;
    return;
  }}
  if (res.grupos.length === 1) {{ abrirCaso(res.grupos[0]); return; }}
  renderHitsCaso(res.grupos);
}}
function limpiarCaso() {{
  casoActivo = null;
  document.getElementById('cal-caso').value = '';
  document.getElementById('cal-caso-hits').innerHTML = '';
  if (selectedDia) showDiaDetalle(selectedDia, false);
  else {{
    document.getElementById('cal-detail-title').textContent = 'Resumen del día';
    document.getElementById('cal-detail-body').innerHTML = '<em style="color:var(--muted)">Sin día seleccionado</em>';
    document.getElementById('cal-day-box').classList.remove('highlight');
  }}
}}
function fichaCaso(grupo) {{
  const c = grupo[0];
  const nCaso = grupo.reduce((a, r) => a + (Number(r.n) || 0), 0);
  const costoCaso = grupo.reduce((a, r) => a + (Number(r.costo_operativo_clp) || 0), 0);
  const centros = [...new Set(grupo.map(r => r.centro))].join(', ');
  const progs = [...new Set(grupo.map(r => r.programa))].join(', ');
  const vets = [...new Set(grupo.map(r => r.veterinario))].join(', ');
  const sedes = [...new Set(grupo.map(r => r.sede))].join(', ');
  const empresas = [...new Set(grupo.map(r => r.empresa))].join(', ');
  return `<div class="caso-ficha">
      <div><div class="k">Caso</div><div class="v">${{escHtml(c.caso)}}</div></div>
      <div><div class="k">Día de muestreo</div><div class="v">${{escHtml(c.dia)}}</div></div>
      <div><div class="k">Veterinario</div><div class="v">${{escHtml(vets)}}</div></div>
      <div><div class="k">Sede</div><div class="v">${{escHtml(sedes)}}</div></div>
      <div><div class="k">Empresa</div><div class="v">${{escHtml(empresas)}}</div></div>
      <div><div class="k">Centro</div><div class="v">${{escHtml(centros)}}</div></div>
      <div><div class="k">Programa</div><div class="v">${{escHtml(progs)}}</div></div>
      <div><div class="k">Líneas del caso</div><div class="v">${{fmtN(nCaso)}} · op. ${{fmtM(costoCaso)}}</div></div>
    </div>
    <p class="desc">Todo lo realizado el ${{escHtml(c.dia)}}, sin recortar por veterinario, cliente, sede ni programa. La fila resaltada incluye este caso.</p>`;
}}

let casosPorLinea = null;
function indiceCasosLinea() {{
  if (casosPorLinea) return casosPorLinea;
  const map = new Map();
  (RAW.casos || []).forEach(c => {{
    const k = [c.dia, c.veterinario, c.sede, c.empresa, c.centro || '', c.programa].join('\\t');
    const arr = map.get(k);
    if (arr) arr.push(c.caso);
    else map.set(k, [c.caso]);
  }});
  casosPorLinea = map;
  return map;
}}
function casosDeFila(dia, r) {{
  const k = [dia, r.veterinario, r.sede, r.empresa, r.centro || '', r.programa].join('\\t');
  return indiceCasosLinea().get(k) || [];
}}
function htmlCasos(ids) {{
  const list = [...new Set(ids)].sort((a, b) => String(a).localeCompare(String(b), 'es', {{ numeric: true }}));
  if (!list.length) return '—';
  return list.map(escHtml).join('<br>');
}}
let costosPlanilla = null;
function claveCo(dia, vet, emp, centro) {{
  return [dia, vet, emp, centro || ''].map(x => String(x || '').trim().toUpperCase()).join('\\t');
}}
function indiceCostos() {{
  if (costosPlanilla) return costosPlanilla;
  const map = new Map();
  (RAW.costos || []).forEach(c => {{
    map.set(claveCo(c.dia, c.veterinario, c.empresa, c.centro), c);
  }});
  costosPlanilla = map;
  return map;
}}
function costoDeFila(r) {{
  return indiceCostos().get(claveCo(r.dia, r.veterinario, r.empresa, r.centro)) || {{ co_km: 0, co_uf: 0, co_otros: 0 }};
}}
function sumarCostos(rows) {{
  const seen = new Set();
  let km = 0, uf = 0, otros = 0;
  (rows || []).forEach(r => {{
    const k = claveCo(r.dia, r.veterinario, r.empresa, r.centro);
    if (seen.has(k)) return;
    seen.add(k);
    const c = indiceCostos().get(k);
    if (!c) return;
    km += Number(c.co_km) || 0;
    uf += Number(c.co_uf) || 0;
    otros += Number(c.co_otros) || 0;
  }});
  return {{ km, uf, otros }};
}}
function sinOperativo(km, uf, otros) {{
  const cero = n => Math.abs(Number(n) || 0) < 0.0001;
  return cero(km) && cero(uf) && cero(otros);
}}
function esScreening(nombre) {{
  return String(nombre || '').toUpperCase().includes('SCREEN');
}}
function soloScreening(programas) {{
  const list = Array.isArray(programas) ? programas : String(programas || '').split(',');
  const limpios = list.map(p => String(p).trim()).filter(Boolean);
  return limpios.length > 0 && limpios.every(esScreening);
}}
function faltaOperativo(km, uf, otros, programas) {{
  if (soloScreening(programas)) return false;
  return sinOperativo(km, uf, otros);
}}
function celdaAlertaCo(km, uf, otros, programas) {{
  return faltaOperativo(km, uf, otros, programas) ? '<td class="co-alerta">OPERATIVO NO INGRESADO</td>' : '<td></td>';
}}
function unirLista(vals) {{
  return [...new Set((vals || []).filter(v => v != null && String(v) !== ''))]
    .sort((a, b) => String(a).localeCompare(String(b), 'es'))
    .join(', ');
}}
function agruparVisitas(rows, dia, grupo) {{
  const map = new Map();
  const order = [];
  (rows || []).forEach(r => {{
    const k = claveCo(r.dia, r.veterinario, r.empresa, r.centro);
    let g = map.get(k);
    if (!g) {{
      g = {{
        dia: r.dia, veterinario: r.veterinario, empresa: r.empresa, centro: r.centro || '',
        sedes: [], programas: [], casos: [],
        n: 0, venta_clp: 0, costo_operativo_clp: 0, hit: false
      }};
      map.set(k, g);
      order.push(g);
    }}
    g.sedes.push(r.sede);
    g.programas.push(r.programa);
    casosDeFila(r.dia, r).forEach(id => g.casos.push(id));
    g.n += Number(r.n) || 0;
    g.venta_clp += Number(r.venta_clp) || 0;
    g.costo_operativo_clp += Number(r.costo_operativo_clp) || 0;
    if (grupo && mismaLineaCaso(r, grupo)) g.hit = true;
  }});
  return order.map(g => {{
    const c = costoDeFila(g);
    return {{
      dia: g.dia, veterinario: g.veterinario, empresa: g.empresa, centro: g.centro,
      sede: unirLista(g.sedes), programa: unirLista(g.programas), casos: g.casos,
      n: g.n, venta_clp: g.venta_clp, costo_operativo_clp: g.costo_operativo_clp,
      co_km: c.co_km, co_uf: c.co_uf, co_otros: c.co_otros, hit: g.hit
    }};
  }});
}}

function showDiaDetalle(dia, doScroll=true, grupo=null) {{
  selectedDia = dia;
  document.querySelectorAll('.cal-day.selected').forEach(el => el.classList.remove('selected'));
  const cell = document.querySelector(`.cal-day[data-dia="${{dia}}"]`);
  if (cell) cell.classList.add('selected');

  const box = document.getElementById('cal-day-box');
  box.classList.add('highlight');
  const fuente = grupo ? (RAW.calendario || []) : calTableRows;
  const rows = fuente.filter(r => r.dia === dia)
    .sort((a,b) => String(a.veterinario).localeCompare(String(b.veterinario), 'es')
      || String(a.empresa).localeCompare(String(b.empresa), 'es')
      || String(a.centro||'').localeCompare(String(b.centro||''), 'es')
      || String(a.programa||'').localeCompare(String(b.programa||''), 'es'));
  document.getElementById('cal-detail-title').textContent = grupo
    ? `Caso ${{grupo[0].caso}} · día de muestreo ${{dia}}`
    : `Resumen del día · ${{dia}}`;
  if (!rows.length) {{
    const msg = grupo
      ? 'Ese caso no tiene actividad de muestreo cargada en el calendario.'
      : 'Sin muestreo ese día con el filtro actual';
    document.getElementById('cal-detail-body').innerHTML = (grupo ? fichaCaso(grupo) : '')
      + `<em style="color:var(--muted)">${{msg}}</em>`;
    if (doScroll) box.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
    return;
  }}
  const byVet = new Map();
  rows.forEach(r => {{
    const k = r.veterinario;
    const cur = byVet.get(k) || {{ vet:k, n:0, venta:0, costo:0, empresas:new Set(), programas:new Set(), sedes:new Set(), centros:new Set(), casos:new Set(), filas:[] }};
    cur.n += Number(r.n)||0;
    cur.venta += Number(r.venta_clp)||0;
    cur.costo += Number(r.costo_operativo_clp)||0;
    cur.empresas.add(r.empresa);
    cur.programas.add(r.programa);
    cur.sedes.add(r.sede);
    cur.centros.add(r.centro || '(sin centro)');
    cur.filas.push(r);
    casosDeFila(dia, r).forEach(id => cur.casos.add(id));
    byVet.set(k, cur);
  }});
  const vets = [...byVet.values()].sort((a,b)=>b.costo-a.costo);
  const coDia = sumarCostos(rows);
  document.getElementById('cal-detail-body').innerHTML = `
    ${{grupo ? fichaCaso(grupo) : ''}}
    <p class="desc">${{fmtN(rows.reduce((a,r)=>a+(Number(r.n)||0),0))}} registros del día · venta ${{fmtM(sum(rows))}} · <strong>costo operativo ${{fmtM(sum(rows,'costo_operativo_clp'))}}</strong> · CO km ${{fmtDec(coDia.km)}} · aumentos ${{fmtUf2(coDia.uf)}} UF · otros CO ${{fmt(coDia.otros)}}</p>
    <div class="scroll">
    <table>
      <thead><tr><th>Veterinario</th><th>Sede</th><th>Empresas</th><th>Centros</th><th>Programas</th><th>Casos</th><th class="num">N</th><th class="num">Venta $</th><th class="num">Costo operativo $</th><th class="num">CO km</th><th class="num">Aumentos UF</th><th class="num">Otros CO $</th><th>Comentario</th></tr></thead>
      <tbody>
        ${{vets.map(v => {{
          const co = sumarCostos(v.filas);
          const falta = faltaOperativo(co.km, co.uf, co.otros, [...v.programas]);
          return `<tr${{falta ? ' class="co-falta"' : ''}}>
          <td>${{v.vet}}</td>
          <td>${{[...v.sedes].join(', ')}}</td>
          <td>${{[...v.empresas].join(', ')}}</td>
          <td>${{[...v.centros].join(', ')}}</td>
          <td>${{[...v.programas].join(', ')}}</td>
          <td>${{htmlCasos(v.casos)}}</td>
          <td class="num">${{fmtN(v.n)}}</td>
          <td class="num">${{fmt(v.venta)}}</td>
          <td class="num">${{fmt(v.costo)}}</td>
          <td class="num">${{fmtDec(co.km)}}</td>
          <td class="num">${{fmtUf2(co.uf)}}</td>
          <td class="num">${{fmt(co.otros)}}</td>
          ${{celdaAlertaCo(co.km, co.uf, co.otros, [...v.programas])}}
        </tr>`;
        }}).join('')}}
        <tr style="font-weight:700;background:#F7FAFC">
          <td colspan="6">TOTAL DEL DÍA</td>
          <td class="num">${{fmtN(rows.reduce((a,r)=>a+(Number(r.n)||0),0))}}</td>
          <td class="num">${{fmt(sum(rows))}}</td>
          <td class="num">${{fmt(sum(rows,'costo_operativo_clp'))}}</td>
          <td class="num">${{fmtDec(coDia.km)}}</td>
          <td class="num">${{fmtUf2(coDia.uf)}}</td>
          <td class="num">${{fmt(coDia.otros)}}</td>
          <td></td>
        </tr>
      </tbody>
    </table>
    <h4 style="margin:14px 0 6px;color:var(--navy)">Detalle por centro</h4>
    <table>
      <thead><tr><th>Caso</th><th>Veterinario</th><th>Sede</th><th>Empresa</th><th>Centro</th><th>Programas</th><th class="num">N</th><th class="num">Costo op. $</th><th class="num">CO km</th><th class="num">Aumentos UF</th><th class="num">Otros CO $</th><th>Comentario</th></tr></thead>
      <tbody>
        ${{agruparVisitas(rows, dia, grupo).map(v => {{
          const falta = faltaOperativo(v.co_km, v.co_uf, v.co_otros, v.programa);
          const cls = [v.hit ? 'caso-hit' : '', falta ? 'co-falta' : ''].filter(Boolean).join(' ');
          return `<tr${{cls ? ` class="${{cls}}"` : ''}}>
          <td>${{htmlCasos(v.casos)}}</td>
          <td>${{v.veterinario}}</td><td>${{v.sede}}</td><td>${{v.empresa}}</td>
          <td>${{v.centro||''}}</td><td>${{v.programa}}</td>
          <td class="num">${{fmtN(v.n)}}</td><td class="num">${{fmt(v.costo_operativo_clp)}}</td>
          <td class="num">${{fmtDec(v.co_km)}}</td><td class="num">${{fmtUf2(v.co_uf)}}</td><td class="num">${{fmt(v.co_otros)}}</td>
          ${{celdaAlertaCo(v.co_km, v.co_uf, v.co_otros, v.programa)}}
        </tr>`;
        }}).join('')}}
        <tr style="font-weight:700;background:#F7FAFC">
          <td colspan="6">TOTAL</td>
          <td class="num">${{fmtN(rows.reduce((a,r)=>a+(Number(r.n)||0),0))}}</td>
          <td class="num">${{fmt(sum(rows,'costo_operativo_clp'))}}</td>
          <td class="num">${{fmtDec(coDia.km)}}</td>
          <td class="num">${{fmtUf2(coDia.uf)}}</td>
          <td class="num">${{fmt(coDia.otros)}}</td>
          <td></td>
        </tr>
      </tbody>
    </table>
    </div>`;
  if (doScroll) box.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
}}

function csvNum(n) {{
  return (Math.round((Number(n) || 0) * 10) / 10).toFixed(1).replace('.', ',');
}}

function downloadCalExcel() {{
  const rows = calTableRows;
  if (!rows.length) {{ alert('No hay filas para exportar con el filtro actual.'); return; }}
  const headers = ['Dia','Veterinario','Sede','Empresa','Centros','Programa','Casos','N','Venta_CLP','Costo_Operativo_CLP','CO_km','Aumentos_UF','Otros_CO','Comentario'];
  const lines = [headers.join(';')];
  const visitas = agruparTablaMes(rows);
  visitas.forEach(v => {{
    lines.push([
      v.dia, v.veterinario, v.sede, v.empresa, v.centro||'', v.programa, textoCasos(v.casos),
      Number(v.n)||0,
      Math.round(Number(v.venta_clp)||0),
      Math.round(Number(v.costo_operativo_clp)||0),
      Math.round(Number(v.co_km)||0),
      (Number(v.co_uf)||0).toFixed(2).replace('.', ','),
      Math.round(Number(v.co_otros)||0),
      faltaOperativo(v.co_km, v.co_uf, v.co_otros, v.programa) ? 'OPERATIVO NO INGRESADO' : ''
    ].map(v => {{
      const s = String(v ?? '');
      return /[;"\\n]/.test(s) ? `"${{s.replace(/"/g,'""')}}"` : s;
    }}).join(';'));
  }});
  const totN = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  const co = costosTablaMes(visitas);
  lines.push(['TOTAL','','','','','','', totN, Math.round(sum(rows)), Math.round(sum(rows,'costo_operativo_clp')), Math.round(co.km), (Number(co.uf)||0).toFixed(2).replace('.', ','), Math.round(co.otros), ''].join(';'));
  const bom = '\\uFEFF';
  const blob = new Blob([bom + lines.join('\\r\\n')], {{ type: 'text/csv;charset=utf-8;' }});
  const anio = document.getElementById('cal-anio').value;
  const mes = document.getElementById('cal-mes').value;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `calendario_veterinarios_${{anio}}-${{String(mes).padStart(2,'0')}}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}}

function refreshCal() {{
  fillCalFilters();
  renderCalendario();
}}

function filasFacturaCaso(q) {{
  const nq = normCaso(q);
  if (!nq || nq.length < 3) return {{ error: 'Escribe al menos 3 caracteres del caso.' }};
  const all = RAW.facturas || [];
  let hits = all.filter(r => normCaso(r.caso) === nq);
  if (!hits.length && /^[0-9]+$/.test(nq)) {{
    hits = all.filter(r => normCaso(r.caso).split('-').pop() === nq);
  }}
  if (!hits.length) hits = all.filter(r => normCaso(r.caso).includes(nq));
  const map = new Map();
  hits.forEach(r => {{
    const k = normCaso(r.caso);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(r);
  }});
  const grupos = [...map.values()].sort((a, b) =>
    String(a[0].caso).localeCompare(String(b[0].caso), 'es')
  );
  return {{ grupos }};
}}
function ordenDocs(rows) {{
  return rows.slice().sort((a, b) =>
    String(b.fecha || '').localeCompare(String(a.fecha || ''))
    || String(b.factura || '').localeCompare(String(a.factura || ''), 'es', {{ numeric: true }})
    || String(b.prefactura || '').localeCompare(String(a.prefactura || ''), 'es', {{ numeric: true }})
  );
}}
function docNum(v) {{
  const s = String(v ?? '').trim();
  return s ? escHtml(s) : '—';
}}
function pintarFacturaCaso(rows) {{
  const box = document.getElementById('fac-caso-result');
  const c = rows[0];
  const empresas = [...new Set(rows.map(r => r.empresa).filter(Boolean))];
  const docs = ordenDocs(rows);
  box.innerHTML = `
    <p class="desc"><strong>${{escHtml(c.caso)}}</strong>${{empresas.length ? ' · ' + escHtml(empresas.join(', ')) : ''}}</p>
    <table>
      <thead><tr><th>Pre-factura</th><th>Factura</th><th>Estado</th><th>Fecha facturación</th></tr></thead>
      <tbody>
        ${{docs.map(r => `<tr>
          <td>${{docNum(r.prefactura)}}</td>
          <td>${{docNum(r.factura)}}</td>
          <td>${{escHtml(r.estado || '')}}</td>
          <td>${{escHtml(r.fecha || '—')}}</td>
        </tr>`).join('')}}
      </tbody>
    </table>`;
}}
function renderHitsFactura(grupos) {{
  const box = document.getElementById('fac-caso-hits');
  const show = grupos.slice(0, 30);
  const extra = grupos.length > show.length ? ` Mostrando ${{show.length}}. Afina el número.` : '';
  box.innerHTML = `<div class="msg">${{fmtN(grupos.length)}} casos coinciden.${{extra}} Elige uno.</div>`
    + show.map(g => {{
      const c = g[0];
      const facs = [...new Set(g.map(x => x.factura).filter(Boolean))].join(', ') || '—';
      const pres = [...new Set(g.map(x => x.prefactura).filter(Boolean))].join(', ') || '—';
      return `<button type="button" class="hit"><strong>${{escHtml(c.caso)}}</strong> · pre ${{escHtml(pres)}} · fac ${{escHtml(facs)}}</button>`;
    }}).join('');
  box.querySelectorAll('button.hit').forEach((btn, i) => {{
    btn.addEventListener('click', () => {{
      box.innerHTML = '';
      pintarFacturaCaso(show[i]);
    }});
  }});
}}
function buscarFacturaCaso() {{
  const q = document.getElementById('fac-caso').value;
  const res = filasFacturaCaso(q);
  const hits = document.getElementById('fac-caso-hits');
  const box = document.getElementById('fac-caso-result');
  box.innerHTML = '';
  if (res.error) {{ hits.innerHTML = `<div class="msg">${{res.error}}</div>`; return; }}
  if (!res.grupos.length) {{
    hits.innerHTML = `<div class="msg">No hay un caso “${{escHtml(normCaso(q))}}” en la consulta.</div>`;
    return;
  }}
  hits.innerHTML = '';
  if (res.grupos.length === 1) {{ pintarFacturaCaso(res.grupos[0]); return; }}
  renderHitsFactura(res.grupos);
}}
function limpiarFacturaCaso() {{
  document.getElementById('fac-caso').value = '';
  document.getElementById('fac-caso-hits').innerHTML = '';
  document.getElementById('fac-caso-result').innerHTML = '';
}}

document.getElementById('btn-buscar-fac-caso').addEventListener('click', buscarFacturaCaso);
document.getElementById('btn-limpiar-fac-caso').addEventListener('click', limpiarFacturaCaso);
document.getElementById('fac-caso').addEventListener('keydown', ev => {{
  if (ev.key === 'Enter') {{ ev.preventDefault(); buscarFacturaCaso(); }}
}});
document.getElementById('btn-buscar-caso').addEventListener('click', buscarCaso);
document.getElementById('btn-limpiar-caso').addEventListener('click', limpiarCaso);
document.getElementById('cal-caso').addEventListener('keydown', ev => {{
  if (ev.key === 'Enter') {{ ev.preventDefault(); buscarCaso(); }}
}});
document.getElementById('btn-excel-cal').addEventListener('click', downloadCalExcel);
document.getElementById('btn-excel-cal-resumen').addEventListener('click', downloadCalResumenExcel);
['cal-resumen-anio','cal-resumen-mes','cal-resumen-programa'].forEach(id => {{
  document.getElementById(id).addEventListener('change', renderCalResumen);
}});
['cal-tabla-anio','cal-tabla-mes','cal-tabla-empresa','cal-tabla-programa'].forEach(id => {{
  document.getElementById(id).addEventListener('change', () => {{
    if (id === 'cal-tabla-mes') calTablaMesManual = true;
    if (id === 'cal-tabla-anio') calTablaAnioManual = true;
    renderCalTable();
  }});
}});
['cal-anio','cal-mes','cal-ocultar-na'].forEach(id => {{
  document.getElementById(id).addEventListener('change', () => {{
    if (id === 'cal-ocultar-na') fillCalFilters();
    renderCalendario();
  }});
}});

fillFilters();
['f-anio','f-mes','f-programa','f-empresa','f-estado'].forEach(id => {{
  document.getElementById(id).addEventListener('change', renderAnalisis);
}});
renderAnalisis();
if (typeof adlAplicarSede === 'function') adlAplicarSede();
refreshCal();
['cal-vet','cal-cliente','cal-sede','cal-programa'].forEach(id => {{
  document.getElementById(id).addEventListener('change', renderCalendario);
}});
if (typeof adlApplyCalendarioOnly === 'function') adlApplyCalendarioOnly();
</script>
</body>
</html>
"""


def main() -> None:
    print("Cargando credenciales...")
    cfg = cargar_credenciales()
    vista = cfg["VISTA"]
    print(f"Conectando a {cfg['SERVIDOR']} / {cfg['BASE']} · {vista}")
    conn = conectar(cfg)
    cur = conn.cursor()
    print("Consultando (solo lectura)...")
    datos = analizar(cur, vista)
    conn.close()

    payload = {
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "servidor": cfg["SERVIDOR"],
        "base": cfg["BASE"],
        "vista": vista,
        **datos,
    }
    OUT_HTML.write_text(render_html(payload), encoding="utf-8")
    print(f"OK -> {OUT_HTML}")
    print(f"  Serie: {len(datos['serie']):,} grupos · Calendario: {len(datos['calendario']):,} filas · Casos: {len(datos['casos']):,} · Facturas: {len(datos['facturas']):,} · Costos planilla: {len(datos['costos']):,}")
    k = datos["kpis"]
    print(f"  Venta CLP facturada: ${k.get('venta_clp_facturada') or 0:,.0f}")
    try:
        from enviar_alertas_operativo import enviar_alertas
        enviar_alertas(datos["calendario"], datos["costos"])
    except Exception as exc:
        print(f"AVISO: las alertas por correo no se enviaron: {exc}")


if __name__ == "__main__":
    main()
