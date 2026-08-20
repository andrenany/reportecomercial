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
    <p class="hint-multi">Multi-selección con búsqueda en cada filtro. Sin elegir = todos (mes vacío = acumulado).</p>
    <div class="filters-top">
      <label class="f">Empresa<div class="msel" id="f-empresa" data-empty="Todas"></div></label>
      <label class="f">Mes (Top)<div class="msel" id="f-mes" data-empty="Acumulado"></div></label>
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
    <p class="cmp-note">Como la hoja <em>Gráficos por Empresa</em>: meses en el eje X y series por año (2024 / 2025 / 2026) para la empresa seleccionada.</p>
    <div class="grid">
      {panel_chart("Facturación mensual por año", "Selecciona una empresa arriba. Filtra por tipo (SDG/PVE/SCR).", "chartEmpMes")}
      {panel_chart("Acumulado por año", "Total del filtro empresa + tipo.", "chartEmpAnio", "sm")}
    </div>
  </section>

  <section id="vista-anio" class="section">
    <p class="cmp-note">Como la hoja <em>Gráficos por Año</em>: evolución SDG / PVE / SCR / Total y desglose por sede.</p>
    <div class="grid">
      {panel_chart("Ventas por año × tipo", "Serie histórica anual (SDG, PVE, SCR y Total).", "chartAnioTipo")}
      {panel_chart("Por sede × año", "Puerto Montt / Villarrica / Aysén.", "chartAnioSede", "sm")}
    </div>
    <div class="grid" style="margin-top:12px">
      {panel_chart("Meses del año comparar", "Desglose mensual SDG/PVE/SCR del año B (filtro).", "chartAnioMes")}
      {panel_chart("Variación año B vs A", "Δ % por tipo de ingreso (acumulado).", "chartAnioDelta", "sm")}
    </div>
  </section>

  <section id="vista-top" class="section">
    <p class="cmp-note">Como <em>Gráficos Nuevos Top 30</em>: ranking de empresas año A vs año B (mes o acumulado) y variación.</p>
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
          <p class="desc"><span id="det-count">0</span> docs (máx. 500).</p>
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
  <footer>ADL Diagnostic Chile · gráficos estilo Excel Facturación · <span id="gen"></span></footer>
</div>
<script>
const RAW = {data};
const TIPO_COLOR = {tipo_colors};
const MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const ANIOS_EMP = [2024,2025,2026];
const YEAR_COLORS = {{2024:'#7A92A8', 2025:'#003E6D', 2026:'#F37021'}};
const SEDE_COLORS = ['#003E6D','#F37021','#0A8F9C','#E8A317','#1F6F8B'];
const TIPOS = ["SDG","PVE","SCR"];

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
  return ms.length + ' meses';
}}
function matchMes(r, meses) {{
  return !meses.length || meses.includes(String(r.mes_venta));
}}
function matchAnios(r, anios) {{
  return anios.includes(Number(r.anio_venta));
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
  fillMulti('f-sede', uniqueSorted(rows.map(r => r.sede)));
}}

function baseFilter(rows) {{
  const sedes = selectedMulti('f-sede');
  return rows.filter(r => {{
    if (tiposSel.size && !tiposSel.has(r.tipo)) return false;
    if (sedes.length && !sedes.includes(r.sede)) return false;
    return true;
  }});
}}

function sum(rows) {{ return rows.reduce((a,r)=>a+(Number(r.monto)||0),0); }}

function renderKpis(rows) {{
  const aYears = yearsSelected('f-anio-a', 2025);
  const bYears = yearsSelected('f-anio-b', 2026);
  const meses = monthsSelected();
  const ra = rows.filter(r => matchAnios(r, aYears) && matchMes(r, meses));
  const rb = rows.filter(r => matchAnios(r, bYears) && matchMes(r, meses));
  const ta = sum(ra), tb = sum(rb);
  const delta = tb - ta;
  const pct = ta ? (delta/ta*100) : null;
  const mesHint = labelMeses(meses);
  const items = [
    [`Facturación ${{labelYears(aYears)}}`, fmtM(ta), mesHint, 'navy'],
    [`Facturación ${{labelYears(bYears)}}`, fmtM(tb), mesHint, 'accent'],
    ['Variación', fmtM(delta), pct==null?'—':((pct>0?'+':'')+pct.toFixed(1)+'%'), delta>=0?'ok':'danger'],
    ['Documentos (filtro)', rows.length, uniqueSorted(rows.map(r=>r.cliente_corto)).length + ' empresas', 'info'],
  ];
  document.getElementById('kpis').innerHTML = items.map(([l,v,h,cls]) =>
    `<div class="kpi ${{cls}}"><div class="label">${{l}}</div><div class="value">${{v}}</div><div class="hint">${{h}}</div></div>`).join('');
}}

function renderPorEmpresa(rows) {{
  const emps = selectedMulti('f-empresa');
  const data = emps.length ? rows.filter(r => emps.includes(r.cliente_corto)) : rows;
  const labels = MESES.slice(1);
  const datasets = ANIOS_EMP.map(y => {{
    const vals = Array(12).fill(0);
    data.filter(r => Number(r.anio_venta)===y).forEach(r => {{
      const m = Number(r.mes_venta); if (m>=1 && m<=12) vals[m-1] += Number(r.monto)||0;
    }});
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
      plugins: {{ legend:{{position:'bottom'}}, tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: ${{fmt(c.raw)}}`}}}} }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const porAnio = ANIOS_EMP.map(y => sum(data.filter(r => Number(r.anio_venta)===y)));
  charts.empAnio = new Chart(document.getElementById('chartEmpAnio'), {{
    type: 'bar',
    data: {{ labels: ANIOS_EMP.map(String), datasets:[{{ data: porAnio, backgroundColor: ANIOS_EMP.map(y=>YEAR_COLORS[y]), borderRadius:8, maxBarThickness:48 }}] }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>fmt(c.raw)}}}} }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});
}}

function renderPorAnio(rows) {{
  const anios = uniqueSorted(rows.map(r => r.anio_venta)).filter(Boolean);
  const tiposPlot = TIPOS.filter(t => !tiposSel.size || tiposSel.has(t));
  const datasets = tiposPlot.map(t => ({{
    label: t,
    data: anios.map(y => sum(rows.filter(r => Number(r.anio_venta)===y && r.tipo===t))),
    backgroundColor: TIPO_COLOR[t] || '#829AB1',
    borderColor: TIPO_COLOR[t] || '#829AB1',
    borderWidth: 2, tension: .2, fill: false, maxBarThickness: 36, borderRadius: 6
  }}));
  // Total
  datasets.push({{
    label: 'Total',
    data: anios.map(y => sum(rows.filter(r => Number(r.anio_venta)===y && (!tiposSel.size || tiposSel.has(r.tipo))))),
    type: 'line',
    borderColor: '#102A43', backgroundColor: '#102A43', borderWidth: 2, tension: .2, pointRadius: 3
  }});
  charts.anioTipo = new Chart(document.getElementById('chartAnioTipo'), {{
    type: 'bar',
    data: {{ labels: anios.map(String), datasets }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{position:'bottom', labels:{{boxWidth:12}}}}, tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: ${{fmt(c.raw)}}`}}}} }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const sedes = uniqueSorted(rows.map(r => r.sede));
  charts.anioSede = new Chart(document.getElementById('chartAnioSede'), {{
    type: 'bar',
    data: {{
      labels: anios.map(String),
      datasets: sedes.map((s,i) => ({{
        label: s,
        data: anios.map(y => sum(rows.filter(r => Number(r.anio_venta)===y && r.sede===s))),
        backgroundColor: SEDE_COLORS[i%SEDE_COLORS.length],
        maxBarThickness: 28
      }}))
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{position:'bottom', labels:{{boxWidth:12}}}}, tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: ${{fmt(c.raw)}}`}}}} }},
      scales: {{
        x: {{ stacked:false, ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const bYears = yearsSelected('f-anio-b', 2026);
  const rowsB = rows.filter(r => matchAnios(r, bYears));
  charts.anioMes = new Chart(document.getElementById('chartAnioMes'), {{
    type: 'bar',
    data: {{
      labels: MESES.slice(1),
      datasets: tiposPlot.map(t => ({{
        label: t,
        data: Array.from({{length:12}}, (_,i) => sum(rowsB.filter(r => Number(r.mes_venta)===i+1 && r.tipo===t))),
        backgroundColor: TIPO_COLOR[t]||'#829AB1',
        stack: 'm', maxBarThickness: 36, borderRadius: 4
      }}))
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{position:'bottom'}}, tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: ${{fmt(c.raw)}}`}}}} }},
      scales: {{
        x: {{ stacked:true, ticks:{{color:'#627D98', maxRotation:45, font:{{size:10}}}}, grid:{{display:false}} }},
        y: {{ stacked:true, ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});

  const aYears = yearsSelected('f-anio-a', 2025);
  const deltaLabels = tiposPlot;
  const deltaVals = deltaLabels.map(t => {{
    const va = sum(rows.filter(r => matchAnios(r, aYears) && r.tipo===t));
    const vb = sum(rows.filter(r => matchAnios(r, bYears) && r.tipo===t));
    return va ? ((vb-va)/va*100) : 0;
  }});
  charts.anioDelta = new Chart(document.getElementById('chartAnioDelta'), {{
    type: 'bar',
    data: {{
      labels: deltaLabels,
      datasets: [{{ data: deltaVals, backgroundColor: deltaVals.map(v => v>=0 ? '#2F9E71' : '#D64545'), borderRadius:8, maxBarThickness:48 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=> (c.raw||0).toFixed(1)+' %'}}}} }},
      scales: {{
        x: {{ ticks:{{color:'#627D98'}}, grid:{{display:false}} }},
        y: {{ ticks:{{callback:v=>v+'%', color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }}
      }}
    }}
  }});
}}

function renderTop(rows) {{
  const aYears = yearsSelected('f-anio-a', 2025);
  const bYears = yearsSelected('f-anio-b', 2026);
  const meses = monthsSelected();
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
      plugins: {{ legend:{{position:'bottom'}}, tooltip:{{callbacks:{{label:c=>`${{c.dataset.label}}: ${{fmt(c.raw)}}`}}}} }},
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
      plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>fmt(c.raw)}}}} }},
      scales: {{
        x: {{ ticks:{{callback:v=>fmtM(v), color:'#627D98'}}, grid:{{color:'#E4EBF2'}} }},
        y: {{ ticks:{{color:'#102A43', font:{{size:10}}}}, grid:{{display:false}} }}
      }}
    }}
  }});
}}

function renderDetalle(rows) {{
  const show = rows.slice(0,500);
  document.getElementById('det-count').textContent = rows.length;
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
</body>
</html>
"""
