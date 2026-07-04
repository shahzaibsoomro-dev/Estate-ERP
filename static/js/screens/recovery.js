import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort, overdueBadge } from '../format.js';
import { projectFilterQuery } from '../project-filter.js';

export async function loadRecovery() {
  const d = await api(`/api/recovery${projectFilterQuery()}`);
  $('r-recv').textContent = fmtShort(d.receivable);
  $('r-over').textContent = fmtShort(d.overdue_amt);
  $('r-coll').textContent = fmtShort(d.collected_month);
  $('r-cases').textContent = d.overdue.length;

  $('recovery-tbody').innerHTML = d.overdue.length
    ? d.overdue.map((o) => `
      <tr>
        <td class="td-b">${esc(o.customer_name)}</td>
        <td>${esc(o.unit_no)}</td>
        <td>${esc(o.project_name)}</td>
        <td class="td-red">${fmt(o.amount)}</td>
        <td>${esc(o.due_date)}</td>
        <td><span class="badge ${overdueBadge(o.days_overdue)}">${o.days_overdue} Days</span></td>
        <td style="font-family:monospace;font-size:11px">${esc(o.phone)}</td>
        <td><button class="btn sm" data-wa="${esc(o.customer_name)}">💬 WA</button></td>
      </tr>`).join('')
    : '<tr><td colspan="8" style="text-align:center;color:var(--success);padding:20px">✅ No overdue installments</td></tr>';

  $('recovery-tbody').querySelectorAll('[data-wa]').forEach((btn) => {
    btn.addEventListener('click', () => toast(`WA sent to ${btn.dataset.wa}!`));
  });
}
