import { $, esc } from '../dom.js';
import { api } from '../api.js';
import { fmt, fmtShort } from '../format.js';

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

export function initReportsEvents() {
  document.querySelectorAll('[data-report]').forEach((el) => {
    el.addEventListener('click', () => {
      const type = el.dataset.report;
      if (type === 'ageing') loadAgeing();
      else if (type === 'sales') loadSalesReport();
    });
  });
}
