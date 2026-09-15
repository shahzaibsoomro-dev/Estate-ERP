import { icon } from './icons.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((el) => {
    el.innerHTML = icon(el.dataset.icon, Number(el.dataset.size) || 20);
  });
}

function priceShort(n) {
  if (!n) return '—';
  if (n >= 10000000) return `PKR ${(n / 10000000).toFixed(1)} Cr`;
  if (n >= 100000) return `PKR ${(n / 100000).toFixed(0)} Lac`;
  return `PKR ${Number(n).toLocaleString('en-PK')}`;
}

const STATUS = {
  under_construction: ['Under construction', 'b-blue'],
  planning: ['Launching soon', 'b-amber'],
  completed: ['Ready to move', 'b-green'],
};

const PALETTES = [['#0B2A47', '#2563EB'], ['#062E2A', '#059669'], ['#2A1B47', '#7C3AED'], ['#3A240A', '#D97706']];

/** Generic skyline illustration, varied per project. */
function art(seed, floors) {
  const [bg, fg] = PALETTES[seed % PALETTES.length];
  let x = 20;
  let bars = '';
  let i = 0;
  while (x < 380) {
    const w = 34 + ((seed * 7 + i * 13) % 30);
    const h = 40 + ((seed * 11 + i * 17) % 70) + (i === 2 ? Math.min(floors || 0, 20) * 3 : 0);
    const op = i === 2 ? 1 : 0.55;
    bars += `<rect x="${x}" y="${150 - h}" width="${w}" height="${h}" rx="3" fill="${fg}" opacity="${op}"/>`;
    for (let wy = 150 - h + 10; wy < 140; wy += 14) {
      for (let wx = x + 7; wx < x + w - 8; wx += 10) {
        bars += `<rect x="${wx}" y="${wy}" width="4" height="6" fill="#fff" opacity="${(wx + wy + seed) % 3 ? 0.25 : 0.6}"/>`;
      }
    }
    x += w + 8;
    i += 1;
  }
  return `<svg viewBox="0 0 400 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs><linearGradient id="g${seed}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${bg}"/><stop offset="1" stop-color="${fg}" stop-opacity=".35"/></linearGradient></defs>
    <rect width="400" height="150" fill="url(#g${seed})"/>
    <circle cx="330" cy="36" r="16" fill="#fff" opacity=".18"/>${bars}</svg>`;
}

let allProjects = [];
let filter = 'all';

function renderProjects() {
  const grid = document.getElementById('proj-grid');
  const list = allProjects.filter((p) => filter === 'all' || p.city === filter);
  if (!list.length) {
    grid.innerHTML = '<p class="hint">No projects to show right now.</p>';
    return;
  }
  grid.innerHTML = list.map((p) => {
    const [label, cls] = STATUS[p.status] || [p.status || 'Project', 'b-grey'];
    const progress = Math.max(0, Math.min(100, p.current_progress || 0));
    return `<article class="proj">
      <div class="proj-art">${art(p.id, p.number_of_floors)}<span class="badge ${cls}">${esc(label)}</span></div>
      <div class="proj-body">
        <h3>${esc(p.name)}</h3>
        <div class="proj-loc">${icon('pin', 15)} ${esc([p.area, p.city].filter(Boolean).join(', ') || p.location)}</div>
        <div class="proj-meta">
          <div><b>${p.available_units}</b><span>of ${p.total_units} available</span></div>
          <div><b>${p.price_from ? priceShort(p.price_from) : '—'}</b><span>${p.price_from ? 'Starting from' : 'Price on request'}</span></div>
        </div>
        <div>
          <div class="prog-lbl"><span>Construction</span><span>${progress}%</span></div>
          <div class="prog"><span style="width:${progress}%"></span></div>
        </div>
        <div class="chips">${[...p.unit_types, ...p.attributes].slice(0, 6).map((a) => `<span class="chip">${esc(a)}</span>`).join('')}</div>
      </div>
    </article>`;
  }).join('');
}

function renderFilters() {
  const cities = [...new Set(allProjects.map((p) => p.city).filter(Boolean))];
  const box = document.getElementById('proj-filters');
  if (cities.length < 2) { box.hidden = true; return; }
  box.innerHTML = ['all', ...cities].map((c) =>
    `<button type="button" class="pill ${c === filter ? 'on' : ''}" data-city="${esc(c)}">${c === 'all' ? 'All cities' : esc(c)}</button>`).join('');
  box.querySelectorAll('[data-city]').forEach((b) => b.addEventListener('click', () => {
    filter = b.dataset.city;
    renderFilters();
    renderProjects();
  }));
}

async function load() {
  try {
    const slug = (location.pathname.match(/^\/c\/([\w-]+)/) || [])[1];
    const r = await fetch(`/api/public/overview${slug ? `?company=${encodeURIComponent(slug)}` : ''}`);
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    allProjects = d.projects || [];
    document.getElementById('st-projects').textContent = d.stats.projects;
    document.getElementById('st-units').textContent = d.stats.units.toLocaleString('en-PK');
    document.getElementById('st-cities').textContent = d.stats.cities;
    const building = [...new Set(allProjects.filter((p) => p.status !== 'completed').map((p) => p.city).filter(Boolean))];
    if (building.length) document.getElementById('hero-cities').textContent = building.join(' & ');
    if (d.company?.name) document.querySelectorAll('[data-company]').forEach((el) => { el.textContent = d.company.name; });
    const phone = document.getElementById('cta-phone');
    if (d.company?.phone) {
      phone.href = `tel:${d.company.phone.replace(/[^\d+]/g, '')}`;
      phone.lastElementChild.textContent = d.company.phone;
    } else if (d.company?.email) {
      phone.href = `mailto:${d.company.email}`;
      phone.lastElementChild.textContent = d.company.email;
    }
    renderFilters();
    renderProjects();
  } catch {
    document.getElementById('proj-grid').innerHTML = '<p class="hint">Projects could not be loaded. Please refresh the page.</p>';
  }
}

async function adaptNavToSession() {
  try {
    const r = await fetch('/api/auth/session');
    const me = await r.json();
    if (!me.authenticated) return;
    const cta = document.querySelector('.nav-cta');
    const label = { customer: 'My portal', superadmin: 'Platform console' }[me.role] || 'Open ERP';
    cta.innerHTML = `<a class="btn btn-primary btn-sm" href="${esc(me.home)}">${label}</a>`;
  } catch { /* signed out */ }
}

hydrateIcons();
document.getElementById('year').textContent = new Date().getFullYear();
document.getElementById('nav-toggle').addEventListener('click', () => document.getElementById('site-nav').classList.toggle('open'));
document.querySelectorAll('.site-nav nav a').forEach((a) => a.addEventListener('click', () => document.getElementById('site-nav').classList.remove('open')));
load();
adaptNavToSession();
