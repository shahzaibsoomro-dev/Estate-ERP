/** DOM helper */
export const $ = (id) => document.getElementById(id);

export function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function loadingHtml(msg = 'Loading…') {
  return `<div class="loading"><span class="spinner"></span>${msg}</div>`;
}
