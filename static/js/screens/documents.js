import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { openModal, closeModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { icon } from '../icons.js';
import { customerOptionLabel } from '../customer-pick.js';

let templates = [];
let fields = {};
let docs = [];
let customers = [];
let activeTab = 'issued';

const fdate = (s) => (s ? String(s).slice(0, 16).replace('T', ' ') : '—');

async function loadCustomers() {
  if (customers.length) return customers;
  customers = await api('/api/customers');
  customers.sort((a, b) => String(a.name).localeCompare(String(b.name)));
  return customers;
}

async function loadTemplates() {
  const d = await api('/api/document-templates');
  templates = d.templates;
  fields = d.fields;
}

// ------------------------------------------------------------ issued list
function renderDocs() {
  const q = ($('doc-q')?.value || '').trim().toLowerCase();
  const vis = $('doc-f-vis')?.value || '';
  const rows = docs.filter((d) => {
    if (vis === 'revoked' && !d.revoked_at) return false;
    if ((vis === '1' || vis === '0') && (d.revoked_at || String(d.visible_to_customer) !== vis)) return false;
    if (!q) return true;
    return [d.doc_no, d.title, d.customer_name, d.unit_no, d.project_name, d.booking_no]
      .some((v) => String(v || '').toLowerCase().includes(q));
  });
  const tb = $('doc-tbody');
  if (!rows.length) {
    tb.innerHTML = `<tr><td colspan="6"><div class="empty">${icon('documents', 28)}<b>No documents yet</b>Generate a payment plan, statement or letter for a customer.</div></td></tr>`;
    return;
  }
  tb.innerHTML = rows.map((d) => `
    <tr>
      <td><div class="td-b">${esc(d.title)}</div><div class="cust-sub">${esc(d.doc_no)}${d.revoked_at ? ' · <span style="color:var(--danger)">Revoked</span>' : ''}</div></td>
      <td><div class="td-b">${esc(d.customer_name)}</div></td>
      <td>${d.unit_no ? `<div>${esc(d.unit_no)}</div><div class="cust-sub">${esc(d.project_name || '')}</div>` : '—'}</td>
      <td><div>${esc(fdate(d.created_at))}</div><div class="cust-sub">${esc(d.created_by_name || '')}</div></td>
      <td>${d.revoked_at ? '<span class="badge bg-grey">Revoked</span>'
        : `<label class="check-row" style="margin:0"><input type="checkbox" data-vis="${d.id}" ${d.visible_to_customer ? 'checked' : ''}> ${d.visible_to_customer ? 'Visible' : 'Hidden'}</label>`}</td>
      <td>
        <a class="btn sm" href="/documents/${d.id}" target="_blank" rel="noopener">Open</a>
        ${d.revoked_at ? '' : `<button type="button" class="btn sm danger" data-revoke="${d.id}">Revoke</button>`}
      </td>
    </tr>`).join('');
  tb.querySelectorAll('[data-vis]').forEach((cb) => cb.addEventListener('change', async () => {
    try {
      await api(`/api/customer-documents/${cb.dataset.vis}`, { method: 'PATCH', body: JSON.stringify({ visible_to_customer: cb.checked }) });
      toast(cb.checked ? 'Now visible in the customer portal' : 'Hidden from the customer portal');
      await loadDocs();
    } catch { cb.checked = !cb.checked; }
  }));
  tb.querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => {
    const ok = await askConfirm('Revoke this document? The customer will no longer be able to open it, and staff copies will be marked as revoked.', { title: 'Revoke document', confirmLabel: 'Revoke', danger: true });
    if (!ok) return;
    await api(`/api/customer-documents/${b.dataset.revoke}`, { method: 'PATCH', body: JSON.stringify({ revoke: true }) });
    toast('Document revoked');
    loadDocs();
  }));
}

async function loadDocs() {
  docs = await api('/api/customer-documents');
  renderDocs();
}

// ------------------------------------------------------------ templates tab
function renderTemplates() {
  const grid = $('tmpl-grid');
  grid.innerHTML = templates.map((t) => `
    <div class="tmpl-card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div class="tmpl-ico">${icon('documents', 18)}</div>
        <span class="badge ${t.is_active ? 'bg-green' : 'bg-grey'}">${t.is_active ? 'Active' : 'Inactive'}</span>
      </div>
      <h3>${esc(t.name)}</h3>
      <p>${esc(t.description || '')}</p>
      <div class="cust-sub">${esc(t.kind)} · ${t.requires_booking ? 'needs a booking' : 'customer only'}</div>
      <div class="row-actions">
        <button type="button" class="btn sm" data-edit-tmpl="${t.id}">Edit</button>
        <button type="button" class="btn sm" data-copy-tmpl="${t.id}">Duplicate</button>
        ${t.is_active ? `<button type="button" class="btn sm primary" data-use-tmpl="${t.id}">Use</button>` : ''}
      </div>
    </div>`).join('');
  grid.querySelectorAll('[data-edit-tmpl]').forEach((b) => b.addEventListener('click', () => openTemplate(+b.dataset.editTmpl)));
  grid.querySelectorAll('[data-copy-tmpl]').forEach((b) => b.addEventListener('click', () => openTemplate(+b.dataset.copyTmpl, true)));
  grid.querySelectorAll('[data-use-tmpl]').forEach((b) => b.addEventListener('click', () => openGenerate({ templateId: +b.dataset.useTmpl })));
}

function renderFieldList() {
  const q = ($('tm-field-q').value || '').toLowerCase();
  $('tm-fields').innerHTML = Object.entries(fields)
    .filter(([k, v]) => !q || k.includes(q) || v.toLowerCase().includes(q))
    .map(([k, v]) => `<button type="button" data-field="${esc(k)}"><code>{{${esc(k)}}}</code><span>${esc(v)}</span></button>`).join('');
  $('tm-fields').querySelectorAll('[data-field]').forEach((b) => b.addEventListener('click', () => {
    const ta = $('tm-body');
    const ins = `{{${b.dataset.field}}}`;
    const { selectionStart: s, selectionEnd: e } = ta;
    ta.setRangeText(ins, s, e, 'end');
    ta.focus();
  }));
}

async function fillCustomerSelect(sel, placeholder) {
  const list = await loadCustomers();
  sel.innerHTML = `<option value="">${esc(placeholder)}</option>` + list.map((c) =>
    `<option value="${c.id}">${esc(customerOptionLabel(c))}</option>`).join('');
}

async function openTemplate(id, duplicate = false) {
  const t = id ? await api(`/api/document-templates/${id}`) : null;
  $('tmpl-modal-title').textContent = t ? (duplicate ? 'Duplicate template' : 'Edit template') : 'New template';
  $('tm-id').value = t && !duplicate ? t.id : '';
  $('tm-name').value = t ? (duplicate ? `${t.name} (copy)` : t.name) : '';
  $('tm-kind').value = t?.kind || 'general';
  $('tm-active').value = t && !t.is_active ? '0' : '1';
  $('tm-desc').value = t?.description || '';
  $('tm-booking').checked = t ? !!t.requires_booking : true;
  $('tm-body').value = t?.body_html || '<h1>{{doc.title}}</h1>\n<p>Dear {{customer.name}},</p>\n<p></p>\n';
  $('tm-field-q').value = '';
  renderFieldList();
  await fillCustomerSelect($('tm-preview-cust'), 'Preview as…');
  const withBooking = customers.find((c) => (c.units || c.unit_nos || []).length) || customers[0];
  if (withBooking) $('tm-preview-cust').value = withBooking.id;
  openModal('tmpl-modal');
}

function showPreview(html) {
  const frame = $('doc-preview-frame');
  frame.srcdoc = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${PREVIEW_CSS}</style></head><body><article class="page">${html}</article></body></html>`;
  openModal('doc-preview-modal');
}

let PREVIEW_CSS = '';
async function ensurePreviewCss() {
  if (PREVIEW_CSS) return;
  // Compact copy of the document page styles (the preview iframe is sandboxed, so styles are inlined).
  PREVIEW_CSS = 'body{margin:0;background:#EEF2F7;font:14px/1.55 Inter,system-ui,sans-serif;color:#0B1B2E}.page{max-width:820px;margin:20px auto;background:#fff;padding:40px 48px;border-radius:6px}.doc-head{display:flex;justify-content:space-between;border-bottom:3px solid #061A2C;padding-bottom:14px;margin-bottom:22px}.doc-brand{font-size:22px;font-weight:800}.doc-sub,.doc-meta,.doc-muted{font-size:12px;color:#5B6B82}.doc-meta{text-align:right}h1{font-size:20px;margin:0 0 14px}h2{font-size:15px;margin:22px 0 8px}p{margin:0 0 10px}.doc-table{width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:12.5px}.doc-table th{background:#F1F5F9;padding:7px 9px;border-bottom:2px solid #CBD5E1;font-size:11px;text-transform:uppercase;color:#475569}.doc-table td{padding:7px 9px;border-bottom:1px solid #E2E8F0}.doc-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;margin:6px 0 16px;font-size:13px}.doc-grid span{color:#5B6B82}.doc-box{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:12px 14px;margin:10px 0}.doc-sign{display:flex;justify-content:space-between;margin-top:48px;font-size:12px}.doc-sign div{border-top:1px solid #94A3B8;padding-top:6px;width:200px;text-align:center}.doc-foot{margin-top:28px;padding-top:10px;border-top:1px solid #E2E8F0;font-size:11px;color:#64748B}';
}

async function firstBookingId(customerId) {
  const p = await api(`/api/portal?customer_id=${customerId}`);
  return p.bookings?.[0]?.id ?? null;
}

async function previewTemplate() {
  const cid = +$('tm-preview-cust').value;
  if (!cid) { toast('Choose a customer to preview with', 'error'); return; }
  const bid = $('tm-booking').checked ? await firstBookingId(cid) : null;
  if ($('tm-booking').checked && !bid) { toast('That customer has no active booking — pick another', 'error'); return; }
  await ensurePreviewCss();
  const d = await api('/api/document-templates/preview', {
    method: 'POST',
    body: JSON.stringify({ body_html: $('tm-body').value, customer_id: cid, booking_id: bid }),
  });
  showPreview(d.html);
}

async function saveTemplate() {
  const id = $('tm-id').value;
  const body = {
    name: $('tm-name').value.trim(),
    kind: $('tm-kind').value,
    description: $('tm-desc').value.trim() || null,
    body_html: $('tm-body').value,
    requires_booking: $('tm-booking').checked,
    is_active: $('tm-active').value === '1',
  };
  if (!body.name) { toast('Template name is required', 'error'); return; }
  await api(id ? `/api/document-templates/${id}` : '/api/document-templates', {
    method: id ? 'PUT' : 'POST', body: JSON.stringify(body),
  });
  toast('Template saved');
  closeModal('tmpl-modal');
  await loadTemplates();
  renderTemplates();
}

// ------------------------------------------------------------ generate
async function loadBookingsFor(cid, preselect) {
  const sel = $('gd-booking');
  if (!cid) { sel.innerHTML = '<option value="">— Select customer first —</option>'; return; }
  sel.innerHTML = '<option value="">Loading…</option>';
  const p = await api(`/api/portal?customer_id=${cid}`);
  const list = p.bookings || [];
  sel.innerHTML = list.length
    ? list.map((b) => `<option value="${b.id}">${esc(b.booking_no)} · ${esc(b.unit_no)} · ${esc(b.project_name)}</option>`).join('')
      + '<option value="">No booking (customer-level document)</option>'
    : '<option value="">No active bookings</option>';
  if (preselect) sel.value = String(preselect);
}

function syncTemplateHint() {
  const t = templates.find((x) => x.id === +$('gd-template').value);
  $('gd-tmpl-desc').textContent = t ? `${t.description || ''}${t.requires_booking ? ' Requires a booking.' : ''}` : '';
}

export async function openGenerate({ customerId = null, bookingId = null, templateId = null, kind = null } = {}) {
  if (!templates.length) await loadTemplates();
  await fillCustomerSelect($('gd-customer'), '— Select customer —');
  $('gd-template').innerHTML = templates.filter((t) => t.is_active)
    .map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
  if (!templateId && kind) {
    const match = templates.find((t) => t.is_active && (t.kind === kind || t.code === kind));
    if (match) templateId = match.id;
  }
  if (templateId) $('gd-template').value = String(templateId);
  $('gd-customer').value = customerId ? String(customerId) : '';
  $('gd-title').value = '';
  $('gd-visible').checked = true;
  syncTemplateHint();
  await loadBookingsFor(customerId, bookingId);
  openModal('gen-doc-modal');
}

function genPayload() {
  return {
    template_id: +$('gd-template').value,
    customer_id: +$('gd-customer').value,
    booking_id: $('gd-booking').value ? +$('gd-booking').value : null,
    title: $('gd-title').value.trim() || null,
    visible_to_customer: $('gd-visible').checked,
  };
}

async function previewGenerate() {
  const p = genPayload();
  if (!p.customer_id || !p.template_id) { toast('Choose a customer and template', 'error'); return; }
  await ensurePreviewCss();
  const d = await api('/api/document-templates/preview', {
    method: 'POST', body: JSON.stringify({ template_id: p.template_id, customer_id: p.customer_id, booking_id: p.booking_id }),
  });
  showPreview(d.html);
}

async function saveGenerate() {
  const p = genPayload();
  if (!p.customer_id || !p.template_id) { toast('Choose a customer and template', 'error'); return; }
  const btn = $('btn-gd-save');
  btn.disabled = true;
  try {
    const doc = await api('/api/customer-documents', { method: 'POST', body: JSON.stringify(p) });
    closeModal('gen-doc-modal');
    toast(`${doc.doc_no} created${p.visible_to_customer ? ' — visible in the customer portal' : ''}`);
    window.open(`/documents/${doc.id}`, '_blank', 'noopener');
    if (activeTab === 'issued') loadDocs();
  } finally {
    btn.disabled = false;
  }
}

const COMPANY_KEYS = { 'co-name': 'company_name', 'co-address': 'company_address', 'co-phone': 'company_phone', 'co-email': 'company_email' };

async function loadCompany() {
  const st = await api('/api/settings');
  Object.entries(COMPANY_KEYS).forEach(([id, key]) => { $(id).value = st[key] || ''; });
}

async function saveCompany() {
  if (!$('co-name').value.trim()) { toast('Company name is required', 'error'); return; }
  for (const [id, key] of Object.entries(COMPANY_KEYS)) {
    await api(`/api/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value: $(id).value.trim() }) });
  }
  toast('Company details saved — new documents will use them');
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('[data-dtab]').forEach((b) => b.classList.toggle('active', b.dataset.dtab === tab));
  $('dtab-issued').hidden = tab !== 'issued';
  $('dtab-templates').hidden = tab !== 'templates';
  if (tab === 'issued') loadDocs(); else { loadTemplates().then(renderTemplates); loadCompany(); }
}

export function loadDocuments() {
  switchTab(activeTab);
}

export function initDocumentEvents() {
  document.querySelectorAll('[data-dtab]').forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.dtab)));
  $('doc-q')?.addEventListener('input', renderDocs);
  $('doc-f-vis')?.addEventListener('change', renderDocs);
  $('btn-gen-doc')?.addEventListener('click', () => openGenerate());
  $('btn-save-company')?.addEventListener('click', saveCompany);
  $('btn-new-tmpl')?.addEventListener('click', () => openTemplate(null));
  $('tm-field-q')?.addEventListener('input', renderFieldList);
  $('btn-tm-preview')?.addEventListener('click', previewTemplate);
  $('btn-tm-save')?.addEventListener('click', saveTemplate);
  $('gd-customer')?.addEventListener('change', () => loadBookingsFor(+$('gd-customer').value || null));
  $('gd-template')?.addEventListener('change', syncTemplateHint);
  $('btn-gd-preview')?.addEventListener('click', previewGenerate);
  $('btn-gd-save')?.addEventListener('click', saveGenerate);
}
