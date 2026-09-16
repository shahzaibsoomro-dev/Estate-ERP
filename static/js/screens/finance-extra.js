/* Reports centre: period + project filters, KPI tiles, charts with hover, sortable tables, CSV export, print. */
import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { projectFilterQuery, filterLabelShort } from '../project-filter.js';
import { icon } from '../icons.js';

// Validated categorical slots (light surface) — see dataviz palette check.
const C = { blue: '#2a78d6', aqua: '#1baf7a', yellow: '#eda100', violet: '#4a3aa7' };
// Ordinal one-hue ramp for ageing buckets (lightest step still clears 2:1).
const AGE_RAMP = ['#86b6ef', '#3987e5', '#1c5cab', '#0d366b'];

// mode: 'range' (period), 'asof' (single date), 'none' (as of today). group: 'main' | 'more'.
const REPORTS = [
  { key: 'sales', label: 'Sales', ico: 'booking', mode: 'range', group: 'main', desc: 'Bookings, sales value and collection by project' },
  { key: 'ageing', label: 'Ageing', ico: 'clock', mode: 'none', group: 'main', desc: 'Overdue installments by age' },
  { key: 'monthly', label: 'Monthly in & out', ico: 'swap', mode: 'range', group: 'main', desc: 'Cash received and paid out each month, with opening and closing cash' },
  { key: 'projectwise', label: 'Project wise', ico: 'projects', mode: 'range', group: 'main', desc: 'Sales, collections, costs and margin for each project' },
  { key: 'expenses', label: 'Expense ledger', ico: 'wallet', mode: 'range', group: 'main', desc: 'Every expense by category, project and party' },
  { key: 'gl', label: 'General ledger', ico: 'ledger', mode: 'range', group: 'main', desc: 'Account balances and the entries behind them' },
  { key: 'tb', label: 'Trial balance', ico: 'scale', mode: 'asof', group: 'main', desc: 'Debit and credit balance of every account' },
  { key: 'bs', label: 'Balance sheet', ico: 'accounts', mode: 'asof', group: 'main', desc: 'Assets, liabilities and equity' },
  { key: 'audit', label: 'Audit', ico: 'shield', mode: 'range', group: 'main', desc: 'Activity trail, exceptions and integrity checks (company-wide)' },
  { key: 'overview', label: 'Overview', ico: 'dashboard', mode: 'range', group: 'more', desc: 'Headline figures for the selected period' },
  { key: 'collections', label: 'Collections', ico: 'recovery', mode: 'range', group: 'more', desc: 'Customer payments received' },
  { key: 'customers', label: 'Customer balances', ico: 'customers', mode: 'none', group: 'more', desc: 'Sale value, paid, outstanding and overdue per customer' },
  { key: 'inventory', label: 'Inventory', ico: 'units', mode: 'none', group: 'more', desc: 'Unit status and unsold stock value' },
  { key: 'payables', label: 'Payables', ico: 'procurement', mode: 'none', group: 'more', desc: 'What we owe vendors and agents' },
  { key: 'budget', label: 'Budget vs actual', ico: 'budget', mode: 'none', group: 'more', desc: 'Planned vs spent per project and category' },
];

const PERIODS = [
  ['this_month', 'This month'], ['last_month', 'Last month'], ['this_quarter', 'This quarter'],
  ['this_year', 'This year'], ['last_12', 'Last 12 months'], ['all', 'All time'], ['custom', 'Custom range'],
];
const ASOF = [
  ['today', 'Today'], ['end_last_month', 'End of last month'], ['end_last_quarter', 'End of last quarter'],
  ['end_last_year', 'End of last year'], ['custom', 'Custom date'],
];

let current = 'sales';
let period = 'last_12';
let asof = 'today';
let glAccount = '';
let auditEntity = '';
let exportable = null; // { name, columns, rows }

// ------------------------------------------------------------------ helpers
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const mode = () => REPORTS.find((r) => r.key === current).mode;

function asofDate() {
  const t = new Date();
  const y = t.getFullYear();
  const m = t.getMonth();
  switch (asof) {
    case 'end_last_month': return iso(new Date(y, m, 0));
    case 'end_last_quarter': return iso(new Date(y, Math.floor(m / 3) * 3, 0));
    case 'end_last_year': return iso(new Date(y - 1, 11, 31));
    case 'custom': return $('rp-to').value || iso(t);
    default: return iso(t);
  }
}

function periodRange() {
  const t = new Date();
  const y = t.getFullYear();
  const m = t.getMonth();
  switch (period) {
    case 'this_month': return [iso(new Date(y, m, 1)), iso(t)];
    case 'last_month': return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))];
    case 'this_quarter': return [iso(new Date(y, Math.floor(m / 3) * 3, 1)), iso(t)];
    case 'this_year': return [iso(new Date(y, 0, 1)), iso(t)];
    case 'last_12': return [iso(new Date(y, m - 11, 1)), iso(t)];
    case 'custom': return [$('rp-from').value || '', $('rp-to').value || ''];
    default: return ['', ''];
  }
}

function periodLabel() {
  if (mode() === 'asof') return `As of ${fdate(asofDate())}`;
  if (mode() === 'none') return 'As of today';
  if (period === 'custom') {
    const [a, b] = periodRange();
    return `${a ? fdate(a) : 'start'} – ${b ? fdate(b) : 'today'}`;
  }
  return PERIODS.find(([k]) => k === period)?.[1] || '';
}

function query(withPeriod, more = {}) {
  const extra = { ...more };
  if (withPeriod && mode() === 'asof') {
    extra.date_to = asofDate();
  } else if (withPeriod) {
    const [from, to] = periodRange();
    extra.date_from = from;
    extra.date_to = to;
  }
  return projectFilterQuery(extra);
}

const fdate = (s) => {
  if (!s) return '—';
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};
const monthLabel = (ym) => {
  const [y, m] = String(ym).split('-');
  return new Date(+y, +m - 1, 1).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
};
/** Fill empty months so the time axis is continuous. */
function fillMonths(rows, zero) {
  const have = new Map(rows.map((r) => [String(r.month).slice(0, 7), r]));
  let [from, to] = periodRange();
  const keys = [...have.keys()].sort();
  if (!from) from = keys[0] || '';
  if (!to) to = keys[keys.length - 1] || '';
  if (!from || !to) return rows;
  let [y, m] = from.slice(0, 7).split('-').map(Number);
  const [ty, tm] = to.slice(0, 7).split('-').map(Number);
  const out = [];
  while ((y < ty || (y === ty && m <= tm)) && out.length < 120) {
    const k = `${y}-${String(m).padStart(2, '0')}`;
    out.push(have.get(k) || { month: k, ...zero });
    m += 1; if (m > 12) { m = 1; y += 1; }
  }
  return out;
}
const plural = (n, word) => `${Number(n).toLocaleString('en-PK')} ${Number(n) === 1 ? word : word.endsWith('y') ? `${word.slice(0, -1)}ies` : `${word}s`}`;
const pct = (v) => (v == null ? '—' : `${v}%`);

function fmtCell(v, type) {
  if (v == null || v === '') return '<span class="muted">—</span>';
  if (type === 'money') return fmt(v);
  if (type === 'date') return esc(fdate(v));
  if (type === 'pct') return pct(v);
  if (type === 'num') return Number(v).toLocaleString('en-PK');
  return esc(v);
}

function kpis(items) {
  return `<div class="rp-kpis">${items.map((k) => `
    <div class="rp-kpi ${k.tone || ''}">
      <span>${esc(k.label)}</span>
      <b>${k.value}</b>
      ${k.sub ? `<small>${k.sub}</small>` : ''}
    </div>`).join('')}</div>`;
}

function card(title, sub, body, actions = '') {
  return `<div class="card rp-card"><div class="card-hd"><div><div class="card-title">${esc(title)}</div>${sub ? `<div class="card-sub">${sub}</div>` : ''}</div>${actions}</div>${body}</div>`;
}

function empty(text) {
  return `<div class="empty">${icon('reports', 28)}<b>Nothing to show</b>${esc(text)}</div>`;
}

// ------------------------------------------------------------------ charts
function niceMax(v) {
  if (v <= 0) return 4;
  const raw = v / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * p * 4;
}
const axis = (n) => (n >= 1e7 ? `${+(n / 1e7).toFixed(1)}Cr` : n >= 1e5 ? `${+(n / 1e5).toFixed(1)}L` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n));

function tick(label, i, n) {
  const [mon, yr] = String(label).split(' ');
  const every = n > 24 ? 6 : n > 13 ? 3 : 1;
  if (!yr) return esc(label);
  if (i % every) return '';
  return `${esc(mon)}${i === 0 || mon === 'Jan' ? `<small>${esc(yr)}</small>` : ''}`;
}

/** Single-series column chart (one hue), hover tooltip per column. */
function columns(points, { money = true, color = C.blue, label = 'value' } = {}) {
  if (!points.some((p) => p.value)) return empty('No data in this period.');
  const max = niceMax(Math.max(...points.map((p) => p.value), 0));
  return `<div class="card-bd"><div class="chart rp-chart" role="img" aria-label="${esc(label)} by month">
    <div class="chart-grid">${[1, 0.75, 0.5, 0.25, 0].map((t) => `<div><span>${money ? axis(max * t) : Math.round(max * t)}</span></div>`).join('')}</div>
    ${points.map((p, i) => `<div class="chart-col">
      <div class="chart-bar" style="height:${(p.value / max) * 100}%;background:${color}">
        <div class="chart-tip">${money ? fmt(p.value) : p.value}<small>${esc(p.tip ? `${p.label} · ${p.tip}` : p.label)}</small></div>
      </div>
      <div class="chart-lbl">${tick(p.label, i, points.length)}</div></div>`).join('')}
  </div></div>`;
}

/** Horizontal bars for a breakdown; values printed beside each bar. */
function hbars(rows, { money = true, color = C.blue, colors = null } = {}) {
  if (!rows.length) return empty('No data.');
  const max = Math.max(...rows.map((r) => r.value), 1);
  return `<div class="card-bd rp-hbars">${rows.map((r, i) => `
    <div class="rp-hbar" title="${esc(r.label)}: ${money ? fmt(r.value) : r.value}">
      <div class="rp-hbar-lbl">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</div>
      <div class="rp-hbar-track"><span style="width:${Math.max((r.value / max) * 100, r.value ? 1.5 : 0)}%;background:${colors ? colors[i % colors.length] : color}"></span></div>
      <div class="rp-hbar-val">${money ? fmtShort(r.value) : r.value.toLocaleString('en-PK')}</div>
    </div>`).join('')}</div>`;
}

/** Stacked horizontal bar per row (inventory), legend always present. */
function stacked(rows, parts) {
  if (!rows.length) return empty('No units.');
  const legend = `<div class="rp-legend">${parts.map((p) => `<span><i style="background:${p.color}"></i>${esc(p.label)}</span>`).join('')}</div>`;
  return `<div class="card-bd">${legend}<div class="rp-stacks">${rows.map((r) => {
    const total = parts.reduce((a, p) => a + (r[p.key] || 0), 0) || 1;
    return `<div class="rp-hbar">
      <div class="rp-hbar-lbl">${esc(r.label)}<small>${plural(total, 'unit')}</small></div>
      <div class="rp-stack">${parts.map((p) => (r[p.key] ? `<span style="width:${(r[p.key] / total) * 100}%;background:${p.color}" title="${esc(p.label)}: ${r[p.key]}"></span>` : '')).join('')}</div>
      <div class="rp-hbar-val">${r.valueLabel || ''}</div>
    </div>`;
  }).join('')}</div></div>`;
}

// ------------------------------------------------------------------ tables
const tables = {};

function table(id, columnsDef, rows, { search = true, name = 'report', primary = false, footer = null, sortable = true } = {}) {
  const shown = columnsDef.filter((c) => !c.hide);
  tables[id] = { columns: shown, all: columnsDef, rows, sortKey: null, dir: 1, q: '' };
  if (primary) exportable = { name, columns: columnsDef, rows };
  return `${search ? `<div class="rp-tbl-tools"><input type="search" class="rp-search" data-tbl="${id}" placeholder="Search ${rows.length} rows…"></div>` : ''}
    <div class="tbl-wrap"><table class="rp-table" id="${id}">
      <thead><tr>${shown.map((c) => `<th ${sortable ? `data-sort="${c.key}" tabindex="0"` : ''} class="${['money', 'num', 'pct'].includes(c.type) ? 'r' : ''}">${esc(c.label)}<span class="sort-ind"></span></th>`).join('')}</tr></thead>
      <tbody></tbody>${footer ? `<tfoot><tr>${footer}</tr></tfoot>` : ''}
    </table></div>`;
}

function drawTable(id) {
  const t = tables[id];
  const el = $(id);
  if (!t || !el) return;
  let rows = t.rows;
  if (t.q) {
    const q = t.q.toLowerCase();
    rows = rows.filter((r) => t.all.some((c) => String(r[c.key] ?? '').toLowerCase().includes(q)));
  }
  if (t.sortKey) {
    const col = t.columns.find((c) => c.key === t.sortKey);
    const numeric = ['money', 'num', 'pct'].includes(col?.type);
    rows = [...rows].sort((a, b) => {
      const x = a[t.sortKey]; const y = b[t.sortKey];
      if (numeric) return ((Number(x) || 0) - (Number(y) || 0)) * t.dir;
      return String(x ?? '').localeCompare(String(y ?? '')) * t.dir;
    });
  }
  el.querySelector('tbody').innerHTML = rows.length ? rows.slice(0, 500).map((r) => `<tr>${t.columns.map((c) => {
    const cls = ['money', 'num', 'pct'].includes(c.type) ? 'r num' : '';
    const html = c.render ? c.render(r) : fmtCell(r[c.key], c.type);
    return `<td class="${cls} ${c.cls || ''}">${html}</td>`;
  }).join('')}</tr>`).join('')
    : `<tr><td colspan="${t.columns.length}"><div class="empty">No matching rows</div></td></tr>`;
  if (rows.length > 500) {
    el.querySelector('tbody').insertAdjacentHTML('beforeend', `<tr><td colspan="${t.columns.length}" class="muted">Showing 500 of ${rows.length} rows — export CSV for all.</td></tr>`);
  }
  el.querySelectorAll('th[data-sort]').forEach((th) => {
    const ind = th.querySelector('.sort-ind');
    ind.textContent = th.dataset.sort === t.sortKey ? (t.dir > 0 ? ' ▲' : ' ▼') : '';
    th.setAttribute('aria-sort', th.dataset.sort === t.sortKey ? (t.dir > 0 ? 'ascending' : 'descending') : 'none');
  });
}

function wireTables(root) {
  Object.keys(tables).forEach((id) => {
    const el = $(id);
    if (!el) { delete tables[id]; return; }
    el.querySelectorAll('th[data-sort]').forEach((th) => {
      const sort = () => {
        const t = tables[id];
        if (t.sortKey === th.dataset.sort) t.dir *= -1; else { t.sortKey = th.dataset.sort; t.dir = -1; }
        drawTable(id);
      };
      th.addEventListener('click', sort);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter') sort(); });
    });
    drawTable(id);
  });
  root.querySelectorAll('.rp-search').forEach((inp) => inp.addEventListener('input', () => {
    tables[inp.dataset.tbl].q = inp.value.trim();
    drawTable(inp.dataset.tbl);
  }));
}

function exportCsv() {
  if (!exportable || !exportable.rows.length) { toast('Nothing to export', 'error'); return; }
  const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [exportable.columns.map((c) => q(c.label)).join(',')];
  exportable.rows.forEach((r) => lines.push(exportable.columns.map((c) => q(c.csv ? c.csv(r) : r[c.key])).join(',')));
  const blob = new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${exportable.name}-${iso(new Date())}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

const statusBadge = (s) => {
  const cls = { Overdue: 'bg-red', Cleared: 'bg-green', 'On track': 'bg-blue', Exceeded: 'bg-red', 'Near Limit': 'bg-yellow', 'Within Budget': 'bg-green', overdue: 'bg-red', partial: 'bg-orange' }[s] || 'bg-grey';
  return `<span class="badge ${cls}">${esc(s)}</span>`;
};

// ------------------------------------------------------------------ reports
async function rOverview() {
  const d = await api(`/api/reports/overview${query(true)}`);
  const s = await api(`/api/reports/sales-summary${query(true)}`);
  const c = await api(`/api/reports/collections${query(true)}`);
  return kpis([
    { label: 'Bookings', value: d.bookings.toLocaleString('en-PK'), sub: `${d.cancelled_bookings} cancelled in period` },
    { label: 'Sales value', value: fmtShort(d.sales_value), sub: 'Active bookings' },
    { label: 'Collected', value: fmtShort(d.collections), sub: `${plural(d.collection_count, 'payment')}${c.collection_rate != null ? ` · ${c.collection_rate}% of due` : ''}` },
    { label: 'Receivable now', value: fmtShort(d.receivable), sub: 'Open installments' },
    { label: 'Overdue now', value: fmtShort(d.overdue), sub: `${plural(d.overdue_count, 'installment')}`, tone: d.overdue ? 'bad' : '' },
    { label: 'Unsold stock', value: fmtShort(d.available_value), sub: `${d.available_units} available units` },
  ]) + `<div class="rp-grid">
      ${card('Collections by month', esc(periodLabel()), columns(fillMonths(c.monthly, { amount: 0, count: 0 }).map((m) => ({ label: monthLabel(m.month), value: m.amount, tip: `${plural(m.count, 'payment')}` })), { label: 'Collections' }))}
      ${card('Sales by month', esc(periodLabel()), columns(fillMonths(s.monthly, { sales_value: 0, bookings: 0 }).map((m) => ({ label: monthLabel(m.month), value: m.sales_value, tip: `${plural(m.bookings, 'booking')}` })), { label: 'Sales' }))}
    </div>
    <div class="rp-grid">
      ${card('Sales by project', '', hbars(s.by_project.map((p) => ({ label: p.project_name, value: p.sales_value, sub: `${plural(p.bookings, 'booking')}` }))))}
      ${card('Collections by method', '', hbars(c.by_method.map((p) => ({ label: p.method, value: p.amount, sub: `${plural(p.count, 'payment')}` }))))}
    </div>`;
}

async function rSales() {
  const d = await api(`/api/reports/sales-summary${query(true)}`);
  const t = d.by_project.reduce((a, p) => ({ v: a.v + p.sales_value, n: a.n + p.bookings, c: a.c + p.collected }), { v: 0, n: 0, c: 0 });
  return kpis([
    { label: 'Bookings', value: t.n, sub: `${d.cancelled} cancelled` },
    { label: 'Sales value', value: fmtShort(t.v) },
    { label: 'Collected on these', value: fmtShort(t.c), sub: t.v ? `${Math.round((t.c / t.v) * 100)}% of value` : '' },
    { label: 'Average sale', value: fmtShort(t.n ? t.v / t.n : 0) },
  ]) + `<div class="rp-grid">
      ${card('Sales value by month', esc(periodLabel()), columns(fillMonths(d.monthly, { sales_value: 0, bookings: 0 }).map((m) => ({ label: monthLabel(m.month), value: m.sales_value, tip: `${plural(m.bookings, 'booking')}` })), { label: 'Sales' }))}
      ${card('By unit type', '', hbars(d.by_type.map((x) => ({ label: x.unit_type, value: x.sales_value, sub: `${plural(x.bookings, 'booking')}` }))))}
    </div>
    ${card('By project', '', table('rt-sales-proj', [
      { key: 'project_name', label: 'Project', cls: 'td-b' },
      { key: 'bookings', label: 'Bookings', type: 'num' },
      { key: 'sales_value', label: 'Sales value', type: 'money' },
      { key: 'avg_price', label: 'Avg price', type: 'money' },
      { key: 'discounts', label: 'Discounts', type: 'money' },
      { key: 'collected', label: 'Collected', type: 'money' },
      { key: 'outstanding', label: 'Outstanding', type: 'money' },
      { key: 'collected_pct', label: 'Collected %', type: 'pct' },
      { key: 'via_agent', label: 'Via agent', type: 'num' },
    ], d.by_project, { search: false }))}
    ${card('Bookings in period', `${plural(d.bookings.length, 'booking')}`, table('rt-sales', [
      { key: 'booking_date', label: 'Date', type: 'date' },
      { key: 'booking_no', label: 'Booking', cls: 'td-mono' },
      { key: 'customer_name', label: 'Customer', cls: 'td-b' },
      { key: 'project_name', label: 'Project' },
      { key: 'unit_no', label: 'Unit' },
      { key: 'unit_type', label: 'Type' },
      { key: 'agent_name', label: 'Agent' },
      { key: 'final_sale_price', label: 'Sale price', type: 'money' },
      { key: 'booking_amount', label: 'Booking amount', type: 'money' },
    ], d.bookings, { name: 'sales', primary: true }))}`;
}

async function rCollections() {
  const d = await api(`/api/reports/collections${query(true)}`);
  return kpis([
    { label: 'Collected', value: fmtShort(d.total), sub: `${plural(d.count, 'payment')}` },
    { label: 'Due in period', value: fmtShort(d.due_in_period), sub: 'Installments due up to today' },
    { label: 'Collection rate', value: pct(d.collection_rate), tone: d.collection_rate != null && d.collection_rate < 60 ? 'bad' : '' },
    { label: 'Average payment', value: fmtShort(d.count ? d.total / d.count : 0) },
  ]) + `${card('Collections by month', esc(periodLabel()), columns(fillMonths(d.monthly, { amount: 0, count: 0 }).map((m) => ({ label: monthLabel(m.month), value: m.amount, tip: `${plural(m.count, 'payment')}` })), { label: 'Collections' }))}
    <div class="rp-grid">
      ${card('By payment method', '', hbars(d.by_method.map((x) => ({ label: x.method, value: x.amount, sub: `${plural(x.count, 'payment')}` }))))}
      ${card('By project', '', hbars(d.by_project.map((x) => ({ label: x.project_name, value: x.amount, sub: `${plural(x.count, 'payment')}` }))))}
    </div>
    ${card('Payments', `${d.payments.length} received`, table('rt-coll', [
      { key: 'payment_date', label: 'Date', type: 'date' },
      { key: 'receipt_no', label: 'Receipt', cls: 'td-mono' },
      { key: 'customer_name', label: 'Customer', cls: 'td-b' },
      { key: 'project_name', label: 'Project' },
      { key: 'unit_no', label: 'Unit' },
      { key: 'against', label: 'Against' },
      { key: 'payment_method', label: 'Method' },
      { key: 'reference_number', label: 'Reference' },
      { key: 'amount', label: 'Amount', type: 'money', cls: 'td-b' },
    ], d.payments, { name: 'collections', primary: true }))}`;
}

async function rAgeing() {
  const d = await api(`/api/reports/ageing${query(false)}`);
  const buckets = d.buckets || [];
  return kpis([
    { label: 'Total overdue', value: fmtShort(d.total), sub: `${plural(d.items.length, 'installment')} · ${plural(d.by_customer.length, 'customer')}`, tone: d.total ? 'bad' : '' },
    ...buckets.map((b) => ({ label: b.bucket, value: fmtShort(b.amount), sub: `${plural(b.count, 'installment')}` })),
  ]) + `<div class="rp-grid">
      ${card('Overdue by age', 'Older debt is harder to recover', hbars(buckets.map((b) => ({ label: b.bucket, value: b.amount, sub: `${plural(b.count, 'item')}` })), { colors: AGE_RAMP }))}
      ${card('By project', '', table('rt-age-proj', [
        { key: 'project_name', label: 'Project', cls: 'td-b' },
        ...buckets.map((b) => ({ key: b.bucket, label: b.bucket, type: 'money' })),
        { key: 'amount', label: 'Total', type: 'money', cls: 'td-b' },
      ], d.by_project, { search: false }))}
    </div>
    ${card('Customers to follow up', 'Largest overdue first', table('rt-age-cust', [
      { key: 'customer_name', label: 'Customer', cls: 'td-b' },
      { key: 'phone', label: 'Phone', cls: 'td-mono' },
      { key: 'units', label: 'Units' },
      { key: 'count', label: 'Installments', type: 'num' },
      { key: 'oldest_days', label: 'Oldest (days)', type: 'num' },
      { key: 'amount', label: 'Overdue', type: 'money', cls: 'td-red' },
    ], d.by_customer, { name: 'overdue-customers' }))}
    ${card('All overdue installments', '', table('rt-age', [
      { key: 'customer_name', label: 'Customer', cls: 'td-b' },
      { key: 'project_name', label: 'Project' },
      { key: 'unit_no', label: 'Unit' },
      { key: 'booking_no', label: 'Booking', cls: 'td-mono' },
      { key: 'type', label: 'Installment' },
      { key: 'due_date', label: 'Due', type: 'date' },
      { key: 'days_overdue', label: 'Days late', type: 'num' },
      { key: 'bucket', label: 'Bucket' },
      { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
      { key: 'amount', label: 'Remaining', type: 'money', cls: 'td-red' },
    ], d.items, { name: 'ageing', primary: true }))}`;
}

async function rCustomers() {
  const d = await api(`/api/reports/customer-balances${query(false)}`);
  const t = d.totals;
  const counts = d.customers.reduce((a, c) => ({ ...a, [c.status]: (a[c.status] || 0) + 1 }), {});
  return kpis([
    { label: 'Customers with bookings', value: d.customers.length, sub: `${counts.Overdue || 0} overdue · ${counts.Cleared || 0} cleared` },
    { label: 'Total sale value', value: fmtShort(t.sale_value) },
    { label: 'Received', value: fmtShort(t.paid), sub: t.sale_value ? `${Math.round((t.paid / t.sale_value) * 100)}% of value` : '' },
    { label: 'Outstanding', value: fmtShort(t.outstanding) },
    { label: 'Overdue', value: fmtShort(t.overdue), tone: t.overdue ? 'bad' : '' },
  ]) + card('Customer balances', 'Overdue customers first', table('rt-cust', [
    { key: 'customer_name', label: 'Customer', render: (r) => `<b>${esc(r.customer_name)}</b><div class="rp-sub">${esc([r.cnic, r.phone].filter(Boolean).join(' · ') || '—')}</div>` },
    { key: 'cnic', label: 'CNIC', hide: true },
    { key: 'phone', label: 'Phone', hide: true },
    { key: 'units', label: 'Units' },
    { key: 'sale_value', label: 'Sale value', type: 'money' },
    { key: 'paid', label: 'Paid', type: 'money' },
    { key: 'paid_pct', label: 'Paid %', type: 'pct' },
    { key: 'outstanding', label: 'Outstanding', type: 'money' },
    { key: 'overdue', label: 'Overdue', type: 'money', render: (r) => `<span class="${r.overdue > 0 ? 'td-red' : ''}">${fmt(r.overdue)}</span>` },
    { key: 'last_payment', label: 'Last payment', type: 'date' },
    { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
  ], d.customers, { name: 'customer-balances', primary: true }));
}

async function rInventory() {
  const d = await api(`/api/reports/inventory${query(false)}`);
  const sum = (k) => d.by_project.reduce((a, p) => a + (p[k] || 0), 0);
  const total = sum('total');
  return kpis([
    { label: 'Total units', value: total.toLocaleString('en-PK'), sub: `${d.by_project.length} projects` },
    { label: 'Available', value: sum('available'), sub: fmtShort(sum('available_value')) },
    { label: 'On hold', value: sum('hold'), sub: `${d.holds.length} active holds` },
    { label: 'Booked / sold', value: sum('booked'), sub: total ? `${Math.round(((sum('booked') + sum('delivered')) / total) * 100)}% sold incl. delivered` : '' },
    { label: 'Possession delivered', value: sum('delivered') },
  ]) + card('Unit status by project', '', stacked(d.by_project.map((p) => ({ ...p, label: p.project_name, valueLabel: `${p.sold_pct}% sold` })), [
    { key: 'available', label: 'Available', color: C.aqua },
    { key: 'hold', label: 'Hold', color: C.yellow },
    { key: 'booked', label: 'Booked / sold', color: C.blue },
    { key: 'delivered', label: 'Delivered', color: C.violet },
  ])) + card('By project', '', table('rt-inv', [
    { key: 'project_name', label: 'Project', cls: 'td-b' },
    { key: 'progress', label: 'Construction', type: 'pct' },
    { key: 'total', label: 'Units', type: 'num' },
    { key: 'available', label: 'Available', type: 'num' },
    { key: 'hold', label: 'Hold', type: 'num' },
    { key: 'booked', label: 'Booked', type: 'num' },
    { key: 'delivered', label: 'Delivered', type: 'num' },
    { key: 'sold_pct', label: 'Sold %', type: 'pct' },
    { key: 'available_value', label: 'Unsold value', type: 'money' },
  ], d.by_project, { name: 'inventory', primary: true, search: false })) + `<div class="rp-grid">
    ${card('By unit type', 'Available price range', table('rt-inv-type', [
      { key: 'unit_type', label: 'Type', cls: 'td-b' },
      { key: 'total', label: 'Units', type: 'num' },
      { key: 'available', label: 'Available', type: 'num' },
      { key: 'min_price', label: 'From', type: 'money' },
      { key: 'max_price', label: 'To', type: 'money' },
    ], d.by_type, { search: false }))}
    ${card('Active holds', 'Expiring soonest first', table('rt-holds', [
      { key: 'unit_no', label: 'Unit', cls: 'td-b' },
      { key: 'project_name', label: 'Project' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'hold_until', label: 'Until', type: 'date' },
      { key: 'days_left', label: 'Days left', type: 'num' },
      { key: 'token_amount', label: 'Token', type: 'money' },
    ], d.holds, { search: false }))}
  </div>`;
}

async function rPayables() {
  const d = await api(`/api/reports/payables${query(false)}`);
  const t = d.totals;
  return kpis([
    { label: 'Total payable', value: fmtShort(t.vendor_balance + t.agent_balance), tone: 'bad' },
    { label: 'Vendors', value: fmtShort(t.vendor_balance), sub: `${fmtShort(t.vendor_paid)} paid of ${fmtShort(t.vendor_ordered)}` },
    { label: 'Agent commission due', value: fmtShort(t.agent_balance), sub: `${d.agents.length} agents` },
  ]) + card('Vendor balances', 'Largest balance first', table('rt-vendors', [
    { key: 'vendor_name', label: 'Vendor', cls: 'td-b' },
    { key: 'category', label: 'Category' },
    { key: 'contact', label: 'Contact' },
    { key: 'orders', label: 'POs', type: 'num' },
    { key: 'last_order', label: 'Last order', type: 'date' },
    { key: 'ordered', label: 'Ordered', type: 'money' },
    { key: 'paid', label: 'Paid', type: 'money' },
    { key: 'balance', label: 'Balance', type: 'money', render: (r) => `<span class="${r.balance > 0 ? 'td-red' : ''}">${fmt(r.balance)}</span>` },
  ], d.vendors, { name: 'vendor-payables', primary: true, search: false })) + card('Agent commissions', '', table('rt-agents', [
    { key: 'agent_name', label: 'Agent', cls: 'td-b' },
    { key: 'deals', label: 'Deals', type: 'num' },
    { key: 'earned', label: 'Earned', type: 'money' },
    { key: 'paid', label: 'Paid', type: 'money' },
    { key: 'balance', label: 'Due', type: 'money', render: (r) => `<span class="${r.balance > 0 ? 'td-red' : ''}">${fmt(r.balance)}</span>` },
  ], d.agents, { search: false }));
}

async function rBudget() {
  const d = await api(`/api/reports/budget${query(false)}`);
  const planned = d.lines.reduce((a, l) => a + l.planned_amount, 0);
  const spent = d.lines.reduce((a, l) => a + l.actual_spent, 0);
  const exceeded = d.lines.filter((l) => l.status === 'Exceeded').length;
  return kpis([
    { label: 'Planned', value: fmtShort(planned), sub: `${d.lines.length} budget lines` },
    { label: 'Spent', value: fmtShort(spent), sub: planned ? `${Math.round((spent / planned) * 100)}% used` : '' },
    { label: 'Remaining', value: fmtShort(planned - spent), tone: planned - spent < 0 ? 'bad' : '' },
    { label: 'Lines over budget', value: exceeded, tone: exceeded ? 'bad' : '' },
  ]) + card('By project', '', `<div class="card-bd rp-hbars">${d.by_project.length ? d.by_project.map((p) => `
    <div class="rp-hbar" title="${esc(p.project_name)}: ${p.pct_used}% used">
      <div class="rp-hbar-lbl">${esc(p.project_name)}<small>${fmtShort(p.spent)} of ${fmtShort(p.planned)}</small></div>
      <div class="rp-hbar-track rp-budget"><span style="width:${Math.min(p.pct_used, 100)}%;background:${p.pct_used > 100 ? 'var(--danger)' : p.pct_used >= 85 ? 'var(--accent)' : C.blue}"></span></div>
      <div class="rp-hbar-val">${p.pct_used}%</div>
    </div>`).join('') : empty('No budget lines yet.')}</div>`)
    + card('Budget lines', '', table('rt-budget', [
      { key: 'project_name', label: 'Project', cls: 'td-b' },
      { key: 'category_name', label: 'Category' },
      { key: 'planned_amount', label: 'Planned', type: 'money' },
      { key: 'actual_spent', label: 'Spent', type: 'money' },
      { key: 'variance', label: 'Variance', type: 'money', render: (r) => `<span class="${r.variance < 0 ? 'td-red' : ''}">${fmt(r.variance)}</span>` },
      { key: 'pct_used', label: '% used', type: 'pct' },
      { key: 'status', label: 'Status', render: (r) => statusBadge(r.status) },
    ], [...d.lines].sort((a, b) => (b.pct_used || 0) - (a.pct_used || 0)), { name: 'budget', primary: true }));
}


// ------------------------------------------------------------------ accounting & management reports
const signedMoney = (v) => `<span class="${v < 0 ? 'td-red' : ''}">${fmt(v)}</span>`;
const TYPE_LABEL = { asset: 'Asset', liability: 'Liability', equity: 'Equity', income: 'Income', expense: 'Expense' };

/** Two-series column chart (e.g. cash in vs out), legend always present. */
function pairColumns(points, series) {
  if (!points.some((p) => series.some((s) => p[s.key]))) return empty('No data in this period.');
  const max = niceMax(Math.max(...points.flatMap((p) => series.map((s) => p[s.key] || 0)), 0));
  const legend = `<div class="rp-legend">${series.map((x) => `<span><i style="background:${x.color}"></i>${esc(x.label)}</span>`).join('')}</div>`;
  return `<div class="card-bd">${legend}<div class="chart rp-chart" role="img" aria-label="${esc(series.map((x) => x.label).join(' and '))} by month">
    <div class="chart-grid">${[1, 0.75, 0.5, 0.25, 0].map((t) => `<div><span>${axis(max * t)}</span></div>`).join('')}</div>
    ${points.map((p, i) => `<div class="chart-col">
      <div class="rp-pair">${series.map((x) => `<div class="chart-bar" style="height:${((p[x.key] || 0) / max) * 100}%;background:${x.color}"></div>`).join('')}
        <div class="chart-tip">${esc(p.label)}${series.map((x) => `<small>${esc(x.label)}: ${fmt(p[x.key] || 0)}</small>`).join('')}</div>
      </div>
      <div class="chart-lbl">${tick(p.label, i, points.length)}</div></div>`).join('')}
  </div></div>`;
}

async function rMonthly() {
  const d = await api(`/api/reports/monthly${query(true)}`);
  const months = fillMonths(d.months, { cash_in: 0, cash_out: 0, net: 0 });
  // carry balances through empty months
  let bal = d.opening;
  months.forEach((m) => {
    if (m.opening == null) { m.opening = bal; m.closing = bal; m.in = {}; m.out = {}; }
    bal = m.closing;
  });
  const net = d.total_in - d.total_out;
  const sourceCsv = (side) => (r) => Object.entries(r[side] || {}).map(([k, v]) => `${k}: ${v}`).join('; ');
  return kpis([
    { label: 'Opening cash', value: fmtShort(d.opening), sub: 'Cash in hand + bank' },
    { label: 'Money in', value: fmtShort(d.total_in) },
    { label: 'Money out', value: fmtShort(d.total_out) },
    { label: 'Net change', value: fmtShort(net), tone: net < 0 ? 'bad' : '' },
    { label: 'Closing cash', value: fmtShort(d.closing), tone: d.closing < 0 ? 'bad' : '' },
  ]) + card('Money in vs out', esc(periodLabel()), pairColumns(
    months.map((m) => ({ label: monthLabel(m.month), in: m.cash_in, out: m.cash_out })),
    [{ key: 'in', label: 'Money in', color: C.blue }, { key: 'out', label: 'Money out', color: C.aqua }],
  )) + `<div class="rp-grid">
      ${card('Where money came from', '', hbars(d.in_sources.map((x) => ({ label: x.name, value: x.amount }))))}
      ${card('Where money went', '', hbars(d.out_sources.map((x) => ({ label: x.name, value: x.amount }))))}
    </div>` + card('Month by month', 'Cash in hand and bank combined', table('rt-monthly', [
    { key: 'month', label: 'Month', render: (r) => `<b>${esc(monthLabel(r.month))}</b>`, csv: (r) => r.month },
    { key: 'opening', label: 'Opening', type: 'money', render: (r) => signedMoney(r.opening) },
    { key: 'cash_in', label: 'Money in', type: 'money' },
    { key: 'cash_out', label: 'Money out', type: 'money' },
    { key: 'net', label: 'Net', type: 'money', render: (r) => signedMoney(r.net) },
    { key: 'closing', label: 'Closing', type: 'money', render: (r) => `<b>${signedMoney(r.closing)}</b>` },
    { key: 'in_detail', label: 'In — detail', hide: true, csv: sourceCsv('in') },
    { key: 'out_detail', label: 'Out — detail', hide: true, csv: sourceCsv('out') },
  ], months, { name: 'monthly-in-out', primary: true, search: false, sortable: false,
    footer: `<td>Total</td><td class="r">${fmt(d.opening)}</td><td class="r">${fmt(d.total_in)}</td><td class="r">${fmt(d.total_out)}</td><td class="r">${fmt(net)}</td><td class="r">${fmt(d.closing)}</td>` }));
}

async function rProjectWise() {
  const d = await api(`/api/reports/project-wise${query(true)}`);
  const t = d.totals;
  const active = d.projects.filter((p) => p.units || p.net_sales || p.costs);
  return kpis([
    { label: 'Net sales', value: fmtShort(t.net_sales), sub: `${plural(t.bookings, 'booking')} · ${fmtShort(t.cancellations)} cancelled` },
    { label: 'Collected', value: fmtShort(t.collected), sub: t.net_sales > 0 ? `${Math.round((t.collected / t.net_sales) * 100)}% of net sales` : '' },
    { label: 'Construction cost', value: fmtShort(t.costs), sub: t.budget ? `${Math.round((t.costs / t.budget) * 100)}% of budget` : '' },
    { label: 'Commissions', value: fmtShort(t.commissions) },
    { label: 'Margin', value: fmtShort(t.margin), tone: t.margin < 0 ? 'bad' : 'good', sub: 'See note below the table' },
  ]) + `<div class="rp-grid">
      ${card('Sales by project', `${esc(periodLabel())} · before cancellations`, hbars(active.filter((p) => p.sales).sort((a, b) => b.sales - a.sales).map((p) => ({ label: p.project_name, value: p.sales, sub: `${plural(p.bookings, 'booking')}${p.cancellations ? ` · ${fmtShort(p.cancellations)} cancelled` : ''}` }))))}
      ${card('Cost by project', 'Materials + contractors', hbars(active.filter((p) => p.costs).sort((a, b) => b.costs - a.costs).map((p) => ({ label: p.project_name, value: p.costs, sub: p.budget ? `${p.budget_used_pct}% of budget` : 'No budget set' })), { color: C.aqua }))}
    </div>` + card('Project summary', 'Receivable and overdue are as of today', table('rt-projects', [
    { key: 'project_name', label: 'Project', cls: 'td-b' },
    { key: 'units', label: 'Units', type: 'num' },
    { key: 'sold', label: 'Sold', type: 'num' },
    { key: 'progress', label: 'Built %', type: 'pct', hide: true },
    { key: 'sales', label: 'Sales', type: 'money' },
    { key: 'cancellations', label: 'Cancelled', type: 'money' },
    { key: 'net_sales', label: 'Net sales', type: 'money', render: (r) => signedMoney(r.net_sales) },
    { key: 'collected', label: 'Collected', type: 'money' },
    { key: 'collected_pct', label: 'Collected %', type: 'pct', hide: true },
    { key: 'receivable', label: 'Receivable', type: 'money' },
    { key: 'overdue', label: 'Overdue', type: 'money', render: (r) => `<span class="${r.overdue > 0 ? 'td-red' : ''}">${fmt(r.overdue)}</span>` },
    { key: 'costs', label: 'Costs', type: 'money' },
    { key: 'budget', label: 'Budget', type: 'money', hide: true },
    { key: 'commissions', label: 'Commission', type: 'money', hide: true },
    { key: 'other_income', label: 'Other income', type: 'money', hide: true },
    { key: 'funding', label: 'Investor/partner funds', type: 'money', hide: true },
    { key: 'margin', label: 'Margin', type: 'money', render: (r) => `<b>${signedMoney(r.margin)}</b>` },
  ], d.projects, { name: 'project-wise', primary: true, search: false,
    footer: `<td>Total</td>${[t.units, t.sold].map((v) => `<td class="r">${v}</td>`).join('')}${[t.sales, t.cancellations, t.net_sales, t.collected, t.receivable, t.overdue, t.costs, t.margin].map((v) => `<td class="r">${fmt(v)}</td>`).join('')}` }))
  + `<p class="rp-note">${icon('alert', 13)} Sales and cancellations are counted in the month they happen, so cancelling an older booking can make a period's net sales negative. Margin = net sales + other income − construction costs − commissions.</p>`;
}

async function rExpenses() {
  const d = await api(`/api/reports/expense-ledger${query(true)}`);
  const top = d.by_category[0];
  const months = fillMonths(d.monthly, { amount: 0 });
  return kpis([
    { label: 'Total expenses', value: fmtShort(d.total), sub: plural(d.count, 'entry') },
    { label: 'Largest category', value: top ? esc(top.name) : '—', sub: top ? fmtShort(top.amount) : '' },
    { label: 'Monthly average', value: fmtShort(months.length ? Math.round(d.total / months.length) : 0) },
    { label: 'Projects', value: d.by_project.length },
  ]) + card('Expenses by month', esc(periodLabel()), columns(months.map((m) => ({ label: monthLabel(m.month), value: m.amount })), { label: 'Expenses', color: C.aqua }))
  + `<div class="rp-grid">
      ${card('By category', '', hbars(d.by_category.map((x) => ({ label: x.name, value: x.amount, sub: plural(x.count, 'entry') })), { color: C.aqua }))}
      ${card('By project', '', hbars(d.by_project.map((x) => ({ label: x.name, value: x.amount, sub: plural(x.count, 'entry') })), { color: C.aqua }))}
    </div>` + card('Expense entries', 'Purchase orders count when ordered; other costs when paid', table('rt-expenses', [
    { key: 'date', label: 'Date', type: 'date' },
    { key: 'ref', label: 'Ref', cls: 'td-mono' },
    { key: 'category', label: 'Category', cls: 'td-b' },
    { key: 'group', label: 'Type' },
    { key: 'narration', label: 'Description', cls: 'wrap' },
    { key: 'project_name', label: 'Project' },
    { key: 'amount', label: 'Amount', type: 'money' },
  ], d.rows, { name: 'expense-ledger', primary: true,
    footer: `<td colspan="6">Total</td><td class="r">${fmt(d.total)}</td>` }));
}

async function rGeneralLedger() {
  const d = await api(`/api/reports/general-ledger${query(true, { account: glAccount })}`);
  const picker = `<select id="rp-gl-account" class="rp-inline-select" aria-label="Account">
      <option value="">All accounts (summary)</option>
      ${d.chart.map((a) => `<option value="${a.code}" ${a.code === glAccount ? 'selected' : ''}>${a.code} · ${esc(a.name)}</option>`).join('')}
    </select>`;
  if (!glAccount) {
    return `<div class="rp-bar">${picker}<span class="muted">Pick an account, or click one below, to see its entries.</span></div>`
      + card('Account balances', esc(periodLabel()), table('rt-gl-sum', [
        { key: 'code', label: 'Code', cls: 'td-mono' },
        { key: 'name', label: 'Account', render: (r) => `<button type="button" class="linkbtn" data-gl="${r.code}">${esc(r.name)}</button>`, csv: (r) => r.name },
        { key: 'type', label: 'Type', render: (r) => esc(TYPE_LABEL[r.type]) },
        { key: 'opening', label: 'Opening', type: 'money', render: (r) => signedMoney(r.opening) },
        { key: 'debits', label: 'Debits', type: 'money' },
        { key: 'credits', label: 'Credits', type: 'money' },
        { key: 'closing', label: 'Closing', type: 'money', render: (r) => `<b>${signedMoney(r.closing)}</b>` },
      ], d.accounts, { name: 'general-ledger-summary', primary: true, search: false, sortable: false }));
  }
  const acc = d.account;
  const last = d.lines.length ? d.lines[d.lines.length - 1].balance : d.opening;
  const dr = d.lines.reduce((a, l) => a + l.debit, 0);
  const cr = d.lines.reduce((a, l) => a + l.credit, 0);
  return `<div class="rp-bar">${picker}<button type="button" class="btn sm" data-gl="">${icon('arrow', 14)} All accounts</button></div>`
    + kpis([
      { label: `${acc.code} · ${TYPE_LABEL[acc.type]}`, value: esc(acc.name), sub: esc(acc.group) },
      { label: 'Opening balance', value: fmtShort(d.opening) },
      { label: 'Debits', value: fmtShort(dr), sub: plural(d.lines.length, 'entry') },
      { label: 'Credits', value: fmtShort(cr) },
      { label: 'Closing balance', value: fmtShort(last), tone: last < 0 ? 'bad' : '' },
    ]) + card(`${acc.name} — entries`, `Balance shown on the account's normal side · ${esc(periodLabel())}`, table('rt-gl', [
      { key: 'date', label: 'Date', type: 'date' },
      { key: 'ref', label: 'Ref', cls: 'td-mono' },
      { key: 'narration', label: 'Description', cls: 'wrap' },
      { key: 'project_name', label: 'Project' },
      { key: 'debit', label: 'Debit', type: 'money', render: (r) => (r.debit ? fmt(r.debit) : '') },
      { key: 'credit', label: 'Credit', type: 'money', render: (r) => (r.credit ? fmt(r.credit) : '') },
      { key: 'balance', label: 'Balance', type: 'money', render: (r) => `<b>${signedMoney(r.balance)}</b>` },
    ], [{ date: '', ref: '', narration: 'Opening balance', project_name: '', debit: 0, credit: 0, balance: d.opening, opening: true }, ...d.lines],
    { name: `ledger-${acc.code}`, primary: true, sortable: false,
      footer: `<td colspan="4">Closing balance</td><td class="r">${fmt(dr)}</td><td class="r">${fmt(cr)}</td><td class="r">${fmt(last)}</td>` }));
}

async function rTrialBalance() {
  const d = await api(`/api/reports/trial-balance${query(true)}`);
  return kpis([
    { label: 'Total debits', value: fmtShort(d.total_debit) },
    { label: 'Total credits', value: fmtShort(d.total_credit) },
    { label: 'Difference', value: fmtShort(d.total_debit - d.total_credit), tone: d.balanced ? 'good' : 'bad', sub: d.balanced ? `${icon('check', 12)} Books balance` : `${icon('alert', 12)} Out of balance` },
    { label: 'Journal entries', value: d.entries.toLocaleString('en-PK'), sub: 'Generated from transactions' },
  ]) + card('Trial balance', esc(periodLabel()), table('rt-tb', [
    { key: 'code', label: 'Code', cls: 'td-mono' },
    { key: 'name', label: 'Account', render: (r) => `<button type="button" class="linkbtn" data-gl="${r.code}">${esc(r.name)}</button>`, csv: (r) => r.name },
    { key: 'type', label: 'Type', render: (r) => esc(TYPE_LABEL[r.type]), csv: (r) => TYPE_LABEL[r.type] },
    { key: 'debit', label: 'Debit', type: 'money', render: (r) => (r.debit ? fmt(r.debit) : '') },
    { key: 'credit', label: 'Credit', type: 'money', render: (r) => (r.credit ? fmt(r.credit) : '') },
  ], d.accounts, { name: 'trial-balance', primary: true, search: false, sortable: false,
    footer: `<td colspan="3">Total</td><td class="r">${fmt(d.total_debit)}</td><td class="r">${fmt(d.total_credit)}</td>` }))
  + `<p class="rp-note">${icon('alert', 13)} Figures are generated from bookings, payments, purchase orders, commissions, investor/partner funds and cashbook entries. Sales count as revenue on the booking date.</p>`;
}

function statement(title, rows, total, totalLabel) {
  const groups = [];
  rows.forEach((r) => {
    let g = groups.find((x) => x.name === r.group);
    if (!g) { g = { name: r.group, rows: [], total: 0 }; groups.push(g); }
    g.rows.push(r);
    g.total += r.amount;
  });
  const body = groups.length ? groups.map((g) => `
      <tr class="rp-st-group"><td colspan="2">${esc(g.name)}</td></tr>
      ${g.rows.map((r) => `<tr><td class="rp-st-item">${r.code !== 'RE' ? `<button type="button" class="linkbtn" data-gl="${r.code}">${esc(r.name)}</button>` : esc(r.name)}</td><td class="r num">${signedMoney(r.amount)}</td></tr>`).join('')}
      ${g.rows.length > 1 ? `<tr class="rp-st-sub"><td>Total ${esc(g.name.toLowerCase())}</td><td class="r num">${signedMoney(g.total)}</td></tr>` : ''}`).join('')
    : '<tr><td colspan="2" class="muted">Nothing to show</td></tr>';
  return `<table class="rp-statement"><thead><tr><th>${esc(title)}</th><th class="r">PKR</th></tr></thead>
    <tbody>${body}</tbody>
    <tfoot><tr><td>${esc(totalLabel)}</td><td class="r num">${signedMoney(total)}</td></tr></tfoot></table>`;
}

async function rBalanceSheet() {
  const d = await api(`/api/reports/balance-sheet${query(true)}`);
  const le = d.total_liabilities + d.total_equity;
  exportable = {
    name: 'balance-sheet',
    columns: [{ key: 'section', label: 'Section' }, { key: 'group', label: 'Group' }, { key: 'name', label: 'Account' }, { key: 'amount', label: 'Amount (PKR)' }],
    rows: [
      ...d.assets.map((r) => ({ section: 'Assets', ...r })),
      { section: 'Assets', group: '', name: 'Total assets', amount: d.total_assets },
      ...d.liabilities.map((r) => ({ section: 'Liabilities', ...r })),
      { section: 'Liabilities', group: '', name: 'Total liabilities', amount: d.total_liabilities },
      ...d.equity.map((r) => ({ section: 'Equity', ...r })),
      { section: 'Equity', group: '', name: 'Total equity', amount: d.total_equity },
    ],
  };
  return kpis([
    { label: 'Total assets', value: fmtShort(d.total_assets) },
    { label: 'Total liabilities', value: fmtShort(d.total_liabilities) },
    { label: 'Equity', value: fmtShort(d.total_equity), sub: `Profit to date ${fmtShort(d.profit_to_date)}` },
    { label: 'Check', value: d.balanced ? 'Balanced' : 'Not balanced', tone: d.balanced ? 'good' : 'bad', sub: 'Assets = liabilities + equity' },
  ]) + `<div class="rp-grid">
      ${card('Assets', esc(periodLabel()), `<div class="card-bd">${statement('Asset', d.assets, d.total_assets, 'Total assets')}</div>`)}
      ${card('Liabilities & equity', esc(periodLabel()), `<div class="card-bd">
        ${statement('Liability', d.liabilities, d.total_liabilities, 'Total liabilities')}
        ${statement('Equity', d.equity, d.total_equity, 'Total equity')}
        <table class="rp-statement rp-st-grand"><tfoot><tr><td>Total liabilities & equity</td><td class="r num">${signedMoney(le)}</td></tr></tfoot></table>
      </div>`)}
    </div>
    <p class="rp-note">${icon('alert', 13)} Customer receivables are the unpaid sale value of all bookings (revenue is recognised at booking). Investor money is shown as a liability; partner money as capital.</p>`;
}

async function rAudit() {
  const d = await api(`/api/reports/audit${query(true, { entity: auditEntity })}`);
  const passed = d.checks.filter((c) => c.ok).length;
  const entitySel = `<select id="rp-audit-entity" class="rp-inline-select" aria-label="Record type">
      <option value="">All record types</option>
      ${d.entities.map((e) => `<option value="${esc(e)}" ${e === auditEntity ? 'selected' : ''}>${esc(e.replace(/_/g, ' '))}</option>`).join('')}
    </select>`;
  return kpis([
    { label: 'Recorded events', value: d.count.toLocaleString('en-PK'), sub: esc(periodLabel()) },
    { label: 'Needs review', value: d.exceptions.length.toLocaleString('en-PK'), sub: 'Cancellations, transfers, manual changes', tone: d.exceptions.length ? 'bad' : '' },
    { label: 'Integrity checks', value: `${passed} / ${d.checks.length}`, sub: passed === d.checks.length ? 'All passed' : `${d.checks.length - passed} need attention`, tone: passed === d.checks.length ? 'good' : 'bad' },
  ]) + card('Integrity checks', 'Run on the current books', `<div class="card-bd"><ul class="rp-checks">${d.checks.map((c) => `
      <li class="${c.ok ? 'ok' : 'fail'}"><span class="rp-check-ico">${icon(c.ok ? 'check' : 'alert', 14)}</span>
        <div><b>${esc(c.check)}</b><small>${c.ok ? 'Passed' : 'Failed'} · ${esc(c.detail)}</small></div></li>`).join('')}</ul></div>`)
  + `<div class="rp-grid">
      ${card('Activity by type', '', hbars(d.by_action.slice(0, 12).map((x) => ({ label: x.name, value: x.count })), { money: false }))}
      ${card('Needs review', 'Most recent first', table('rt-exc', [
        { key: 'created_at', label: 'When', type: 'date' },
        { key: 'flag', label: 'What', cls: 'td-b' },
        { key: 'entity_id', label: 'Record', render: (r) => `${esc(r.entity_type.replace(/_/g, ' '))} #${r.entity_id ?? '—'}` },
      ], d.exceptions, { search: false }))}
    </div>`
  + `<div class="rp-bar">${entitySel}<span class="muted">Audit is company-wide; the project filter does not apply.</span></div>`
  + card('Audit trail', 'Every change recorded by the system', table('rt-audit', [
    { key: 'created_at', label: 'Date & time', render: (r) => esc(r.created_at), csv: (r) => r.created_at },
    { key: 'entity_type', label: 'Record', render: (r) => `${esc(r.entity_type.replace(/_/g, ' '))} <span class="muted">#${r.entity_id ?? '—'}</span>` },
    { key: 'entity_id', label: 'Record ID', hide: true },
    { key: 'action', label: 'Action', render: (r) => `<span class="badge ${/cancel|delet|expired/.test(r.action) ? 'bg-red' : /transfer|status/.test(r.action) ? 'bg-yellow' : 'bg-grey'}">${esc(r.action)}</span>`, csv: (r) => r.action },
    { key: 'details', label: 'Details', cls: 'wrap' },
  ], d.events, { name: 'audit-trail', primary: true }));
}

const RENDER = { monthly: rMonthly, projectwise: rProjectWise, expenses: rExpenses, gl: rGeneralLedger, tb: rTrialBalance, bs: rBalanceSheet, audit: rAudit, overview: rOverview, sales: rSales, collections: rCollections, ageing: rAgeing, customers: rCustomers, inventory: rInventory, payables: rPayables, budget: rBudget };

// ------------------------------------------------------------------ shell
function renderShell() {
  const host = $('s-reports');
  if (host.dataset.ready) return;
  host.dataset.ready = '1';
  host.innerHTML = `
    <div class="rp-tabs" role="tablist">${['main', 'more'].map((g) => `${g === 'more' ? '<span class="rp-tab-sep" aria-hidden="true">More</span>' : ''}${REPORTS.filter((r) => r.group === g).map((r) => `
      <button type="button" role="tab" class="rp-tab" data-rp="${r.key}" title="${esc(r.desc)}">${icon(r.ico, 16)}<span>${esc(r.label)}</span></button>`).join('')}`).join('')}
    </div>
    <div class="card filter-card rp-filters">
      <div class="toolbar">
        <div class="rp-period" id="rp-period-wrap">
          <label class="fg-hint" for="rp-period" id="rp-period-lbl" style="margin:0">Period</label>
          <select id="rp-period"></select>
          <span id="rp-custom" hidden><input type="date" id="rp-from" aria-label="From"> <input type="date" id="rp-to" aria-label="To"></span>
        </div>
        <span class="rp-scope" id="rp-scope"></span>
        <div class="toolbar-end">
          <button type="button" class="btn" id="rp-csv" data-perm="view">${icon('download', 15)} Export CSV</button>
          <button type="button" class="btn" id="rp-print" data-perm="view">${icon('file', 15)} Print / PDF</button>
        </div>
      </div>
    </div>
    <div class="rp-head"><h2 id="rp-title"></h2><p id="rp-desc"></p></div>
    <div id="report-output"></div>`;
  host.querySelectorAll('[data-rp]').forEach((b) => b.addEventListener('click', () => { current = b.dataset.rp; loadReports(); }));
  $('rp-period').addEventListener('change', () => {
    const v = $('rp-period').value;
    if (mode() === 'asof') asof = v; else period = v;
    syncPeriodControls();
    if (v !== 'custom') loadReports();
  });
  // Clicks inside the report: open an account in the general ledger.
  $('report-output').addEventListener('click', (e) => {
    const b = e.target.closest('[data-gl]');
    if (!b) return;
    glAccount = b.dataset.gl;
    current = 'gl';
    loadReports();
  });
  $('report-output').addEventListener('change', (e) => {
    if (e.target.id === 'rp-gl-account') { glAccount = e.target.value; loadReports(); }
    if (e.target.id === 'rp-audit-entity') { auditEntity = e.target.value; loadReports(); }
  });
  ['rp-from', 'rp-to'].forEach((id) => $(id).addEventListener('change', () => loadReports()));
  $('rp-csv').addEventListener('click', exportCsv);
  $('rp-print').addEventListener('click', () => window.print());
}

function syncPeriodControls() {
  const m = mode();
  const sel = $('rp-period');
  const opts = m === 'asof' ? ASOF : PERIODS;
  const val = m === 'asof' ? asof : period;
  if (sel.dataset.kind !== m) {
    sel.innerHTML = opts.map(([k, l]) => `<option value="${k}">${l}</option>`).join('');
    sel.dataset.kind = m;
  }
  sel.value = val;
  $('rp-period-lbl').textContent = m === 'asof' ? 'As of' : 'Period';
  $('rp-custom').hidden = val !== 'custom';
  $('rp-from').hidden = m === 'asof';
}

let seq = 0;
export async function loadReports() {
  renderShell();
  const def = REPORTS.find((r) => r.key === current);
  document.querySelectorAll('.rp-tab').forEach((b) => {
    b.classList.toggle('active', b.dataset.rp === current);
    b.setAttribute('aria-selected', String(b.dataset.rp === current));
  });
  $('rp-period-wrap').hidden = def.mode === 'none';
  if (def.mode !== 'none') syncPeriodControls();
  $('rp-title').textContent = def.label;
  $('rp-desc').textContent = def.desc;
  $('rp-scope').innerHTML = `${icon('projects', 14)} ${esc(def.key === 'audit' ? 'Company-wide' : filterLabelShort())} · ${esc(periodLabel())}`;
  const out = $('report-output');
  out.innerHTML = '<div class="loading"><span class="spinner"></span>Building report…</div>';
  exportable = null;
  Object.keys(tables).forEach((k) => delete tables[k]);
  const my = ++seq;
  try {
    const html = await RENDER[current]();
    if (my !== seq) return; // a newer request replaced this one
    out.innerHTML = html;
    wireTables(out);
    $('rp-csv').disabled = !exportable;
  } catch (e) {
    if (my === seq) out.innerHTML = `<div class="empty"><b>Could not build this report</b>${esc(e.message)}</div>`;
  }
}

export function initReportsEvents() { /* shell is built lazily on first open */ }

// Legacy names kept for any old callers.
export const loadAgeing = () => { current = 'ageing'; return loadReports(); };
export const loadSalesReport = () => { current = 'sales'; return loadReports(); };
