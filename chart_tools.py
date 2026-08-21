"""
Utilidades UI: vista tabla / copiar datos de gráficos + multi-select con búsqueda.
Importado por generar_dashboard.py
"""

# CSS extra (pegar dentro de CSS)
CSS_CHART_TOOLS = r"""
.filters .hint-multi {
  font-size: .72rem; color: var(--muted); margin: 0 0 10px; line-height: 1.35;
}
.filters-top label.f { min-width: 150px; position: relative; z-index: 1; overflow: visible; }
.msel {
  position: relative;
  width: 100%;
  z-index: 1;
}
.msel.open { z-index: 80; }
.msel-btn {
  width: 100%;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 34px 10px 12px;
  font: inherit;
  color: var(--ink);
  background: #fff
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath fill='%005B738B' d='M0 0l6 8 6-8z'/%3E%3C/svg%3E")
    right 12px center / 10px no-repeat;
  cursor: pointer;
  transition: border-color .18s, box-shadow .18s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.msel.open .msel-btn,
.msel-btn:hover, .msel-btn:focus {
  border-color: var(--adl-orange);
  outline: none;
  box-shadow: 0 0 0 3px rgba(243,112,33,.16);
}
.msel-btn.has-sel { font-weight: 600; color: var(--adl-navy); }
.msel-panel {
  display: none;
  position: absolute;
  z-index: 90;
  left: 0; right: 0;
  top: calc(100% + 4px);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 14px 32px rgba(0,42,74,.22);
  padding: 8px;
  min-width: 260px;
}
.msel.open .msel-panel { display: block; }
.msel-q {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
  margin-bottom: 6px;
  box-sizing: border-box;
}
.msel-q:focus {
  border-color: var(--adl-teal, #0A8F9C);
  outline: none;
  box-shadow: 0 0 0 2px rgba(10,143,156,.18);
}
.msel-opts {
  max-height: 200px;
  overflow: auto;
}
.msel-opt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  cursor: pointer;
  font-size: .86rem;
  color: var(--ink);
}
.msel-opt:hover { background: #F0F6FA; }
.msel-opt.on { background: rgba(10,143,156,.12); font-weight: 600; }
.msel-opt input { margin-top: 2px; accent-color: var(--adl-navy); flex-shrink: 0; }
.msel-opt span { line-height: 1.3; word-break: break-word; }
.msel-empty {
  padding: 10px 8px;
  color: var(--muted);
  font-size: .82rem;
}
.msel-foot {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--line);
}
.msel-foot button {
  flex: 1;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: .72rem;
  font-weight: 700;
  color: var(--adl-navy);
  cursor: pointer;
}
.msel-foot button:hover { border-color: var(--adl-orange); color: var(--adl-orange); }

.panel-head { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:6px; }
.panel-head .titles { min-width:0; flex:1; }
.panel-tools { display:flex; gap:6px; flex-wrap:wrap; flex-shrink:0; }
.panel-tools button {
  border:1px solid var(--line); background:#fff; color:var(--adl-navy);
  border-radius:999px; padding:6px 11px; font-size:.72rem; font-weight:700; cursor:pointer;
  transition: all .15s ease;
}
.panel-tools button:hover { border-color: var(--adl-orange); color: var(--adl-orange); }
.panel-tools button.on { background: linear-gradient(135deg, var(--adl-navy), #0A8F9C); color:#fff; border-color: transparent; }
.panel-tools button.copied { background: var(--ok); color:#fff; border-color: var(--ok); }
.chart-box {
  position: relative;
  background: linear-gradient(165deg, #ffffff 0%, #f3f7fb 100%);
  border-radius: 14px;
  padding: 10px 8px 6px;
  border: 1px solid rgba(215,227,238,.95);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.9),
    0 8px 20px rgba(0,62,109,.08),
    0 2px 4px rgba(0,42,74,.04);
}
.chart-table-wrap { display:none; overflow:auto; max-height:360px; margin-top:6px; }
.chart-table-wrap.show { display:block; }
.chart-table-wrap table { font-size:.8rem; }
.toast {
  position:fixed; bottom:18px; right:18px; background:var(--adl-navy); color:#fff;
  padding:10px 14px; border-radius:10px; font-size:.85rem; font-weight:600;
  opacity:0; transform:translateY(8px); transition:.2s; z-index:50; pointer-events:none;
}
.toast.show { opacity:1; transform:none; }
.hero-mini { display: none !important; }
"""

JS_CHART_TOOLS = r"""
const chartTables = {};
const mselData = {};
const chartDepthPlugin = {
  id: 'adlDepth',
  beforeDatasetsDraw(chart) {
    const ctx = chart.ctx;
    ctx.save();
    ctx.shadowColor = 'rgba(0, 42, 74, 0.28)';
    ctx.shadowBlur = 16;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 10;
  },
  afterDatasetsDraw(chart) {
    chart.ctx.restore();
  }
};
if (typeof Chart !== 'undefined' && !Chart.registry.plugins.get('adlDepth')) {
  Chart.register(chartDepthPlugin);
}

function showToast(msg) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1600);
}
/** Tooltip agrupado: todas las series del punto + periodo en el título. */
function tipGrupo(periodoFn, { pct=false, conTotal=false, suffix='' } = {}) {
  return {
    mode: 'index',
    intersect: false,
    callbacks: {
      title(items) {
        const label = items[0]?.label ?? '';
        const periodo = typeof periodoFn === 'function' ? periodoFn() : (periodoFn || '');
        const base = periodo ? `${label} · ${periodo}` : String(label);
        return suffix ? `${base} · ${suffix}` : base;
      },
      label(c) {
        const name = c.dataset.label || c.label || 'Monto';
        if (pct) return `${name}: ${(Number(c.raw)||0).toFixed(1)} %`;
        if (suffix === 'días' || String(name).toLowerCase().includes('día'))
          return `${name}: ${(Number(c.raw)||0).toFixed(1)}`;
        return `${name}: ${typeof fmt === 'function' ? fmt(c.raw) : c.raw}`;
      },
      footer(items) {
        if (!conTotal || !items.length) return '';
        const tot = items.reduce((a, i) => a + (Number(i.raw) || 0), 0);
        return 'Total: ' + (typeof fmt === 'function' ? fmt(tot) : tot);
      }
    }
  };
}
const interactIndex = { mode: 'index', intersect: false };
function registerChartTable(id, headers, rows) {
  chartTables[id] = { headers, rows };
  const wrap = document.getElementById('tbl-' + id);
  if (!wrap) return;
  const thead = '<tr>' + headers.map(h => `<th${typeof rows[0]?.[headers.indexOf(h)] === 'number' || String(h).toLowerCase().includes('monto') || String(h).toLowerCase().includes('valor') || String(h).toLowerCase().includes('total') || String(h).toLowerCase().includes('días') || String(h).toLowerCase().includes('docs') ? ' class="num"' : ''}>${h}</th>`).join('') + '</tr>';
  const body = rows.map(r => '<tr>' + r.map((c) => {
    const isNum = typeof c === 'number';
    const val = isNum ? (Math.abs(c) >= 1000 ? fmt(c) : (Number.isInteger(c) ? c : Number(c).toFixed(1))) : (c ?? '');
    return `<td${isNum ? ' class="num"' : ''}>${val}</td>`;
  }).join('') + '</tr>').join('');
  wrap.innerHTML = `<table><thead>${thead}</thead><tbody>${body}</tbody></table>`;
}
function tableFromChart(chart) {
  if (!chart || !chart.data) return null;
  const labels = chart.data.labels || [];
  const datasets = chart.data.datasets || [];
  if (!datasets.length) return null;
  if (datasets.length === 1) {
    return {
      headers: ['Categoría', datasets[0].label || 'Valor'],
      rows: labels.map((l,i) => [l, Number(datasets[0].data[i]) || 0]),
    };
  }
  return {
    headers: ['Categoría', ...datasets.map(d => d.label || 'Serie')],
    rows: labels.map((l,i) => [l, ...datasets.map(d => Number(d.data[i]) || 0)]),
  };
}
function syncAllChartTables() {
  Object.values(charts).forEach((chart) => {
    if (!chart || !chart.canvas) return;
    const id = chart.canvas.id;
    const t = tableFromChart(chart);
    if (t) registerChartTable(id, t.headers, t.rows);
  });
}
function copyTable(id) {
  const t = chartTables[id];
  if (!t) { showToast('Sin datos para copiar'); return; }
  const lines = [t.headers.join('\t')].concat(t.rows.map(r => r.join('\t')));
  navigator.clipboard.writeText(lines.join('\n')).then(() => showToast('Datos copiados')).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = lines.join('\n');
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
    showToast('Datos copiados');
  });
}
function setPanelMode(id, mode) {
  const canvasBox = document.getElementById(id)?.closest('.chart-box');
  const wrap = document.getElementById('tbl-' + id);
  const btnG = document.querySelector(`[data-mode="chart"][data-target="${id}"]`);
  const btnT = document.querySelector(`[data-mode="table"][data-target="${id}"]`);
  if (!wrap) return;
  if (mode === 'table') {
    if (canvasBox) canvasBox.style.display = 'none';
    wrap.classList.add('show');
    btnG && btnG.classList.remove('on');
    btnT && btnT.classList.add('on');
  } else {
    if (canvasBox) canvasBox.style.display = '';
    wrap.classList.remove('show');
    btnT && btnT.classList.remove('on');
    btnG && btnG.classList.add('on');
  }
}
document.addEventListener('click', (ev) => {
  const btn = ev.target.closest('[data-mode],[data-copy]');
  if (!btn) return;
  if (btn.dataset.copy) { copyTable(btn.dataset.copy); return; }
  if (btn.dataset.mode) setPanelMode(btn.dataset.target, btn.dataset.mode);
});

function selectedMulti(id) {
  return [...(mselData[id]?.selected || [])];
}
function closeAllMsels(exceptId) {
  document.querySelectorAll('.msel.open').forEach(el => {
    if (el.id !== exceptId) el.classList.remove('open');
  });
}
function updateMselBtn(id) {
  const root = document.getElementById(id);
  const st = mselData[id];
  if (!root || !st) return;
  const btn = root.querySelector('.msel-btn');
  if (!btn) return;
  const n = st.selected.size;
  const empty = root.dataset.empty || 'Todos';
  if (!n) {
    btn.textContent = empty;
    btn.classList.remove('has-sel');
    return;
  }
  btn.classList.add('has-sel');
  if (n === 1) {
    const v = [...st.selected][0];
    btn.textContent = st.labels[v] || v;
  } else if (n <= 3) {
    btn.textContent = [...st.selected].map(v => st.labels[v] || v).join(', ');
  } else {
    btn.textContent = n + ' seleccionados';
  }
}
function renderMselOpts(id) {
  const root = document.getElementById(id);
  const st = mselData[id];
  if (!root || !st) return;
  const box = root.querySelector('.msel-opts');
  const q = (root.querySelector('.msel-q')?.value || '').trim().toLowerCase();
  const filtered = st.values.filter(v => {
    const lab = (st.labels[v] || v).toLowerCase();
    return !q || lab.includes(q) || String(v).toLowerCase().includes(q);
  });
  if (!filtered.length) {
    box.innerHTML = '<div class="msel-empty">Sin coincidencias</div>';
    return;
  }
  box.innerHTML = filtered.map(v => {
    const on = st.selected.has(v) ? ' on' : '';
    const chk = st.selected.has(v) ? ' checked' : '';
    const lab = (st.labels[v] || v).replace(/</g,'&lt;');
    return `<label class="msel-opt${on}" data-val="${String(v).replace(/"/g,'&quot;')}"><input type="checkbox"${chk} /><span>${lab}</span></label>`;
  }).join('');
  box.querySelectorAll('.msel-opt').forEach(opt => {
    opt.addEventListener('click', (e) => {
      e.preventDefault();
      const val = opt.dataset.val;
      if (st.selected.has(val)) st.selected.delete(val);
      else st.selected.add(val);
      updateMselBtn(id);
      renderMselOpts(id);
      root.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
}
function fillMulti(id, values, preselect, labelMap) {
  const root = document.getElementById(id);
  if (!root) return;
  const vals = values.map(v => String(v));
  const labels = {};
  vals.forEach(v => {
    labels[v] = labelMap && labelMap[v] != null ? String(labelMap[v])
      : (labelMap && labelMap[Number(v)] != null ? String(labelMap[Number(v)]) : v);
  });
  const pref = new Set((preselect || []).map(String).filter(v => vals.includes(v)));
  mselData[id] = { values: vals, labels, selected: pref };
  root.classList.add('msel');
  root.classList.remove('open');
  root.innerHTML = `
    <button type="button" class="msel-btn"></button>
    <div class="msel-panel">
      <input type="search" class="msel-q" placeholder="Buscar..." autocomplete="off" />
      <div class="msel-opts"></div>
      <div class="msel-foot">
        <button type="button" data-act="clear">Quitar</button>
        <button type="button" data-act="visible">Marcar filtrados</button>
      </div>
    </div>`;
  const btn = root.querySelector('.msel-btn');
  const q = root.querySelector('.msel-q');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const willOpen = !root.classList.contains('open');
    closeAllMsels(id);
    root.classList.toggle('open', willOpen);
    if (willOpen) { renderMselOpts(id); q.focus(); }
  });
  root.querySelector('.msel-panel').addEventListener('click', e => e.stopPropagation());
  q.addEventListener('click', e => e.stopPropagation());
  q.addEventListener('input', () => renderMselOpts(id));
  root.querySelectorAll('.msel-foot button').forEach(b => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const st = mselData[id];
      if (b.dataset.act === 'clear') {
        st.selected.clear();
      } else if (b.dataset.act === 'visible') {
        const qq = (q.value || '').trim().toLowerCase();
        st.values.forEach(v => {
          const lab = (st.labels[v] || v).toLowerCase();
          if (!qq || lab.includes(qq) || String(v).toLowerCase().includes(qq)) st.selected.add(v);
        });
      }
      updateMselBtn(id);
      renderMselOpts(id);
      root.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
  updateMselBtn(id);
}
document.addEventListener('click', () => closeAllMsels());
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAllMsels();
});
"""


def panel_chart(title: str, desc: str, canvas_id: str, height_class: str = "") -> str:
    """Panel con herramientas Gráfico / Tabla / Copiar."""
    h = f"chart-box {height_class}".strip() if height_class else "chart-box"
    height = "270px" if height_class == "sm" else ("400px" if height_class == "tall" else "310px")
    return f"""
      <div class="panel" data-panel="{canvas_id}">
        <div class="panel-head">
          <div class="titles">
            <h2>{title}</h2>
            <p class="desc">{desc}</p>
          </div>
          <div class="panel-tools">
            <button type="button" class="on" data-mode="chart" data-target="{canvas_id}">Gráfico</button>
            <button type="button" data-mode="table" data-target="{canvas_id}">Tabla</button>
            <button type="button" data-copy="{canvas_id}">Copiar</button>
          </div>
        </div>
        <div class="{h}" style="height:{height}"><canvas id="{canvas_id}"></canvas></div>
        <div class="chart-table-wrap" id="tbl-{canvas_id}"></div>
      </div>
    """
