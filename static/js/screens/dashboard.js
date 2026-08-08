import { $, esc, loadingHtml } from '../dom.js';
import { api } from '../api.js';
import { fmt, fmtShort, instStatusBadge, overdueBadge } from '../format.js';
import { projectFilterQuery, filterLabelShort } from '../project-filter.js';

export async function loadDashboard() {
  const d = await api(`/api/dashboard${projectFilterQuery()}`);
  const k = d?.kpi;
  if (!k || !$('kpi-row')) return;
  const soldPct = k.total_units ? Math.round((k.sold / k.total_units) * 100) : 0;
  const scope = filterLabelShort();

  $('kpi-row').innerHTML = `
    <div class="kpi blue"><div class="kpi-lbl">Total Units</div><div class="kpi-val">${k.total_units}</div><div class="kpi-sub">${esc(scope)}</div><div class="kpi-ico">🏢</div></div>
    <div class="kpi green"><div class="kpi-lbl">Sold</div><div class="kpi-val">${k.sold}</div><div class="kpi-sub">${soldPct}% of total</div><div class="kpi-ico">✅</div></div>
    <div class="kpi amber"><div class="kpi-lbl">Available</div><div class="kpi-val">${k.available}</div><div class="kpi-sub">${k.hold} on hold</div><div class="kpi-ico">🟢</div></div>
    <div class="kpi navy"><div class="kpi-lbl">Receivable</div><div class="kpi-val">${fmtShort(k.receivable)}</div><div class="kpi-sub">Outstanding dues</div><div class="kpi-ico">📥</div></div>
    <div class="kpi red"><div class="kpi-lbl">Payable</div><div class="kpi-val">${fmtShort(k.payable)}</div><div class="kpi-sub">Vendor & agent dues</div><div class="kpi-ico">📤</div></div>
    <div class="kpi purple"><div class="kpi-lbl">Overdue Cases</div><div class="kpi-val">${d.overdue.length}</div><div class="kpi-sub">Need attention</div><div class="kpi-ico">⚠️</div></div>
  `;

  $('overdue-badge').textContent = d.overdue.length;
  $('overdue-count-badge').textContent = d.overdue.length + ' Overdue';

  $('overdue-tbody').innerHTML = d.overdue.length
    ? d.overdue.map((o) => `
      <tr>
        <td class="td-b">${esc(o.customer_name)}</td>
        <td>${esc(o.unit_no)}</td>
        <td>${esc(o.project_name)}</td>
        <td class="td-red">${fmt(o.amount)}</td>
        <td><span class="badge ${overdueBadge(o.days_overdue)}">${o.days_overdue} Days</span></td>
        <td style="font-family:monospace">${esc(o.phone)}</td>
        <td><button class="btn sm" data-wa="${esc(o.customer_name)}">💬 WA</button></td>
      </tr>`).join('')
    : '<tr><td colspan="7" style="text-align:center;color:var(--g400);padding:20px">✅ No overdue installments</td></tr>';

  $('overdue-tbody').querySelectorAll('[data-wa]').forEach((btn) => {
    btn.addEventListener('click', () => import('../api.js').then(({ toast }) =>
      toast(`WhatsApp reminder sent to ${btn.dataset.wa}!`)));
  });

  const sc = $('salesChart');
  sc.innerHTML = '';
  const months = ['Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
  const peak = Math.max(...d.sales_chart, 1);
  d.sales_chart.forEach((v, i) => {
    const pct = Math.round((v / peak) * 100);
    const w = document.createElement('div');
    w.className = 'bw';
    w.innerHTML = `<div class="bar ${v === peak ? 'accent' : ''}" style="height:${pct}%" data-tip="PKR ${v}L"></div><div class="bar-lbl">${months[i]}</div>`;
    sc.appendChild(w);
  });

  const rcMonths = ['Jan', 'Feb', 'Mar', 'Apr', 'May'];
  const rcColors = ['var(--blue)', 'var(--blue)', 'var(--success)', 'var(--accent)', 'var(--danger)'];
  $('rec-chart').innerHTML = d.recovery_chart.map((v, i) => `
    <div class="rec-row">
      <span class="rec-lbl">${rcMonths[i]}</span>
      <div class="rec-bg"><div class="rec-fill" style="width:${v}%;background:${rcColors[i]}"></div></div>
      <span class="rec-pct">${v}%</span>
    </div>`).join('');

  $('alerts-box').innerHTML = d.alerts.map((a) => `
    <div class="alert-item">
      <div class="adot ${a.type === 'danger' ? 'red' : a.type === 'success' ? 'green' : 'amber'}"></div>
      <div><div style="font-weight:700;font-size:12px">${esc(a.title)}</div>
      <div style="font-size:10.5px;color:var(--g400);margin-top:1px">${esc(a.sub)}</div></div>
    </div>`).join('');
}
