"""
Dashboard HTML que replica las hojas del Excel de Facturación:
- Gráficos por Empresa
- Gráficos por Año
- Gráficos Nuevos Top 30
"""

from __future__ import annotations

import json

from chart_tools import JS_CHART_TOOLS, panel_chart


def render_dashboard_excel(payload: dict, css: str, nav_html: str, tipo_color: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    tipo_colors = json.dumps(tipo_color, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ADL · Facturación (gráficos Excel)</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<script src="auth.js"></script>
<style>{css}
.cmp-note {{ font-size:.82rem; color:var(--muted); margin:0 0 10px; }}
</style>
</head>
<body>
<div class="wrap">
  {nav_html}

  <div class="filters">
    <div class="chip-row">
      <span class="chip-label">Tipo ingreso</span>
      <div id="chips-tipo" style="display:contents">
        <button type="button" class="chip" data-tipo="SDG">SDG</button>
        <button type="button" class="chip" data-tipo="PVE">PVE</button>
        <button type="button" class="chip" data-tipo="SCR">SCR</button>
      </div>
      <div class="actions"><button class="btn ghost" id="btn-reset" type="button">Limpiar</button></div>
    </div>
    <p class="hint-multi">Multi-selección con búsqueda. Sin elegir mes = <strong>acumulado comparable</strong> (mismo tramo ene→último mes del año comparar). Si marcas meses, se usan exactamente esos.</p>
    <div class="filters-top">
      <label class="f">Empresa<div class="msel" id="f-empresa" data-empty="Todas"></div></label>
      <label class="f">Mes<div class="msel" id="f-mes" data-empty="Acumulado YTD"></div></label>
      <label class="f">Año base<div class="msel" id="f-anio-a" data-empty="2025"></div></label>
      <label class="f">Año comparar<div class="msel" id="f-anio-b" data-empty="2026"></div></label>
      <label class="f">Sede<div class="msel" id="f-sede" data-empty="Todas"></div></label>
    </div>
  </div>

  <section class="kpis" id="kpis"></section>

  <div class="tabs">
    <button class="active" data-tab="vista-empresa">Por Empresa</button>
    <button data-tab="vista-anio">Por Año</button>
    <button data-tab="vista-top">Top empresas</button>
    <button data-tab="vista-detalle">Detalle</button>
  </div>

  <section id="vista-empresa" class="section active">
    <p class="cmp-note">Como la hoja <em>Gráficos por Empresa</em>: meses en el eje X y series por año. Responde a empresa, tipo, sede y periodo (mes / acumulado YTD).</p>
    <div class="grid">
      {panel_chart("Facturación mensual por año", "Meses del periodo activo (filtro o YTD).", "chartEmpMes")}
      {panel_chart("Acumulado por año", "Suma del mismo periodo en cada año (empresa + tipo + sede).", "chartEmpAnio", "sm")}
    </div>
  </section>

  <section id="vista-anio" class="section">
    <p class="cmp-note"><strong>Acumulado</strong> = mismo tramo de meses en año A y B (p. ej. si 2026 llega a junio, 2025 también suma ene–jun), salvo que marques meses en el filtro.
      No se incluyen montos provisionados.</p>
    <div class="grid">
      {panel_chart("Ventas por año × tipo", "Serie histórica anual (SDG, PVE, SCR y Total) · filtros activos.", "chartAnioTipo")}
      {panel_chart("Por sede × año", "Puerto Montt / Villarrica / Aysén · filtros activos.", "chartAnioSede", "sm")}
    </div>
    <div class="grid" style="margin-top:12px">
      {panel_chart("Meses del año comparar", "Desglose mensual del año B en el periodo activo.", "chartAnioMes")}
      {panel_chart("Variación año B vs A (tipo)", "Δ % por tipo · acumulado comparable.", "chartAnioDelta", "sm")}
    </div>
    <div class="grid" style="margin-top:12px">
      {panel_chart("Variación año B vs A (sede)", "Δ % por sede · acumulado comparable.", "chartAnioDeltaSede", "sm")}
    </div>
    <div class="panel" style="margin-top:12px" data-panel="chartAnioDeltaEmpSede">
      <div class="panel-head">
        <div class="titles">
          <h2>Variación ventas · empresa × sede</h2>
          <p class="desc">Δ $ año B − año A. Cada color = sede (apilado desde 0).</p>
        </div>
        <div class="panel-tools">
          <button type="button" class="on" data-mode="chart" data-target="chartAnioDeltaEmpSede">Gráfico</button>
          <button type="button" data-mode="table" data-target="chartAnioDeltaEmpSede">Tabla</button>
          <button type="button" data-copy="chartAnioDeltaEmpSede">Copiar</button>
        </div>
      </div>
      <div class="chart-box tall" id="box-chartAnioDeltaEmpSede" style="height:460px"><canvas id="chartAnioDeltaEmpSede"></canvas></div>
      <div class="chart-table-wrap" id="tbl-chartAnioDeltaEmpSede"></div>
      <div class="scroll" style="max-height:280px;margin-top:10px">
        <table class="pivot" id="tabla-delta-sede">
          <thead id="delta-sede-thead"></thead>
          <tbody id="delta-sede-tbody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section id="vista-top" class="section">
    <p class="cmp-note">Ranking año A vs B en el <strong>mismo periodo</strong> (meses marcados o acumulado YTD).</p>
    <div class="grid">
      {panel_chart("Top 30 · comparación de años", "Barras agrupadas año A vs año B.", "chartTop", "tall")}
      {panel_chart("Top variaciones (Δ)", "Diferencia año B − año A.", "chartTopDelta", "tall")}
    </div>
  </section>

  <section id="vista-detalle" class="section">
    <div class="panel">
      <div class="panel-head">
        <div class="titles">
          <h2>Detalle (Excel consolidado)</h2>
          <p class="desc"><span id="det-count">0</span> docs (máx. 500). Sin provisionados.</p>
        </div>
        <div class="panel-tools"><button type="button" data-copy="detalle">Copiar detalle</button></div>
      </div>
      <div class="scroll">
        <table>
          <thead><tr>
            <th>N° Doc</th><th>Periodo</th><th>Cliente</th><th>Tipo</th><th>Sede</th><th>Glosa</th><th class="num">Monto</th>
          </tr></thead>
          <tbody id="tbl-det"></tbody>
        </table>
      </div>
    </div>
  </section>
  <footer>
    ADL Diagnostic Chile · gráficos estilo Excel Facturación · <span id="gen"></span>
    <div>
      <button type="button" class="btn-mail-foot" onclick="solicitarActualizacion(this)">Solicitar actualización por correo</button>
    </div>
  </footer>
</div>
<script>
const RAW = {data};
const TIPO_COLOR = {tipo_colors};
const MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const ANIOS_EMP = [2024,2025,2026];
const YEAR_COLORS = {{2024:'#7A92A8', 2025:'#003E6D', 2026:'#F37021'}};
const SEDE_COLORS = ['#003E6D','#F37021','#0A8F9C','#E8A317','#1F6F8B'];
const SEDE_COLOR_MAP = {{
  'PUERTO MONTT': '#E8D5A3',
  'VILLARRICA': '#2F9E71',
  'AYSEN': '#003E6D',
  'AYSÉN': '#003E6D',
  'Puerto Montt': '#E8D5A3',
  'Villarrica': '#2F9E71',
  'Aysén': '#003E6D',
  'Aysen': '#003E6D',
}};
function colorSede(s, i) {{
  return SEDE_COLOR_MAP[s] || SEDE_COLOR_MAP[String(s||'').toUpperCase()] || SEDE_COLORS[i % SEDE_COLORS.length];
}}
const TIPOS = ["SDG","PVE","SCR"];
const isProv = (r) => !!(r.es_provisionado === true || r.es_provisionado === 1 || r.estado_venta === 'provisionado');

const fmt = (n) => new Intl.NumberFormat('es-CL', {{ style:'currency', currency:'CLP', maximumFractionDigits:0 }}).format(n||0);
const fmtM = (n) => {{
  const v = Number(n)||0;
  if (Math.abs(v) >= 1e9) return '$' + (v/1e9).toFixed(2) + ' mil M';
  if (Math.abs(v) >= 1e6) return '$' + (v/1e6).toFixed(1) + ' M';
  return fmt(v);
}};

let charts = {{}};
let tiposSel = new Set();
function destroyCharts() {{ Object.values(charts).forEach(c => c && c.destroy()); charts = {{}}; }}
function uniqueSorted(arr) {{
  return [...new Set(arr.filter(x => x !== null && x !== undefined && x !== ''))]
    .sort((a,b) => String(a).localeCompare(String(b),'es'));
}}
function yearsSelected(id, fallback) {{
  const sel = selectedMulti(id).map(Number).filter(Boolean);
  return sel.length ? sel : [fallback];
}}
function monthsSelected() {{
  return selectedMulti('f-mes').map(String);
}}
function labelYears(ys) {{ return ys.length===1 ? String(ys[0]) : ys.join('+'); }}
function labelMeses(ms) {{
  if (!ms.length) return 'Acumulado';
  if (ms.length===1) return MESES[Number(ms[0])] || ms[0];
  if (ms.length > 1) {{
    const nums = ms.map(Number).filter(n=>n>=1&&n<=12).sort((a,b)=>a-b);
    if (nums.length && nums[0]===1 && nums.every((n,i)=>n===i+1))
      return 'Acum. ene–' + (MESES[nums[nums.length-1]]||'').slice(0,3).toLowerCase();
  }}
  return ms.length + ' meses';
}}
function matchMes(r, meses) {{
  return !meses.length || meses.includes(String(r.mes_venta));
}}
function matchAnios(r, anios) {{
  return anios.includes(Number(r.anio_venta));
}}
/** Meses para comparar: si el usuario no elige, YTD hasta el último mes con dato en año B. */
function mesesEfectivos(rows) {{
  const sel = monthsSelected();
  if (sel.length) return {{ meses: sel, auto: false, label: labelMeses(sel) }};
  const bYears = yearsSelected('f-anio-b', 2026);
  let maxB = 0;
  rows.forEach(r => {{
    if (matchAnios(r, bYears)) maxB = Math.max(maxB, Number(r.mes_venta)||0);
  }});
  if (maxB >= 1 && maxB <= 12) {{
    const meses = Array.from({{length: maxB}}, (_,i) => String(i+1));
    return {{ meses, auto: true, label: labelMeses(meses) }};
  }}
  return {{ meses: [], auto: true, label: 'Acumulado' }};
}}

function fillFilters() {{
  const rows = RAW.ventas;
  const anios = uniqueSorted(rows.map(r => r.anio_venta)).filter(Boolean);
  fillMulti('f-empresa', uniqueSorted(rows.map(r => r.cliente_corto)));
  const meses = [...Array(12)].map((_,i)=>i+1);
  const mesLab = Object.fromEntries(meses.map(m => [String(m), MESES[m]]));
  fillMulti('f-mes', meses, [], mesLab);
  fillMulti('f-anio-a', anios, anios.includes(2025) ? [2025] : anios.slice(0,1));
  fillMulti('f-anio-b', anios, anios.includes(2026) ? [2026] : anios.slice(-1));
  fillMulti('f-sede', uniqueSorted(rows.map(r => r.sede).filter(s => s && s !== 'SIN SEDE')));
}}

function baseFilter(rows) {{
  const sedes = selectedMulti('f-sede');
  const emps = selectedMulti('f-empresa');
  return rows.filter(r => {{
    if (isProv(r)) return false; // no se consideran provisionados
    if (tiposSel.size && !tiposSel.has(r.tipo)) return false;
    if (sedes.length && !sedes.includes(r.sede)) return false;
    if (emps.length && !emps.includes(r.cliente_corto)) return false;
    return true;
  }});
}}

function sum(rows) {{ return rows.reduce((a,r)=>a+(Number(r.monto)||0),0); }}

function renderKpis(rows) {{
  const aYears = yearsSelected('f-anio-a', 2025);
  const bYears = yearsSelected('f-anio-b', 2026);
  const {{ meses, label: mesHint }} = mesesEfectivos(rows);
  const ra = rows.filter(r => matchAnios(r, aYears) && matchMes(r, meses));
  const rb = rows.filter(r => matchAnios(r, bYears) && matchMes(r, meses));
  const ta = sum(ra), tb = sum(rb);
  const delta = tb - ta;
  const pct = ta ? (delta/ta*100) : null;
  const hintB = mesHint;
  const items = [
    [`Facturación ${{labelYears(aYears)}}`, fmtM(ta), mesHint, 'navy'],
    [`Facturación ${{labelYears(bYears)}}`, fmtM(tb), hintB, 'accent'],
    ['Variación', fmtM(delta), pct==null?'—':((pct>0?'+':'')+pct.toFixed(1)+'%'), delta>=0?'ok':'danger'],
    ['Empresas', uniqueSorted(rows.map(r=>r.cliente_corto)).length, 'en filtro activo', 'info'],
  ];
  document.getElementById('kpis').innerHTML = items.map(([l,v,h,cls]) =>
    `<div class="kpi ${{cls}}"><div class="label">${{l}}</div><div class="value">${{v}}</div><div class="hint">${{h}}</div></div>`).join('');
}}

function renderPorEmpresa(rows) {{
  const {{ meses, label: periodoLab }} = mesesEfectivos(rows);
  const data = rows.filter(r => matchMes(r, meses));
  const mesNums = meses.length
    ? [...new Set(meses.map(Number))].filter(m=>m>=1&&m<=12).sort((a,b)=>a-b)
    : [...Array(12)].map((_,i)=>i+1);
  const labels = mesNums.map(m => MESES[m]);
  const datasets = ANIOS_EMP.map(y => {{
    const vals = mesNums.map(m => sum(data.filter(r => Number(r.anio_venta)===y && Number(r.mes_venta)===m)));
    return {{
      label: String(y), data: vals, backgroundColor: YEAR_COLORS[y],
      borderColor: YEAR_COLORS[y], borderWidth: 2, tension: .25, fill: false, maxBarThickness: 28
    }};
  }});
  charts.empMes = new Chart(document.getElementById('chartEmpMes'), {{
    type: 'bar',
    data: {{ labels, datasets }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom'}},
        tooltip: tipGrupo(() => {{
          const emps = selectedMulti('f-empresa');
          return (emps.length ? emps.join(', ') : 'Todas') + ' · ' + periodoLab;
        }}, {{ conTotal: true }}),
        datalabels: dlMoney({{ minRatio: 0.06 }})
      }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const porAnio = ANIOS_EMP.map(y => sum(data.filter(r => Number(r.anio_venta)===y)));
  charts.empAnio = new Chart(document.getElementById('chartEmpAnio'), {{
    type: 'bar',
    data: {{
      labels: ANIOS_EMP.map(String),
      datasets:[{{
        label: 'Facturación',
        data: porAnio,
        backgroundColor: ANIOS_EMP.map(y=>YEAR_COLORS[y]),
        borderRadius:8,
        maxBarThickness:48
      }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{display:false}},
        tooltip: tipGrupo(() => 'Acumulado · ' + periodoLab, {{ conTotal: false }}),
        datalabels: dlMoney()
      }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});
}}

function renderPorAnio(rows) {{
  const {{ meses, label: periodoLab }} = mesesEfectivos(rows);
  const rowsP = rows.filter(r => matchMes(r, meses));
  const anios = uniqueSorted(rowsP.map(r => r.anio_venta)).filter(Boolean);
  const tiposPlot = TIPOS.filter(t => !tiposSel.size || tiposSel.has(t));
  const aYears = yearsSelected('f-anio-a', 2025);
  const bYears = yearsSelected('f-anio-b', 2026);
  const la = labelYears(aYears), lb = labelYears(bYears);
  const datasets = [];
  tiposPlot.forEach(t => {{
    datasets.push({{
      label: t,
      data: anios.map(y => sum(rowsP.filter(r => Number(r.anio_venta)===y && r.tipo===t))),
      backgroundColor: TIPO_COLOR[t] || '#829AB1',
      borderColor: TIPO_COLOR[t] || '#829AB1',
      borderWidth: 2, tension: .2, fill: false, maxBarThickness: 36, borderRadius: 6
    }});
  }});
  datasets.push({{
    label: 'Total',
    data: anios.map(y => sum(rowsP.filter(r => Number(r.anio_venta)===y && (!tiposSel.size || tiposSel.has(r.tipo))))),
    type: 'line',
    borderColor: '#102A43', backgroundColor: '#102A43', borderWidth: 2, tension: .2, pointRadius: 3
  }});
  charts.anioTipo = new Chart(document.getElementById('chartAnioTipo'), {{
    type: 'bar',
    data: {{ labels: anios.map(String), datasets }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom', labels:{{boxWidth:12}}}},
        tooltip: tipGrupo(() => periodoLab, {{ conTotal: false }}),
        datalabels: dlMoney({{ minRatio: 0.08 }})
      }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const sedes = uniqueSorted(rowsP.map(r => r.sede).filter(s => s && s !== 'SIN SEDE'));
  charts.anioSede = new Chart(document.getElementById('chartAnioSede'), {{
    type: 'bar',
    data: {{
      labels: anios.map(String),
      datasets: sedes.map((s,i) => ({{
        label: s,
        data: anios.map(y => sum(rowsP.filter(r => Number(r.anio_venta)===y && r.sede===s))),
        backgroundColor: SEDE_COLORS[i%SEDE_COLORS.length],
        maxBarThickness: 28, borderRadius: 4
      }}))
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom', labels:{{boxWidth:12}}}},
        tooltip: tipGrupo(() => 'Sede × año · ' + periodoLab, {{ conTotal: true }}),
        datalabels: dlMoney({{ minRatio: 0.07 }})
      }},
      scales: {{
        x: {{ stacked:false, ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const mesNums = meses.length
    ? [...new Set(meses.map(Number))].filter(m=>m>=1&&m<=12).sort((a,b)=>a-b)
    : [...Array(12)].map((_,i)=>i+1);
  const rowsB = rowsP.filter(r => matchAnios(r, bYears));
  charts.anioMes = new Chart(document.getElementById('chartAnioMes'), {{
    type: 'bar',
    data: {{
      labels: mesNums.map(m => MESES[m]),
      datasets: tiposPlot.map(t => ({{
        label: t,
        data: mesNums.map(m => sum(rowsB.filter(r => Number(r.mes_venta)===m && r.tipo===t))),
        backgroundColor: TIPO_COLOR[t]||'#829AB1',
        stack: 'm', maxBarThickness: 36, borderRadius: 4
      }}))
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom'}},
        tooltip: tipGrupo(() => `Año ${{lb}} · ${{periodoLab}}`, {{ conTotal: true }}),
        datalabels: dlMoney({{ stacked:true, minRatio:0.06 }})
      }},
      scales: {{
        x: {{ stacked:true, ticks:{{color:'#627D98', maxRotation:45, font:{{size:10}}}}, grid:{{display:false}} }},
        y: {{ stacked:true, ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const deltaLabels = tiposPlot;
  const deltaVals = deltaLabels.map(t => {{
    const va = sum(rowsP.filter(r => matchAnios(r, aYears) && r.tipo===t));
    const vb = sum(rowsP.filter(r => matchAnios(r, bYears) && r.tipo===t));
    return va ? ((vb-va)/va*100) : 0;
  }});
  charts.anioDelta = new Chart(document.getElementById('chartAnioDelta'), {{
    type: 'bar',
    data: {{
      labels: deltaLabels,
      datasets: [{{
        label: `Δ % ${{lb}} vs ${{la}}`,
        data: deltaVals,
        backgroundColor: deltaVals.map(v => v>=0 ? '#2F9E71' : '#D64545'),
        borderRadius:8, maxBarThickness:48
      }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{display:false}},
        tooltip: tipGrupo(() => `${{lb}} vs ${{la}} · ${{periodoLab}}`, {{ pct: true }}),
        datalabels: dlPct()
      }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>v+'%', color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const deltaSedeVals = sedes.map(s => {{
    const va = sum(rowsP.filter(r => matchAnios(r, aYears) && r.sede===s));
    const vb = sum(rowsP.filter(r => matchAnios(r, bYears) && r.sede===s));
    return va ? ((vb-va)/va*100) : 0;
  }});
  charts.anioDeltaSede = new Chart(document.getElementById('chartAnioDeltaSede'), {{
    type: 'bar',
    data: {{
      labels: sedes,
      datasets: [{{
        label: `Δ % ${{lb}} vs ${{la}}`,
        data: deltaSedeVals,
        backgroundColor: deltaSedeVals.map(v => v>=0 ? '#2F9E71' : '#D64545'),
        borderRadius:8, maxBarThickness:48
      }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{display:false}},
        tooltip: tipGrupo(() => `${{lb}} vs ${{la}} · sede · ${{periodoLab}}`, {{ pct: true }}),
        datalabels: dlPct()
      }},
      scales: {{
        x: {{ ticks:{{color:'#627D98', maxRotation:25, font:{{size:10}}}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>v+'%', color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const ra = rowsP.filter(r => matchAnios(r, aYears));
  const rb = rowsP.filter(r => matchAnios(r, bYears));
  const sedesDelta = uniqueSorted(
    [...ra, ...rb].map(r => r.sede).filter(s => s && s !== 'SIN SEDE' && !String(s).toUpperCase().includes('NO CORRESPONDE'))
  );
  const empDeltaMap = new Map();
  const bump = (rows, sign) => {{
    rows.forEach(r => {{
      const emp = r.cliente_corto || '(sin)';
      const sede = r.sede || '(sin sede)';
      if (!empDeltaMap.has(emp)) empDeltaMap.set(emp, {{}});
      const o = empDeltaMap.get(emp);
      o[sede] = (o[sede]||0) + sign * (Number(r.monto)||0);
    }});
  }};
  bump(ra, -1);
  bump(rb, +1);
  const empresasDelta = [...empDeltaMap.entries()]
    .map(([e, byS]) => {{
      const tot = Object.values(byS).reduce((a,v)=>a+(Number(v)||0),0);
      return {{ e, byS, tot }};
    }})
    .filter(x => Math.abs(x.tot) > 0)
    .sort((a,b) => a.tot - b.tot); // menor (más negativo) abajo / arriba según eje Y invertido

  const boxDelta = document.getElementById('box-chartAnioDeltaEmpSede');
  if (boxDelta) boxDelta.style.height = Math.max(360, Math.min(900, 22 * Math.max(empresasDelta.length,1) + 90)) + 'px';

  charts.anioDeltaEmpSede = new Chart(document.getElementById('chartAnioDeltaEmpSede'), {{
    type: 'bar',
    data: {{
      labels: empresasDelta.map(r => r.e),
      datasets: sedesDelta.map((s,i) => ({{
        label: s,
        data: empresasDelta.map(r => r.byS[s] || 0),
        backgroundColor: colorSede(s, i),
        borderColor: colorSede(s, i),
        borderWidth: 0,
        stack: 'delta',
        maxBarThickness: 18
      }}))
    }},
    options: {{
      indexAxis: 'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{ position:'bottom', labels:{{ boxWidth:12, font:{{size:11}} }} }},
        tooltip: tipGrupo(() => `Δ $ ${{lb}} − ${{la}} · ${{periodoLab}}`, {{ conTotal: true }}),
        datalabels: dlMoney({{ horiz:true, stacked:true, minRatio:0.05 }})
      }},
      scales: {{
        x: {{
          stacked: true,
          ticks:{{ callback:v=>fmtM(v), color:'#627D98' }},
          grid:{{ color:'#E4EBF2' }},
          title: {{ display:true, text: `Variación $ (${{lb}} vs ${{la}})`, color:'#627D98', font:{{size:11}} }}
        }},
        y: {{ stacked: true, ticks:{{ color:'#102A43', font:{{size:10}} }}, grid:{{ display:false }} }}
      }}
    }}
  }});

  // Tabla sede × empresa (como el ejemplo Excel)
  const thead = document.getElementById('delta-sede-thead');
  const tbody = document.getElementById('delta-sede-tbody');
  if (thead && tbody) {{
    const empsShow = [...empresasDelta].reverse(); // mismo orden visual típico de la tabla bajo el gráfico
    thead.innerHTML = `<tr><th>Sede</th>${{empsShow.map(r=>`<th class="num">${{r.e}}</th>`).join('')}}</tr>`;
    tbody.innerHTML = sedesDelta.map((s,i) => `<tr>
      <td><span class="swatch" style="background:${{colorSede(s,i)}}"></span>${{s}}</td>
      ${{empsShow.map(r => {{
        const v = r.byS[s]||0;
        return `<td class="num">${{v ? fmtM(v) : '—'}}</td>`;
      }}).join('')}}
    </tr>`).join('') || '';
  }}
}}

function renderTop(rows) {{
  const aYears = yearsSelected('f-anio-a', 2025);
  const bYears = yearsSelected('f-anio-b', 2026);
  const {{ meses, label: periodoLab }} = mesesEfectivos(rows);
  const la = labelYears(aYears), lb = labelYears(bYears);
  const slice = (years) => rows.filter(r => matchAnios(r, years) && matchMes(r, meses));
  const ra = slice(aYears), rb = slice(bYears);
  const empresas = uniqueSorted([...ra, ...rb].map(r => r.cliente_corto));
  const rowsTop = empresas.map(e => {{
    const va = sum(ra.filter(r => r.cliente_corto===e));
    const vb = sum(rb.filter(r => r.cliente_corto===e));
    return {{ e, va, vb, delta: vb-va }};
  }}).sort((x,y) => Math.max(y.va,y.vb) - Math.max(x.va,x.vb)).slice(0,30);

  charts.top = new Chart(document.getElementById('chartTop'), {{
    type: 'bar',
    data: {{
      labels: rowsTop.map(r => r.e),
      datasets: [
        {{ label: la, data: rowsTop.map(r => r.va), backgroundColor: '#003E6D', maxBarThickness: 16, borderRadius: 4 }},
        {{ label: lb, data: rowsTop.map(r => r.vb), backgroundColor: '#F37021', maxBarThickness: 16, borderRadius: 4 }},
      ]
    }},
    options: {{
      indexAxis: 'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{position:'bottom'}},
        tooltip: tipGrupo(() => `${{la}} vs ${{lb}} · ${{periodoLab}}`, {{ conTotal: false }}),
        datalabels: dlMoney({{ horiz:true, minRatio:0.05 }})
      }},
      scales: {{
        x: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }},
        y: {{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});

  const byDelta = [...rowsTop].sort((x,y) => Math.abs(y.delta)-Math.abs(x.delta)).slice(0,30);
  charts.topDelta = new Chart(document.getElementById('chartTopDelta'), {{
    type: 'bar',
    data: {{
      labels: byDelta.map(r => r.e),
      datasets: [{{
        label: `Δ ${{lb}}-${{la}}`,
        data: byDelta.map(r => r.delta),
        backgroundColor: byDelta.map(r => r.delta>=0 ? '#2F9E71' : '#D64545'),
        maxBarThickness: 16, borderRadius: 4
      }}]
    }},
    options: {{
      indexAxis: 'y', responsive:true, maintainAspectRatio:false,
      interaction: interactIndex,
      plugins: {{
        legend:{{display:false}},
        tooltip: tipGrupo(() => `Δ ${{lb}}-${{la}} · ${{periodoLab}}`, {{ conTotal: false }}),
        datalabels: dlMoney({{ horiz:true, minRatio:0.04 }})
      }},
      scales: {{
        x: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }},
        y: {{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});
}}

function renderDetalle(rows) {{
  const {{ meses }} = mesesEfectivos(rows);
  const filtered = rows.filter(r => matchMes(r, meses));
  const show = filtered.slice(0,500);
  document.getElementById('det-count').textContent = filtered.length;
  document.getElementById('tbl-det').innerHTML = show.map(r => `
    <tr>
      <td>${{r.id_caso ?? '—'}}</td><td>${{r.periodo||''}}</td><td>${{r.cliente_corto||''}}</td>
      <td>${{r.tipo||''}}</td><td>${{r.sede||''}}</td><td>${{r.programa||''}}</td>
      <td class="num">${{fmt(r.monto)}}</td>
    </tr>`).join('');
  registerChartTable('detalle',
    ['N Doc','Periodo','Cliente','Tipo','Sede','Glosa','Monto'],
    show.map(r => [r.id_caso??'', r.periodo||'', r.cliente_corto||'', r.tipo||'', r.sede||'', r.programa||'', Number(r.monto)||0])
  );
}}

function refresh() {{
  destroyCharts();
  const rows = baseFilter(RAW.ventas);
  renderKpis(rows);
  renderPorEmpresa(rows);
  renderPorAnio(rows);
  renderTop(rows);
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
['f-empresa','f-mes','f-anio-a','f-anio-b','f-sede'].forEach(id => {{
  document.getElementById(id).addEventListener('change', refresh);
}});

fillFilters();
document.getElementById('gen').textContent = RAW.generado;
refresh();
</script>
<script>
async function solicitarActualizacion(btn) {{
  const el = btn || document.querySelector('.btn-mail, .btn-mail-foot');
  const prev = el ? el.textContent : '';
  if (el) {{ el.disabled = true; el.textContent = 'Enviando…'; }}
  try {{
    const res = await fetch('https://formsubmit.co/ajax/faraujo@adldiagnostic.cl', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
      body: JSON.stringify({{
        _subject: 'Solicitud de actualizacion - Dashboard Facturacion ADL',
        _template: 'table',
        _captcha: 'false',
        mensaje: 'Solicito actualizar el dashboard de facturacion / reporte comercial.',
        pagina: window.location.href,
        fecha: new Date().toLocaleString('es-CL')
      }})
    }});
    const data = await res.json().catch(() => ({{}}));
    if (!res.ok) throw new Error(data.message || 'No se pudo enviar');
    if (typeof showToast === 'function') showToast('Solicitud enviada a faraujo@adldiagnostic.cl');
    else alert('Solicitud enviada a faraujo@adldiagnostic.cl');
    if (el) el.textContent = 'Enviado';
  }} catch (err) {{
    console.error(err);
    if (typeof showToast === 'function') showToast('Error al enviar. Intenta de nuevo.');
    else alert('Error al enviar. Si es la primera vez, Fanny debe confirmar el correo de FormSubmit.');
    if (el) el.textContent = prev || 'Solicitar actualización';
  }} finally {{
    if (el) setTimeout(() => {{ el.disabled = false; if (el.textContent === 'Enviado') el.textContent = prev || 'Solicitar actualización'; }}, 2500);
  }}
}}
</script>
</body>
</html>
"""
