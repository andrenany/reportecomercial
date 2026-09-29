# -*- coding: utf-8 -*-
"""
Fotos mensuales del stock en blanco (Falta OC/HES).

El 28 de cada mes (o el primer generate desde el 28) se guarda una foto
del pendiente de facturar. Las fotos se acumulan en fotos_pendiente_blanco.json.
"""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from leer_oc_pendientes import DIR_SALIDA, limpiar_fecha

ARCHIVO_FOTOS = DIR_SALIDA / "fotos_pendiente_blanco.json"
DIA_FOTO = 28
ETQ = {
    "PENDIENTE DE OC/HES",
    "POR FACTURAR",
    "FACTURADO",
    "NULO/ N.CREDITO",
    "NULO/N.CREDITO",
}
PAT_OC = re.compile(r"OC\s*(?:parcial\s*)?(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", re.I)


def _periodo(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _fecha_oc_obs(obs) -> pd.Timestamp:
    m = PAT_OC.search(str(obs or ""))
    if not m:
        return pd.NaT
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return pd.Timestamp(year=y, month=mo, day=d)
    except ValueError:
        return pd.NaT


def cargar_fotos() -> list[dict]:
    if not ARCHIVO_FOTOS.exists():
        return []
    try:
        data = json.loads(ARCHIVO_FOTOS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return list(data.get("fotos") or [])
    if isinstance(data, list):
        return data
    return []


def guardar_fotos(fotos: list[dict]) -> None:
    fotos = sorted(fotos, key=lambda f: f.get("periodo") or "")
    ARCHIVO_FOTOS.write_text(
        json.dumps({"fotos": fotos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def stock_blanco_actual(ventas: pd.DataFrame) -> tuple[float, int]:
    """Filas blancas = Falta OC/HES (mismo criterio que la hoja Pendiente facturar)."""
    blanco = ventas[ventas["estado_venta"] == "pendiente_facturar"]
    monto = float(pd.to_numeric(blanco["monto"], errors="coerce").fillna(0).sum())
    return monto, int(len(blanco))


def _preparar_oc_blanco(oc: pd.DataFrame) -> pd.DataFrame:
    out = oc.copy()
    if "Fecha_limpia" not in out.columns:
        out["Fecha_limpia"] = limpiar_fecha(out["Fecha"])
    out = out[out["ID"].notna()].copy()
    out = out[~out["Cliente_norm"].isin(ETQ)].copy()
    out = out[out["estado"] != "anulada"].copy()
    out["monto"] = pd.to_numeric(out["Total_num"], errors="coerce").fillna(0)
    out["fecha_oc"] = out["Observaciones"].map(_fecha_oc_obs)
    return out


def reconstruir_blanco_al(oc: pd.DataFrame, d: date) -> tuple[float, int]:
    """Aprox. de filas blancas en la fecha d (aún sin OC/HES)."""
    ts = pd.Timestamp(d)
    base = _preparar_oc_blanco(oc)
    existe = base["Fecha_limpia"].notna() & (base["Fecha_limpia"] <= ts)
    sigue_blanco = base["estado"] == "pendiente_facturar"
    gano_oc_despues = base["fecha_oc"].notna() & (base["fecha_oc"] > ts)
    mask = existe & (sigue_blanco | gano_oc_despues)
    sub = base.loc[mask]
    return float(sub["monto"].sum()), int(len(sub))


def cortes_dia28(hasta: date, desde: date | None = None) -> list[date]:
    if desde is None:
        desde = date(2025, 9, 1)
    out = []
    y, m = desde.year, desde.month
    while date(y, m, 1) <= date(hasta.year, hasta.month, 1):
        last = monthrange(y, m)[1]
        d = date(y, m, min(DIA_FOTO, last))
        if d > hasta:
            break
        out.append(d)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def sembrar_reconstruidas(fotos: list[dict], oc: pd.DataFrame, hoy: date) -> list[dict]:
    por_periodo = {f.get("periodo"): f for f in fotos if f.get("periodo")}
    for d in cortes_dia28(hoy):
        per = _periodo(d)
        actual = por_periodo.get(per)
        if actual and actual.get("origen") == "foto":
            continue
        if actual and actual.get("origen") == "reconstruido":
            continue
        monto, n = reconstruir_blanco_al(oc, d)
        por_periodo[per] = {
            "periodo": per,
            "fecha_foto": d.isoformat(),
            "tomada": None,
            "monto": round(monto, 0),
            "n": n,
            "origen": "reconstruido",
        }
    return list(por_periodo.values())


def tomar_foto_si_corresponde(fotos: list[dict], ventas: pd.DataFrame, hoy: date | None = None) -> list[dict]:
    """Si ya pasó el día 28 del mes y no hay foto real, la toma ahora."""
    hoy = hoy or date.today()
    if hoy.day < DIA_FOTO:
        return fotos
    per = _periodo(hoy)
    por = {f.get("periodo"): f for f in fotos if f.get("periodo")}
    if por.get(per, {}).get("origen") == "foto":
        return fotos
    monto, n = stock_blanco_actual(ventas)
    fecha_oficial = date(hoy.year, hoy.month, min(DIA_FOTO, monthrange(hoy.year, hoy.month)[1]))
    por[per] = {
        "periodo": per,
        "fecha_foto": fecha_oficial.isoformat(),
        "tomada": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "monto": round(monto, 0),
        "n": n,
        "origen": "foto",
    }
    print(f"  Foto {per} (blanco / Falta OC-HES): ${monto:,.0f} · {n} docs")
    return list(por.values())


def actualizar_fotos_pendiente(oc: pd.DataFrame, ventas: pd.DataFrame) -> list[dict]:
    hoy = date.today()
    fotos = cargar_fotos()
    fotos = sembrar_reconstruidas(fotos, oc, hoy)
    fotos = tomar_foto_si_corresponde(fotos, ventas, hoy)
    fotos = sorted(fotos, key=lambda f: f.get("periodo") or "")
    guardar_fotos(fotos)
    return fotos
