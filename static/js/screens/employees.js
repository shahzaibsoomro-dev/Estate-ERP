import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { openModal, closeModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { session } from '../session.js';
import { initials, avatarColor } from './dashboard.js';
import { showTempPassword } from './access.js';

let catalogue = null;
let employees = [];
let projects = [];

const ACTIONS = ['view', 'add', 'edit', 'delete'];

const when = (s) => {
  if (!s) return '<span class="muted">Never</span>';
  const d = new Date(`${s.replace(' ', 'T')}Z`);
  return Number.isNaN(d.getTime()) ? esc(s)
    : esc(d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }));
};

async function ensureCatalogue() {
  if (!catalogue) catalogue = await api('/api/company/access-catalogue');
  projects = await api('/api/projects');
}

function accessSummary(u) {
  if (u.role === 'admin') return '<span class="badge bg-purple">Full access</span>';
  const mods = Object.entries(u.permissions || {});
  if (!mods.length) return '<span class="muted">No pages</span>';
  const writes = mods.filter(([, p]) => p.add || p.edit || p.delete).length;
  const labels = mods.slice(0, 3).map(([k]) => catalogue.modules.find((m) => m.key === k)?.label.split(' (')[0] || k);
  return `<div class="td-b">${mods.length} page${mods.length === 1 ? '' : 's'}${writes ? ` · ${writes} with changes` : ' · view only'}</div>
    <div class="cust-sub">${esc(labels.join(', '))}${mods.length > 3 ? '…' : ''}</div>`;
}

function projectSummary(u) {
  if (u.role === 'admin' || u.project_ids == null) return 'All projects';
  const names = u.project_ids.map((id) => projects.find((p) => p.id === id)?.name || `#${id}`);
  return `<div>${names.length} selected</div><div class="cust-sub">${esc(names.slice(0, 2).join(', '))}${names.length > 2 ? '…' : ''}</div>`;
}

function statusBadge(u) {
  if (!u.is_active) return '<span class="badge bg-red">Disabled</span>';
  if (u.locked) return '<span class="badge bg-orange">Locked out</span>';
  if (u.must_change_password) return '<span class="badge bg-yellow">Invite pending</span>';
  return '<span class="badge bg-green">Active</span>';
}

function render() {
  const staff = employees.filter((u) => u.role === 'employee');
  const active = staff.filter((u) => u.is_active);
  $('emp-stats').innerHTML = [
    ['Employees', active.length, 'var(--navy)'],
    ['Limited to some projects', active.filter((u) => u.project_ids != null).length, 'var(--blue)'],
    ['Invites pending', active.filter((u) => u.must_change_password).length, 'var(--warn)'],
    ['Company admins', employees.filter((u) => u.role === 'admin' && u.is_active).length, '#7C3AED'],
  ].map(([l, v, c]) => `<div class="sm" style="color:${c}"><div class="sm-v">${v}</div><div class="sm-l">${l}</div></div>`).join('');

  const me = session.user.id;
  $('emp-tbody').innerHTML = employees.map((u) => `
    <tr>
      <td><div class="cust-cell"><div class="av" style="background:${avatarColor(u.name)}">${esc(initials(u.name))}</div>
        <div><div class="td-b">${esc(u.name)}${u.id === me ? ' <span class="muted">(you)</span>' : ''}</div><div class="cust-sub">${esc(u.email)}</div></div></div></td>
      <td>${u.role === 'admin' ? '<span class="badge bg-purple">Admin</span>' : `<div>${esc(u.job_title || 'Employee')}</div>`}</td>
      <td class="wrap cell-md">${accessSummary(u)}</td>
      <td class="wrap cell-sm">${projectSummary(u)}</td>
      <td>${statusBadge(u)}</td>
      <td>${when(u.last_login_at)}</td>
      <td>${u.role === 'admin' ? '<span class="muted">Managed by platform</span>' : `
        <button type="button" class="btn sm primary" data-emp-edit="${u.id}">Edit access</button>
        ${u.locked ? `<button type="button" class="btn sm" data-emp-unlock="${u.id}">Unlock</button>` : ''}
        <button type="button" class="btn sm" data-emp-reset="${u.id}">Reset password</button>
        <button type="button" class="btn sm ${u.is_active ? 'danger' : ''}" data-emp-toggle="${u.id}">${u.is_active ? 'Disable' : 'Enable'}</button>`}
      </td>
    </tr>`).join('');

  const tb = $('emp-tbody');
  const find = (id) => employees.find((x) => x.id === +id);
  tb.querySelectorAll('[data-emp-edit]').forEach((b) => b.addEventListener('click', () => openEditor(find(b.dataset.empEdit))));
  tb.querySelectorAll('[data-emp-unlock]').forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/company/employees/${b.dataset.empUnlock}/unlock`, { method: 'POST' });
    toast('Unlocked — they can sign in again');
    loadEmployees();
  }));
  tb.querySelectorAll('[data-emp-reset]').forEach((b) => b.addEventListener('click', async () => {
    const u = find(b.dataset.empReset);
    if (!await askConfirm(`Reset the password for ${u.name}? They will be signed out everywhere.`, { title: 'Reset password', confirmLabel: 'Reset' })) return;
    const d = await api(`/api/company/employees/${u.id}/reset-password`, { method: 'POST' });
    showTempPassword({ name: u.name, password: d.temporary_password, phone: '', loginHint: `Sign in with ${u.email}` });
    loadEmployees();
  }));
  tb.querySelectorAll('[data-emp-toggle]').forEach((b) => b.addEventListener('click', async () => {
    const u = find(b.dataset.empToggle);
    if (u.is_active && !await askConfirm(`Disable ${u.name}? They will be signed out immediately.`, { title: 'Disable employee', confirmLabel: 'Disable', danger: true })) return;
    await api(`/api/company/employees/${u.id}/status`, { method: 'POST', body: JSON.stringify({ is_active: !u.is_active }) });
    toast(u.is_active ? 'Employee disabled' : 'Employee enabled');
    loadEmployees();
  }));
}

// ------------------------------------------------------------ editor
function scope() {
  return document.querySelector('input[name="emp-scope"]:checked')?.value || 'all';
}

function renderPermTable(perms) {
  const limited = scope() === 'some';
  let lastGroup = '';
  $('emp-perms').innerHTML = catalogue.modules.map((m) => {
    const group = m.group !== lastGroup ? `<tr class="perm-group"><td colspan="5">${esc(m.group)}</td></tr>` : '';
    lastGroup = m.group;
    const blocked = limited && m.needs_all_projects;
    const row = perms[m.key] || {};
    const cells = ACTIONS.map((a) => {
      if (!m.actions.includes(a)) return '<td class="perm-na">—</td>';
      return `<td><input type="checkbox" data-mod="${m.key}" data-act="${a}" ${row[a] && !blocked ? 'checked' : ''} ${blocked ? 'disabled' : ''} aria-label="${esc(m.label)}: ${a}"></td>`;
    }).join('');
    return `${group}<tr class="${blocked ? 'perm-blocked' : ''}"><td><div>${esc(m.label)}</div>${blocked ? '<div class="cust-sub">Company-wide — needs all projects</div>' : ''}</td>${cells}</tr>`;
  }).join('');
  $('emp-perms').querySelectorAll('input[type=checkbox]').forEach((cb) => cb.addEventListener('change', () => {
    const mod = cb.dataset.mod;
    const box = (act) => $('emp-perms').querySelector(`[data-mod="${mod}"][data-act="${act}"]`);
    if (cb.checked && cb.dataset.act !== 'view' && box('view')) box('view').checked = true;
    if (!cb.checked && cb.dataset.act === 'view') ACTIONS.forEach((a) => { if (box(a)) box(a).checked = false; });
  }));
}

function readPerms() {
  const out = {};
  $('emp-perms').querySelectorAll('input[type=checkbox]:checked').forEach((cb) => {
    out[cb.dataset.mod] = out[cb.dataset.mod] || {};
    out[cb.dataset.mod][cb.dataset.act] = true;
  });
  return out;
}

function renderProjectPicks(selected) {
  const box = $('emp-projects');
  box.innerHTML = projects.length ? projects.map((p) => `
    <label class="check-row proj-pick"><input type="checkbox" value="${p.id}" ${selected.includes(p.id) ? 'checked' : ''}>
      <span><b>${esc(p.name)}</b><span class="cust-sub">${esc(p.city || p.location || '')}</span></span></label>`).join('')
    : '<p class="muted">No projects yet.</p>';
  box.hidden = scope() !== 'some';
}

async function openEditor(u = null) {
  await ensureCatalogue();
  $('emp-modal-title').textContent = u ? `Edit access — ${u.name}` : 'Add employee';
  $('emp-id').value = u?.id || '';
  $('emp-name').value = u?.name || '';
  $('emp-email').value = u?.email || '';
  $('emp-email').disabled = !!u;
  $('emp-title').value = u?.job_title || '';
  $('emp-new-hint').hidden = !!u;
  const some = u && u.project_ids != null;
  document.querySelector(`input[name="emp-scope"][value="${some ? 'some' : 'all'}"]`).checked = true;
  renderProjectPicks(u?.project_ids || []);
  renderPermTable(u?.permissions || {});
  $('emp-presets').innerHTML = catalogue.presets.map((p) =>
    `<button type="button" class="btn sm" data-preset="${p.key}">${esc(p.label)}</button>`).join('');
  $('emp-presets').querySelectorAll('[data-preset]').forEach((b) => b.addEventListener('click', () => {
    const preset = catalogue.presets.find((p) => p.key === b.dataset.preset);
    renderPermTable(preset.permissions);
    if (!$('emp-title').value) $('emp-title').value = preset.label;
  }));
  openModal('emp-modal');
  setTimeout(() => (u ? $('emp-title') : $('emp-name')).focus(), 50);
}

async function save() {
  const id = $('emp-id').value;
  const body = {
    name: $('emp-name').value.trim(),
    email: $('emp-email').value.trim(),
    job_title: $('emp-title').value.trim() || null,
    permissions: readPerms(),
    all_projects: scope() === 'all',
    project_ids: [...$('emp-projects').querySelectorAll('input:checked')].map((c) => +c.value),
  };
  if (!body.name || (!id && !body.email)) { toast('Name and email are required', 'error'); return; }
  if (!body.all_projects && !body.project_ids.length) { toast('Select at least one project', 'error'); return; }
  if (!Object.keys(body.permissions).length
      && !await askConfirm('No pages are ticked, so this employee will not be able to see anything. Save anyway?', { title: 'No access selected', confirmLabel: 'Save anyway' })) return;
  const btn = $('btn-emp-save');
  btn.disabled = true;
  try {
    if (id) {
      await api(`/api/company/employees/${id}`, { method: 'PUT', body: JSON.stringify(body) });
      closeModal('emp-modal');
      toast('Access updated — takes effect immediately');
    } else {
      const d = await api('/api/company/employees', { method: 'POST', body: JSON.stringify(body) });
      closeModal('emp-modal');
      showTempPassword({ name: d.user.name, password: d.temporary_password, phone: '', loginHint: `Sign in with ${d.user.email}` });
    }
    loadEmployees();
  } finally {
    btn.disabled = false;
  }
}

export async function loadEmployees() {
  await ensureCatalogue();
  employees = await api('/api/company/employees');
  render();
}

export function initEmployeeEvents() {
  $('btn-new-emp')?.addEventListener('click', () => openEditor(null));
  $('btn-emp-save')?.addEventListener('click', save);
  document.querySelectorAll('input[name="emp-scope"]').forEach((r) => r.addEventListener('change', () => {
    $('emp-projects').hidden = scope() !== 'some';
    renderPermTable(readPerms());
  }));
}
