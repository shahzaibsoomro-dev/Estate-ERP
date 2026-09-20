/** Activity Log — readable trail of who changed what across the company. */
import { $, esc, loadingHtml } from '../dom.js';
import { api } from '../api.js';
import { fmt } from '../format.js';

let wired = false;
let lastMeta = { entities: [], modules: [] };

function fmtWhen(iso) {
  if (!iso) return '—';
  const s = String(iso).replace('T', ' ').slice(0, 16);
  const d = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T') + 'Z');
  if (Number.isNaN(d.getTime())) return esc(s);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  if (sameDay) return `Today · ${time}`;
  const yday = new Date(today);
  yday.setDate(today.getDate() - 1);
  if (d.toDateString() === yday.toDateString()) return `Yesterday · ${time}`;
  return esc(d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) + ' · ' + time);
}

function moduleBadge(mod) {
  const tone = {
    Sales: 'bg-blue', Inventory: 'bg-blue', Procurement: 'bg-orange',
    Planning: 'bg-purple', Construction: 'bg-yellow', Investment: 'bg-green',
    Stakeholders: 'bg-grey', Documents: 'bg-grey', Projects: 'bg-blue',
  }[mod] || 'bg-grey';
  return `<span class="badge ${tone}">${esc(mod || 'Other')}</span>`;
}

function roleLabel(role) {
  if (!role) return '';
  const map = { admin: 'Admin', employee: 'Staff', superadmin: 'Support' };
  return map[role] || role;
}

function factsHtml(facts) {
  if (!facts?.length) {
    return '<div class="act-facts-empty">No extra facts recorded for this event.</div>';
  }
  return `<div class="act-facts">${facts.map((f) => `
    <div class="act-fact"><span class="act-fact-k">${esc(f.label)}</span>
      <span class="act-fact-v">${esc(f.value)}</span></div>`).join('')}</div>`;
}

function paintStats(rows) {
  const host = $('act-stats');
  if (!host) return;
  const today = new Date().toISOString().slice(0, 10);
  const todayN = rows.filter((r) => String(r.when || '').startsWith(today)).length;
  const money = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const people = new Set(rows.map((r) => r.actor_name).filter(Boolean)).size;
  host.innerHTML = `
    <div class="sm"><div class="sm-v">${rows.length}</div><div class="sm-l">Shown</div></div>
    <div class="sm"><div class="sm-v">${todayN}</div><div class="sm-l">Today</div></div>
    <div class="sm"><div class="sm-v">${people}</div><div class="sm-l">People</div></div>
    <div class="sm"><div class="sm-v" style="font-size:15px">${money ? esc(fmt(money)) : '—'}</div><div class="sm-l">Amounts in view</div></div>`;
}

function fillFilters(meta) {
  lastMeta = meta || lastMeta;
  const mod = $('act-module');
  const ent = $('act-entity');
  if (mod && !mod.dataset.ready) {
    (lastMeta.modules || []).forEach((m) => {
      const o = document.createElement('option');
      o.value = m;
      o.textContent = m;
      mod.appendChild(o);
    });
    mod.dataset.ready = '1';
  }
  if (ent) {
    const cur = ent.value;
    ent.innerHTML = '<option value="">All types</option>';
    (lastMeta.entities || []).forEach((e) => {
      const o = document.createElement('option');
      o.value = e;
      o.textContent = e.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      ent.appendChild(o);
    });
    if (cur) ent.value = cur;
  }
}

function queryString() {
  const p = new URLSearchParams({ limit: '200' });
  const q = $('act-q')?.value?.trim();
  const module = $('act-module')?.value;
  const entity = $('act-entity')?.value;
  const from = $('act-from')?.value;
  const to = $('act-to')?.value;
  if (q) p.set('q', q);
  if (module) p.set('module', module);
  if (entity) p.set('entity', entity);
  if (from) p.set('date_from', from);
  if (to) p.set('date_to', to);
  return p.toString();
}

function rowHtml(r) {
  const facts = factsHtml(r.facts);
  const who = r.actor_name || 'System';
  const role = roleLabel(r.actor_role);
  return `
    <tr class="act-row" data-id="${r.id}" tabindex="0">
      <td class="act-exp"><button type="button" class="act-toggle" aria-label="Show facts">▸</button></td>
      <td class="td-sm act-when">${fmtWhen(r.when)}</td>
      <td>
        <div class="act-who">${esc(who)}</div>
        ${role ? `<div class="td-sm">${esc(role)}${r.ip ? ` · ${esc(r.ip)}` : ''}</div>` : (r.ip ? `<div class="td-sm">${esc(r.ip)}</div>` : '')}
      </td>
      <td>
        <div class="act-summary">${esc(r.summary || '—')}</div>
        <div class="td-sm">${esc(r.entity_label || r.entity_type || '')} · ${esc(r.action_label || r.action || '')}</div>
      </td>
      <td>${moduleBadge(r.module)}</td>
      <td class="td-sm">${esc(r.project_name || '—')}</td>
      <td class="td-sm" style="font-variant-numeric:tabular-nums">${r.amount != null ? esc(fmt(r.amount)) : '—'}</td>
      <td class="td-sm">${esc(r.ref || '—')}</td>
    </tr>
    <tr class="act-detail" data-for="${r.id}" hidden>
      <td colspan="8">${facts}</td>
    </tr>`;
}

function toggleRow(id) {
  const detail = document.querySelector(`.act-detail[data-for="${id}"]`);
  const btn = document.querySelector(`.act-row[data-id="${id}"] .act-toggle`);
  if (!detail || !btn) return;
  const open = detail.hasAttribute('hidden');
  detail.toggleAttribute('hidden', !open);
  btn.textContent = open ? '▾' : '▸';
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

export async function loadActivity() {
  wireActivity();
  const tbody = $('audit-tbody');
  if (tbody) tbody.innerHTML = `<tr><td colspan="8">${loadingHtml('Loading activity…')}</td></tr>`;
  let data;
  try {
    data = await api(`/api/audit?${queryString()}`);
  } catch {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--g400);padding:20px">Could not load activity</td></tr>';
    }
    return;
  }
  const rows = Array.isArray(data) ? data : (data?.rows || []);
  fillFilters({ entities: data?.entities || [], modules: data?.modules || [] });
  paintStats(rows);
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map(rowHtml).join('')
    : '<tr><td colspan="8" style="text-align:center;color:var(--g400);padding:20px">No activity matches these filters</td></tr>';
}

function wireActivity() {
  if (wired) return;
  wired = true;
  let timer;
  const reload = () => loadActivity();
  const debounced = () => {
    clearTimeout(timer);
    timer = setTimeout(reload, 280);
  };
  $('act-q')?.addEventListener('input', debounced);
  $('act-module')?.addEventListener('change', reload);
  $('act-entity')?.addEventListener('change', reload);
  $('act-from')?.addEventListener('change', reload);
  $('act-to')?.addEventListener('change', reload);
  $('act-clear')?.addEventListener('click', () => {
    ['act-q', 'act-module', 'act-entity', 'act-from', 'act-to'].forEach((id) => {
      const el = $(id);
      if (el) el.value = '';
    });
    reload();
  });
  $('audit-tbody')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.act-toggle, .act-row');
    if (!btn) return;
    const row = e.target.closest('.act-row');
    if (!row) return;
    if (e.target.closest('a, button') && !e.target.closest('.act-toggle')) return;
    toggleRow(row.dataset.id);
  });
  $('audit-tbody')?.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const row = e.target.closest('.act-row');
    if (!row) return;
    e.preventDefault();
    toggleRow(row.dataset.id);
  });
}
