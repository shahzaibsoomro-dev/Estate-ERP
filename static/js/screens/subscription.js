import { $, esc } from '../dom.js';
import { api } from '../api.js';
import { fmt } from '../format.js';

const fdate = (s) => {
  if (!s) return '—';
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? esc(s) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

const STATE_BADGE = {
  trial: 'bg-blue', active: 'bg-green', grace: 'bg-orange', expired: 'bg-red', suspended: 'bg-red', none: 'bg-grey',
};

function usageBar(label, used, max) {
  const pct = max ? Math.min(100, Math.round((used / max) * 100)) : 0;
  const color = !max ? 'var(--success)' : pct >= 100 ? 'var(--danger)' : pct >= 80 ? 'var(--accent)' : 'var(--blue)';
  return `<div class="usage">
    <div class="usage-top"><span>${label}</span><b>${used}${max ? ` / ${max}` : ' · unlimited'}</b></div>
    <div class="prog"><div class="prog-fill" style="width:${max ? pct : 8}%;background:${color}"></div></div>
  </div>`;
}

export async function loadSubscription() {
  const d = await api('/api/company/subscription');
  const s = d.subscription || {};
  const st = d.state;
  const cycle = s.billing_cycle === 'yearly' ? 'year' : 'month';
  let note = '';
  if (st.state === 'trial') note = `Your free trial ends on <b>${fdate(s.current_period_end)}</b> (${st.days_left} days left).`;
  else if (st.state === 'active') note = `Renews on <b>${fdate(s.current_period_end)}</b> — ${st.days_left} days left.`;
  else if (st.state === 'grace') note = `Payment was due on <b>${fdate(s.current_period_end)}</b>. Everything keeps working until <b>${fdate(st.grace_ends)}</b>; after that the system becomes read-only.`;
  else if (st.state === 'expired') note = 'Your subscription has expired. You can still view everything, but adding or changing records is paused until payment is received.';
  else if (st.state === 'suspended') note = 'Your account is suspended. Please contact platform support.';

  $('sub-view').innerHTML = `
    <div class="row">
      <div class="col" style="flex:1.3">
        <div class="card sub-hero">
          <div class="card-bd">
            <div class="sub-top">
              <div><div class="card-sub">Current plan</div><div class="sub-plan">${esc(s.plan_name || '—')}</div></div>
              <span class="badge ${STATE_BADGE[st.state] || 'bg-grey'}">${esc(st.label)}</span>
            </div>
            <div class="sub-price">${fmt(s.amount)} <span>/ ${cycle}</span></div>
            <p class="sub-note">${note}</p>
            <div class="sub-facts">
              <div><span>Customer since</span><b>${fdate(s.started_on)}</b></div>
              <div><span>Current period ends</span><b>${fdate(s.current_period_end)}</b></div>
              <div><span>Grace period</span><b>${s.grace_days ?? 0} days</b></div>
            </div>
          </div>
        </div>
      </div>
      <div class="col">
        <div class="card">
          <div class="card-hd"><div class="card-title">Plan usage</div></div>
          <div class="card-bd">
            ${usageBar('Employees', d.usage.employees, s.max_employees)}
            ${usageBar('Projects', d.usage.projects, s.max_projects)}
            <p class="fg-hint" style="margin-top:12px">To renew, upgrade or change billing, contact platform support${d.company.contact_email ? '' : ''}. Payments are recorded by the platform team and appear below.</p>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-hd"><div><div class="card-title">Payment history</div><div class="card-sub">Subscription payments received from ${esc(d.company.name)}</div></div></div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Receipt</th><th>Paid on</th><th>Method</th><th>Covers</th><th style="text-align:right">Amount</th></tr></thead>
        <tbody>${d.payments.length ? d.payments.map((p) => `
          <tr${p.voided_at ? ' style="opacity:.55"' : ''}>
            <td class="td-mono">${esc(p.receipt_no)}${p.voided_at ? ' <span class="badge bg-grey">Voided</span>' : ''}</td>
            <td>${fdate(p.paid_on)}</td>
            <td>${esc(p.method)}${p.reference ? `<div class="cust-sub">${esc(p.reference)}</div>` : ''}</td>
            <td>${fdate(p.period_start)} → ${fdate(p.period_end)}</td>
            <td class="num td-b" style="text-align:right">${fmt(p.amount)}</td>
          </tr>`).join('') : '<tr><td colspan="5"><div class="empty"><b>No payments yet</b>Payments recorded by platform support will show here.</div></td></tr>'}
        </tbody>
      </table></div>
    </div>`;
}
