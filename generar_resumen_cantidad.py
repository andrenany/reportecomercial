# -*- coding: utf-8 -*-
"""
Replica la página Power BI «Resumen Cantidad» (solo lectura).

No modifica el .pbix. Fuente SQL: dbo.vw_FVivaldiWebSalud (credenciales.env).

Filtros de UI: empresa, sede, unidad, calendario (año/mes), programa.
Cantidad = SUM(fac_n_analisis) por fecha_recepcion.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from chart_tools import CSS_CHART_TOOLS, JS_CHART_TOOLS, panel_chart
from generar_consulta_facturacion import cargar_credenciales, conectar

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

BASE_DIR = Path(__file__).resolve().parent
OUT_HTML = BASE_DIR / "resumen_cantidad.html"
VISTA = "dbo.vw_FVivaldiWebSalud"

MES_NOM = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

REGLAS_HTML = """
  <section class="rules-full" id="reglas-cantidad">
    <div class="panel rules-box" style="margin-top:16px">
      <h3>Reglas de Resumen cantidad</h3>
      <p class="desc" style="margin:0 0 8px">Criterios de esta página. Réplica de Power BI «Resumen Cantidad»; el archivo .pbix no se modifica.</p>
      <h4>De dónde salen los datos</h4>
      <ul>
        <li>Servidor SQL <code>192.168.10.5</code>, base <code>ControlDeGestion</code>, vista <code>dbo.vw_FVivaldiWebSalud</code> (solo lectura, mismas credenciales que el resto del reporte).</li>
        <li>La página Power BI usa además el modelo de diagnóstico en <code>LaboratorioADL</code> (vistas <code>WEB_Analista_BMolecularDET</code>, <code>WEB_Analista_Recepcion</code>, <code>WEB_Analista_BacteriologiaRESULTADO</code>). El usuario SQL de este reporte no tiene SELECT ahí; por eso aquí se lee FVivaldi.</li>
        <li>Fecha de calendario = <code>fecha_recepcion</code> (día/mes/año). Serie desde 2017.</li>
      </ul>
      <h4>Cómo se cuenta un análisis</h4>
      <ul>
        <li><strong>Cantidad de análisis</strong> = suma de <code>fac_n_analisis</code> de cada fila. No es el recuento de filas ni de casos.</li>
        <li>Una misma recepción puede aportar más de un análisis si <code>fac_n_analisis</code> &gt; 1.</li>
        <li>Periodo actual = filtros de calendario (año/mes) + empresa + sede + unidad + programa.</li>
        <li>Periodo anterior = mismos meses, un año antes. Si no eliges mes y el año actual llega p. ej. hasta septiembre, el anterior es enero–septiembre del año previo (no el año completo).</li>
        <li>Variación = actual − anterior. % variación = variación / anterior.</li>
        <li>El gráfico <strong>Por año</strong> no usa el filtro de calendario; sí empresa, sede, unidad y programa.</li>
        <li>Si el calendario cubre más de un año, las tablas Excel de meses incluyen el año en cada fila (p. ej. Enero 2025, Enero 2026).</li>
      </ul>
      <h4>Filtros de esta página</h4>
      <ul>
        <li><strong>Empresa</strong> ← <code>nombre_empresaservicios</code> (en el BI: E.Facturar).</li>
        <li><strong>Sede</strong> ← <code>nombre_lugaranalisis</code> (Puerto Montt, Aysén, Villarrica…).</li>
        <li><strong>Unidad</strong> ← <code>nombre_seccion</code> (Biología molecular, bacteriología, microscopía, costo operativo, etc.).</li>
        <li><strong>Calendario</strong> ← año y mes de <code>fecha_recepcion</code>. Vacío = todos.</li>
        <li><strong>Programa</strong> ← <code>nombre_programa</code>.</li>
        <li>Multi-selección: vacío = todos los valores (salvo las exclusiones fijas de abajo).</li>
      </ul>
    </div>
    <div class="rules-grid">
      <div class="panel rules-box" style="margin:0">
        <h3>Empresas que se excluyen siempre</h3>
        <p class="desc">Filtro de página del BI sobre E.Facturar (no aparecen en filtros ni gráficos).</p>
        <ul>
          <li><code>ADL Diagnostic Chile Ltda.</code></li>
          <li><code>ADL Diagnostic Chile SpA</code></li>
        </ul>
        <p class="desc" style="margin-top:10px">En SQL se aplica como nombre de empresa que contiene «ADL Diagnostic».</p>
      </div>
      <div class="panel rules-box" style="margin:0">
        <h3>Qué entra en la cantidad</h3>
        <ul>
          <li>Entran todas las secciones/unidades de FVivaldi salvo las exclusiones de empresa y ELF: diagnóstico, microscopía, histopatología, costo operativo, I+D, etc., si tienen <code>fac_n_analisis</code>.</li>
          <li>En el BI la medida <em>Cantidad de análisis ACT</em> es más restrictiva: cuenta técnicas de Biología Molecular + placas de bacteriología + recepción (ATBPlex, CIM/cultivos/recuentos sin antibiograma, derivaciones, cultivo celular y microscopía). No suma histopatología ni costo operativo.</li>
          <li>Esta página, al usar FVivaldi, puede dar un total distinto al del BI.</li>
        </ul>
      </div>
    </div>
    <div class="panel rules-box">
      <h3>Técnicas ELF que se excluyen siempre</h3>
      <p class="desc">Misma lista del filtro de página del BI sobre Técnica. Aquí se excluye cualquier técnica cuyo nombre contiene ELF, lo que cubre estos nombres:</p>
      <ul class="cols">
        <li>RT-PCR ELF</li>
        <li>RT-PCR ELF (BKD, IPNV)</li>
        <li>RT-PCR ELF (ISAV)</li>
        <li>RT-PCR ELF (Multiplex)</li>
        <li>RT-PCR ELF Alphavirus</li>
        <li>RT-PCR ELF Corazón-Músculo esquelético</li>
        <li>RT-PCR ELF PMCV</li>
        <li>RT-PCR ELF Riñón</li>
        <li>RT-PCR ELF Riñón anterior</li>
        <li>RT-PCR ELF Riñón IPNV</li>
        <li>RT-PCR ELF Riñón medio</li>
        <li>RT-PCR ELF Riñón posterior</li>
        <li>RT-PCR ELF Riñón-Branquia-Corazón</li>
        <li>RT-PCR ELF Riñón-Corazón</li>
        <li>RT-PCR ELF Sangre</li>
        <li>RT-PCR Multiplex (BKD-IPNV+Elf)</li>
        <li>RT-PCR Multiplex (ISAV-BKD-IPNV+Elf)</li>
        <li>RT-PCR-ELF</li>
        <li>RT-PCR-ELF (BKD, IPNV)</li>
        <li>RT-PCR-ELF (ISAV)</li>
        <li>RT-PCR-ELF Corazón-Músculo esquelético</li>
        <li>RT-PCR-ELF Riñón</li>
        <li>RT-PCR-ELF Riñón IPNV</li>
        <li>RT-PCR-ELF Riñón-Corazón</li>
        <li>RT-PCR-ELF Sangre</li>
        <li>RT-PCR-ELF Riñón-Branquia-Corazón</li>
      </ul>
    </div>
    <div class="panel rules-box">
      <h3>Gráficos, Excel y actualización</h3>
      <ul>
        <li>Gráficos de análisis: por año; técnica vs periodo anterior (top 20); empresa vs periodo anterior (top 15); por mes; por sede; por sede y mes; por programa.</li>
        <li>Bajo estas reglas: ELF por sede y ELF por sede×mes. Entran técnicas cuyo nombre contiene ELF, <strong>excepto</strong> las Multiplex.</li>
        <li>Hoja <strong>Proyección</strong>: algoritmo Prophet (Meta) sobre la serie mensual sin ELF ni empresas ADL. Filtros por sede y programa. Vacío = modelo del total; con selección = modelo de esa corte (si hay varios, se suman).</li>
        <li>Cada gráfico: vista tabla, copiar y descargar Excel. El botón verde baja todas las tablas visibles de análisis (incluye ELF).</li>
        <li>Para refrescar datos y reproyectar: <code>python generar_resumen_cantidad.py</code> (solo lectura SQL).</li>
      </ul>
    </div>
  </section>
"""


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


def nz(valor, vacio):
    if valor is None:
        return vacio
    texto = str(valor).strip()
    return texto or vacio


def internar(listas: dict[str, list[str]], clave: str, valor: str) -> int:
    idx = listas["_map"][clave]
    if valor not in idx:
        idx[valor] = len(listas[clave])
        listas[clave].append(valor)
    return idx[valor]


def es_elf(tecnica: str) -> bool:
    return "ELF" in tecnica.upper()


def es_elf_multiplex(tecnica: str) -> bool:
    return es_elf(tecnica) and "MULTIPLEX" in tecnica.upper()


def serie_mensual(filas) -> dict[tuple[int, int], float]:
    tot: dict[tuple[int, int], float] = defaultdict(float)
    for r in filas:
        tot[(int(r[0]), int(r[1]))] += float(r[7] or 0)
    return tot


def _puntos_solo_real(tot: dict[tuple[int, int], float], anio_objetivo: int) -> list[dict]:
    puntos = []
    for y in range(anio_objetivo, anio_objetivo + 2):
        for mth in range(1, 13):
            val = tot.get((y, mth))
            puntos.append({
                "anio": y,
                "mes": mth,
                "real": int(round(val)) if val is not None else None,
                "yhat": None,
                "lo": None,
                "hi": None,
            })
    return puntos


def proyectar_prophet(tot: dict[tuple[int, int], float], anio_objetivo: int, recortar: bool = False) -> dict:
    """Serie mensual + pronóstico Prophet hasta dic. del año siguiente."""
    last_real = max(tot) if tot else None
    hasta_real = f"{last_real[0]:04d}-{last_real[1]:02d}" if last_real else None
    if len(tot) < 24:
        return {
            "ok": True,
            "solo_real": True,
            "anio_default": anio_objetivo,
            "anios": [anio_objetivo, anio_objetivo + 1],
            "hasta_real": hasta_real,
            "puntos": _puntos_solo_real(tot, anio_objetivo),
        }

    hist = sorted(tot)
    df = pd.DataFrame({
        "ds": [pd.Timestamp(y, m, 1) for y, m in hist],
        "y": [tot[k] for k in hist],
    })
    last = df["ds"].max()
    fin = pd.Timestamp(anio_objetivo + 1, 12, 1)
    periodos = max(0, (fin.year - last.year) * 12 + (fin.month - last.month))

    from prophet import Prophet

    modelo = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",
    )
    modelo.fit(df)
    futuro = modelo.make_future_dataframe(periods=periodos, freq="MS")
    pred = modelo.predict(futuro)
    real_map = {(y, m): int(round(tot[(y, m)])) for y, m in hist}
    puntos = []
    for _, row in pred.iterrows():
        ds = pd.Timestamp(row["ds"])
        y, mth = int(ds.year), int(ds.month)
        if recortar and y < anio_objetivo:
            continue
        puntos.append({
            "anio": y,
            "mes": mth,
            "real": real_map.get((y, mth)),
            "yhat": max(0, int(round(float(row["yhat"])))),
            "lo": max(0, int(round(float(row["yhat_lower"])))),
            "hi": max(0, int(round(float(row["yhat_upper"])))),
        })
    anios = sorted({p["anio"] for p in puntos if p["anio"] >= anio_objetivo})
    if anio_objetivo not in anios:
        anios = [anio_objetivo] + anios
    return {
        "ok": True,
        "solo_real": False,
        "anio_default": anio_objetivo,
        "anios": anios,
        "hasta_real": last.strftime("%Y-%m"),
        "puntos": puntos,
    }


def _ajustar_grupo(filas, anio_objetivo: int) -> dict:
    tot = serie_mensual(filas)
    try:
        return proyectar_prophet(tot, anio_objetivo, recortar=True)
    except Exception:
        return {
            "ok": True,
            "solo_real": True,
            "puntos": _puntos_solo_real(tot, anio_objetivo),
        }


def _ajustar_mapa(grupos: dict[str, list], anio_objetivo: int) -> tuple[dict, list, list]:
    por: dict[str, list] = {}
    con_modelo: list[str] = []
    for nombre, filas in grupos.items():
        if not filas:
            continue
        res = _ajustar_grupo(filas, anio_objetivo)
        por[nombre] = res.get("puntos") or []
        if res.get("ok") and not res.get("solo_real"):
            con_modelo.append(nombre)
    nombres = sorted(por.keys(), key=lambda s: s.casefold())
    return por, nombres, sorted(con_modelo, key=lambda s: s.casefold())


def proyectar_cantidad(filas_main: list, dims: dict, anio_objetivo: int) -> dict:
    print("  · proyección Prophet (total)...")
    try:
        base = proyectar_prophet(serie_mensual(filas_main), anio_objetivo)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "por_programa": {}, "programas": []}

    by_p: dict[str, list] = defaultdict(list)
    by_s: dict[str, list] = defaultdict(list)
    by_sp: dict[str, list] = defaultdict(list)
    nom_p = dims.get("p") or []
    nom_s = dims.get("s") or []
    for r in filas_main:
        sede = nom_s[int(r[3])] if int(r[3]) < len(nom_s) else "(sin sede)"
        prog = nom_p[int(r[5])] if int(r[5]) < len(nom_p) else "(sin programa)"
        by_p[prog].append(r)
        by_s[sede].append(r)
        by_sp[f"{sede}||{prog}"].append(r)

    print(f"  · proyección Prophet por programa ({len(by_p)})...")
    por_p, programas, prog_ok = _ajustar_mapa(by_p, anio_objetivo)
    print(f"    {len(prog_ok)} programas con modelo")
    print(f"  · proyección Prophet por sede ({len(by_s)})...")
    por_s, sedes, sede_ok = _ajustar_mapa(by_s, anio_objetivo)
    print(f"    {len(sede_ok)} sedes con modelo")
    print(f"  · proyección Prophet sede×programa ({len(by_sp)})...")
    por_sp, _, sp_ok = _ajustar_mapa(by_sp, anio_objetivo)
    print(f"    {len(sp_ok)} combinaciones con modelo")

    base["por_programa"] = por_p
    base["programas"] = programas
    base["programas_prophet"] = prog_ok
    base["por_sede"] = por_s
    base["sedes"] = sedes
    base["sedes_prophet"] = sede_ok
    base["por_sede_programa"] = por_sp
    base["sede_programa_prophet"] = sp_ok
    return base


def consultar_cantidad(cur, vista: str) -> dict:
    if vista.lower() not in {VISTA.lower(), "dbo.vw_fvivaldiwebsalud"}:
        raise ValueError(f"Vista no permitida: {vista}")

    print("  · cubo cantidad (año×mes×empresa×sede×unidad×programa×técnica)...")
    cur.execute(
        f"""
        SELECT
            YEAR(TRY_CONVERT(date, fecha_recepcion, 103)) AS anio,
            MONTH(TRY_CONVERT(date, fecha_recepcion, 103)) AS mes,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)') AS empresa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)') AS sede,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_seccion)), ''), '(sin unidad)') AS unidad,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)') AS programa,
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_tecnica)), ''), '(sin tecnica)') AS tecnica,
            SUM(CAST(ISNULL(fac_n_analisis, 0) AS FLOAT)) AS n
        FROM {vista}
        WHERE TRY_CONVERT(date, fecha_recepcion, 103) IS NOT NULL
          AND TRY_CONVERT(date, fecha_recepcion, 103) >= '2017-01-01'
          AND ISNULL(nombre_empresaservicios, '') NOT LIKE '%ADL Diagnostic%'
        GROUP BY
            YEAR(TRY_CONVERT(date, fecha_recepcion, 103)),
            MONTH(TRY_CONVERT(date, fecha_recepcion, 103)),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_empresaservicios)), ''), '(sin empresa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_lugaranalisis)), ''), '(sin sede)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_seccion)), ''), '(sin unidad)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_programa)), ''), '(sin programa)'),
            ISNULL(NULLIF(LTRIM(RTRIM(nombre_tecnica)), ''), '(sin tecnica)')
        """
    )
    cols = [c[0] for c in cur.description]
    dims = {
        "e": [], "s": [], "u": [], "p": [], "t": [],
        "_map": {"e": {}, "s": {}, "u": {}, "p": {}, "t": {}},
    }
    rows = []
    elf_rows = []
    anios = set()
    for raw in cur.fetchall():
        rec = {c: serializar(v) for c, v in zip(cols, raw)}
        anio = rec.get("anio")
        mes = rec.get("mes")
        if not anio or not mes:
            continue
        n = rec.get("n") or 0
        tecnica = nz(rec.get("tecnica"), "(sin tecnica)")
        fila = [
            int(anio),
            int(mes),
            internar(dims, "e", nz(rec.get("empresa"), "(sin empresa)")),
            internar(dims, "s", nz(rec.get("sede"), "(sin sede)")),
            internar(dims, "u", nz(rec.get("unidad"), "(sin unidad)")),
            internar(dims, "p", nz(rec.get("programa"), "(sin programa)")),
            internar(dims, "t", tecnica),
            int(round(float(n))),
        ]
        if es_elf(tecnica):
            if not es_elf_multiplex(tecnica):
                elf_rows.append(fila)
            continue
        rows.append(fila)
        anios.add(int(anio))

    del dims["_map"]
    anio_obj = datetime.now().year
    print("  · proyección Prophet...")
    proyeccion = proyectar_cantidad(rows, dims, anio_obj)
    return {
        "dims": dims,
        "rows": rows,
        "elf": elf_rows,
        "anios": sorted(anios),
        "anio_default": max(anios) if anios else anio_obj,
        "n_grupos": len(rows),
        "total": sum(r[-1] for r in rows),
        "n_elf": len(elf_rows),
        "total_elf": sum(r[-1] for r in elf_rows),
        "proyeccion": proyeccion,
    }


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    p_anio = panel_chart(
        "Por año",
        "Evolución de la cantidad de análisis. No aplica el filtro de calendario (año/mes), sí empresa, sede, unidad y programa.",
        "cAnio",
        excel=True,
    )
    p_tec = panel_chart(
        "Por técnica vs periodo anterior",
        "Top 20 técnicas del periodo actual comparado con los mismos meses del año anterior.",
        "cTec",
        "xtall",
        excel=True,
    )
    p_emp = panel_chart(
        "Por empresa vs periodo anterior",
        "Top 15 empresas del periodo actual comparado con los mismos meses del año anterior.",
        "cEmp",
        "xtall",
        excel=True,
    )
    p_mes = panel_chart(
        "Por periodo",
        "Cantidad mensual del calendario seleccionado vs el mismo mes del año anterior.",
        "cMes",
        excel=True,
    )
    p_sede = panel_chart(
        "Por sede",
        "Periodo actual, anterior y % de variación.",
        "cSede",
        excel=True,
    )
    p_sede_mes = panel_chart(
        "Por sede y mes",
        "Cantidad mensual del periodo actual, una línea por sede. Si hay más de un año, el eje y el Excel muestran mes + año.",
        "cSedeMes",
        excel=True,
    )
    p_prog = panel_chart(
        "Por programa",
        "Periodo actual, anterior y % de variación.",
        "cProg",
        excel=True,
    )
    p_elf_sede = panel_chart(
        "ELF por sede",
        "Técnicas ELF del periodo (sin Multiplex). Actual vs mismo periodo del año anterior.",
        "cElfSede",
        excel=True,
    )
    p_elf_sede_mes = panel_chart(
        "ELF por sede y mes",
        "ELF sin Multiplex, una línea por sede. Si hay más de un año, mes + año en eje y Excel.",
        "cElfSedeMes",
        excel=True,
    )
    p_proy = panel_chart(
        "Real vs proyección Prophet",
        "Línea de fondo = cantidad real (sin ELF). Línea punteada = pronóstico Prophet del año, sede y programa elegidos. Vacío = total.",
        "cProy",
        excel=True,
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADL · Resumen cantidad</title>
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
.subhead {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:flex-start; margin-bottom:12px; }}
.subhead h2 {{ margin:0; font-size:1.1rem; color:var(--navy); }}
.subhead p {{ margin:4px 0 0; color:var(--teal); font-size:.85rem; font-weight:600; }}
.meta {{ color:var(--muted); font-size:.78rem; text-align:right; line-height:1.45; }}
.filters {{
  display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end;
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px;
  margin-bottom:14px; position:relative; z-index:30;
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.filters label.f {{ display:flex; flex-direction:column; gap:5px; font-size:.7rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); min-width:160px; flex:1; }}
.filters .hint-multi {{ width:100%; font-size:.72rem; color:var(--muted); margin:0; text-transform:none; letter-spacing:0; font-weight:400; }}
.kpis {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; margin-bottom:14px; }}
@media (max-width:1100px) {{ .kpis {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }} }}
.kpi {{
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px 16px 14px;
  border-left:4px solid var(--navy);
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.kpi.accent {{ border-left-color:var(--orange); }}
.kpi.ok {{ border-left-color:var(--ok); }}
.kpi.warn {{ border-left-color:var(--danger); }}
.kpi .l {{ font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
.kpi .v {{ font-family:Manrope,sans-serif; font-size:1.38rem; font-weight:800; color:var(--navy); margin-top:6px; letter-spacing:-.02em; }}
.kpi .h {{ font-size:.76rem; color:var(--muted); margin-top:4px; }}
.grid3 {{ display:grid; grid-template-columns:1.2fr 1fr 1fr; gap:14px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }}
@media (max-width:1200px) {{ .grid3, .grid2 {{ grid-template-columns:1fr; }} }}
.panel {{
  background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:16px;
  box-shadow:0 4px 16px rgba(0,62,109,.05);
}}
.panel h2 {{ margin:0 0 4px; font-family:Manrope,sans-serif; font-size:1.02rem; color:var(--navy); }}
.panel .desc {{ margin:0; color:var(--muted); font-size:.82rem; }}
.rules-box {{
  background:#fff; border:1px solid var(--line); border-radius:16px; padding:16px 18px; margin-top:14px;
}}
.rules-box h3 {{ margin:0 0 10px; color:var(--navy); font-size:1.05rem; font-family:Manrope,sans-serif; }}
.rules-box h4 {{ margin:14px 0 6px; color:var(--adl-teal); font-size:.88rem; }}
.rules-box ul {{ margin:0; padding-left:1.2rem; color:var(--muted); line-height:1.55; }}
.rules-box li {{ margin:4px 0; }}
.rules-box strong {{ color:var(--ink); }}
.rules-box code {{ font-size:.82em; background:#F0F6FA; padding:1px 5px; border-radius:6px; }}
.rules-grid {{
  display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px;
}}
@media (max-width:980px) {{ .rules-grid {{ grid-template-columns:1fr; }} }}
.rules-box .cols {{
  columns: 2; column-gap: 18px; margin: 0; padding-left: 1.2rem; color: var(--muted);
}}
@media (max-width:700px) {{ .rules-box .cols {{ columns: 1; }} }}
.rules-box .cols li {{ break-inside: avoid; font-size: .82rem; }}
.page-tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }}
.page-tabs button {{
  border:1px solid var(--line); background:#fff; color:var(--navy);
  padding:9px 16px; border-radius:999px; font:inherit; font-size:.85rem; font-weight:700; cursor:pointer;
}}
.page-tabs button.on {{
  background:linear-gradient(135deg, var(--navy), var(--adl-navy-soft));
  color:#fff; border-color:transparent;
}}
.tab-pane {{ display:none; }}
.tab-pane.on {{ display:block; }}
.proy-note {{ color:var(--muted); font-size:.82rem; margin:0 0 12px; line-height:1.45; }}
footer {{ text-align:center; color:var(--muted); font-size:.78rem; padding:16px; }}
{CSS_CHART_TOOLS}
</style>
</head>
<body>
<div class="wrap">
<div class="topnav">
  <div class="brand-row">
    <img src="logo_adl.png" alt="ADL" onerror="this.style.display='none'" />
    <div class="brand-text">Dashboard <span>Diagnóstico</span></div>
  </div>
  <div class="nav-links">
    <a href="dashboard_facturacion.html">Unificado</a>
    <a href="dashboard_facturacion_excel.html">Solo facturación</a>
    <a href="consulta_facturacion.html">Consulta facturación</a>
    <a class="active" href="resumen_cantidad.html">Resumen cantidad</a>
    <a href="reglas.html">Reglas</a>
    <button type="button" class="chip" style="border-radius:999px;padding:9px 14px" onclick="adlLogout()">Salir</button>
  </div>
</div>
  <div class="subhead">
    <div>
      <h2>Resumen cantidad</h2>
      <p>Vista SQL · vw_FVivaldiWebSalud · cantidad = fac_n_analisis · fecha de recepción</p>
    </div>
    <div class="meta" id="meta"></div>
  </div>
  <div class="page-tabs" role="tablist">
    <button type="button" class="on" data-tab="analisis">Análisis</button>
    <button type="button" data-tab="proyeccion">Proyección</button>
  </div>

  <div class="tab-pane on" id="tab-analisis">
  <div class="filters" id="filters">
    <p class="hint-multi">Filtros multi-selección. Vacío = todos. Calendario = año y mes de recepción. El periodo anterior son los mismos meses del año previo.</p>
    <label class="f">Empresa<div class="msel" id="f-empresa" data-empty="Todas"></div></label>
    <label class="f">Sede<div class="msel" id="f-sede" data-empty="Todas"></div></label>
    <label class="f">Unidad<div class="msel" id="f-unidad" data-empty="Todas"></div></label>
    <label class="f">Calendario · año<div class="msel" id="f-anio" data-empty="Todos"></div></label>
    <label class="f">Calendario · mes<div class="msel" id="f-mes" data-empty="Todos"></div></label>
    <label class="f">Programa<div class="msel" id="f-programa" data-empty="Todos"></div></label>
    <div class="f" style="min-width:200px;text-transform:none">
      <span style="font-size:.7rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)">Excel</span>
      <button type="button" class="chip" data-excel-all="resumen_cantidad.xlsx" style="border-radius:999px;padding:10px 14px;background:var(--ok);color:#fff;border-color:var(--ok);text-transform:none">Descargar todas las tablas</button>
    </div>
  </div>

  <div class="kpis" id="kpis"></div>
  <div class="grid3">
    {p_anio}
    {p_tec}
    {p_emp}
  </div>
  <div class="grid2">
    {p_mes}
    {p_sede}
  </div>
  <div style="margin-top:14px">
    {p_sede_mes}
  </div>
  <div style="margin-top:14px">
    {p_prog}
  </div>
{REGLAS_HTML}
  <div class="grid2">
    {p_elf_sede}
    {p_elf_sede_mes}
  </div>
  </div>

  <div class="tab-pane" id="tab-proyeccion">
    <div class="filters">
      <p class="proy-note">Algoritmo: Prophet (Meta). Se entrena al generar esta página, sin ELF ni empresas ADL. Vacío en sede y programa = modelo del total. Si filtras, cada corte tiene su propio modelo (con varios, se suman). Fondo = real; punteada = pronóstico.</p>
      <label class="f">Año a proyectar
        <select id="f-proy-anio" style="border:1px solid var(--line);border-radius:12px;padding:10px 12px;font:inherit;color:var(--ink);background:#fff"></select>
      </label>
      <label class="f">Sede<div class="msel" id="f-proy-sede" data-empty="Todas"></div></label>
      <label class="f">Programa<div class="msel" id="f-proy-programa" data-empty="Todos"></div></label>
      <div class="f" style="min-width:200px;text-transform:none">
        <span style="font-size:.7rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)">Excel</span>
        <button type="button" class="chip" data-excel="cProy" style="border-radius:999px;padding:10px 14px;background:var(--ok);color:#fff;border-color:var(--ok);text-transform:none">Descargar proyección</button>
      </div>
    </div>
    <div class="kpis" id="kpis-proy"></div>
    {p_proy}
    <div class="panel rules-box" style="margin-top:14px">
      <h3>Cómo leer la proyección</h3>
      <h4>Algoritmo</h4>
      <ul>
        <li>Se usa <strong>Prophet 1.1.7</strong> (Meta / Facebook, Taylor y Letham): un modelo aditivo de series de tiempo, no una red neuronal ni un ARIMA clásico.</li>
        <li>Fórmula: <code>y(t) = tendencia g(t) + estacionalidad s(t) + error</code>. La tendencia es lineal a tramos (growth lineal por defecto). La estacionalidad es <strong>anual</strong> (componentes de Fourier), porque los datos son mensuales: se apagan la semanal y la diaria. No se cargan feriados.</li>
        <li>El ajuste es bayesiano aproximado (MAP) con Stan/CmdStan. El intervalo inferior/superior es incertidumbre del modelo, no un compromiso comercial ni un intervalo de predicción “garantizado”.</li>
        <li>Los valores proyectados se recortan a ≥ 0 (no se informan cantidades negativas).</li>
      </ul>
      <h4>Cómo se construye la serie y se proyecta</h4>
      <ul>
        <li>Fuente: suma mensual de <code>fac_n_analisis</code> por <code>fecha_recepcion</code>, desde 2017. Se excluyen técnicas ELF y empresas cuyo nombre contiene «ADL Diagnostic».</li>
        <li>Se agrupa al primer día de cada mes. Hace falta un mínimo de <strong>24 meses</strong> con dato para entrenar; si no llega, esa corte muestra solo lo real, sin línea punteada.</li>
        <li>Se entrena con toda la historia hasta el último mes cerrado y se pronostica mes a mes hasta diciembre del año siguiente al actual (hoy: resto de 2026 y todo 2027).</li>
        <li>En el gráfico, la línea de fondo (navy, relleno) es lo <strong>real</strong>; la punteada naranja es el <strong>yhat</strong> de Prophet. En meses ya cerrados puedes comparar ambas; en los que aún no hay recepción, solo hay pronóstico.</li>
        <li>Al regenerar con <code>python generar_resumen_cantidad.py</code> se reentrena con la historia nueva (sirve igual para 2027, 2028, etc.).</li>
      </ul>
      <h4>Filtros de esta hoja</h4>
      <ul>
        <li><strong>Año</strong>: qué calendario miras (2026, 2027, …).</li>
        <li><strong>Sede</strong> y <strong>Programa</strong> vacíos: un solo modelo Prophet sobre el total.</li>
        <li>Solo sede, o solo programa: cada valor elegido tiene su propio modelo; si marcas varios, se suman real y pronóstico.</li>
        <li>Sede y programa a la vez: se usa el modelo de cada combinación sede×programa (no es el producto de los dos filtros por separado).</li>
        <li>Empresa, unidad y calendario de la hoja Análisis no aplican aquí.</li>
      </ul>
    </div>
  </div>
</div>
<footer>ADL Diagnostic Chile · solo lectura SQL · el archivo Power BI no se modifica</footer>
<script>
const RAW = {data};
const MESES = {json.dumps(MES_NOM[1:], ensure_ascii=False)};
const PAL = {{ act:'#003E6D', ant:'#70BBFF', var:'#F37021', line:'#0A8F9C' }};
const SEDE_COLS = ['#003E6D','#F37021','#0A8F9C','#2F9E71','#7B68A6','#E8A317','#D64545','#5B738B'];
const charts = {{}};
function fmtN(v) {{
  return (Number(v)||0).toLocaleString('es-CL', {{ maximumFractionDigits: 0 }});
}}
function fmt(v) {{ return fmtN(v); }}
{JS_CHART_TOOLS}
function fmtPct(v) {{
  if (v == null || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
}}
function shortLabel(s, n=36) {{
  const t = String(s||'');
  return t.length > n ? t.slice(0, n-1) + '…' : t;
}}
function uniqueSorted(arr) {{
  return [...new Set(arr.map(v => String(v)))].sort((a,b) => a.localeCompare(b,'es',{{numeric:true}}));
}}
function ymKey(a, m) {{ return Number(a) * 100 + Number(m); }}
function ymParts(k) {{ return {{ y: Math.floor(Number(k) / 100), m: Number(k) % 100 }}; }}
function ymMulti(keys) {{
  return new Set([...keys].map(k => Math.floor(Number(k) / 100))).size > 1;
}}
function ymLab(k, multi) {{
  const {{ y, m }} = ymParts(k);
  return multi ? (MESES[m - 1] + ' ' + y) : MESES[m - 1];
}}
function monthHeaders(multi) {{ return multi ? ['Año', 'Mes'] : ['Mes']; }}
function monthCells(k, multi) {{
  const {{ y, m }} = ymParts(k);
  return multi ? [y, MESES[m - 1]] : [MESES[m - 1]];
}}
function addNested(root, a, b, n) {{
  if (!root.has(a)) root.set(a, new Map());
  const inner = root.get(a);
  inner.set(b, (inner.get(b) || 0) + n);
}}
function currentFilters() {{
  return {{
    emp: new Set(selectedMulti('f-empresa')),
    sede: new Set(selectedMulti('f-sede')),
    unid: new Set(selectedMulti('f-unidad')),
    anio: new Set(selectedMulti('f-anio').map(Number)),
    mes: new Set(selectedMulti('f-mes').map(Number)),
    prog: new Set(selectedMulti('f-programa')),
  }};
}}
function passDims(r, f) {{
  const D = RAW.dims;
  if (f.emp.size && !f.emp.has(D.e[r[2]])) return false;
  if (f.sede.size && !f.sede.has(D.s[r[3]])) return false;
  if (f.unid.size && !f.unid.has(D.u[r[4]])) return false;
  if (f.prog.size && !f.prog.has(D.p[r[5]])) return false;
  return true;
}}
function passCal(r, f) {{
  if (f.anio.size && !f.anio.has(r[0])) return false;
  if (f.mes.size && !f.mes.has(r[1])) return false;
  return true;
}}
function addMap(map, key, n) {{
  map.set(key, (map.get(key)||0) + n);
}}
function varPct(act, ant) {{
  if (!ant) return ant === 0 && act ? 100 : 0;
  return (act - ant) / ant * 100;
}}
function topEntries(map, n) {{
  return [...map.entries()].sort((a,b) => b[1]-a[1]).slice(0, n);
}}
function destroyChart(id) {{
  if (charts[id]) {{ charts[id].destroy(); delete charts[id]; }}
}}
function makeChart(id, cfg) {{
  destroyChart(id);
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, cfg);
}}
function dlInt(opts={{}}) {{
  const horiz = !!opts.horiz;
  return {{
    display: (ctx) => {{
      const v = Math.abs(Number(ctx.dataset.data[ctx.dataIndex])||0);
      if (!v) return false;
      const all = (ctx.chart.data.datasets||[]).flatMap(d => (d.data||[]).map(x => Math.abs(Number(x)||0)));
      const max = Math.max(0, ...all);
      return max ? v >= max * (opts.minRatio ?? 0.04) : true;
    }},
    formatter: (v) => fmtN(v),
    color: opts.color || '#102A43',
    font: {{ size: opts.size || 9, weight: '700', family: 'IBM Plex Sans, sans-serif' }},
    anchor: opts.anchor || (horiz ? 'end' : 'end'),
    align: opts.align || (horiz ? 'right' : 'top'),
    clamp: true,
    clip: false,
  }};
}}
const tipNum = {{
  mode: 'index',
  intersect: false,
  callbacks: {{
    label(c) {{
      const name = c.dataset.label || 'Cantidad';
      if (String(name).includes('%')) return name + ': ' + fmtPct(c.raw);
      return name + ': ' + fmtN(c.raw);
    }}
  }}
}};

function fillFilters() {{
  const D = RAW.dims;
  const prev = {{
    emp: selectedMulti('f-empresa'),
    sede: selectedMulti('f-sede'),
    unid: selectedMulti('f-unidad'),
    anio: selectedMulti('f-anio'),
    mes: selectedMulti('f-mes'),
    prog: selectedMulti('f-programa'),
  }};
  const anios = (RAW.anios || []).map(String);
  const defAnio = String(RAW.anio_default || anios[anios.length-1] || '');
  const preAnio = prev.anio.length ? prev.anio.filter(v => anios.includes(v)) : (defAnio ? [defAnio] : []);
  fillMulti('f-empresa', uniqueSorted(D.e), prev.emp);
  fillMulti('f-sede', uniqueSorted(D.s), prev.sede);
  fillMulti('f-unidad', uniqueSorted(D.u), prev.unid);
  fillMulti('f-anio', anios, preAnio);
  fillMulti('f-mes', MESES.map((_,i) => String(i+1)), prev.mes, Object.fromEntries(MESES.map((n,i)=>[String(i+1), n])));
  fillMulti('f-programa', uniqueSorted(D.p), prev.prog);
}}

function render() {{
  const f = currentFilters();
  const D = RAW.dims;
  const byYear = new Map();
  const byMonthAct = new Map();
  const byMonthAnt = new Map();
  const byEmpAct = new Map();
  const byEmpAnt = new Map();
  const byTecAct = new Map();
  const byTecAnt = new Map();
  const bySedeAct = new Map();
  const bySedeAnt = new Map();
  const byProgAct = new Map();
  const byProgAnt = new Map();
  const bySedeYm = new Map();
  const byElfSedeAct = new Map();
  const byElfSedeAnt = new Map();
  const byElfSedeYm = new Map();
  const aniosSel = f.anio.size ? [...f.anio] : (RAW.anios || []);
  const anioAntSet = f.anio.size ? new Set(aniosSel.map(a => a - 1)) : new Set();
  const mesesEnAct = new Set();
  if (!f.mes.size) {{
    for (const r of RAW.rows) {{
      if (!passDims(r, f)) continue;
      if (passCal(r, f)) mesesEnAct.add(r[1]);
    }}
    for (const r of (RAW.elf || [])) {{
      if (!passDims(r, f)) continue;
      if (passCal(r, f)) mesesEnAct.add(r[1]);
    }}
  }}
  let totAct = 0, totAnt = 0;

  function acumular(r, maps) {{
    const n = r[7] || 0;
    const inAct = passCal(r, f);
    const inAnt = anioAntSet.has(r[0]) && (f.mes.size ? f.mes.has(r[1]) : mesesEnAct.has(r[1]));
    if (inAct) {{
      maps.totAct += n;
      addMap(maps.byMonthAct, ymKey(r[0], r[1]), n);
      addMap(maps.bySedeAct, D.s[r[3]], n);
      addNested(maps.bySedeYm, D.s[r[3]], ymKey(r[0], r[1]), n);
    }}
    if (inAnt) {{
      maps.totAnt += n;
      addMap(maps.byMonthAnt, ymKey(r[0] + 1, r[1]), n);
      addMap(maps.bySedeAnt, D.s[r[3]], n);
    }}
    return {{ inAct, inAnt, n }};
  }}

  const mainMaps = {{ totAct:0, totAnt:0, byMonthAct, byMonthAnt, bySedeAct, bySedeAnt, bySedeYm }};
  for (const r of RAW.rows) {{
    if (!passDims(r, f)) continue;
    const n = r[7] || 0;
    addMap(byYear, r[0], n);
    const {{ inAct, inAnt }} = acumular(r, mainMaps);
    if (inAct) {{
      totAct += n;
      addMap(byEmpAct, D.e[r[2]], n);
      addMap(byTecAct, D.t[r[6]], n);
      addMap(byProgAct, D.p[r[5]], n);
    }}
    if (inAnt) {{
      totAnt += n;
      addMap(byEmpAnt, D.e[r[2]], n);
      addMap(byTecAnt, D.t[r[6]], n);
      addMap(byProgAnt, D.p[r[5]], n);
    }}
  }}
  totAct = mainMaps.totAct;
  totAnt = mainMaps.totAnt;

  const elfMaps = {{ totAct:0, totAnt:0, byMonthAct: new Map(), byMonthAnt: new Map(), bySedeAct: byElfSedeAct, bySedeAnt: byElfSedeAnt, bySedeYm: byElfSedeYm }};
  for (const r of (RAW.elf || [])) {{
    if (!passDims(r, f)) continue;
    acumular(r, elfMaps);
  }}

  const delta = totAct - totAnt;
  const pct = varPct(totAct, totAnt);
  const kpiCls = pct > 0.5 ? 'ok' : (pct < -0.5 ? 'warn' : 'accent');
  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div class="l">Periodo actual</div><div class="v">${{fmtN(totAct)}}</div><div class="h">Análisis según recepción</div></div>
    <div class="kpi"><div class="l">Periodo anterior</div><div class="v">${{fmtN(totAnt)}}</div><div class="h">Mismos meses, año anterior</div></div>
    <div class="kpi ${{kpiCls}}"><div class="l">Variación</div><div class="v">${{delta>=0?'+':''}}${{fmtN(delta)}}</div><div class="h">Actual − anterior</div></div>
    <div class="kpi ${{kpiCls}}"><div class="l">% variación</div><div class="v">${{fmtPct(pct)}}</div><div class="h">${{aniosSel.sort().join(', ') || 'todos los años'}}</div></div>`;

  document.getElementById('meta').innerHTML =
    RAW.generado + '<br>' + (RAW.n_grupos||0).toLocaleString('es-CL') + ' grupos · ' +
    fmtN(RAW.total) + ' análisis en el cubo';

  const years = [...byYear.keys()].sort((a,b)=>a-b);
  makeChart('cAnio', {{
    type: 'line',
    data: {{
      labels: years,
      datasets: [{{
        label: 'Cantidad de análisis',
        data: years.map(y => byYear.get(y)||0),
        borderColor: PAL.act, backgroundColor: 'rgba(0,62,109,.12)',
        fill: true, tension: .25, pointRadius: 4, borderWidth: 3,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }}, datalabels: dlInt(), tooltip: tipNum }},
      scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, x: {{ grid: {{ display: false }} }} }}
    }}
  }});
  registerChartTable('cAnio', ['Año', 'Cantidad'], years.map(y => [y, byYear.get(y)||0]));

  const tecTop = topEntries(byTecAct, 20);
  const tecLabels = tecTop.map(([k]) => shortLabel(k, 42));
  makeChart('cTec', {{
    type: 'bar',
    data: {{
      labels: tecLabels,
      datasets: [
        {{ label: 'Periodo actual', data: tecTop.map(([k]) => byTecAct.get(k)||0), backgroundColor: PAL.act, borderRadius: 6 }},
        {{ label: 'Periodo anterior', data: tecTop.map(([k]) => byTecAnt.get(k)||0), backgroundColor: PAL.ant, borderRadius: 6 }},
      ]
    }},
    options: {{
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }}, datalabels: dlInt({{ horiz:true, minRatio: 0.06 }}), tooltip: tipNum }},
      scales: {{ x: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, y: {{ ticks: {{ font: {{ size: 10 }} }} }} }}
    }}
  }});
  registerChartTable('cTec', ['Técnica', 'Actual', 'Anterior', 'Variación', '%'], tecTop.map(([k, actv]) => {{
    const antv = byTecAnt.get(k)||0;
    return [k, actv, antv, actv-antv, Number(varPct(actv, antv).toFixed(1))];
  }}));

  const empTop = topEntries(byEmpAct, 15);
  makeChart('cEmp', {{
    type: 'bar',
    data: {{
      labels: empTop.map(([k]) => shortLabel(k, 34)),
      datasets: [
        {{ label: 'Periodo actual', data: empTop.map(([k]) => byEmpAct.get(k)||0), backgroundColor: PAL.act, borderRadius: 6 }},
        {{ label: 'Periodo anterior', data: empTop.map(([k]) => byEmpAnt.get(k)||0), backgroundColor: PAL.ant, borderRadius: 6 }},
      ]
    }},
    options: {{
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }}, datalabels: dlInt({{ horiz:true, minRatio: 0.06 }}), tooltip: tipNum }},
      scales: {{ x: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, y: {{ ticks: {{ font: {{ size: 10 }} }} }} }}
    }}
  }});
  registerChartTable('cEmp', ['Empresa', 'Actual', 'Anterior', 'Variación', '%'], empTop.map(([k, actv]) => {{
    const antv = byEmpAnt.get(k)||0;
    return [k, actv, antv, actv-antv, Number(varPct(actv, antv).toFixed(1))];
  }}));

  const ymKeys = [...new Set([...byMonthAct.keys(), ...byMonthAnt.keys()])].sort((a,b)=>a-b);
  const meses = ymKeys.length ? ymKeys : [1,2,3,4,5,6,7,8,9,10,11,12].map(m => ymKey(aniosSel[0] || RAW.anio_default || 2026, m));
  const multiMes = ymMulti(meses);
  makeChart('cMes', {{
    type: 'line',
    data: {{
      labels: meses.map(k => ymLab(k, multiMes)),
      datasets: [
        {{ label: 'Periodo actual', data: meses.map(k => byMonthAct.get(k)||0), borderColor: PAL.act, backgroundColor: PAL.act, tension: .25, pointRadius: 4, borderWidth: 3 }},
        {{ label: 'Periodo anterior', data: meses.map(k => byMonthAnt.get(k)||0), borderColor: PAL.ant, backgroundColor: PAL.ant, tension: .25, pointRadius: 4, borderWidth: 3 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }}, datalabels: dlInt({{ minRatio: 0.08 }}), tooltip: tipNum }},
      scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, x: {{ grid: {{ display: false }} }} }}
    }}
  }});
  registerChartTable('cMes', [...monthHeaders(multiMes), 'Actual', 'Anterior', 'Variación', '%'], meses.map(k => {{
    const a = byMonthAct.get(k)||0, b = byMonthAnt.get(k)||0;
    return [...monthCells(k, multiMes), a, b, a-b, Number(varPct(a,b).toFixed(1))];
  }}));

  function combo(id, entries, headers, actMap, antMap) {{
    const labels = entries.map(([k]) => shortLabel(k, 28));
    const srcAct = actMap || (id === 'cSede' ? bySedeAct : byProgAct);
    const srcAnt = antMap || (id === 'cSede' ? bySedeAnt : byProgAnt);
    const actD = entries.map(([k]) => srcAct.get(k)||0);
    const antD = entries.map(([k]) => srcAnt.get(k)||0);
    const pctD = actD.map((a,i) => Number(varPct(a, antD[i]).toFixed(1)));
    makeChart(id, {{
      type: 'bar',
      data: {{
        labels,
        datasets: [
          {{ type:'bar', label:'Periodo actual', data: actD, backgroundColor: PAL.act, borderRadius: 6, yAxisID:'y' }},
          {{ type:'bar', label:'Periodo anterior', data: antD, backgroundColor: PAL.ant, borderRadius: 6, yAxisID:'y' }},
          {{ type:'line', label:'% variación', data: pctD, borderColor: PAL.var, backgroundColor: PAL.var, yAxisID:'y2', tension:.2, pointRadius:4, borderWidth:2 }},
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom' }},
          datalabels: {{
            display: (ctx) => ctx.dataset.yAxisID !== 'y2' && (Number(ctx.dataset.data[ctx.dataIndex])||0) > 0,
            formatter: (v, ctx) => ctx.dataset.yAxisID === 'y2' ? fmtPct(v) : fmtN(v),
            color: '#102A43', font: {{ size: 9, weight: '700' }}, anchor: 'end', align: 'top',
          }},
          tooltip: tipNum
        }},
        scales: {{
          y: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }},
          y2: {{ position: 'right', grid: {{ drawOnChartArea: false }}, ticks: {{ callback: v => v + '%' }} }},
          x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
        }}
      }}
    }});
    registerChartTable(id, headers, entries.map(([k], i) => [k, actD[i], antD[i], actD[i]-antD[i], pctD[i]]));
  }}
  combo('cSede', [...bySedeAct.entries()].sort((a,b)=>b[1]-a[1]), ['Sede','Actual','Anterior','Variación','%']);
  combo('cProg', topEntries(byProgAct, 12), ['Programa','Actual','Anterior','Variación','%']);
  combo('cElfSede', [...byElfSedeAct.entries()].sort((a,b)=>b[1]-a[1]), ['Sede','Actual','Anterior','Variación','%'], byElfSedeAct, byElfSedeAnt);

  function sedeMesChart(id, nested, fallbackKeys) {{
    const sedes = uniqueSorted([...nested.keys()]);
    let keys = [];
    nested.forEach(inner => inner.forEach((_, k) => keys.push(k)));
    keys = [...new Set(keys)].sort((a,b)=>a-b);
    if (!keys.length) keys = fallbackKeys.slice();
    const multi = ymMulti(keys);
    makeChart(id, {{
      type: 'line',
      data: {{
        labels: keys.map(k => ymLab(k, multi)),
        datasets: sedes.map((s, i) => {{
          const inner = nested.get(s) || new Map();
          return {{
            label: s,
            data: keys.map(k => inner.get(k) || 0),
            borderColor: SEDE_COLS[i % SEDE_COLS.length],
            backgroundColor: SEDE_COLS[i % SEDE_COLS.length],
            tension: .25, pointRadius: 3, borderWidth: 2.5, fill: false,
          }};
        }})
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }}, datalabels: {{ display: false }}, tooltip: tipNum }},
        scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, x: {{ grid: {{ display: false }} }} }}
      }}
    }});
    registerChartTable(id, [...monthHeaders(multi), ...sedes], keys.map(k => {{
      const vals = sedes.map(s => (nested.get(s) || new Map()).get(k) || 0);
      return [...monthCells(k, multi), ...vals];
    }}));
  }}
  sedeMesChart('cSedeMes', bySedeYm, meses);
  sedeMesChart('cElfSedeMes', byElfSedeYm, meses);
}}

fillFilters();
['f-empresa','f-sede','f-unidad','f-anio','f-mes','f-programa'].forEach(id => {{
  document.getElementById(id).addEventListener('change', render);
}});
render();

function mergePuntos(listas) {{
  const map = new Map();
  for (const pts of listas) {{
    if (!Array.isArray(pts)) continue;
    for (const p of pts) {{
      const k = Number(p.anio) * 100 + Number(p.mes);
      if (!map.has(k)) map.set(k, {{ anio: p.anio, mes: p.mes, real: 0, hasR: false, yhat: 0, lo: 0, hi: 0, hasY: false }});
      const t = map.get(k);
      if (p.real != null) {{ t.real += Number(p.real) || 0; t.hasR = true; }}
      if (p.yhat != null) {{ t.yhat += Number(p.yhat) || 0; t.lo += Number(p.lo) || 0; t.hi += Number(p.hi) || 0; t.hasY = true; }}
    }}
  }}
  return [...map.values()].sort((a,b) => (a.anio*100+a.mes) - (b.anio*100+b.mes)).map(t => ({{
    anio: t.anio, mes: t.mes,
    real: t.hasR ? t.real : null,
    yhat: t.hasY ? t.yhat : null,
    lo: t.hasY ? t.lo : null,
    hi: t.hasY ? t.hi : null,
  }}));
}}
function puntosProyeccion(P) {{
  const sedes = selectedMulti('f-proy-sede');
  const progs = selectedMulti('f-proy-programa');
  if (!sedes.length && !progs.length) return P.puntos || [];
  let listas = [];
  if (sedes.length && progs.length) {{
    const cruz = P.por_sede_programa || {{}};
    for (const s of sedes) for (const p of progs) {{
      const pts = cruz[s + '||' + p];
      if (pts) listas.push(pts);
    }}
  }} else if (sedes.length) {{
    const por = P.por_sede || {{}};
    listas = sedes.map(n => por[n]).filter(a => Array.isArray(a) && a.length);
  }} else {{
    const por = P.por_programa || {{}};
    listas = progs.map(n => por[n]).filter(a => Array.isArray(a) && a.length);
  }}
  return mergePuntos(listas);
}}
function etiquetaSeleccion() {{
  const sedes = selectedMulti('f-proy-sede');
  const progs = selectedMulti('f-proy-programa');
  const labS = !sedes.length ? 'Todas las sedes' : (sedes.length === 1 ? sedes[0] : sedes.length + ' sedes');
  const labP = !progs.length ? 'Todos los programas' : (progs.length === 1 ? progs[0] : progs.length + ' programas');
  return labS + ' · ' + labP;
}}
function cortesSinModelo(P) {{
  const sedes = selectedMulti('f-proy-sede');
  const progs = selectedMulti('f-proy-programa');
  if (sedes.length && progs.length) {{
    const ok = new Set(P.sede_programa_prophet || []);
    const miss = [];
    for (const s of sedes) for (const p of progs) {{
      if (!ok.has(s + '||' + p)) miss.push(s + ' / ' + p);
    }}
    return miss;
  }}
  if (sedes.length) {{
    const ok = new Set(P.sedes_prophet || []);
    return sedes.filter(n => !ok.has(n));
  }}
  if (progs.length) {{
    const ok = new Set(P.programas_prophet || []);
    return progs.filter(n => !ok.has(n));
  }}
  return [];
}}
function fillProyAnio() {{
  const sel = document.getElementById('f-proy-anio');
  if (!sel) return;
  const P = RAW.proyeccion || {{}};
  if (!P.ok) {{
    sel.innerHTML = '<option value="">Sin proyección</option>';
    return;
  }}
  const anios = P.anios || [];
  const def = String(P.anio_default || anios[0] || '');
  sel.innerHTML = anios.map(a => '<option value="' + a + '">' + a + '</option>').join('');
  sel.value = anios.map(String).includes(def) ? def : String(anios[0] || '');
}}
function fillProyFiltros() {{
  const P = RAW.proyeccion || {{}};
  fillMulti('f-proy-sede', P.sedes || uniqueSorted(RAW.dims.s || []), selectedMulti('f-proy-sede'));
  fillMulti('f-proy-programa', P.programas || uniqueSorted(RAW.dims.p || []), selectedMulti('f-proy-programa'));
}}
function renderProyeccion() {{
  const box = document.getElementById('kpis-proy');
  const P = RAW.proyeccion || {{}};
  if (!P.ok) {{
    if (box) box.innerHTML = '<div class="kpi warn"><div class="l">Proyección</div><div class="v">No disponible</div><div class="h">' + (P.error || 'Prophet no pudo entrenarse') + '</div></div>';
    destroyChart('cProy');
    return;
  }}
  const anio = Number(document.getElementById('f-proy-anio')?.value || P.anio_default);
  const sinModelo = cortesSinModelo(P);
  const pts = puntosProyeccion(P).filter(p => p.anio === anio);
  const reals = pts.map(p => p.real == null ? null : p.real);
  const yhats = pts.map(p => p.yhat == null ? null : p.yhat);
  const ambos = pts.filter(p => p.real != null && p.yhat != null);
  const totReal = pts.filter(p => p.real != null).reduce((s, p) => s + p.real, 0);
  const totYhatAnio = pts.filter(p => p.yhat != null).reduce((s, p) => s + p.yhat, 0);
  const totYhatAmbos = ambos.reduce((s, p) => s + p.yhat, 0);
  const diff = totReal - totYhatAmbos;
  const hayPron = pts.some(p => p.yhat != null);
  const hint = sinModelo.length
    ? (sinModelo.length + ' corte(s) sin Prophet: solo real')
    : etiquetaSeleccion();
  box.innerHTML = `
    <div class="kpi"><div class="l">Real ${{anio}}</div><div class="v">${{fmtN(totReal)}}</div><div class="h">${{hint}} · hasta ${{P.hasta_real || '—'}}</div></div>
    <div class="kpi accent"><div class="l">Proyección ${{anio}}</div><div class="v">${{hayPron ? fmtN(totYhatAnio) : '—'}}</div><div class="h">${{hayPron ? 'Suma Prophet de los 12 meses' : 'Sin modelo para la selección'}}</div></div>
    <div class="kpi"><div class="l">Prophet (meses con real)</div><div class="v">${{hayPron ? fmtN(totYhatAmbos) : '—'}}</div><div class="h">${{ambos.length}} mes(es) comparables</div></div>
    <div class="kpi ${{!hayPron?'':(diff>=0?'ok':'warn')}}"><div class="l">Real − Prophet</div><div class="v">${{hayPron ? ((diff>=0?'+':'') + fmtN(diff)) : '—'}}</div><div class="h">Solo meses ya cerrados</div></div>`;
  makeChart('cProy', {{
    type: 'line',
    data: {{
      labels: pts.map(p => MESES[p.mes - 1]),
      datasets: [
        {{
          label: 'Real',
          data: reals,
          borderColor: PAL.act,
          backgroundColor: 'rgba(0,62,109,.18)',
          fill: true,
          tension: .25,
          pointRadius: 4,
          borderWidth: 3,
          spanGaps: false,
          order: 2,
        }},
        {{
          label: 'Proyección Prophet',
          data: yhats,
          borderColor: PAL.var,
          backgroundColor: PAL.var,
          borderDash: [7, 4],
          fill: false,
          tension: .25,
          pointRadius: 4,
          borderWidth: 2.5,
          spanGaps: false,
          order: 1,
        }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }}, datalabels: dlInt({{ minRatio: 0.08 }}), tooltip: tipNum }},
      scales: {{ y: {{ beginAtZero: true, ticks: {{ callback: v => fmtN(v) }} }}, x: {{ grid: {{ display: false }} }} }}
    }}
  }});
  registerChartTable('cProy', ['Año', 'Mes', 'Selección', 'Real', 'Proyección', 'Intervalo inf.', 'Intervalo sup.', 'Real − Prophet'], pts.map(p => [
    p.anio, MESES[p.mes - 1], etiquetaSeleccion(), p.real == null ? '' : p.real,
    p.yhat == null ? '' : p.yhat, p.lo == null ? '' : p.lo, p.hi == null ? '' : p.hi,
    (p.real == null || p.yhat == null) ? '' : (p.real - p.yhat)
  ]));
}}
function showTab(name) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('on', p.id === 'tab-' + name));
  document.querySelectorAll('.page-tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  requestAnimationFrame(() => Object.values(charts).forEach(c => {{ try {{ c.resize(); }} catch (e) {{}} }}));
  if (name === 'proyeccion') renderProyeccion();
}}
document.querySelectorAll('.page-tabs button').forEach(btn => {{
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
}});
fillProyAnio();
fillProyFiltros();
document.getElementById('f-proy-anio')?.addEventListener('change', renderProyeccion);
document.getElementById('f-proy-sede')?.addEventListener('change', renderProyeccion);
document.getElementById('f-proy-programa')?.addEventListener('change', renderProyeccion);
</script>
</body>
</html>
"""


def main() -> None:
    print("Cargando credenciales...")
    cfg = cargar_credenciales()
    vista = cfg.get("VISTA") or VISTA
    print(f"Conectando a {cfg['SERVIDOR']} / {cfg['BASE']} · {vista}")
    print("El archivo Power BI no se modifica.")
    conn = conectar(cfg)
    cur = conn.cursor()
    print("Consultando (solo lectura)...")
    datos = consultar_cantidad(cur, vista)
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
    print(f"  Grupos: {datos['n_grupos']:,} · Análisis: {datos['total']:,} · Año default: {datos['anio_default']}")
    print(f"  ELF (sin multiplex): {datos.get('n_elf', 0):,} grupos · {datos.get('total_elf', 0):,} análisis")
    proy = datos.get("proyeccion") or {}
    if proy.get("ok"):
        print(f"  Prophet OK · real hasta {proy.get('hasta_real')} · años {proy.get('anios')} · sedes {len(proy.get('sedes') or [])} ({len(proy.get('sedes_prophet') or [])} con modelo) · programas {len(proy.get('programas') or [])} ({len(proy.get('programas_prophet') or [])} con modelo)")
    else:
        print(f"  Prophet no disponible: {proy.get('error')}")


if __name__ == "__main__":
    main()
