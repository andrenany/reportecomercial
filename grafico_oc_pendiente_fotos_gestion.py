# -*- coding: utf-8 -*-
"""
PNG de gestión desde OC Pendientes de facturar.xlsx (hoja OC PENDIENTES).

El archivo vivo no guarda fotos mensuales. Se reconstruye el stock al día 28
de cada mes: el servicio ya existía (Fecha) y aún no estaba facturado (Fecha_doc).
No modifica Excel ni el dashboard.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from leer_oc_pendientes import EXCEL_OC, leer_oc_pendientes, preparar_oc, limpiar_fecha

OUT = Path(__file__).resolve().parent / "oc_pendiente_dia28_oc_pendientes.png"
ETQ = {
    "PENDIENTE DE OC/HES", "POR FACTURAR", "FACTURADO",
    "NULO/ N.CREDITO", "NULO/N.CREDITO",
}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
NAVY = "#003E6D"
ORANGE = "#F37021"
MUTED = "#5B738B"
PAT_OC = re.compile(r"OC\s*(?:parcial\s*)?(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", re.I)


def copiar_excel(origen: str) -> str:
    src = Path(origen)
    tmp = Path(tempfile.gettempdir()) / "oc_pendientes_foto.xlsx"
    try:
        shutil.copyfile(src, tmp)
        return str(tmp)
    except OSError as exc:
        alt = Path(tempfile.gettempdir()) / "oc_pendientes_tmp.xlsx"
        if alt.exists():
            print(f"  aviso: no se pudo copiar el Excel vivo ({exc}). Uso copia temporal.")
            return str(alt)
        raise


def oc_vacia(v) -> bool:
    t = str(v or "").strip().lower()
    return t in {"", "nan", "none", "pendiente", "pend.", "s/n", "-", "no aplica", "ok"}


def fecha_oc_obs(obs):
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


def cargar() -> pd.DataFrame:
    path = copiar_excel(EXCEL_OC)
    print(f"Leyendo OC Pendientes:\n  {EXCEL_OC}")
    oc = preparar_oc(leer_oc_pendientes(path))
    oc["Fecha_doc_limpia"] = limpiar_fecha(oc["Fecha_doc"])
    oc = oc[oc["ID"].notna()].copy()
    oc = oc[~oc["Cliente_norm"].isin(ETQ)].copy()
    oc = oc[oc["estado"] != "anulada"].copy()
    oc["monto"] = pd.to_numeric(oc["Total_num"], errors="coerce").fillna(0)
    doc = oc["Fecha_doc_limpia"]
    oc.loc[(doc < "2018-01-01") | (doc > "2027-12-31"), "Fecha_doc_limpia"] = pd.NaT
    oc["oc_vacia"] = oc["N° OC"].map(oc_vacia)
    oc["fecha_oc"] = oc["Observaciones"].map(fecha_oc_obs)
    return oc.reset_index(drop=True)


def cortes_dia28(hoy: date) -> list[date]:
    out = []
    for y, m in [(2025, 9), (2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]:
        last = monthrange(y, m)[1]
        d = date(y, m, min(28, last))
        if d > hoy:
            d = hoy
        if d not in out:
            out.append(d)
    return out


def stock_al(oc: pd.DataFrame, d: date) -> dict:
    ts = pd.Timestamp(d)
    existe = oc["Fecha_limpia"].notna() & (oc["Fecha_limpia"] <= ts)
    sigue = oc["estado"].isin(["pendiente_facturar", "listo_para_facturar"])
    fact_despues = (oc["estado"] == "facturada_ok") & oc["Fecha_doc_limpia"].notna() & (oc["Fecha_doc_limpia"] > ts)
    abierto = existe & (sigue | fact_despues)
    sin_oc = abierto & (
        oc["oc_vacia"]
        | (oc["fecha_oc"].notna() & (oc["fecha_oc"] > ts))
    )
    return {
        "fecha": d,
        "sin_oc": float(oc.loc[sin_oc, "monto"].sum()),
        "con_oc": float(oc.loc[abierto & ~sin_oc, "monto"].sum()),
        "n": int(abierto.sum()),
        "n_sin": int(sin_oc.sum()),
    }


def main() -> None:
    oc = cargar()
    hoy = date.today()
    filas = [stock_al(oc, d) for d in cortes_dia28(hoy)]
    df = pd.DataFrame(filas)
    df["total"] = df["sin_oc"] + df["con_oc"]
    df["label"] = [f"28-{MESES[d.month - 1]}\n{d.year}" if d.day == 28 else f"{d.day}-{MESES[d.month - 1]}\n{d.year}" for d in df["fecha"]]
    for _, r in df.iterrows():
        print(f"  {r['fecha']}  total ${r['total']:,.0f}  sin OC ${r['sin_oc']:,.0f}  n={r['n']}")

    x = np.arange(len(df))
    w = 0.62
    fig, ax = plt.subplots(figsize=(14.4, 7.4), dpi=160)
    fig.patch.set_facecolor("#F7FAFC")
    ax.set_facecolor("#FFFFFF")
    ax.bar(x, df["sin_oc"], width=w, color=NAVY, label="Sin OC / HES", zorder=3)
    ax.bar(x, df["con_oc"], width=w, bottom=df["sin_oc"], color=ORANGE, label="Con OC, aún sin facturar", zorder=3)
    ax.plot(x, df["total"], color="#0A8F9C", linewidth=2.2, marker="o", markersize=5.5, zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(df["label"], fontsize=9, color=NAVY)
    ax.set_ylabel("Stock pendiente de facturar ($)", color=NAVY, fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1e6:,.0f} M".replace(",", ".")))
    ax.grid(axis="y", color="#D7E3EE", linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D7E3EE")
    ax.spines["bottom"].set_color("#D7E3EE")
    ax.tick_params(colors=MUTED)
    ax.set_ylim(0, max(df["total"].max() * 1.16, 1))
    for i, r in df.iterrows():
        if r["total"] <= 0:
            continue
        ax.annotate(
            f"${r['total']/1e6:,.0f} M".replace(",", "."),
            (i, r["total"]),
            textcoords="offset points", xytext=(0, 7),
            ha="center", fontsize=8, color=NAVY, fontweight="bold",
        )

    ax.set_title(
        "OC pendiente de facturar · foto al día 28 de cada mes",
        loc="left", fontsize=15.5, fontweight="bold", color=NAVY, pad=18,
    )
    ax.text(
        0, 1.01,
        "Fuente: OC Pendientes de facturar.xlsx (Administración). "
        "Reconstruido: el caso ya existía y todavía no tenía fecha de factura.",
        transform=ax.transAxes, fontsize=9.2, color=MUTED, va="bottom",
    )
    ax.legend(frameon=False, loc="upper right", fontsize=9.5)

    df26 = df[df["fecha"].map(lambda d: d.year == 2026)]
    if len(df26) >= 2:
        a, b = df26.iloc[0], df26.iloc[-1]
        pico = df26.loc[df26["sin_oc"].idxmax()]
        d_sin = b["sin_oc"] - pico["sin_oc"]
        pct = d_sin / pico["sin_oc"] * 100 if pico["sin_oc"] else 0
        pie = (
            f"Sin OC 2026: pico {pico['fecha']:%d-%b} ${pico['sin_oc']/1e6:,.0f} M → "
            f"{b['fecha']:%d-%b} ${b['sin_oc']/1e6:,.0f} M  "
            f"({d_sin/1e6:+,.0f} M · {pct:+.0f}%)"
        ).replace(",", ".")
    else:
        pie = f"{len(df)} cortes"
    fig.text(
        0.01, 0.012,
        pie + f"  ·  generado {datetime.now():%Y-%m-%d %H:%M}",
        fontsize=8.5, color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.98))
    fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    main()
