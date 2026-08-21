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
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresa)), ''), '(sin empresa)') AS empresa,
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
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresa)), ''), '(sin empresa)'),
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
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresa)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)') AS programa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)') AS centro,
            COUNT(*) AS n,
            SUM({EXPR_CLP}) AS venta_clp,
            SUM(CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(nombre_seccion,'')))) = 'COSTO OPERATIVO'
                     THEN {EXPR_CLP} ELSE 0 END) AS costo_operativo_clp
        FROM {vista}
        WHERE TRY_CONVERT(date, fecha_muestreo, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_muestreo, 103) >= '2024-01-01'
        GROUP BY
            CONVERT(char(10), TRY_CONVERT(date, fecha_muestreo, 103), 23),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_veterinario)), ''), '(sin veterinario)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresa)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_centro)), ''), '(sin centro)')
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

    return {"serie": serie, "calendario": calendario, "kpis": kpis}


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADL · Consulta facturación</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script src="auth.js"></script>
<style>
:root {{
  --adl-navy:#003E6D; --adl-orange:#F37021; --adl-teal:#0A8F9C;
  --navy:#003E6D; --orange:#F37021; --teal:#0A8F9C;
  --ink:#0F2A40; --muted:#5B738B; --line:#D7E3EE; --bg:#EEF3F8; --panel:#fff;
  --ok:#2F9E71; --danger:#D64545;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"IBM Plex Sans",system-ui,sans-serif; color:var(--ink);
  background: linear-gradient(180deg,#F7FAFC 0%, var(--bg) 40%, #E8EEF4 100%);
}}
.topnav {{
  display:flex; justify-content:space-between; align-items:center; gap:14px; flex-wrap:wrap;
  padding:12px 18px; background:rgba(255,255,255,.92); border-bottom:1px solid var(--line);
  position:sticky; top:0; z-index:40; backdrop-filter:blur(8px);
}}
.brand-row {{ display:flex; align-items:center; gap:12px; }}
.brand-row img {{ height:44px; background:#fff; border-radius:8px; padding:2px; }}
.brand-text {{ font-weight:700; color:var(--navy); font-size:1.05rem; }}
.brand-text span {{ color:var(--orange); }}
.nav-links {{ display:flex; gap:8px; flex-wrap:wrap; }}
.nav-links a, .nav-links button {{
  text-decoration:none; color:var(--navy); border:1px solid var(--line); background:#fff;
  padding:9px 14px; border-radius:999px; font:inherit; font-size:.88rem; cursor:pointer;
}}
.nav-links a:hover {{ border-color:var(--orange); color:var(--orange); }}
.nav-links a.active {{ background:var(--navy); color:#fff; border-color:var(--navy); }}
.chip {{ background:#fff; border:1px solid var(--line); }}
.wrap {{ max-width:1240px; margin:0 auto; padding:14px 18px 28px; }}
.subhead {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:baseline; margin-bottom:12px; }}
.subhead h2 {{ margin:0; font-size:1.1rem; color:var(--navy); }}
.subhead p {{ margin:0; color:var(--teal); font-size:.85rem; font-weight:600; }}
.meta {{ color:var(--muted); font-size:.78rem; text-align:right; line-height:1.45; }}
.tabs {{ display:flex; gap:8px; margin-bottom:12px; }}
.tabs button {{
  border:1px solid var(--line); background:#fff; color:var(--navy); border-radius:999px;
  padding:8px 16px; font:inherit; cursor:pointer;
}}
.tabs button.active {{ background:var(--navy); color:#fff; border-color:var(--navy); }}
.tab-pane {{ display:none; }}
.tab-pane.active {{ display:block; }}
.filters {{
  display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end;
  background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:12px 14px;
  margin-bottom:14px; position:relative; z-index:30;
}}
.filters label.f {{ display:flex; flex-direction:column; gap:4px; font-size:.75rem; color:var(--muted); min-width:150px; }}
.filters .hint-multi {{ width:100%; font-size:.72rem; color:var(--muted); margin:0; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }}
.kpi {{
  background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px 14px;
  border-left:4px solid var(--navy);
}}
.kpi.accent {{ border-left-color:var(--orange); }}
.kpi.ok {{ border-left-color:var(--ok); }}
.kpi .l {{ font-size:.7rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
.kpi .v {{ font-size:1.2rem; font-weight:700; color:var(--navy); margin-top:3px; }}
.kpi .h {{ font-size:.75rem; color:var(--muted); margin-top:2px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
.panel {{
  background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:12px 14px;
}}
.panel h3 {{ margin:0 0 4px; font-size:.95rem; color:var(--navy); }}
.panel .desc {{ margin:0 0 8px; color:var(--muted); font-size:.8rem; }}
.chart-wrap {{ position:relative; height:280px; }}
.chart-wrap.tall {{ height:340px; }}
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
.cal-detail th, .cal-detail td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:left; }}
.cal-detail th {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; }}
.cal-detail td.num, .cal-detail th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.cal-detail .scroll {{ max-height:360px; overflow:auto; }}
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
<div class="topnav">
  <div class="brand-row">
    <img src="logo_adl.png" alt="ADL" onerror="this.style.display='none'" />
    <div class="brand-text">Dashboard <span>Facturación</span></div>
  </div>
  <div class="nav-links">
    <a href="dashboard_facturacion.html">Unificado</a>
    <a href="dashboard_facturacion_excel.html">Solo facturación</a>
    <a class="active" href="consulta_facturacion.html">Consulta facturación</a>
    <a href="reglas.html">Reglas</a>
    <button type="button" class="chip" style="border-radius:999px;padding:9px 14px" onclick="adlLogout()">Salir</button>
  </div>
</div>
<div class="wrap">
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
      <p class="desc">Empresas y programas por veterinario. Costo operativo = sección “Costo Operativo” (UF × UF del día).</p>
      <div class="filters" id="cal-filters" style="margin:10px 0 12px; box-shadow:none">
        <p class="hint-multi">Puedes marcar varios veterinarios, sedes y programas.</p>
        <label class="f">Veterinario<div class="msel" id="cal-vet" data-empty="Todos"></div></label>
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
        <p class="desc">Haz clic en un día del calendario para ver empresas, programas y costo operativo.</p>
        <div id="cal-detail-body"><em style="color:var(--muted)">Sin día seleccionado</em></div>
      </div>
      <div class="cal-detail" style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center">
          <div>
            <h3 id="cal-table-title" style="margin:0">Tabla del mes</h3>
            <p class="desc" id="cal-table-desc" style="margin:4px 0 0">Detalle filtrado del calendario</p>
          </div>
          <button type="button" class="chip" id="btn-excel-cal" style="border-radius:999px;padding:9px 14px;background:var(--ok);color:#fff;border-color:var(--ok)">Descargar Excel</button>
        </div>
        <div class="scroll" style="max-height:420px;overflow:auto;margin-top:10px">
          <table id="cal-table">
            <thead>
              <tr>
                <th>Día</th><th>Veterinario</th><th>Sede</th><th>Empresa</th><th>Centro</th><th>Programa</th>
                <th class="num">N</th><th class="num">Venta $</th><th class="num">Costo operativo $</th>
              </tr>
            </thead>
            <tbody id="cal-tbody"></tbody>
            <tfoot id="cal-tfoot"></tfoot>
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
        <li>Por cada día se listan <strong>veterinario</strong>, <strong>sede</strong> (lugar de análisis), <strong>empresa</strong>, <strong>centro</strong> y <strong>programa</strong>.</li>
        <li><strong>Costo operativo $</strong> = solo filas cuya sección es <strong>“Costo Operativo”</strong>, convertidas a pesos (UF × UF del día).</li>
        <li><strong>Venta $</strong> = todas las filas del filtro (UF × UF del día), útil como referencia.</li>
        <li>Datos de calendario cargados desde <strong>2024 en adelante</strong>.</li>
      </ul>

      <h4>Cómo se hace el match / cruce</h4>
      <ul>
        <li><strong>Día</strong> ← <code>fecha_muestreo</code> (formato día/mes/año de la vista).</li>
        <li><strong>Veterinario</strong> ← <code>nombre_veterinario</code> (se puede ocultar “No aplica” / “Cliente”).</li>
        <li><strong>Sede</strong> ← <code>nombre_lugaranalisis</code> (Puerto Montt / Aysén / Villarrica).</li>
        <li><strong>Empresa</strong> ← <code>nombre_empresa</code>.</li>
        <li><strong>Centro</strong> ← <code>nombre_centro</code>.</li>
        <li><strong>Programa</strong> ← <code>nombre_programa</code>.</li>
        <li>Los filtros del calendario (veterinario, sede, programa) son multi-selección: vacío = todos.</li>
        <li>Al hacer clic en un día se arma el resumen del día sumando N, venta $ y costo operativo $ por veterinario y el detalle por centro.</li>
        <li>La tabla del mes y el Excel exportan el mismo detalle filtrado (día, vet, sede, empresa, centro, programa, montos).</li>
      </ul>

      <h4>Qué NO incluye este calendario</h4>
      <ul>
        <li>No incluye días de <strong>vuelo</strong>.</li>
        <li>No incluye <strong>hospedaje</strong>.</li>
        <li>No incluye <strong>puerto cerrado</strong>.</li>
        <li>No incluye días de <strong>muestreo de calidad</strong>.</li>
      </ul>
      <div class="warn">
        Este calendario refleja actividad de muestreo operativo registrada en FVivaldi (Web Salud).
        Los conceptos de vuelo, hospedaje, puerto cerrado y muestreo de calidad quedan fuera del alcance de esta hoja;
        no deben usarse estos totales para esos ítems.
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
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Por año', {{ conTotal:false }}) }},
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
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Mensual', {{ conTotal:false }}) }},
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
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Programa', {{ conTotal:false }}) }},
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
      plugins: {{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Empresa', {{ conTotal:false }}) }},
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
        tooltip: {{ callbacks: {{ label: c => `${{c.label}}: ${{fmtN(c.raw)}} · ${{fmtM(porEst[c.dataIndex]?.venta_clp||0)}}` }} }} }}
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
        tooltip: tipGrupo(() => 'Año × programa', {{ conTotal:true }})
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
  const prevS = selectedMulti('cal-sede');
  const prevP = selectedMulti('cal-programa');
  fillMulti('cal-vet', uniqueSorted(rows.map(r => r.veterinario)), prevV.filter(v => rows.some(r => r.veterinario===v)));
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
}}

function filteredCalRows() {{
  const anio = Number(document.getElementById('cal-anio').value);
  const mes = Number(document.getElementById('cal-mes').value);
  const vets = new Set(selectedMulti('cal-vet'));
  const sedes = new Set(selectedMulti('cal-sede'));
  const progs = new Set(selectedMulti('cal-programa'));
  const prefix = `${{anio}}-${{String(mes).padStart(2,'0')}}`;
  return calBaseRows().filter(r => {{
    if (!String(r.dia||'').startsWith(prefix)) return false;
    if (vets.size && !vets.has(r.veterinario)) return false;
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
    || String(a.centro||'').localeCompare(String(b.centro||''), 'es'));

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
    const open = () => showDiaDetalle(el.dataset.dia);
    el.addEventListener('click', open);
    el.addEventListener('keydown', (ev) => {{ if (ev.key === 'Enter' || ev.key === ' ') {{ ev.preventDefault(); open(); }} }});
  }});

  renderCalTable();
  if (selectedDia && selectedDia.startsWith(`${{anio}}-${{String(mes).padStart(2,'0')}}`))
    showDiaDetalle(selectedDia, false);
}}

function renderCalTable() {{
  const rows = calTableRows;
  document.getElementById('cal-table-title').textContent = 'Tabla del mes (filtro actual)';
  document.getElementById('cal-table-desc').textContent =
    `${{rows.length}} filas · costo operativo total ${{fmtM(sum(rows, 'costo_operativo_clp'))}}`;
  document.getElementById('cal-tbody').innerHTML = rows.map(r => `
    <tr>
      <td>${{r.dia||''}}</td>
      <td>${{r.veterinario||''}}</td>
      <td>${{r.sede||''}}</td>
      <td>${{r.empresa||''}}</td>
      <td>${{r.centro||''}}</td>
      <td>${{r.programa||''}}</td>
      <td class="num">${{fmtN(r.n)}}</td>
      <td class="num">${{fmt(r.venta_clp)}}</td>
      <td class="num">${{fmt(r.costo_operativo_clp)}}</td>
    </tr>`).join('') || `<tr><td colspan="9" style="color:var(--muted)">Sin datos para el filtro</td></tr>`;
  const totN = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  document.getElementById('cal-tfoot').innerHTML = rows.length ? `
    <tr style="font-weight:700;background:#F7FAFC">
      <td colspan="6">TOTAL</td>
      <td class="num">${{fmtN(totN)}}</td>
      <td class="num">${{fmt(sum(rows))}}</td>
      <td class="num">${{fmt(sum(rows, 'costo_operativo_clp'))}}</td>
    </tr>` : '';
}}

function showDiaDetalle(dia, doScroll=true) {{
  selectedDia = dia;
  document.querySelectorAll('.cal-day.selected').forEach(el => el.classList.remove('selected'));
  const cell = document.querySelector(`.cal-day[data-dia="${{dia}}"]`);
  if (cell) cell.classList.add('selected');

  const box = document.getElementById('cal-day-box');
  box.classList.add('highlight');
  const rows = calTableRows.filter(r => r.dia === dia)
    .sort((a,b) => (b.costo_operativo_clp||0)-(a.costo_operativo_clp||0));
  document.getElementById('cal-detail-title').textContent = `Resumen del día · ${{dia}}`;
  if (!rows.length) {{
    document.getElementById('cal-detail-body').innerHTML = '<em style="color:var(--muted)">Sin muestreo ese día con el filtro actual</em>';
    if (doScroll) box.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
    return;
  }}
  const byVet = new Map();
  rows.forEach(r => {{
    const k = r.veterinario;
    const cur = byVet.get(k) || {{ vet:k, n:0, venta:0, costo:0, empresas:new Set(), programas:new Set(), sedes:new Set(), centros:new Set() }};
    cur.n += Number(r.n)||0;
    cur.venta += Number(r.venta_clp)||0;
    cur.costo += Number(r.costo_operativo_clp)||0;
    cur.empresas.add(r.empresa);
    cur.programas.add(r.programa);
    cur.sedes.add(r.sede);
    cur.centros.add(r.centro || '(sin centro)');
    byVet.set(k, cur);
  }});
  const vets = [...byVet.values()].sort((a,b)=>b.costo-a.costo);
  document.getElementById('cal-detail-body').innerHTML = `
    <p class="desc">${{fmtN(rows.reduce((a,r)=>a+(Number(r.n)||0),0))}} registros · venta ${{fmtM(sum(rows))}} · <strong>costo operativo ${{fmtM(sum(rows,'costo_operativo_clp'))}}</strong></p>
    <div class="scroll">
    <table>
      <thead><tr><th>Veterinario</th><th>Sede</th><th>Empresas</th><th>Centros</th><th>Programas</th><th class="num">N</th><th class="num">Venta $</th><th class="num">Costo operativo $</th></tr></thead>
      <tbody>
        ${{vets.map(v => `<tr>
          <td>${{v.vet}}</td>
          <td>${{[...v.sedes].join(', ')}}</td>
          <td>${{[...v.empresas].join(', ')}}</td>
          <td>${{[...v.centros].join(', ')}}</td>
          <td>${{[...v.programas].join(', ')}}</td>
          <td class="num">${{fmtN(v.n)}}</td>
          <td class="num">${{fmt(v.venta)}}</td>
          <td class="num">${{fmt(v.costo)}}</td>
        </tr>`).join('')}}
        <tr style="font-weight:700;background:#F7FAFC">
          <td colspan="5">TOTAL DEL DÍA</td>
          <td class="num">${{fmtN(rows.reduce((a,r)=>a+(Number(r.n)||0),0))}}</td>
          <td class="num">${{fmt(sum(rows))}}</td>
          <td class="num">${{fmt(sum(rows,'costo_operativo_clp'))}}</td>
        </tr>
      </tbody>
    </table>
    <h4 style="margin:14px 0 6px;color:var(--navy)">Detalle por centro</h4>
    <table>
      <thead><tr><th>Veterinario</th><th>Sede</th><th>Empresa</th><th>Centro</th><th>Programa</th><th class="num">N</th><th class="num">Costo op. $</th></tr></thead>
      <tbody>
        ${{rows.map(r => `<tr>
          <td>${{r.veterinario}}</td><td>${{r.sede}}</td><td>${{r.empresa}}</td>
          <td>${{r.centro||''}}</td><td>${{r.programa}}</td>
          <td class="num">${{fmtN(r.n)}}</td><td class="num">${{fmt(r.costo_operativo_clp)}}</td>
        </tr>`).join('')}}
      </tbody>
    </table>
    </div>`;
  if (doScroll) box.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
}}

function downloadCalExcel() {{
  const rows = calTableRows;
  if (!rows.length) {{ alert('No hay filas para exportar con el filtro actual.'); return; }}
  const headers = ['Dia','Veterinario','Sede','Empresa','Centro','Programa','N','Venta_CLP','Costo_Operativo_CLP'];
  const lines = [headers.join(';')];
  rows.forEach(r => {{
    lines.push([
      r.dia, r.veterinario, r.sede, r.empresa, r.centro||'', r.programa,
      Number(r.n)||0,
      Math.round(Number(r.venta_clp)||0),
      Math.round(Number(r.costo_operativo_clp)||0)
    ].map(v => {{
      const s = String(v ?? '');
      return /[;"\\n]/.test(s) ? `"${{s.replace(/"/g,'""')}}"` : s;
    }}).join(';'));
  }});
  const totN = rows.reduce((a,r)=>a+(Number(r.n)||0),0);
  lines.push(['TOTAL','','','','','', totN, Math.round(sum(rows)), Math.round(sum(rows,'costo_operativo_clp'))].join(';'));
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

document.getElementById('btn-excel-cal').addEventListener('click', downloadCalExcel);
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
refreshCal();
['cal-vet','cal-sede','cal-programa'].forEach(id => {{
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
    print(f"  Serie: {len(datos['serie']):,} grupos · Calendario: {len(datos['calendario']):,} filas")
    k = datos["kpis"]
    print(f"  Venta CLP facturada: ${k.get('venta_clp_facturada') or 0:,.0f}")


if __name__ == "__main__":
    main()
