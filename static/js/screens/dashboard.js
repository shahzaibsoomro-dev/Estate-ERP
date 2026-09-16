import { $, esc } from '../dom.js';
import { api } from '../api.js';
import { fmt, fmtShort, overdueBadge } from '../format.js';
import { projectFilterQuery, filterLabelShort } from '../project-filter.js';
import { icon } from '../icons.js';
import { goScreen } from '../nav.js';
import { session } from '../session.js';

const AV_COLORS = ['#2563EB', '#059669', '#D97706', '#7C3AED', '#DB2777', '#0891B2', '#475569'];

export function avatarColor(name) {
  let h = 0;
  for (const c of String(name || '')) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AV_COLORS[h % AV_COLORS.length];
}

export function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
}

/** Pakistani local number → wa.me link (returns '' if unusable). */
export function waLink(phone, text) {
  let d = String(phone || '').replace(/\D/g, '');
  if (!d) return '';
  if (d.startsWith('00')) d = d.slice(2);
  if (d.startsWith('0')) d = '92' + d.slice(1);
  if (d.length < 11) return '';
  return `https://wa.me/${d}?text=${encodeURIComponent(text)}`;
}

function kpiCard({ tone, label, value, sub, ico, pct, barColor, goto }) {
  return `<div class="kpi ${tone} ${goto ? 'clickable' : ''}" ${goto ? `data-goto="${goto}" role="link" tabindex="0"` : ''}>
    <div class="kpi-top"><div class="kpi-lbl">${label}</div><div class="kpi-chip">${icon(ico, 17)}</div></div>
    <div class="kpi-val">${value}</div>
    ${pct != null ? `<div class="kpi-bar"><span style="width:${Math.min(100, Math.max(0, pct))}%;background:${barColor}"></span></div>` : ''}
    <div class="kpi-sub">${sub}</div>
  </div>`;
}

/** Round the axis max so that 4 gridline steps land on tidy numbers. */
function niceMax(v) {
  if (v <= 0) return 4;
  const raw = v / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * p * 4;
}

function axisLabel(n) {
  if (n >= 10000000) return (n / 10000000).toFixed(n % 10000000 ? 1 : 0) + 'Cr';
  if (n >= 100000) return (n / 100000).toFixed(n % 100000 ? 1 : 0) + 'L';
  if (n >= 1000) return Math.round(n / 1000) + 'K';
  return String(n);
}

function renderSalesChart(series) {
  const sc = $('salesChart');
  if (!sc) return;
  const max = niceMax(Math.max(...series.map((m) => m.amount), 0));
  const total = series.reduce((a, m) => a + m.amount, 0);
  if ($('sales-total')) $('sales-total').textContent = fmtShort(total);
  const ticks = [1, 0.75, 0.5, 0.25, 0];
  sc.innerHTML = `<div class="chart" role="img" aria-label="Monthly collections, last 12 months">
    <div class="chart-grid">${ticks.map((t) => `<div><span>${axisLabel(max * t)}</span></div>`).join('')}</div>
    ${series.map((m, i) => `
      <div class="chart-col ${i === series.length - 1 ? 'current' : ''}">
        <div class="chart-bar" style="height:${(m.amount / max) * 100}%">
          <div class="chart-tip">${fmt(m.amount)}<small>${m.label} ${m.year}</small></div>
        </div>
        <div class="chart-lbl">${m.label}</div>
      </div>`).join('')}
  </div>`;
}

export async function loadDashboard() {
  const d = await api(`/api/dashboard${projectFilterQuery()}`);
  const k = d?.kpi;
  if (!k || !$('kpi-row')) return;
  const soldPct = k.total_units ? Math.round((k.sold / k.total_units) * 100) : 0;
  const limited = Array.isArray(session.user?.project_ids);
  const scope = limited && filterLabelShort() === 'All projects' ? 'Your projects' : filterLabelShort();
  const rate = k.collection_rate ?? 0;
  const overdue = d.overdue || [];

  $('kpi-row').innerHTML = [
    kpiCard({ tone: 'blue', label: 'Units sold', value: `${k.sold}<span style="font-size:15px;color:var(--g400);font-weight:500"> / ${k.total_units}</span>`, sub: `${soldPct}% sold · ${esc(scope)}`, ico: 'units_total', pct: soldPct, barColor: 'var(--blue)', goto: 'units' }),
    kpiCard({ tone: 'green', label: 'Available', value: k.available, sub: `${k.hold} on hold`, ico: 'key', goto: 'units' }),
    kpiCard({ tone: 'navy', label: 'Receivable', value: fmtShort(k.receivable), sub: 'Outstanding installments', ico: 'wallet', goto: 'recovery' }),
    k.payable == null ? '' : kpiCard({ tone: 'amber', label: 'Payable', value: fmtShort(k.payable || 0), sub: 'Vendors + agent commission', ico: 'procurement', goto: 'vendors' }),
    kpiCard({ tone: 'purple', label: 'Collection rate', value: `${rate}%`, sub: `${fmtShort(k.collected_total || 0)} of ${fmtShort(k.billed_total || 0)}`, ico: 'percent', pct: rate, barColor: rate >= 80 ? 'var(--success)' : rate >= 60 ? 'var(--accent)' : 'var(--danger)' }),
    kpiCard({ tone: 'red', label: 'Overdue cases', value: overdue.length, sub: overdue.length ? 'Need follow-up' : 'All on track', ico: 'alert', goto: 'recovery' }),
  ].join('');

  if ($('overdue-badge')) $('overdue-badge').textContent = overdue.length;
  $('overdue-count-badge').textContent = `${overdue.length} overdue`;

  const top = [...overdue].sort((a, b) => b.days_overdue - a.days_overdue).slice(0, 10);
  $('overdue-tbody').innerHTML = top.length
    ? top.map((o) => {
      const link = waLink(o.phone, `Assalam o Alaikum ${o.customer_name}, a reminder that your installment of ${fmt(o.remaining_amount ?? o.amount)} for unit ${o.unit_no} (${o.project_name}) was due on ${o.due_date}. Kindly arrange payment. — Haven Builders`);
      return `
      <tr>
        <td><div class="cust-cell">
          <div class="av" style="background:${avatarColor(o.customer_name)}">${esc(initials(o.customer_name))}</div>
          <div><div class="td-b">${esc(o.customer_name)}</div><div class="cust-sub">${esc(o.phone || 'No phone')}</div></div>
        </div></td>
        <td><div class="td-b">${esc(o.unit_no)}</div><div class="cust-sub">${esc(o.project_name)}</div></td>
        <td style="text-align:right"><div class="td-red num">${fmt(o.remaining_amount ?? o.amount)}</div><div class="cust-sub">due ${esc(o.due_date)}</div></td>
        <td><span class="badge ${overdueBadge(o.days_overdue)}">${o.days_overdue} days</span></td>
        <td style="text-align:right">${link
          ? `<a class="btn sm btn-wa" href="${link}" target="_blank" rel="noopener" title="Open WhatsApp with a reminder message">${icon('whatsapp', 15)} Remind</a>`
          : '<span class="cust-sub">—</span>'}</td>
      </tr>`;
    }).join('')
    : `<tr><td colspan="5"><div class="empty">${icon('check', 28)}<b>No overdue installments</b>Every customer is on track.</div></td></tr>`;

  renderSalesChart(d.sales_series || (d.sales_chart || []).map((v, i) => ({ label: String(i + 1), year: '', amount: v * 100000 })));
  if ($('sales-sub')) $('sales-sub').textContent = `Customer payments received · ${scope} · last 12 months`;

  if ($('rec-overall')) $('rec-overall').textContent = `${rate}% overall`;
  if ($('rec-scope')) $('rec-scope').textContent = `Due vs collected · last 5 months`;
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const rcMonths = (d.recovery_months || []).map((ym) => {
    const [, m] = String(ym).split('-');
    return names[parseInt(m, 10) - 1] || ym;
  });
  const colorFor = (v) => (v >= 80 ? 'var(--success)' : v >= 50 ? 'var(--accent)' : v > 0 ? 'var(--danger)' : 'var(--g200)');
  $('rec-chart').innerHTML = (d.recovery_chart || []).map((v, i) => `
    <div class="rec-row">
      <span class="rec-lbl">${rcMonths[i] || '—'}</span>
      <div class="rec-bg"><div class="rec-fill" style="width:${v}%;background:${colorFor(v)}"></div></div>
      <span class="rec-pct">${v}%</span>
    </div>`).join('') || '<div class="empty">No collection data yet</div>';
  $('rec-chart').insertAdjacentHTML('beforeend', `<div class="rec-foot">
    <div><b>${fmtShort(k.collected_total || 0)}</b><span>Collected to date</span></div>
    <div><b>${fmtShort(Math.max(0, (k.billed_total || 0) - (k.collected_total || 0)))}</b><span>Billed, not collected</span></div>
  </div>`);

  const alerts = d.alerts || [];
  if ($('alerts-count')) $('alerts-count').textContent = alerts.length;
  $('alerts-box').innerHTML = alerts.length ? alerts.map((a) => {
    const tone = a.type === 'danger' ? 'red' : a.type === 'success' ? 'green' : 'amber';
    return `<div class="alert-item">
      <div class="alert-ico ${tone}">${icon(a.type === 'success' ? 'check' : 'alert', 16)}</div>
      <div><div class="alert-title">${esc(a.title)}</div><div class="alert-sub">${esc(a.sub)}</div></div>
    </div>`;
  }).join('') : `<div class="empty">${icon('check', 28)}<b>All clear</b>No alerts right now.</div>`;
}

export function initDashboardEvents() {
  const host = $('s-dashboard');
  if (!host) return;
  host.addEventListener('click', (e) => {
    const t = e.target.closest('[data-goto]');
    if (t) goScreen(t.dataset.goto);
  });
  host.addEventListener('keydown', (e) => {
    const t = e.target.closest('[data-goto]');
    if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); goScreen(t.dataset.goto); }
  });
}
