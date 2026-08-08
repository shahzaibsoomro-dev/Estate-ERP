import { esc } from './dom.js';

/**
 * Native <select> dropdown + search box to filter options.
 */
export function mountSearchSelect(wrapEl, {
  placeholder = 'Search…',
  emptyText = 'No matches',
  selectLabel = '— Select —',
  items = [],
  onChange = () => {},
} = {}) {
  if (!wrapEl) {
    console.error('search-select: missing container');
    return dummy();
  }

  wrapEl.classList.add('ss');
  wrapEl.innerHTML = `
    <input type="search" class="ss-search" placeholder="${esc(placeholder)}" autocomplete="off">
    <select class="ss-select">
      <option value="">${esc(selectLabel)}</option>
    </select>`;

  const search = wrapEl.querySelector('.ss-search');
  const select = wrapEl.querySelector('.ss-select');
  let list = items || [];
  let selectedId = '';

  function matches(it, q) {
    if (!q) return true;
    return (it.search || `${it.label} ${it.sub || ''}`).toLowerCase().includes(q);
  }

  function render() {
    const q = search.value.trim().toLowerCase();
    const rows = list.filter((it) => matches(it, q));
    const keep = selectedId && list.some((it) => String(it.id) === String(selectedId));
    const opts = [`<option value="">${esc(selectLabel)}</option>`];
    if (!rows.length) {
      opts.push(`<option value="" disabled>${esc(emptyText)}</option>`);
    } else {
      rows.forEach((it) => {
        const text = it.sub ? `${it.label} — ${it.sub}` : it.label;
        opts.push(`<option value="${esc(String(it.id))}">${esc(text)}</option>`);
      });
    }
    select.innerHTML = opts.join('');
    if (keep && (!q || rows.some((it) => String(it.id) === String(selectedId)))) {
      select.value = String(selectedId);
    } else if (keep && q && !rows.some((it) => String(it.id) === String(selectedId))) {
      select.value = '';
    } else {
      select.value = keep ? String(selectedId) : '';
    }
  }

  function emit() {
    const id = select.value;
    selectedId = id;
    const item = list.find((it) => String(it.id) === String(id)) || null;
    onChange(item);
  }

  search.addEventListener('input', render);
  select.addEventListener('change', emit);

  render();

  return {
    setItems(next) {
      list = next || [];
      if (selectedId && !list.some((it) => String(it.id) === String(selectedId))) {
        selectedId = '';
        select.value = '';
        onChange(null);
      }
      render();
    },
    setValue(id) {
      selectedId = id != null && id !== '' ? String(id) : '';
      search.value = '';
      render();
      select.value = selectedId;
      const item = list.find((it) => String(it.id) === selectedId) || null;
      onChange(item);
    },
    getValue() {
      return list.find((it) => String(it.id) === String(selectedId)) || null;
    },
    clear() {
      selectedId = '';
      search.value = '';
      render();
      onChange(null);
    },
  };
}

function dummy() {
  return {
    setItems() {},
    setValue() {},
    getValue() { return null; },
    clear() {},
  };
}
