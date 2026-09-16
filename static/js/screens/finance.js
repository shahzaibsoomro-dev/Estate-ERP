import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';

export async function loadAccounts() {
  const d = await api('/api/ledger');
  if ($('gl-rev')) $('gl-rev').textContent = fmtShort(d.inflow ?? d.revenue ?? 0);
  if ($('gl-exp')) $('gl-exp').textContent = fmtShort(d.outflow ?? d.expenses ?? 0);
  if ($('gl-profit')) $('gl-profit').textContent = fmtShort(d.net ?? d.profit ?? 0);
  const rows = d.entries || [];
  $('gl-entries').innerHTML = rows.length
    ? rows.map((e) => `
      <div class="gl-row">
        <span>${esc(e.entry_date || '—')}</span>
        <span>${esc(e.narration || '—')}</span>
        <span>${e.inflow ? `<span class="cr">${fmt(e.inflow)}</span>` : '—'}</span>
        <span>${e.outflow ? `<span class="dr">${fmt(e.outflow)}</span>` : '—'}</span>
        <span style="font-family:monospace;font-size:11px;display:flex;align-items:center;justify-content:space-between;gap:8px">
          ${fmt(e.balance)}
          ${e.source === 'manual' && e.id ? `<button type="button" class="btn sm danger" data-del-le="${e.id}">✕</button>` : ''}
        </span>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No cash movements yet</div>';

  $('gl-entries').querySelectorAll('[data-del-le]').forEach((btn) => {
    btn.addEventListener('click', () => deleteLedgerEntry(parseInt(btn.dataset.delLe, 10)));
  });
}

async function deleteLedgerEntry(id) {
  if (!await askConfirm('Delete this manual entry?', { title: 'Delete entry', confirmLabel: 'Delete', danger: true })) return;
  try {
    await api(`/api/ledger/${id}`, { method: 'DELETE' });
    toast('Entry deleted');
    await loadAccounts();
  } catch { /* toasted */ }
}

export function openLedgerModal() {
  if ($('le-date')) $('le-date').value = new Date().toISOString().split('T')[0];
  if ($('le-dir')) $('le-dir').value = 'out';
  if ($('le-amount')) $('le-amount').value = '';
  if ($('le-nar')) $('le-nar').value = '';
  if ($('le-type')) $('le-type').value = 'General';
  openModal('ledger-modal');
}

export async function submitLedger() {
  const nar = ($('le-nar')?.value || '').trim();
  const amount = parseInt($('le-amount')?.value, 10);
  if (!nar || !amount) {
    toast('Narration and amount are required.', 'error');
    return;
  }
  try {
    await api('/api/ledger', {
      method: 'POST',
      body: JSON.stringify({
        entry_date: $('le-date').value,
        narration: nar,
        amount,
        direction: $('le-dir')?.value || 'out',
        category: $('le-type')?.value || 'General',
      }),
    });
    closeModal('ledger-modal');
    toast('Entry saved');
    await loadAccounts();
  } catch { /* toasted */ }
}

export function initAccountsEvents() {
  $('btn-ledger-entry')?.addEventListener('click', openLedgerModal);
  $('btn-save-ledger')?.addEventListener('click', submitLedger);
}
