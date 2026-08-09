import { $ } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';

export async function loadAccounts() {
  const d = await api('/api/ledger');
  $('gl-rev').textContent = fmtShort(d.revenue);
  $('gl-exp').textContent = fmtShort(d.expenses);
  $('gl-profit').textContent = fmtShort(d.profit);
  $('gl-entries').innerHTML = d.entries.length
    ? d.entries.map((e) => `
      <div class="gl-row">
        <span>${e.entry_date}</span><span>${e.narration}</span>
        <span>${e.debit ? `<span class="dr">${fmt(e.debit)}</span>` : '—'}</span>
        <span>${e.credit ? `<span class="cr">${fmt(e.credit)}</span>` : '—'}</span>
        <span style="font-family:monospace;font-size:11px">${fmt(e.balance)}</span>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No ledger entries — module coming soon</div>';
}

export function openLedgerModal() {
  $('le-date').value = new Date().toISOString().split('T')[0];
  openModal('ledger-modal');
}

export async function submitLedger() {
  const nar = $('le-nar').value.trim();
  if (!nar) {
    toast('Narration required', 'error');
    return;
  }
  await api('/api/ledger', {
    method: 'POST',
    body: JSON.stringify({
      entry_date: $('le-date').value,
      narration: nar,
      debit: parseInt($('le-dr').value, 10) || 0,
      credit: parseInt($('le-cr').value, 10) || 0,
      account_type: $('le-type').value,
    }),
  });
  closeModal('ledger-modal');
  toast('Journal entry posted');
  loadAccounts();
}

export function initAccountsEvents() {
  $('btn-ledger-entry')?.addEventListener('click', openLedgerModal);
  $('btn-save-ledger')?.addEventListener('click', submitLedger);
}
