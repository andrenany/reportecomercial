"""
Genera dashboard HTML interactivo + página de reglas.

- Ventas unificadas (OC fecha vs Facturación consolidada sin OC)
- Clasificación por tipo de ingreso según PROGRAMAS.xlsx (SDG / PVE / SCR / Cap.)
- Excluye Medio Ambiente e I+D (documentado en reglas)
- Gráficos estilo Facturación (mes x tipo, top empresas, ciclo)
- Logo ADL sobre fondo blanco

No modifica los Excel de red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from leer_oc_pendientes import (
    DIR_SALIDA,
    limpiar_fecha,
    leer_facturacion,
    leer_mapa_empresas,
    leer_oc_pendientes,
    normalizar_texto,
    preparar_fac,
    preparar_oc,
    sede_desde_cuenta,
)
from chart_tools import CSS_CHART_TOOLS, JS_CHART_TOOLS, panel_chart
from render_excel_dashboard import render_dashboard_excel as render_dashboard_excel_views

EXCEL_PROGRAMAS = (
    r"\\192.168.10.5\adl.ws\Disco I\PM\COM\Carpeta compartida comercial"
    r"\analsisi fanny\PROGRAMAS.xlsx"
)

EMPRESAS_SIN_OC_RAW = [
    "AQUAGEN CHILE S.A.",
    "CIA. SALMONIFERA DALCAHUE",
    "SALMONES ANTARTICA  S.A.",
    "ACUICOLA E INVERS NALCAHUE LTD",
    "THE CHALLENGE ROOM SPA",
    "BAJA TROUT SA",
    "CODEBREAKER BIOSCIENCE SPA",
]

ALIAS_SIN_OC = {
    "AQUAGEN CHILE SA": "AQUAGEN",
    "CIA. SALMONIFERA DALCAHUE": "SALMONIFERA DALCAHUE",
    "CIA SALMONIFERA DALCAHUE": "SALMONIFERA DALCAHUE",
    "SALMONES ANTARTICA SA": "SASA",
    "ACUICOLA E INVERS NALCAHUE LTD": "NALCAHUE",
    "THE CHALLENGE ROOM SPA": "THE CHALLENGE ROOM",
    "BAJA TROUT SA": "BAJA TROUT",
    "CODEBREAKER BIOSCIENCE SPA": "CODEBREAKER",
}

# Etiquetas amplias de tipo de ingreso (según PROGRAMAS.xlsx)
TIPO_LABEL = {
    "SDG": "SDG · Servicios Diagnósticos",
    "PVE": "PVE · Programas / Vigilancia",
    "SCR": "SCR · Screening",
    "CAP": "Capacitación",
    "ATV": "ATV · Asistencia técnica",
    "OTROS": "Otros",
}

# Exclusiones explícitas del análisis (documentadas en reglas.html)
EXCLUIR_TIPOS = {"I+D"}
EXCLUIR_PROGRAMA_CONTIENE = ("MEDIO AMBIENTE",)
EXCLUIR_SEDES = {"NO CORRESPONDE"}

# Paleta ampliada ADL (navy + naranja + complementarios)
TIPO_COLOR = {
    "SDG": "#003E6D",
    "PVE": "#F37021",
    "SCR": "#0A8F9C",
    "CAP": "#E8A317",
    "ATV": "#1F6F8B",
    "OTROS": "#7A92A8",
}

MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]
MES_A_NUM = {m: i + 1 for i, m in enumerate(MESES)}
MES_EN = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _keys_sin_oc() -> set[str]:
    keys = set()
    for raw in EMPRESAS_SIN_OC_RAW:
        n = normalizar_texto(raw)
        if n:
            keys.add(n)
            keys.add(ALIAS_SIN_OC.get(n, n))
    keys.update(ALIAS_SIN_OC.values())
    return {k for k in keys if k}


def _es_sin_oc(cliente_norm, empresa_abr, cliente_key, sin_oc_keys: set[str]) -> bool:
    for v in (cliente_norm, empresa_abr, cliente_key):
        if v and v in sin_oc_keys:
            return True
    texto = " | ".join(str(x) for x in (cliente_norm, empresa_abr, cliente_key) if x)
    fuertes = [
        "AQUAGEN", "SALMONIFERA DALCAHUE", "ANTARTICA", "NALCAHUE",
        "CHALLENGE ROOM", "BAJA TROUT", "CODEBREAKER",
    ]
    return any(f in texto for f in fuertes)


def _periodo_label(anio, mes_num) -> str:
    if pd.isna(anio) or pd.isna(mes_num):
        return "SIN PERIODO"
    mes_num, anio = int(mes_num), int(anio)
    if mes_num < 1 or mes_num > 12:
        return f"{anio}"
    return f"{anio}-{mes_num:02d}"


def _norm_sigla(valor) -> str:
    t = normalizar_texto(valor) or ""
    t = t.replace(" ", "")
    if t in ("SDG",):
        return "SDG"
    if t in ("PVE", "PVA", "ISA", "SRS", "SAMIC"):
        return "PVE"
    if t in ("SCR", "SCREENING"):
        return "SCR"
    if "I+D" in t or t == "ID":
        return "I+D"
    if "CAPACIT" in t:
        return "CAP"
    return t or "OTROS"


def leer_mapa_programas(path: str = EXCEL_PROGRAMAS) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = ["nombre_sucio", "nombre", "siglas", "sub_programa"]
    df = df.dropna(how="all")
    df["key"] = df["nombre_sucio"].map(normalizar_texto)
    df["tipo"] = df["siglas"].map(_norm_sigla)
    df["tipo_nombre"] = df["nombre"].map(lambda x: str(x).strip() if pd.notna(x) else None)
    df["sub"] = df["sub_programa"].map(lambda x: str(x).strip() if pd.notna(x) else None)
    return df.dropna(subset=["key"]).drop_duplicates("key")


def clasificar_tipo(texto, mapa: pd.DataFrame, fallback_tipo: str | None = None) -> tuple[str, str | None, str | None]:
    """Devuelve (tipo, tipo_nombre, sub_programa)."""
    if fallback_tipo:
        t = _norm_sigla(fallback_tipo)
        return t, TIPO_LABEL.get(t, t), None

    k = normalizar_texto(texto)
    if not k:
        return "OTROS", TIPO_LABEL["OTROS"], None

    hit = mapa.loc[mapa["key"] == k]
    if not hit.empty:
        row = hit.iloc[0]
        return row["tipo"], row["tipo_nombre"] or TIPO_LABEL.get(row["tipo"], row["tipo"]), row["sub"]

    # Heurísticas amplias (cuando no hay match exacto en PROGRAMAS.xlsx)
    if any(x in k for x in ("SCREEN", "SCREE", "RNA LATER", "RNALATER")):
        return "SCR", "Screening", "SCR"
    if any(x in k for x in ("VIGILANCIA", "EPIDIO", "EPIDEM", "CONTINGENCIA", "ISAV", "PVA", "SRS", "SUSCEP", "SUCEP", "ANTIMICRO")):
        return "PVE", "PVE", "PVE"
    if "I+D" in k or "INVESTIGACION" in k:
        return "I+D", "Investigación I+D", "I+D"
    if "CAPACIT" in k:
        return "CAP", "Ventas Capacitación", "Ventas Capacitación"
    if any(x in k for x in ("LABORATORIO", "DIAGNOSTICO", "ASISTENCIA", "ASIST.", "MEDIO AMBIENTE", "MATERIAL", "CERTIFIC")):
        return "SDG", "Servicios Diagnósticos", "SDG"
    return "OTROS", TIPO_LABEL["OTROS"], None


def construir_ventas_unificadas(oc: pd.DataFrame, fac: pd.DataFrame, mapa_prog: pd.DataFrame) -> pd.DataFrame:
    sin_oc_keys = _keys_sin_oc()

    oc2 = oc.copy()
    oc2["es_sin_oc"] = [
        _es_sin_oc(a, b, c, sin_oc_keys)
        for a, b, c in zip(oc2["Cliente_norm"], oc2["Empresa_Abr"], oc2["Cliente_key"])
    ]
    oc2["Fecha_doc_limpia"] = limpiar_fecha(oc2["Fecha_doc"])

    tipos = [clasificar_tipo(p, mapa_prog) for p in oc2["Programa"]]
    oc2["tipo"] = [t[0] for t in tipos]
    oc2["tipo_nombre"] = [t[1] for t in tipos]
    oc2["sub_programa"] = [t[2] for t in tipos]
    oc2["programa"] = oc2["Programa"].map(normalizar_texto)

    oc_venta = oc2[(oc2["estado"] != "anulada") & (~oc2["es_sin_oc"])].copy()
    # Excluir filas resumen del Excel (sin ID / totales / etiquetas de control)
    oc_venta = oc_venta[oc_venta["ID"].notna()].copy()
    etiquetas_basura = {
        "PENDIENTE DE OC/HES",
        "POR FACTURAR",
        "FACTURADO",
        "NULO/ N.CREDITO",
        "NULO/N.CREDITO",
    }
    oc_venta = oc_venta[
        ~oc_venta["Cliente_norm"].isin(etiquetas_basura)
        & ~oc_venta["Cliente_key"].isin(etiquetas_basura)
    ].copy()
    oc_venta["fuente"] = "Registro comercial (OC)"
    oc_venta["anio_venta"] = oc_venta["Fecha_limpia"].dt.year
    oc_venta["mes_venta"] = oc_venta["Fecha_limpia"].dt.month
    oc_venta["periodo"] = [
        _periodo_label(a, m) for a, m in zip(oc_venta["anio_venta"], oc_venta["mes_venta"])
    ]
    oc_venta["monto"] = oc_venta["Total_num"]
    oc_venta["cliente_corto"] = oc_venta["Cliente_key"].fillna(oc_venta["Cliente_norm"])
    oc_venta["estado_venta"] = oc_venta["estado"]
    oc_venta["sede"] = None
    oc_venta["id_caso"] = oc_venta["ID"]
    oc_venta["id_origen"] = "OC-" + oc_venta["ID"].astype(str)

    dias = (oc_venta["Fecha_doc_limpia"] - oc_venta["Fecha_limpia"]).dt.days
    oc_venta["dias_ciclo"] = dias.where(
        (oc_venta["estado"] == "facturada_ok")
        & oc_venta["Fecha_limpia"].notna()
        & oc_venta["Fecha_doc_limpia"].notna()
        & dias.between(0, 730)
    )

    part_oc = oc_venta[
        [
            "fuente", "id_origen", "id_caso", "cliente_corto", "programa", "tipo", "tipo_nombre",
            "sub_programa", "monto", "anio_venta", "mes_venta", "periodo",
            "estado_venta", "sede", "Fecha_limpia", "dias_ciclo",
        ]
    ].rename(columns={"Fecha_limpia": "fecha_venta"})

    fac2 = fac.copy()
    fac2["es_sin_oc"] = [
        _es_sin_oc(a, b, c, sin_oc_keys)
        for a, b, c in zip(fac2["Cliente_norm"], fac2["Empresa_Abr"], fac2["Cliente_key"])
    ]
    fac_venta = fac2[fac2["es_sin_oc"]].copy()

    def mes_desde_fila(row) -> float:
        p = row.get("PERIODO_norm")
        if p in MES_A_NUM:
            return MES_A_NUM[p]
        m = normalizar_texto(row.get("Month"))
        if m in MES_EN:
            return MES_EN[m]
        return float("nan")

    fac_venta["anio_venta"] = fac_venta["Anio"]
    fac_venta["mes_venta"] = fac_venta.apply(mes_desde_fila, axis=1)
    fac_venta["periodo"] = [
        _periodo_label(a, m) for a, m in zip(fac_venta["anio_venta"], fac_venta["mes_venta"])
    ]
    fac_venta["fuente"] = "Facturación consolidada (sin OC)"
    fac_venta["monto"] = fac_venta["MONTO"]
    fac_venta["cliente_corto"] = fac_venta["Cliente_key"].fillna(fac_venta["Empresa_norm"])

    tipos_f = [
        clasificar_tipo(g, mapa_prog, fallback_tipo=ti)
        for g, ti in zip(fac_venta.get("Glosa", fac_venta.get(" GLOSA", pd.Series(index=fac_venta.index))), fac_venta["Tipo_Ingreso"])
    ]
    # Prefer Tipo_Ingreso already in consolidado
    fac_venta["tipo"] = fac_venta["Tipo_Ingreso"].map(_norm_sigla)
    fac_venta["tipo_nombre"] = fac_venta["tipo"].map(lambda t: TIPO_LABEL.get(t, t))
    fac_venta["sub_programa"] = fac_venta["tipo"]
    fac_venta["programa"] = fac_venta["Tipo_Ingreso"].map(normalizar_texto)
    fac_venta["estado_venta"] = "facturada_sin_oc"
    fac_venta["sede"] = fac_venta.get("Sede_norm")
    fac_venta["id_caso"] = fac_venta.get("Num_Doc", pd.Series(index=fac_venta.index))
    fac_venta["id_origen"] = "FAC-" + fac_venta.index.astype(str)
    fac_venta["fecha_venta"] = pd.to_datetime(
        dict(
            year=fac_venta["anio_venta"],
            month=fac_venta["mes_venta"].fillna(1).astype(int),
            day=1,
        ),
        errors="coerce",
    )
    fac_venta["dias_ciclo"] = pd.Series([pd.NA] * len(fac_venta), dtype="Float64")

    part_fac = fac_venta[
        [
            "fuente", "id_origen", "id_caso", "cliente_corto", "programa", "tipo", "tipo_nombre",
            "sub_programa", "monto", "anio_venta", "mes_venta", "periodo",
            "estado_venta", "sede", "fecha_venta", "dias_ciclo",
        ]
    ]

    ventas = pd.concat([part_oc, part_fac], ignore_index=True)
    ventas = ventas.dropna(subset=["monto"])
    ventas = ventas[ventas["monto"] != 0].drop_duplicates(subset=["id_origen"])

    mask = ventas["cliente_corto"].isna() | (ventas["cliente_corto"] == "")
    # alias sin OC
    for raw, short in ALIAS_SIN_OC.items():
        ventas.loc[ventas["cliente_corto"].map(normalizar_texto) == raw, "cliente_corto"] = short

    ventas["anio_venta"] = pd.to_numeric(ventas["anio_venta"], errors="coerce")
    ventas["mes_venta"] = pd.to_numeric(ventas["mes_venta"], errors="coerce")
    ventas["dias_ciclo"] = pd.to_numeric(ventas["dias_ciclo"], errors="coerce")
    ventas["fecha_venta"] = pd.to_datetime(ventas["fecha_venta"], errors="coerce").dt.strftime("%Y-%m-%d")
    ventas["tipo"] = ventas["tipo"].fillna("OTROS")
    ventas["programa"] = ventas["programa"].fillna("Sin programa")
    ventas["cliente_corto"] = ventas["cliente_corto"].fillna("Sin cliente")
    ventas = _aplicar_exclusiones(ventas)
    return ventas.reset_index(drop=True)


def _aplicar_exclusiones(ventas: pd.DataFrame) -> pd.DataFrame:
    mask_excl = ventas["tipo"].isin(EXCLUIR_TIPOS)
    prog = ventas["programa"].fillna("").astype(str).str.upper()
    for frag in EXCLUIR_PROGRAMA_CONTIENE:
        mask_excl = mask_excl | prog.str.contains(frag, na=False)
    mask_excl = mask_excl | prog.str.contains(r"I\+D", na=False) | prog.str.contains("INVESTIGACION", na=False)
    if "tipo_nombre" in ventas.columns:
        tn = ventas["tipo_nombre"].fillna("").astype(str).str.upper()
        mask_excl = mask_excl | tn.str.contains(r"INVESTIGACION I\+D", na=False)
    if "cuenta" in ventas.columns:
        cu = ventas["cuenta"].fillna("").astype(str).str.upper()
        mask_excl = mask_excl | cu.str.contains("MEDIO AMBIENTE", na=False)
    if "sede" in ventas.columns:
        sede = ventas["sede"].fillna("").astype(str).str.upper().str.strip()
        mask_excl = mask_excl | sede.isin(EXCLUIR_SEDES) | sede.str.contains("NO CORRESPONDE", na=False)
    return ventas.loc[~mask_excl].copy()


def construir_ventas_facturacion_excel(
    fac: pd.DataFrame,
    mapa_prog: pd.DataFrame,
    facturado_2026: pd.DataFrame | None = None,  # ignorado: la fuente es Juan
) -> pd.DataFrame:
    """
    Solo facturación: toda la serie sale del consolidado Juan
    (KR Resumen Consolidado). No se usa facturado 2026.xlsx ni provisionados.
    """
    del facturado_2026  # compat firma; ya no se usa
    fac2 = fac.reset_index(drop=True).copy()

    def mes_desde_fila(row) -> float:
        p = row.get("PERIODO_norm")
        if p in MES_A_NUM:
            return MES_A_NUM[p]
        m = normalizar_texto(row.get("Month"))
        if m in MES_EN:
            return MES_EN[m]
        return float("nan")

    glosa = fac2["Glosa"] if "Glosa" in fac2.columns else pd.Series([None] * len(fac2))
    sede = fac2["Sede_norm"] if "Sede_norm" in fac2.columns else pd.Series([None] * len(fac2))
    # Fallback sede desde cuenta si falta
    if "Cuenta" in fac2.columns:
        sede = sede.where(sede.notna() & (sede != "") & (sede != "SIN SEDE"), fac2["Cuenta"].map(sede_desde_cuenta))
    sede = sede.fillna("PUERTO MONTT")

    out = pd.DataFrame({
        "anio_origen": fac2["Anio"],
        "anio_venta": fac2["Anio"],
        "mes_venta": fac2.apply(mes_desde_fila, axis=1),
        "monto": pd.to_numeric(fac2["MONTO"], errors="coerce"),
        "cliente_corto": fac2["Cliente_key"].fillna(fac2["Empresa_norm"]).fillna(fac2["Cliente_norm"]),
        "tipo": fac2["Tipo_Ingreso"].map(_norm_sigla),
        "programa": glosa.map(normalizar_texto).fillna(fac2["Tipo_Ingreso"].map(normalizar_texto)),
        "sede": sede,
        "cuenta": fac2["Cuenta"] if "Cuenta" in fac2.columns else None,
        "id_caso": fac2["Num_Doc"] if "Num_Doc" in fac2.columns else fac2.index.astype(str),
        "num_doc": pd.to_numeric(fac2["Num_Doc"], errors="coerce") if "Num_Doc" in fac2.columns else pd.NA,
        "es_provisionado": False,
        "fuente": "Juan consolidado",
    })

    out["periodo"] = [_periodo_label(a, m) for a, m in zip(out["anio_venta"], out["mes_venta"])]
    out["tipo_nombre"] = out["tipo"].map(lambda t: TIPO_LABEL.get(t, t))
    out["id_origen"] = "FAC-" + out["num_doc"].fillna(out.index.to_series()).astype(str)
    out["estado_venta"] = "facturada"
    out["fecha_venta"] = pd.to_datetime(
        dict(
            year=pd.to_numeric(out["anio_venta"], errors="coerce"),
            month=pd.to_numeric(out["mes_venta"], errors="coerce").fillna(1).astype(int),
            day=1,
        ),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")

    vacios = out["tipo"].isna() | (out["tipo"] == "") | (out["tipo"] == "OTROS")
    if vacios.any():
        for idx in out.index[vacios]:
            t, nom, _ = clasificar_tipo(out.at[idx, "programa"], mapa_prog)
            if t and t != "OTROS":
                out.at[idx, "tipo"] = t
                out.at[idx, "tipo_nombre"] = nom

    out = out.dropna(subset=["monto"])
    out = out[out["monto"] != 0]
    out["tipo"] = out["tipo"].fillna("OTROS")
    out["programa"] = out["programa"].fillna("Sin programa")
    out["cliente_corto"] = out["cliente_corto"].fillna("Sin cliente")
    out = _aplicar_exclusiones(out)
    return out.reset_index(drop=True)


CSS = r"""
:root {
  --adl-navy: #003E6D;
  --adl-navy-deep: #002844;
  --adl-navy-soft: #1A5F8A;
  --adl-orange: #F37021;
  --adl-orange-soft: #FF8A3D;
  --adl-teal: #0A8F9C;
  --adl-sand: #F7F1E8;
  --adl-sky: #E8F1F7;
  --ink: #0F2A40;
  --muted: #5B738B;
  --line: #D7E3EE;
  --bg: #EEF3F8;
  --panel: rgba(255,255,255,.92);
  --ok: #2F9E71;
  --warn: #E8A317;
  --danger: #D64545;
  --info: #3E7CB1;
  --shadow: 0 12px 36px rgba(0,42,74,.08);
  --shadow-soft: 0 4px 16px rgba(0,62,109,.05);
  --radius: 18px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  color: var(--ink);
  background:
    radial-gradient(900px 420px at -5% -10%, rgba(243,112,33,.16), transparent 55%),
    radial-gradient(800px 380px at 105% 0%, rgba(10,143,156,.14), transparent 50%),
    radial-gradient(700px 360px at 50% 110%, rgba(0,62,109,.08), transparent 55%),
    linear-gradient(180deg, #F7FAFC 0%, var(--bg) 40%, #E8EEF4 100%);
  min-height: 100vh;
}
.wrap { max-width: none; width: 100%; margin: 0 auto; padding: 18px 28px 56px; box-sizing: border-box; }
.topnav {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 16px; margin-bottom: 14px;
  background: linear-gradient(135deg, #fff 0%, var(--adl-sky) 100%);
  border: 1px solid rgba(215,227,238,.9); border-radius: 20px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(8px);
}
.brand-row { display: flex; align-items: center; gap: 12px; }
.brand-row img { height: 54px; width: auto; display: block; filter: drop-shadow(0 2px 6px rgba(0,62,109,.08)); }
.brand-text { font-family: Manrope, sans-serif; font-weight: 800; font-size: 1.08rem; color: var(--adl-navy); line-height: 1.15; }
.brand-text span { color: var(--adl-orange); }
.nav-links { display: flex; gap: 8px; flex-wrap: wrap; }
.nav-links a {
  text-decoration: none; font-size: .85rem; font-weight: 700;
  padding: 9px 14px; border-radius: 999px; color: var(--adl-navy);
  background: rgba(255,255,255,.75); border: 1px solid var(--line);
  transition: all .18s ease;
}
.nav-links a:hover { border-color: var(--adl-orange); color: var(--adl-orange); transform: translateY(-1px); }
.nav-links a.active {
  background: linear-gradient(135deg, var(--adl-navy), var(--adl-navy-soft));
  color: #fff; border-color: transparent;
  box-shadow: 0 8px 18px rgba(0,62,109,.22);
}
.nav-links a.btn-mail,
.nav-links button.btn-mail {
  background: linear-gradient(135deg, var(--adl-orange), #FF8A3D);
  color: #fff; border-color: transparent;
  box-shadow: 0 6px 14px rgba(243,112,33,.28);
  font: inherit; font-size: .85rem; font-weight: 700;
  padding: 9px 14px; border-radius: 999px; cursor: pointer;
  border: 1px solid transparent;
  transition: all .18s ease;
}
.nav-links a.btn-mail:hover,
.nav-links button.btn-mail:hover {
  color: #fff; filter: brightness(1.05);
  border-color: transparent; transform: translateY(-1px);
}
.nav-links button.btn-mail:disabled {
  opacity: .7; cursor: wait; transform: none;
}
footer { margin-top: 22px; text-align: center; color: var(--muted); font-size: .78rem; }
footer a.btn-mail-foot,
footer button.btn-mail-foot {
  display: inline-block; margin-top: 10px;
  text-decoration: none; font-weight: 700; font-size: .82rem;
  padding: 10px 16px; border-radius: 999px; color: #fff;
  background: linear-gradient(135deg, var(--adl-orange), #FF8A3D);
  box-shadow: 0 6px 14px rgba(243,112,33,.25);
  border: 0; cursor: pointer; font: inherit;
}
footer a.btn-mail-foot:hover,
footer button.btn-mail-foot:hover { filter: brightness(1.05); }
footer button.btn-mail-foot:disabled { opacity: .7; cursor: wait; }

.hero-mini {
  color: var(--muted); font-size: .92rem; margin: 0 4px 14px; line-height: 1.45;
  padding: 10px 14px; border-radius: 14px;
  background: linear-gradient(90deg, rgba(255,255,255,.7), rgba(232,241,247,.55));
  border: 1px solid rgba(215,227,238,.7);
}
.hero-mini strong { color: var(--adl-navy); }

.filters {
  background: var(--panel); border: 1px solid var(--line); border-radius: 20px;
  padding: 16px; margin-bottom: 14px; box-shadow: var(--shadow-soft);
  backdrop-filter: blur(10px);
  position: relative;
  z-index: 40;
  overflow: visible;
}
.filters-top {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: end;
  overflow: visible;
  position: relative;
  z-index: 1;
}
label.f { display: flex; flex-direction: column; gap: 5px; font-size: .7rem; color: var(--muted); font-weight: 700; letter-spacing: .04em; text-transform: uppercase; min-width: 130px; flex: 1; }
select {
  appearance: none;
  border: 1px solid var(--line); border-radius: 12px; padding: 10px 34px 10px 12px;
  font: inherit; color: var(--ink); background: #fff
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath fill='%005B738B' d='M0 0l6 8 6-8z'/%3E%3C/svg%3E")
    right 12px center / 10px no-repeat;
  transition: border-color .18s, box-shadow .18s, transform .18s;
}
select:hover, select:focus { border-color: var(--adl-orange); outline: none; box-shadow: 0 0 0 3px rgba(243,112,33,.16); }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.chip-label { font-size: .72rem; font-weight: 700; color: var(--muted); text-transform: uppercase; margin-right: 4px; }
.chip {
  border: 1px solid var(--line); background: #fff; color: var(--ink);
  border-radius: 999px; padding: 8px 14px; font-weight: 700; font-size: .82rem;
  cursor: pointer; transition: all .18s ease;
}
.chip:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(0,62,109,.1); }
.chip.on { color: #fff; border-color: transparent; box-shadow: 0 8px 16px rgba(0,62,109,.18); }
.chip[data-tipo="SDG"].on { background: linear-gradient(135deg,#003E6D,#1A5F8A); }
.chip[data-tipo="PVE"].on { background: linear-gradient(135deg,#F37021,#FF8A3D); }
.chip[data-tipo="SCR"].on { background: linear-gradient(135deg,#0A8F9C,#14B0BE); }
.chip[data-tipo="CAP"].on { background: linear-gradient(135deg,#E8A317,#F0BD4A); }
.chip[data-tipo="ATV"].on { background: linear-gradient(135deg,#1F6F8B,#2A8AA8); }
.chip[data-tipo="OTROS"].on { background: linear-gradient(135deg,#7A92A8,#95A9BB); }
.chip[data-tipo="ALL"].on { background: linear-gradient(135deg,#003E6D,#0A8F9C); }
.actions { display: flex; gap: 8px; margin-left: auto; }
.btn {
  border: 0; border-radius: 12px; padding: 10px 14px; font: inherit; font-weight: 700;
  cursor: pointer; transition: transform .15s, box-shadow .15s;
}
.btn:hover { transform: translateY(-1px); }
.btn.primary { background: linear-gradient(135deg,var(--adl-orange),var(--adl-orange-soft)); color: #fff; box-shadow: 0 8px 16px rgba(243,112,33,.25); }
.btn.ghost { background: #fff; color: var(--adl-navy); border: 1px solid var(--line); }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; position: relative; z-index: 1; }
@media (max-width: 980px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
.kpi {
  background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px 16px 14px; box-shadow: var(--shadow-soft);
  transition: transform .2s ease, box-shadow .2s ease;
  position: relative; overflow: hidden;
}
.kpi::before {
  content: ""; position: absolute; inset: 0 auto 0 0; width: 4px;
  background: linear-gradient(180deg, var(--adl-navy), var(--adl-teal));
}
.kpi:hover { transform: translateY(-3px); box-shadow: var(--shadow); }
.kpi .label { color: var(--muted); font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
.kpi .value { font-family: Manrope, sans-serif; font-weight: 800; font-size: 1.38rem; margin-top: 6px; color: var(--adl-navy); letter-spacing: -.02em; }
.kpi .hint { color: var(--muted); font-size: .76rem; margin-top: 4px; }
.kpi.accent::before { background: linear-gradient(180deg, var(--adl-orange), #FFB07A); }
.kpi.navy::before { background: linear-gradient(180deg, var(--adl-navy), var(--adl-navy-soft)); }
.kpi.ok::before { background: linear-gradient(180deg, var(--ok), #5BC49A); }
.kpi.warn::before { background: linear-gradient(180deg, var(--warn), #F0BD4A); }
.kpi.info::before { background: linear-gradient(180deg, var(--info), #6BA3D0); }
.kpi.teal::before { background: linear-gradient(180deg, var(--adl-teal), #3BC4D0); }
.kpi.danger::before { background: linear-gradient(180deg, var(--danger), #F07171); }
.kpi.accent, .kpi.navy, .kpi.ok, .kpi.warn, .kpi.info, .kpi.teal, .kpi.danger { border-top: 0; }

.tabs { display: flex; gap: 8px; margin: 16px 0 0; flex-wrap: wrap; }
.tabs button {
  border: 1px solid var(--line); background: rgba(255,255,255,.85); border-radius: 999px;
  padding: 9px 16px; font-weight: 700; color: var(--adl-navy); cursor: pointer;
  transition: all .18s ease;
}
.tabs button:hover { border-color: var(--adl-teal); color: var(--adl-teal); }
.tabs button.active {
  background: linear-gradient(135deg, var(--adl-navy), var(--adl-teal));
  color: #fff; border-color: transparent;
  box-shadow: 0 8px 18px rgba(0,62,109,.2);
}
.section { display: none; margin-top: 14px; animation: fade .28s ease; }
.section.active { display: block; }
@keyframes fade { from { opacity: 0; transform: translateY(6px);} to { opacity:1; transform:none;} }

.grid { display: grid; grid-template-columns: 1.35fr 1fr; gap: 14px; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-top: 14px; }
@media (max-width: 980px) { .grid, .grid3 { grid-template-columns: 1fr; } }
.panel {
  background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px; box-shadow: var(--shadow-soft);
  backdrop-filter: blur(8px);
  transition: box-shadow .2s ease;
}
.panel:hover { box-shadow: var(--shadow); }
.panel h2 { margin: 0 0 2px; font-family: Manrope, sans-serif; font-size: 1.02rem; color: var(--adl-navy); }
.panel p.desc { margin: 0 0 10px; color: var(--muted); font-size: .82rem; }
.chart-box { position: relative; height: 310px; }
.chart-box.sm { height: 270px; }
.chart-box.tall { height: 400px; }
table { width: 100%; border-collapse: collapse; font-size: .82rem; }
th, td { text-align: left; padding: 9px 7px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .04em; position: sticky; top: 0; background: #fff; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.scroll { overflow: auto; max-height: 440px; border-radius: 12px; }
table.pivot th, table.pivot td { white-space: nowrap; }
table.pivot th.num, table.pivot td.num { min-width: 92px; }
table.pivot tfoot td, table.pivot tfoot th { font-weight: 700; background: #F0F6FA; border-top: 2px solid var(--line); }
table.pivot td.empty { color: #B0BEC5; }
.badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; }
.b-pend { background: #EAF0F6; color: var(--adl-navy); }
.b-listo { background: #D9EAF8; color: #1D4E89; }
.b-ok { background: #D8F3E6; color: #1B7A52; }
.b-sinoc { background: #FFE8D6; color: #9A3412; }
.b-anul { background: #FDE2E2; color: #9B1C1C; }
.b-rapido { background: #D8F3E6; color: #1B7A52; }
.b-normal { background: #D9EAF8; color: #1D4E89; }
.b-lento { background: #FFF3CD; color: #8A6D1D; }
.b-critico { background: #FDE2E2; color: #9B1C1C; }
.rule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .rule-grid { grid-template-columns: 1fr; } }
.swatch { display:inline-block; width:14px; height:14px; border-radius:4px; margin-right:6px; vertical-align:middle; }
.cmp-note { font-size:.84rem; color:var(--muted); margin:0 0 12px; padding:10px 12px; border-radius:12px; background:rgba(255,255,255,.65); border:1px solid var(--line); }
""" + CSS_CHART_TOOLS


def _mail_js() -> str:
    """Envío automático vía FormSubmit (sin abrir Outlook)."""
    return r"""
<script>
async function solicitarActualizacion(btn) {
  const el = btn || document.querySelector('.btn-mail, .btn-mail-foot');
  const prev = el ? el.textContent : '';
  if (el) { el.disabled = true; el.textContent = 'Enviando…'; }
  try {
    const res = await fetch('https://formsubmit.co/ajax/faraujo@adldiagnostic.cl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        _subject: 'Solicitud de actualizacion - Dashboard Facturacion ADL',
        _template: 'table',
        _captcha: 'false',
        mensaje: 'Solicito actualizar el dashboard de facturacion / reporte comercial.',
        pagina: window.location.href,
        fecha: new Date().toLocaleString('es-CL')
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || 'No se pudo enviar');
    if (typeof showToast === 'function') showToast('Solicitud enviada a faraujo@adldiagnostic.cl');
    else alert('Solicitud enviada a faraujo@adldiagnostic.cl');
    if (el) el.textContent = 'Enviado';
  } catch (err) {
    console.error(err);
    if (typeof showToast === 'function') showToast('Error al enviar. Intenta de nuevo.');
    else alert('Error al enviar. Si es la primera vez, Fanny debe confirmar el correo de FormSubmit.');
    if (el) el.textContent = prev || 'Solicitar actualización';
  } finally {
    if (el) setTimeout(() => { el.disabled = false; if (el.textContent === 'Enviado') el.textContent = prev || 'Solicitar actualización'; }, 2500);
  }
}
</script>
"""


def _nav(active: str) -> str:
    def cls(name: str) -> str:
        return "active" if name == active else ""
    return f"""
    <div class="topnav">
      <div class="brand-row">
        <img src="logo_adl.png" alt="ADL Diagnostic Chile" />
        <div class="brand-text">Dashboard <span>Facturación</span></div>
      </div>
      <div class="nav-links">
        <a class="{cls('dash')}" href="dashboard_facturacion.html">Unificado</a>
        <a class="{cls('excel')}" href="dashboard_facturacion_excel.html">Solo facturación</a>
        <a class="{cls('sql')}" href="consulta_facturacion.html">Consulta facturación</a>
        <a class="{cls('reglas')}" href="reglas.html">Reglas</a>
        <button type="button" class="btn-mail" onclick="solicitarActualizacion(this)">Solicitar actualización</button>
        <button type="button" class="chip" style="border-radius:999px;padding:9px 14px" onclick="adlLogout()">Salir</button>
      </div>
    </div>
    """


def _footer(extra: str = "") -> str:
    extra_html = f" · {extra}" if extra else ""
    return f"""
  <footer>
    ADL Diagnostic Chile{extra_html}
    <div>
      <button type="button" class="btn-mail-foot" onclick="solicitarActualizacion(this)">Solicitar actualización por correo</button>
    </div>
  </footer>
    """


def render_dashboard(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    tipo_colors = json.dumps(TIPO_COLOR, ensure_ascii=False)
    tipo_labels = json.dumps(TIPO_LABEL, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ADL · Dashboard Facturación</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<script src="auth.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  {_nav('dash')}

  <div class="filters">
    <div class="chip-row">
      <span class="chip-label">Tipo ingreso</span>
      <div id="chips-tipo" style="display:contents">
        <button type="button" class="chip" data-tipo="SDG">SDG</button>
        <button type="button" class="chip" data-tipo="PVE">PVE</button>
        <button type="button" class="chip" data-tipo="SCR">SCR</button>
        <button type="button" class="chip" data-tipo="CAP">Capacitación</button>
        <button type="button" class="chip" data-tipo="ATV">ATV</button>
        <button type="button" class="chip" data-tipo="OTROS">Otros</button>
      </div>
      <div class="actions"><button class="btn ghost" id="btn-reset" type="button">Limpiar</button></div>
    </div>
    <p class="hint-multi">Puedes marcar varios tipos y varias opciones en cada filtro. Usa la búsqueda dentro del desplegable. Sin elegir = todos.</p>
    <div class="filters-top">
      <label class="f">Año<div class="msel" id="f-anio" data-empty="Todos"></div></label>
      <label class="f">Mes<div class="msel" id="f-mes" data-empty="Todos"></div></label>
      <label class="f">Cliente<div class="msel" id="f-cliente" data-empty="Todos"></div></label>
      <label class="f">Programa<div class="msel" id="f-programa" data-empty="Todos"></div></label>
      <label class="f">Estado<div class="msel" id="f-estado" data-empty="Todos"></div></label>
      <label class="f">Fuente<div class="msel" id="f-fuente" data-empty="Todos"></div></label>
    </div>
  </div>

  <section class="kpis" id="kpis"></section>

  <div class="tabs">
    <button class="active" data-tab="vista-ventas">Ventas / Tipo ingreso</button>
    <button data-tab="vista-empresas">Empresas</button>
    <button data-tab="vista-pendiente">Pendiente facturar</button>
    <button data-tab="vista-ciclo">Ciclo clientes</button>
    <button data-tab="vista-detalle">Detalle</button>
  </div>

  <section id="vista-ventas" class="section active">
    <div class="grid">
      {panel_chart("Ventas por mes × tipo de ingreso", "SDG / PVE / SCR / Cap. (sin Medio Ambiente ni I+D).", "chartMesTipo")}
      {panel_chart("Mix por tipo de ingreso", "Participación del monto filtrado.", "chartTipo", "sm")}
    </div>
    <div class="grid" style="margin-top:12px">
      {panel_chart("Por estado operativo", "Falta OC/HES, listo para facturar, facturado, sin OC.", "chartEstado", "sm")}
      {panel_chart("Programa (detalle)", "Programas dentro del filtro actual.", "chartProg", "sm")}
    </div>
  </section>

  <section id="vista-empresas" class="section">
    <div class="grid">
      {panel_chart("Top 15 empresas", "Nombre corto · monto en filtros activos.", "chartCli", "tall")}
      {panel_chart("Empresa × tipo de ingreso", "Top 10 empresas apiladas por SDG/PVE/SCR…", "chartCliTipo", "tall")}
    </div>
  </section>

  <section id="vista-pendiente" class="section">
    <p class="hint-multi" style="margin:0 0 10px">Solo estado <strong>Falta OC/HES</strong>. Barras apiladas por mes · tabla pivote Cliente × Mes (todas las empresas del filtro).</p>
    <div class="panel">
      <div class="panel-head">
        <div class="titles">
          <h2>Pendiente de facturar por empresa × mes</h2>
          <p class="desc">Todas las empresas con pendiente · colores = mes</p>
        </div>
        <div class="panel-tools">
          <button type="button" class="on" data-mode="chart" data-target="chartPendEmp">Gráfico</button>
          <button type="button" data-mode="table" data-target="chartPendEmp">Tabla</button>
          <button type="button" data-copy="chartPendEmp">Copiar</button>
        </div>
      </div>
      <div class="chart-box tall" id="box-chartPendEmp" style="height:420px"><canvas id="chartPendEmp"></canvas></div>
      <div class="chart-table-wrap" id="tbl-chartPendEmp"></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <div class="panel-head">
        <div class="titles">
          <h2>Tabla pivote · Cliente × Mes</h2>
          <p class="desc"><span id="pend-count">0</span> empresas · total <span id="pend-total">—</span></p>
        </div>
        <div class="panel-tools"><button type="button" data-copy="pendiente">Copiar pivote</button></div>
      </div>
      <div class="scroll" style="max-height:520px">
        <table id="tabla-pendiente" class="pivot">
          <thead id="pend-thead"></thead>
          <tbody id="tbl-pendiente"></tbody>
          <tfoot id="pend-tfoot"></tfoot>
        </table>
      </div>
    </div>
  </section>

  <section id="vista-ciclo" class="section">
    <div class="grid">
      {panel_chart("Días promedio pre-factura → factura", "Solo OC facturadas con ambas fechas (0–730 d). Rápido ≤30 · Normal 31–60 · Lento 61–90 · Crítico &gt;90.", "chartCiclo", "tall")}
      {panel_chart("Categoría de clientes", "Según velocidad de facturación.", "chartCat", "sm")}
    </div>
    <div id="cat-resumen" style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 0"></div>
    <div class="panel" style="margin-top:12px">
      <h2>Ranking de ciclo</h2>
      <div class="scroll">
        <table>
          <thead><tr>
            <th>Cliente</th><th class="num">Docs</th><th class="num">Prom. días</th>
            <th class="num">Mediana</th><th class="num">P75</th><th>Categoría</th><th class="num">Monto</th>
          </tr></thead>
          <tbody id="tbl-ciclo"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section id="vista-detalle" class="section">
      <div class="panel">
        <div class="panel-head">
          <div class="titles">
            <h2>Detalle filtrado</h2>
            <p class="desc"><span id="det-count">0</span> filas (máx. 500). La columna Días solo aplica a facturadas del registro OC con ambas fechas; si no hay ciclo aparece "—".</p>
          </div>
          <div class="panel-tools">
            <button type="button" data-copy="detalle">Copiar detalle</button>
          </div>
        </div>
        <div class="scroll">
          <table id="tabla-detalle">
            <thead><tr>
              <th>ID</th><th>Fecha</th><th>Periodo</th><th>Cliente</th><th>Tipo</th><th>Programa</th>
              <th>Estado</th><th class="num">Monto</th><th class="num">Días</th>
            </tr></thead>
            <tbody id="tbl-det"></tbody>
          </table>
        </div>
      </div>
  </section>

  {_footer('actualizado <span id="gen"></span>')}
</div>

<script>
const RAW = {data};
const TIPO_COLOR = {tipo_colors};
const TIPO_LABEL = {tipo_labels};
const MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const TIPOS_ORDEN = ["SDG","PVE","SCR","CAP","ATV","OTROS"];

const fmt = (n) => new Intl.NumberFormat('es-CL', {{ style:'currency', currency:'CLP', maximumFractionDigits:0 }}).format(n||0);
const fmtM = (n) => {{
  const v = Number(n)||0;
  if (Math.abs(v) >= 1e9) return '$' + (v/1e9).toFixed(2) + ' mil M';
  if (Math.abs(v) >= 1e6) return '$' + (v/1e6).toFixed(1) + ' M';
  return fmt(v);
}};
const ESTADO_LABEL = {{
  pendiente_facturar: 'Falta OC/HES',
  listo_para_facturar: 'Listo para facturar',
  facturada_ok: 'Facturada',
  facturada_sin_oc: 'Facturada sin OC',
  anulada: 'Anulada',
}};
const badgeEstado = (e) => {{
  const map = {{
    pendiente_facturar:['Falta OC/HES','b-pend'],
    listo_para_facturar:['Listo para facturar','b-listo'],
    facturada_ok:['Facturada','b-ok'],
    facturada_sin_oc:['Facturada sin OC','b-sinoc'],
    anulada:['Anulada','b-anul'],
  }};
  const [t,c] = map[e] || [ESTADO_LABEL[e] || e, 'b-pend'];
  return `<span class="badge ${{c}}">${{t}}</span>`;
}};
const badgeCat = (c) => {{
  const map = {{ Rapido:'b-rapido', Normal:'b-normal', Lento:'b-lento', Critico:'b-critico' }};
  return `<span class="badge ${{map[c]||'b-pend'}}">${{c}}</span>`;
}};

let charts = {{}};
let tiposSel = new Set();

function destroyCharts() {{
  Object.values(charts).forEach(c => c && c.destroy());
  charts = {{}};
}}
function uniqueSorted(arr) {{
  return [...new Set(arr.filter(x => x !== null && x !== undefined && x !== ''))]
    .sort((a,b) => String(a).localeCompare(String(b),'es'));
}}
function fillFilters() {{
  const rows = RAW.ventas;
  const anios = uniqueSorted(rows.map(r => r.anio_venta)).filter(Boolean);
  fillMulti('f-anio', anios, anios.includes(2026) ? [2026] : anios.slice(-1));
  const meses = [...Array(12)].map((_,i)=>i+1);
  const mesLab = Object.fromEntries(meses.map(m => [String(m), MESES[m]]));
  fillMulti('f-mes', meses, [], mesLab);
  fillMulti('f-cliente', uniqueSorted(rows.map(r => r.cliente_corto)));
  fillMulti('f-programa', uniqueSorted(rows.map(r => r.programa)));
  const estados = uniqueSorted(rows.map(r => r.estado_venta));
  const estLab = Object.fromEntries(estados.map(v => [String(v), ESTADO_LABEL[v] || v]));
  fillMulti('f-estado', estados, [], estLab);
  fillMulti('f-fuente', uniqueSorted(rows.map(r => r.fuente)));
}}
function applyFilters(rows) {{
  const anios = selectedMulti('f-anio').map(String);
  const meses = selectedMulti('f-mes').map(String);
  const clientes = selectedMulti('f-cliente');
  const programas = selectedMulti('f-programa');
  const estados = selectedMulti('f-estado');
  const fuentes = selectedMulti('f-fuente');
  return rows.filter(r => {{
    if (tiposSel.size && !tiposSel.has(r.tipo)) return false;
    if (anios.length && !anios.includes(String(r.anio_venta))) return false;
    if (meses.length && !meses.includes(String(r.mes_venta))) return false;
    if (clientes.length && !clientes.includes(r.cliente_corto)) return false;
    if (programas.length && !programas.includes(r.programa)) return false;
    if (estados.length && !estados.includes(r.estado_venta)) return false;
    if (fuentes.length && !fuentes.includes(r.fuente)) return false;
    return true;
  }});
}}
function groupSum(rows, key) {{
  const m = new Map();
  rows.forEach(r => {{
    const k = r[key] ?? 'Sin dato';
    const cur = m.get(k) || {{ key:k, total:0, docs:0, dias:[], byTipo:{{}} }};
    cur.total += Number(r.monto)||0;
    cur.docs += 1;
    if (r.dias_ciclo != null && !Number.isNaN(Number(r.dias_ciclo))) cur.dias.push(Number(r.dias_ciclo));
    const t = r.tipo || 'OTROS';
    cur.byTipo[t] = (cur.byTipo[t]||0) + (Number(r.monto)||0);
    m.set(k, cur);
  }});
  return [...m.values()];
}}
function avg(a){{ if(!a.length) return null; return a.reduce((x,y)=>x+y,0)/a.length; }}
function median(a){{ if(!a.length) return null; const s=[...a].sort((x,y)=>x-y); const m=Math.floor(s.length/2); return s.length%2?s[m]:(s[m-1]+s[m])/2; }}
function percentile(a,p){{ if(!a.length) return null; const s=[...a].sort((x,y)=>x-y); return s[Math.min(s.length-1, Math.max(0, Math.ceil(p/100*s.length)-1))]; }}
function categoria(prom){{ if(prom==null) return null; if(prom<=30) return 'Rapido'; if(prom<=60) return 'Normal'; if(prom<=90) return 'Lento'; return 'Critico'; }}

function renderKpis(rows) {{
  const total = rows.reduce((a,r)=>a+(Number(r.monto)||0),0);
  const docs = rows.length;
  const pend = rows.filter(r=>r.estado_venta==='pendiente_facturar');
  const listo = rows.filter(r=>r.estado_venta==='listo_para_facturar');
  const ok = rows.filter(r=>r.estado_venta==='facturada_ok' || r.estado_venta==='facturada_sin_oc');
  const dias = rows.map(r=>r.dias_ciclo).filter(x => x!=null && !Number.isNaN(Number(x))).map(Number);
  const porTipo = groupSum(rows,'tipo').sort((a,b)=>b.total-a.total);
  const topTipo = porTipo[0];

  const items = [
    ['Ventas filtradas', fmtM(total), docs + ' documentos', 'accent'],
    ['Promedio por documento', docs ? fmtM(total/docs) : '—', 'monto total ÷ N° docs', 'navy'],
    ['Falta OC / HES', fmtM(pend.reduce((a,r)=>a+r.monto,0)), pend.length + ' docs · aún sin documentación', 'warn'],
    ['Listo para facturar', fmtM(listo.reduce((a,r)=>a+r.monto,0)), listo.length + ' docs · ya tiene OC y HES', 'info'],
    ['Ya facturado', fmtM(ok.reduce((a,r)=>a+r.monto,0)), ok.length + ' docs', 'ok'],
    ['Tipo líder', topTipo ? topTipo.key : '—', topTipo ? fmtM(topTipo.total) : '', 'teal'],
    ['Días ciclo promedio', avg(dias)==null ? '—' : avg(dias).toFixed(1) + ' d', dias.length + ' con fecha FV', 'navy'],
    ['Clientes', uniqueSorted(rows.map(r=>r.cliente_corto)).length, 'nombres cortos', 'info'],
  ];
  document.getElementById('kpis').innerHTML = items.map(([l,v,h,cls]) => `
    <div class="kpi ${{cls}}"><div class="label">${{l}}</div><div class="value">${{v}}</div><div class="hint">${{h}}</div></div>
  `).join('');
}}

function renderVentas(rows) {{
  const periodos = uniqueSorted(rows.map(r => r.periodo)).filter(p => p !== 'SIN PERIODO');
  const tipos = TIPOS_ORDEN.filter(t => rows.some(r => r.tipo === t));
  const datasets = tipos.map(t => {{
    const map = new Map();
    rows.filter(r => r.tipo === t).forEach(r => map.set(r.periodo, (map.get(r.periodo)||0) + (Number(r.monto)||0)));
    return {{
      label: t,
      data: periodos.map(p => map.get(p) || 0),
      backgroundColor: TIPO_COLOR[t] || '#829AB1',
      stack: 'ventas',
      borderWidth: 0,
      borderRadius: 5,
      maxBarThickness: 42,
    }};
  }});
  charts.mesTipo = new Chart(document.getElementById('chartMesTipo'), {{
    type: 'bar',
    data: {{ labels: periodos, datasets }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: interactIndex,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }},
        tooltip: tipGrupo(() => 'Ventas por periodo', {{ conTotal: true }}),
        datalabels: dlMoney({{ stacked: true, minRatio: 0.05 }})
      }},
      scales: {{
        x: {{ stacked: true, ticks: {{ maxRotation: 45, color:'#627D98', font:{{size:10}} }}, grid: {{ display:false }} }},
        y: {{ stacked: true, ticks: {{ callback: v => fmtM(v), color:'#627D98' }}, grid: {{ color:'#E4EBF2' }} }}
      }}
    }}
  }});

  const porTipo = groupSum(rows,'tipo').sort((a,b)=> TIPOS_ORDEN.indexOf(a.key) - TIPOS_ORDEN.indexOf(b.key));
  charts.tipo = new Chart(document.getElementById('chartTipo'), {{
    type: 'doughnut',
    data: {{
      labels: porTipo.map(x => x.key),
      datasets: [{{ data: porTipo.map(x => x.total), backgroundColor: porTipo.map(x => TIPO_COLOR[x.key]||'#829AB1'), borderWidth:0 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{
        legend: {{ position:'bottom' }},
        tooltip: {{
          callbacks: {{
            title: () => 'Mix por tipo',
            label: c => `${{c.label}}: ${{fmt(c.raw)}}`
          }}
        }},
        datalabels: dlPiePct()
      }}
    }}
  }});

  const porEst = groupSum(rows,'estado_venta').sort((a,b)=>b.total-a.total);
  charts.estado = new Chart(document.getElementById('chartEstado'), {{
    type:'bar',
    data: {{
      labels: porEst.map(x => ESTADO_LABEL[x.key] || x.key),
      datasets:[{{ label:'Monto', data: porEst.map(x=>x.total), backgroundColor:'#003E6D', borderRadius:8, maxBarThickness:48 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins:{{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Por estado', {{ conTotal: true }}), datalabels: dlMoney() }},
      scales:{{
        x:{{ ticks:{{ color:'#627D98', font:{{size:10}}, maxRotation:25 }}, grid:{{display:false}} }},
        y:{{ ticks:{{ callback:v=>fmtM(v), color:'#627D98' }}, grid:{{ color:'#E4EBF2' }} }}
      }}
    }}
  }});

  const porProg = groupSum(rows,'programa').sort((a,b)=>b.total-a.total).slice(0,10);
  charts.prog = new Chart(document.getElementById('chartProg'), {{
    type:'bar',
    data: {{
      labels: porProg.map(x=>x.key),
      datasets:[{{ label:'Monto', data: porProg.map(x=>x.total), backgroundColor:'#F37021', borderRadius:8, maxBarThickness:28 }}]
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins:{{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Programa', {{ conTotal: false }}), datalabels: dlMoney({{ horiz:true }}) }},
      scales:{{
        x:{{ ticks:{{ callback:v=>fmtM(v), color:'#627D98' }}, grid:{{ color:'#E4EBF2' }} }},
        y:{{ ticks:{{ color:'#102A43', font:{{size:10}} }}, grid:{{display:false}} }}
      }}
    }}
  }});
}}

function renderEmpresas(rows) {{
  const porCli = groupSum(rows,'cliente_corto').sort((a,b)=>b.total-a.total).slice(0,15);
  charts.cli = new Chart(document.getElementById('chartCli'), {{
    type:'bar',
    data: {{
      labels: porCli.map(x=>x.key),
      datasets:[{{ data: porCli.map(x=>x.total),
        backgroundColor: porCli.map((_,i)=> i%2 ? 'rgba(243,112,33,.92)' : 'rgba(0,62,109,.88)'),
        borderRadius:8, maxBarThickness:22 }}]
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins:{{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Top empresas', {{ conTotal: false }}), datalabels: dlMoney({{ horiz:true }}) }},
      scales:{{
        x:{{ ticks:{{ callback:v=>fmtM(v), color:'#627D98' }}, grid:{{ color:'#E4EBF2' }} }},
        y:{{ ticks:{{ color:'#102A43', font:{{size:10}} }}, grid:{{display:false}} }}
      }}
    }}
  }});

  const top10 = groupSum(rows,'cliente_corto').sort((a,b)=>b.total-a.total).slice(0,10);
  const tipos = TIPOS_ORDEN.filter(t => rows.some(r => r.tipo === t));
  charts.cliTipo = new Chart(document.getElementById('chartCliTipo'), {{
    type:'bar',
    data: {{
      labels: top10.map(x=>x.key),
      datasets: tipos.map(t => ({{
        label: t,
        data: top10.map(x => x.byTipo[t] || 0),
        backgroundColor: TIPO_COLOR[t] || '#829AB1',
        stack: 'emp',
        borderWidth: 0,
        maxBarThickness: 26,
      }}))
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins:{{
        legend:{{ position:'bottom', labels:{{ boxWidth:12 }} }},
        tooltip: tipGrupo(() => 'Empresa × tipo', {{ conTotal: true }}),
        datalabels: dlMoney({{ horiz:true, stacked:true, minRatio:0.06 }})
      }},
      scales:{{
        x:{{ stacked:true, ticks:{{ callback:v=>fmtM(v), color:'#627D98' }}, grid:{{ color:'#E4EBF2' }} }},
        y:{{ stacked:true, ticks:{{ color:'#102A43', font:{{size:10}} }}, grid:{{display:false}} }}
      }}
    }}
  }});
}}

function renderPendiente(rows) {{
  const pend = rows.filter(r => r.estado_venta === 'pendiente_facturar');
  const MES_COLORS = ['#003E6D','#F37021','#0A8F9C','#E9B949','#2F9E71','#7B68A6','#D64545','#829AB1','#1A5F8A','#FF8A3D','#5E8C61','#C45C26'];
  const mesSet = new Set();
  const byEmp = new Map();
  pend.forEach(r => {{
    const emp = r.cliente_corto || '(sin empresa)';
    const m = Number(r.mes_venta)||0;
    if (m < 1 || m > 12) return;
    mesSet.add(m);
    if (!byEmp.has(emp)) byEmp.set(emp, {{ byMes: {{}}, total: 0 }});
    const o = byEmp.get(emp);
    o.byMes[m] = (o.byMes[m]||0) + (Number(r.monto)||0);
    o.total += Number(r.monto)||0;
  }});
  const meses = [...mesSet].sort((a,b)=>a-b);
  const empresas = [...byEmp.entries()].sort((a,b)=>b[1].total-a[1].total).map(([e]) => e);

  const box = document.getElementById('box-chartPendEmp');
  if (box) box.style.height = Math.max(320, Math.min(980, 26 * Math.max(empresas.length,1) + 80)) + 'px';

  charts.pendEmp = new Chart(document.getElementById('chartPendEmp'), {{
    type: 'bar',
    data: {{
      labels: empresas,
      datasets: meses.map((m,i) => ({{
        label: MESES[m],
        data: empresas.map(e => byEmp.get(e).byMes[m] || 0),
        backgroundColor: MES_COLORS[(m-1) % MES_COLORS.length],
        stack: 'pend',
        maxBarThickness: 22,
        borderWidth: 0
      }}))
    }},
    options: {{
      indexAxis: 'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend: {{ position:'bottom', labels:{{ boxWidth:12, font:{{size:10}} }} }},
        tooltip: tipGrupo(() => 'Pendiente · empresa × mes', {{ conTotal: true }}),
        datalabels: dlMoney({{ horiz:true, stacked:true, minRatio:0.06 }})
      }},
      scales: {{
        x: {{ stacked:true, ticks:{{ callback:v=>fmtM(v), color:'#627D98' }}, grid:{{ color:'#E4EBF2' }} }},
        y: {{ stacked:true, ticks:{{ color:'#102A43', font:{{size:10}} }}, grid:{{display:false}} }}
      }}
    }}
  }});

  const colTot = meses.map(m => empresas.reduce((a,e)=>a+(byEmp.get(e).byMes[m]||0),0));
  const granTot = colTot.reduce((a,b)=>a+b,0);
  document.getElementById('pend-count').textContent = empresas.length;
  document.getElementById('pend-total').textContent = fmtM(granTot);
  document.getElementById('pend-thead').innerHTML = `<tr>
    <th>Cliente</th>${{meses.map(m=>`<th class="num">${{MESES[m]}}</th>`).join('')}}<th class="num">Total general</th>
  </tr>`;
  document.getElementById('tbl-pendiente').innerHTML = empresas.map(e => {{
    const o = byEmp.get(e);
    return `<tr>
      <td>${{e}}</td>
      ${{meses.map(m => {{
        const v = o.byMes[m]||0;
        return v ? `<td class="num">${{fmt(v)}}</td>` : `<td class="num empty"></td>`;
      }}).join('')}}
      <td class="num"><strong>${{fmt(o.total)}}</strong></td>
    </tr>`;
  }}).join('') || `<tr><td colspan="${{meses.length+2}}" style="color:var(--muted)">Sin pendiente con el filtro actual</td></tr>`;
  document.getElementById('pend-tfoot').innerHTML = empresas.length ? `<tr>
    <th>Total general</th>
    ${{colTot.map(v => `<th class="num">${{fmt(v)}}</th>`).join('')}}
    <th class="num">${{fmt(granTot)}}</th>
  </tr>` : '';

  registerChartTable('pendiente',
    ['Cliente', ...meses.map(m => MESES[m]), 'Total general'],
    [
      ...empresas.map(e => {{
        const o = byEmp.get(e);
        return [e, ...meses.map(m => o.byMes[m]||0), o.total];
      }}),
      ['Total general', ...colTot, granTot]
    ]
  );
}}

function renderCiclo(rows) {{
  const byCli = groupSum(rows,'cliente_corto').map(x => {{
    const prom = avg(x.dias);
    return {{ ...x, dias_promedio: prom, dias_mediana: median(x.dias), dias_p75: percentile(x.dias,75), categoria: categoria(prom), n_ciclo: x.dias.length }};
  }}).filter(x => x.n_ciclo > 0).sort((a,b)=>(b.dias_promedio||0)-(a.dias_promedio||0));

  const top = byCli.slice(0,20);
  charts.ciclo = new Chart(document.getElementById('chartCiclo'), {{
    type:'bar',
    data: {{
      labels: top.map(x=>x.key),
      datasets:[{{ data: top.map(x=>x.dias_promedio),
        backgroundColor: top.map(x => ({{Rapido:'#2F9E71',Normal:'#3E7CB1',Lento:'#E9B949',Critico:'#D64545'}})[x.categoria]),
        borderRadius:8, maxBarThickness:18 }}]
    }},
    options: {{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins:{{ legend:{{display:false}}, tooltip: tipGrupo(() => 'Ciclo (días)', {{ conTotal: false }}), datalabels: dlDays() }},
      scales:{{
        x:{{ title:{{display:true,text:'Días'}}, grid:{{color:'#E4EBF2'}}, ticks:{{color:'#627D98'}} }},
        y:{{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});

  const cats = ['Rapido','Normal','Lento','Critico'];
  const catCount = cats.map(c => byCli.filter(x=>x.categoria===c).length);
  charts.cat = new Chart(document.getElementById('chartCat'), {{
    type:'doughnut',
    data: {{ labels: cats, datasets:[{{ data: catCount, backgroundColor:['#2F9E71','#3E7CB1','#E9B949','#D64545'], borderWidth:0 }}] }},
    options: {{ responsive:true, maintainAspectRatio:false, plugins:{{ legend:{{position:'bottom'}}, tooltip:{{callbacks:{{label:c=>`${{c.label}}: ${{c.raw}} clientes`}}}}, datalabels: dlPiePct() }} }}
  }});
  document.getElementById('cat-resumen').innerHTML = cats.map((c,i) =>
    `<span class="badge ${{ {{Rapido:'b-rapido',Normal:'b-normal',Lento:'b-lento',Critico:'b-critico'}}[c] }}">${{c}}: ${{catCount[i]}}</span>`
  ).join('');
  document.getElementById('tbl-ciclo').innerHTML = byCli.map(r => `
    <tr>
      <td>${{r.key}}</td><td class="num">${{r.n_ciclo}}</td>
      <td class="num">${{r.dias_promedio.toFixed(1)}}</td>
      <td class="num">${{r.dias_mediana.toFixed(1)}}</td>
      <td class="num">${{r.dias_p75.toFixed(1)}}</td>
      <td>${{badgeCat(r.categoria)}}</td>
      <td class="num">${{fmt(r.total)}}</td>
    </tr>`).join('');
}}

function renderDetalle(rows) {{
  const show = rows.slice(0,500);
  document.getElementById('det-count').textContent = rows.length;
  document.getElementById('tbl-det').innerHTML = show.map(r => `
    <tr>
      <td>${{r.id_caso ?? '—'}}</td>
      <td>${{r.fecha_venta||''}}</td><td>${{r.periodo||''}}</td>
      <td>${{r.cliente_corto||''}}</td><td>${{r.tipo||''}}</td>
      <td>${{r.programa||'Sin programa'}}</td><td>${{badgeEstado(r.estado_venta)}}</td>
      <td class="num">${{fmt(r.monto)}}</td><td class="num">${{r.dias_ciclo ?? '—'}}</td>
    </tr>`).join('');
  registerChartTable('detalle',
    ['ID','Fecha','Periodo','Cliente','Tipo','Programa','Estado','Monto','Días'],
    show.map(r => [r.id_caso ?? '', r.fecha_venta||'', r.periodo||'', r.cliente_corto||'', r.tipo||'', r.programa||'', r.estado_venta||'', Number(r.monto)||0, r.dias_ciclo ?? ''])
  );
}}

function refresh() {{
  destroyCharts();
  const rows = applyFilters(RAW.ventas);
  renderKpis(rows);
  renderVentas(rows);
  renderEmpresas(rows);
  renderPendiente(rows);
  renderCiclo(rows);
  renderDetalle(rows);
  syncAllChartTables();
}}

{JS_CHART_TOOLS}

document.querySelectorAll('.tabs button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  }});
}});
document.querySelectorAll('#chips-tipo .chip').forEach(chip => {{
  chip.addEventListener('click', () => {{
    const t = chip.dataset.tipo;
    if (tiposSel.has(t)) {{ tiposSel.delete(t); chip.classList.remove('on'); }}
    else {{ tiposSel.add(t); chip.classList.add('on'); }}
    refresh();
  }});
}});
document.getElementById('btn-reset').addEventListener('click', () => {{
  tiposSel.clear();
  document.querySelectorAll('#chips-tipo .chip').forEach(c => c.classList.remove('on'));
  fillFilters();
  refresh();
}});
['f-anio','f-mes','f-cliente','f-programa','f-estado','f-fuente'].forEach(id => {{
  document.getElementById(id).addEventListener('change', refresh);
}});

fillFilters();
document.getElementById('gen').textContent = RAW.generado;
refresh();
</script>
{_mail_js()}
</body>
</html>
"""


def render_reglas(generado: str) -> str:
    empresas = "".join(
        f"<li><strong>{ALIAS_SIN_OC.get(normalizar_texto(x), normalizar_texto(x))}</strong> "
        f"<span style='color:#627D98'>({x.strip()})</span></li>"
        for x in EMPRESAS_SIN_OC_RAW
    )
    tipos = "".join(
        f"<li><span class='swatch' style='background:{TIPO_COLOR[k]}'></span>"
        f"<strong>{k}</strong> — {v}</li>"
        for k, v in TIPO_LABEL.items() if k != "OTROS"
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ADL · Reglas del análisis</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
<script src="auth.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  {_nav('reglas')}
  <p class="hero-mini">Reglas de negocio del dashboard · actualizado {generado}</p>
  <div class="rule-grid">
    <div class="panel">
      <h2>Fuentes (solo lectura)</h2>
      <ul style="color:var(--muted);line-height:1.5">
        <li><strong>Registro comercial (archivo OC)</strong> → hoja de control de ventas/casos</li>
        <li><strong>Juan consolidado</strong> → <em>Gráficos Facturación … Juan original.xlsx</em> (KR Resumen Consolidado + Tablas Auxiliares). Fuente de Solo facturación (todos los años, incluido 2026).</li>
        <li><strong>PROGRAMAS.xlsx</strong> → clasifica tipo de ingreso (SDG / PVE / SCR / Cap., etc.)</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Fecha de venta (sin duplicar)</h2>
      <ul style="color:var(--muted);line-height:1.5">
        <li>Con OC: fecha = Fecha del registro comercial</li>
        <li>Sin OC: mes/año = Facturación consolidada</li>
        <li>Anuladas (rojo/naranja) no suman</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Tipos de ingreso (PROGRAMAS.xlsx)</h2>
      <ul style="color:var(--muted);line-height:1.55;list-style:none;padding-left:0">{tipos}</ul>
    </div>
    <div class="panel">
      <h2>Estados del registro comercial</h2>
      <ul style="color:var(--muted);line-height:1.5">
        <li>Sin color → <strong>Falta OC/HES</strong> (aún no se puede facturar)</li>
        <li>Azul → <strong>Listo para facturar</strong> (tiene OC y HES)</li>
        <li>Verde → <strong>Ya facturada</strong></li>
        <li>Rojo / naranja → <strong>Anulada</strong></li>
        <li>El archivo fuente se llama “pendientes”, pero incluye todo el ciclo (también facturado)</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Ciclo y categorías</h2>
      <ul style="color:var(--muted);line-height:1.5">
        <li>Días = Fecha prefactura → Fecha factura (OC)</li>
        <li>Rápido ≤30 · Normal 31–60 · Lento 61–90 · Crítico &gt;90</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Empresas sin OC</h2>
      <ul style="color:var(--muted);line-height:1.5">{empresas}</ul>
    </div>
  </div>
  <div class="panel" style="margin-top:12px; border-top: 3px solid #D64545;">
    <h2>Exclusiones del análisis</h2>
    <ul style="color:var(--muted);line-height:1.55">
      <li><strong>Medio Ambiente</strong>: registros cuyo programa contenga “Medio Ambiente” quedan fuera.</li>
      <li><strong>I+D / Investigación</strong>: tipo de ingreso I+D queda fuera.</li>
      <li><strong>Sede “No corresponde”</strong>: ventas de otro sector de la empresa; no se incluyen en KPIs, gráficos ni detalle.</li>
      <li>Estas exclusiones aplican al dashboard unificado y al de solo facturación.</li>
    </ul>
  </div>

  <div class="panel" style="margin-top:12px">
    <h2>Solo facturación (fuente Juan)</h2>
    <ul style="color:var(--muted);line-height:1.5">
      <li>La fuente única es el Excel de <strong>Juan</strong> (KR Resumen Consolidado). Año y mes salen de las columnas Año / PERIODO (o Month).</li>
      <li><strong>No se usa</strong> <em>facturado 2026.xlsx</em>.</li>
      <li><strong>No se consideran provisionados</strong>: el análisis toma el Año del consolidado tal cual, sin marcar ni separar venta≠factura.</li>
      <li>Para actualizar 2026 (p. ej. julio en adelante), basta con actualizar el archivo de Juan y regenerar el dashboard.</li>
    </ul>
  </div>

  <div class="panel" style="margin-top:12px">
    <h2>Indicadores</h2>
    <ul style="color:var(--muted);line-height:1.5">
      <li><strong>Unificado</strong>: combina registro comercial + facturación sin OC.</li>
      <li><strong>Solo facturación</strong>: solo el consolidado Juan (sin facturado 2026.xlsx ni provisionados).</li>
      <li>En ambos, cada gráfico tiene botones <em>Gráfico / Tabla / Copiar</em>.</li>
      <li><strong>Promedio por documento</strong> = monto total filtrado ÷ cantidad de documentos.</li>
    </ul>
  </div>
  {_footer("página de reglas")}
</div>
{_mail_js()}
</body>
</html>
"""


def render_dashboard_excel(payload: dict) -> str:
    """Dashboard estilo hojas Gráficos por Empresa / por Año / Top 30."""
    return render_dashboard_excel_views(
        payload,
        css=CSS,
        nav_html=_nav("excel"),
        tipo_color=TIPO_COLOR,
    )


def main() -> None:
    print("Cargando fuentes...")
    mapa = leer_mapa_empresas()
    mapa_prog = leer_mapa_programas()
    print(f"  PROGRAMAS mapeados: {len(mapa_prog):,}")

    oc = preparar_oc(leer_oc_pendientes(), mapa)
    fac = preparar_fac(leer_facturacion(), mapa)

    for df in (oc, fac):
        m = df["Cliente_norm"].isin(ALIAS_SIN_OC)
        df.loc[m, "Empresa_Abr"] = df.loc[m, "Cliente_norm"].map(ALIAS_SIN_OC)
        df.loc[m, "Cliente_key"] = df.loc[m, "Empresa_Abr"]

    print("Unificando ventas + tipos de ingreso...")
    ventas = construir_ventas_unificadas(oc, fac, mapa_prog)

    print("Armando dashboard Solo facturación (fuente: Juan consolidado)...")
    ventas_fac = construir_ventas_facturacion_excel(fac, mapa_prog)
    v26 = ventas_fac[pd.to_numeric(ventas_fac["anio_venta"], errors="coerce") == 2026]
    print(
        f"  Juan 2026: {len(v26):,} lineas · {v26['id_caso'].nunique():,} docs · "
        f"${v26['monto'].sum():,.0f} · meses {sorted(pd.to_numeric(v26['mes_venta'], errors='coerce').dropna().astype(int).unique().tolist())}"
    )

    cols_u = [
        "fuente", "id_origen", "id_caso", "cliente_corto", "programa", "tipo", "tipo_nombre",
        "monto", "anio_venta", "mes_venta", "periodo", "estado_venta",
        "fecha_venta", "dias_ciclo",
    ]
    ventas_js = ventas[cols_u].copy()
    ventas_js = ventas_js.where(pd.notnull(ventas_js), None)

    cols_f = [
        "fuente", "id_origen", "id_caso", "cliente_corto", "programa", "tipo", "tipo_nombre",
        "monto", "anio_venta", "mes_venta", "periodo", "estado_venta", "sede", "fecha_venta",
        "es_provisionado", "anio_origen",
    ]
    for c in cols_f:
        if c not in ventas_fac.columns:
            ventas_fac[c] = False if c == "es_provisionado" else None
    fac_js = ventas_fac[cols_f].copy()
    fac_js = fac_js.where(pd.notnull(fac_js), None)

    generado = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    payload = {
        "generado": generado,
        "ventas": json.loads(ventas_js.to_json(orient="records", force_ascii=False)),
        "empresas_sin_oc": [
            ALIAS_SIN_OC.get(normalizar_texto(x), normalizar_texto(x))
            for x in EMPRESAS_SIN_OC_RAW
        ],
    }
    payload_fac = {
        "generado": generado,
        "ventas": json.loads(fac_js.to_json(orient="records", force_ascii=False)),
    }

    ventas.to_csv(DIR_SALIDA / "ventas_unificadas.csv", index=False, encoding="utf-8-sig")
    ventas_fac.to_csv(DIR_SALIDA / "ventas_facturacion_excel.csv", index=False, encoding="utf-8-sig")
    (DIR_SALIDA / "dashboard_facturacion.html").write_text(render_dashboard(payload), encoding="utf-8")
    (DIR_SALIDA / "dashboard_facturacion_excel.html").write_text(
        render_dashboard_excel(payload_fac), encoding="utf-8"
    )
    (DIR_SALIDA / "reglas.html").write_text(render_reglas(generado), encoding="utf-8")

    print("Mix unificado:")
    print(ventas.groupby("tipo")["monto"].agg(["count", "sum"]).sort_values("sum", ascending=False).to_string())
    print("\nMix solo Excel facturación:")
    print(
        ventas_fac.groupby("tipo")["monto"]
        .agg(["count", "sum"])
        .sort_values("sum", ascending=False)
        .to_string()
    )
    print(f"\nUnificado:     {DIR_SALIDA / 'dashboard_facturacion.html'}")
    print(f"Solo factura:  {DIR_SALIDA / 'dashboard_facturacion_excel.html'}")
    print(f"Reglas:        {DIR_SALIDA / 'reglas.html'}")


if __name__ == "__main__":
    main()
