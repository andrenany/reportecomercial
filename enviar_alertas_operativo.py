# -*- coding: utf-8 -*-
"""Al regenerar la consulta, avisa por correo las visitas con OPERATIVO NO INGRESADO.

Los destinatarios están en alertas_correo.env (no se sube a Git).
El envío usa el mismo FormSubmit que el botón «Solicitar actualización».
La primera vez, cada correo debe confirmar el mensaje de activación de FormSubmit.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG = BASE_DIR / "alertas_correo.env"
ESTADO = BASE_DIR / "alertas_correo_estado.json"
SITIO = "https://andrenany.github.io/reportecomercial/consulta_facturacion.html"
MESES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
VETS_FUERA = {"no aplica", "cliente", "(sin veterinario)"}
MAX_LINEAS = 60


def leer_destinatarios() -> dict[str, list[str]]:
    if not CONFIG.exists():
        return {}
    out: dict[str, list[str]] = {}
    for line in CONFIG.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        sede, raw = line.split("=", 1)
        correos = [c.strip() for c in raw.split(",") if c.strip() and "@" in c]
        if correos:
            out[sede.strip().upper()] = correos
    return out


def _cero(valor) -> bool:
    return abs(float(valor or 0)) < 0.0001


def _clave(dia, vet, emp, centro) -> tuple[str, str, str, str]:
    return tuple(str(x or "").strip().upper() for x in (dia, vet, emp, centro))


def visitas_sin_operativo(calendario: list[dict], costos: list[dict], hoy: date | None = None) -> list[dict]:
    """Visitas del mes en curso, hasta hoy, con todos los co_ en 0 y que no son solo screening."""
    hoy = hoy or date.today()
    prefijo = hoy.strftime("%Y-%m")
    limite = hoy.isoformat()
    costos_map = {
        _clave(c.get("dia"), c.get("veterinario"), c.get("empresa"), c.get("centro")): c
        for c in costos or []
    }
    grupos: dict[tuple, dict] = {}
    for row in calendario or []:
        dia = str(row.get("dia") or "")
        if not dia.startswith(prefijo) or dia > limite:
            continue
        vet = str(row.get("veterinario") or "")
        if vet.strip().lower() in VETS_FUERA:
            continue
        key = _clave(dia, vet, row.get("empresa"), row.get("centro"))
        grupo = grupos.get(key)
        if grupo is None:
            grupo = {
                "dia": dia,
                "veterinario": vet,
                "sede": str(row.get("sede") or "").strip().upper(),
                "empresa": row.get("empresa") or "",
                "centro": row.get("centro") or "",
                "programas": set(),
            }
            grupos[key] = grupo
        programa = str(row.get("programa") or "").strip()
        if programa:
            grupo["programas"].add(programa)

    pendientes = []
    for key, grupo in grupos.items():
        programas = grupo["programas"]
        if programas and all("SCREEN" in p.upper() for p in programas):
            continue
        costo = costos_map.get(key)
        if costo and not (
            _cero(costo.get("co_km")) and _cero(costo.get("co_uf")) and _cero(costo.get("co_otros"))
        ):
            continue
        grupo["programas_txt"] = ", ".join(sorted(programas, key=lambda s: s.lower()))
        pendientes.append(grupo)
    pendientes.sort(key=lambda g: (g["dia"], g["veterinario"].lower(), g["empresa"].lower(), g["centro"].lower()))
    return pendientes


def _cuerpo(sede_txt: str, mes_txt: str, filas: list[dict]) -> str:
    lineas = [
        f"Visitas de {mes_txt} con OPERATIVO NO INGRESADO.",
        "En la planilla, CO km, aumentos UF y otros CO están en 0, o no hay fila.",
        "No se incluyen los programas que son solo screening.",
        "",
        f"Sede: {sede_txt}",
        f"Pendientes: {len(filas)}",
        "",
    ]
    mostrar = filas[:MAX_LINEAS]
    for fila in mostrar:
        lineas.append(
            f"{fila['dia']} · {fila['veterinario']} · {fila['empresa']} · {fila['centro']}"
            + (f" · {fila['programas_txt']}" if fila["programas_txt"] else "")
        )
    if len(filas) > len(mostrar):
        lineas.append(f"... y {len(filas) - len(mostrar)} visitas más")
    lineas.extend(["", f"Calendario: {SITIO}"])
    return "\n".join(lineas)


def _ya_enviado(correo: str, firma: str) -> bool:
    if not ESTADO.exists():
        return False
    try:
        data = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (data.get(correo) or {}).get("firma") == firma


def _marcar_enviado(correo: str, firma: str) -> None:
    data = {}
    if ESTADO.exists():
        try:
            data = json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data[correo] = {"firma": firma, "cuando": date.today().isoformat()}
    ESTADO.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _enviar(correo: str, asunto: str, cuerpo: str) -> None:
    payload = json.dumps(
        {
            "_subject": asunto,
            "_template": "box",
            "_captcha": "false",
            "mensaje": cuerpo,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://formsubmit.co/ajax/" + correo,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ADL-reporte-comercial",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            raw = res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{correo}: FormSubmit respondió {exc.code}. {detalle[:240]}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    if str(data.get("success", "")).lower() == "false":
        raise RuntimeError(f"{correo}: {data.get('message') or raw[:240]}")


def enviar_alertas(calendario: list[dict], costos: list[dict]) -> None:
    destinos = leer_destinatarios()
    if not destinos:
        print("  Alertas: no hay correos en alertas_correo.env. No se envía nada.")
        return

    hoy = date.today()
    mes_txt = f"{MESES[hoy.month]} {hoy.year}"
    pendientes = visitas_sin_operativo(calendario, costos, hoy)
    print(f"  Alertas: {len(pendientes)} visitas sin operativo en {mes_txt}.")

    enviados = 0
    for sede, correos in destinos.items():
        if sede == "TODAS":
            filas = pendientes
            sede_txt = "todas las sedes"
        else:
            filas = [f for f in pendientes if f["sede"] == sede]
            sede_txt = {
                "AYSEN": "Aysén",
                "VILLARRICA": "Villarrica",
                "PUERTO MONTT": "Puerto Montt",
            }.get(sede, sede.title())
        if not filas:
            print(f"    {sede_txt}: sin pendientes.")
            continue
        cuerpo = _cuerpo(sede_txt, mes_txt, filas)
        firma = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
        asunto = f"ADL · Operativo no ingresado · {sede_txt} · {mes_txt} · {len(filas)}"
        for correo in correos:
            if _ya_enviado(correo, firma):
                print(f"    {correo}: el listado no cambió, no se reenvía.")
                continue
            _enviar(correo, asunto, cuerpo)
            _marcar_enviado(correo, firma)
            enviados += 1
            print(f"    Enviado a {correo} ({len(filas)} visitas).")
    print(f"  Alertas enviadas: {enviados}.")
