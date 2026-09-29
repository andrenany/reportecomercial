# -*- coding: utf-8 -*-
"""PNG evolutivo OC pendiente de facturar (sep-2025 a sep-2026). No toca el dashboard."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from leer_oc_pendientes import leer_oc_pendientes, preparar_oc

OUT = Path(__file__).resolve().parent / "oc_pendiente_facturar_sep2025_sep2026.png"
INI = pd.Timestamp("2025-09-01")
FIN = pd.Timestamp("2026-09-30")

ETIQUETAS_BASURA = {
    "PENDIENTE DE OC/HES",
    "POR FACTURAR",
    "FACTURADO",
    "NULO/ N.CREDITO",
    "NULO/N.CREDITO",
}
MESES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]
NAVY = "#003E6D"
ORANGE = "#F37021"
TEAL = "#0A8F9C"
MUTED = "#5B738B"


def main() -> None:
    print("Leyendo OC Pendientes de facturar.xlsx (solo lectura)...")
    oc = preparar_oc(leer_oc_pendientes())
    oc = oc[oc["ID"].notna()].copy()
    oc = oc[~oc["Cliente_norm"].isin(ETIQUETAS_BASURA)].copy()
    oc = oc[oc["estado"].isin(["pendiente_facturar", "listo_para_facturar"])].copy()
    oc = oc.dropna(subset=["Fecha_limpia"])
    oc = oc[(oc["Fecha_limpia"] >= INI) & (oc["Fecha_limpia"] <= FIN)].copy()
    oc["monto"] = pd.to_numeric(oc["Total_num"], errors="coerce").fillna(0)
    oc["periodo"] = oc["Fecha_limpia"].dt.to_period("M")

    periodos = pd.period_range(INI, FIN, freq="M")
    filas = []
    for p in periodos:
        sub = oc[oc["periodo"] == p]
        filas.append({
            "periodo": p,
            "label": f"{MESES[p.month - 1]} {p.year}",
            "pendiente": float(sub.loc[sub["estado"] == "pendiente_facturar", "monto"].sum()),
            "listo": float(sub.loc[sub["estado"] == "listo_para_facturar", "monto"].sum()),
            "docs": int(len(sub)),
        })
    df = pd.DataFrame(filas)
    df["total"] = df["pendiente"] + df["listo"]

    tot = df["total"].sum()
    docs = int(df["docs"].sum())
    print(f"  {docs:,} docs · ${tot:,.0f} · {INI:%b %Y}–{FIN:%b %Y}")

    x = np.arange(len(df))
    w = 0.62
    fig, ax = plt.subplots(figsize=(14.2, 7.2), dpi=160)
    fig.patch.set_facecolor("#F7FAFC")
    ax.set_facecolor("#FFFFFF")

    ax.bar(x, df["pendiente"], width=w, color=NAVY, label="Falta OC / HES", zorder=3)
    ax.bar(
        x, df["listo"], width=w, bottom=df["pendiente"],
        color=ORANGE, label="Listo para facturar", zorder=3,
    )
    ax.plot(x, df["total"], color=TEAL, linewidth=2.2, marker="o", markersize=5.5, zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(df["label"], rotation=40, ha="right", fontsize=10, color=NAVY)
    ax.set_ylabel("Monto ($)", color=NAVY, fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v/1e6:,.0f} M".replace(",", ".")))
    ax.grid(axis="y", color="#D7E3EE", linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D7E3EE")
    ax.spines["bottom"].set_color("#D7E3EE")
    ax.tick_params(colors=MUTED)

    ymax = max(df["total"].max() * 1.16, 1)
    ax.set_ylim(0, ymax)
    for i, row in df.iterrows():
        if row["total"] <= 0:
            continue
        ax.annotate(
            f"${row['total']/1e6:,.1f} M".replace(",", "."),
            (i, row["total"]),
            textcoords="offset points",
            xytext=(0, 7),
            ha="center",
            fontsize=8,
            color=NAVY,
            fontweight="bold",
        )

    generado = datetime.now().strftime("%Y-%m-%d %H:%M")
    ax.set_title(
        "OC pendiente de facturar · evolutivo mensual",
        loc="left",
        fontsize=16,
        fontweight="bold",
        color=NAVY,
        pad=18,
    )
    ax.text(
        0, 1.01,
        "Septiembre 2025 – Septiembre 2026  ·  stock actual del Excel (no es un histórico de cierres)",
        transform=ax.transAxes,
        fontsize=9.5,
        color=MUTED,
        va="bottom",
    )
    ax.legend(frameon=False, loc="upper right", fontsize=10)
    fig.text(
        0.01, 0.01,
        f"{docs:,} documentos  ·  total ${tot:,.0f}  ·  generado {generado}".replace(",", "."),
        fontsize=8.5,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    main()
