import { $, esc } from '../dom.js';
import { api } from '../api.js';
import { fmt, fmtShort, instStatusBadge } from '../format.js';

export async function loadAgeing() {
  const d = await api('/api/reports/ageing');
  $('report-output').innerHTML = `
    <div class="card"><div class="card-hd"><span class="card-title">Ageing Report</span></div>
    <div class="g3">
      <div class="sm"><div class="sm-v" style="color:var(--accent)">${fmtShort(d.d30 || 0)}</div><div class="sm-l">1–30 Days</div></div>
      <div class="sm"><div class="sm-v" style="color:var(--warn)">${fmtShort(d.d60 || 0)}</div><div class="sm-l">31–60 Days</div></div>
      <div class="sm"><div class="sm-v" style="color:var(--danger)">${fmtShort(d.d90 || 0)}</div><div class="sm-l">60+ Days</div></div>
    </div></div>`;
}

export async function loadSalesReport() {
  const data = await api('/api/reports/sales');
  $('report-output').innerHTML = `
    <div class="card"><div class="card-hd"><span class="card-title">Sales Report</span></div>
    <div class="tbl-wrap"><table><thead><tr><th>Project</th><th>Bookings</th><th>Total Sales</th><th>DP Collected</th></tr></thead>
    <tbody>${(data || []).length ? data.map((r) => `
      <tr><td class="td-b">${esc(r.project_name)}</td><td>${r.bookings}</td>
      <td class="td-green">${fmt(r.total_sales)}</td><td>${fmt(r.collected_dp)}</td></tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:20px">No sales yet</td></tr>'}
    </tbody></table></div></div>`;
}

export async function loadPortal() {
  const d = await api('/api/units/1');
  const insts = d.installments || [];
  const b = d.booking;
  const s = d.summary;
  const u = d.unit;

  if (b && u) {
    document.querySelector('#s-portal .portal-hero').innerHTML = `
      <div style="font-size:9.5px;font-weight:800;letter-spacing:2px;opacity:.5;text-transform:uppercase;margin-bottom:7px">Haven Builders — Customer Self-Service Portal</div>
      <div style="font-size:21px;font-weight:900;margin-bottom:3px">Welcome, ${esc(b.customer_name)}</div>
      <div style="font-size:12px;opacity:.65;margin-bottom:16px">Unit ${esc(u.unit_no)} · ${esc(u.project_name)} · ${esc(u.location || '')}</div>
      <div style="display:flex;gap:22px">
        <div><div style="font-size:19px;font-weight:900">${fmt(s.sale_price)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Total Value</div></div>
        <div style="width:1px;background:rgba(255,255,255,.2)"></div>
        <div><div style="font-size:19px;font-weight:900">${fmt(s.total_paid)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Paid to Date</div></div>
        <div style="width:1px;background:rgba(255,255,255,.2)"></div>
        <div><div style="font-size:19px;font-weight:900;color:#FDE68A">${fmt(s.outstanding)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Outstanding</div></div>
      </div>`;
  }

  $('portal-sched').innerHTML = insts.length
    ? insts.map((i) => `
      <tr><td>${esc(i.due_date)}</td><td>${esc(i.type)}</td><td>${fmt(i.amount)}</td>
      <td><span class="badge ${instStatusBadge(i.status)}">${esc(i.status)}</span></td>
      <td>${i.status !== 'paid' ? '<button class="btn sm primary">Pay Now</button>' : '<button class="btn sm">Receipt</button>'}</td></tr>`).join('')
    : '<tr><td colspan="5">No schedule</td></tr>';
}

export function initReportsEvents() {
  document.querySelectorAll('[data-report]').forEach((el) => {
    el.addEventListener('click', () => {
      const type = el.dataset.report;
      if (type === 'ageing') loadAgeing();
      else if (type === 'sales') loadSalesReport();
    });
  });
}
