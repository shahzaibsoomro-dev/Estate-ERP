import { $, esc, loadingHtml } from '../dom.js';
import { api } from '../api.js';

function fmtDetails(d) {
  if (d == null || d === '') return '—';
  if (typeof d === 'string') return d;
  try {
    return JSON.stringify(d);
  } catch {
    return String(d);
  }
}

export async function loadActivity() {
  const tbody = $('audit-tbody');
  if (tbody) tbody.innerHTML = `<tr><td colspan="4">${loadingHtml('Loading activity…')}</td></tr>`;
  let rows = [];
  try {
    rows = await api('/api/audit?limit=200');
  } catch {
    if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:20px">Could not load activity</td></tr>';
    return;
  }
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map((r) => `
      <tr>
        <td class="td-sm">${esc(r.created_at || '—')}</td>
        <td>${esc(r.entity_type || '—')} #${esc(r.entity_id ?? '')}</td>
        <td><span class="badge bg-blue">${esc(r.action || '—')}</span></td>
        <td class="td-sm">${esc(fmtDetails(r.details))}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:20px">No activity yet</td></tr>';
}
