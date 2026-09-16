/** Signed-in user, company, permissions and CSRF token for the staff app. */
export const session = { user: null, csrf: '' };

function toLogin(reason) {
  const next = encodeURIComponent(location.pathname + location.hash);
  location.replace(`/login?${reason ? `reason=${reason}&` : ''}next=${next}`);
}

export async function loadSession() {
  const r = await fetch('/api/auth/me', { credentials: 'same-origin' });
  if (r.status === 401) { toLogin(); return null; }
  if (!r.ok) throw new Error(`Session check failed (${r.status})`);
  const me = await r.json();
  if (me.must_change_password) { location.replace('/account/password'); return null; }
  if (me.home !== '/app') { location.replace(me.home); return null; }
  session.user = me;
  session.csrf = me.csrf_token;
  return me;
}

export function handleAuthFailure(status, detail) {
  if (status === 401) { toLogin('expired'); return true; }
  if (status === 403 && detail === 'password_change_required') { location.replace('/account/password'); return true; }
  if (status === 403 && detail === 'company_suspended') { toLogin('suspended'); return true; }
  return false;
}

export function friendlyError(status, detail, action) {
  if (detail === 'permission_denied') {
    const verb = { view: 'view', add: 'add', edit: 'change', delete: 'delete' }[action] || 'do';
    return `You don't have permission to ${verb} this. Ask your admin for access.`;
  }
  if (status === 402 || detail === 'subscription_expired') {
    return 'Your subscription has expired — the system is read-only until it is renewed.';
  }
  return null;
}

export async function logout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf } });
  } finally {
    location.replace('/login?reason=signedout');
  }
}

export async function exitSupport() {
  await fetch('/api/auth/exit-support', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf } });
  location.replace('/console');
}

export const role = () => session.user?.role;
export const isAdmin = () => role() === 'admin' || (role() === 'superadmin' && session.user?.support_mode);
export const isEmployee = () => role() === 'employee';

/** Can the current user do `action` on `module`? Admins can do everything. */
export function can(module, action = 'view') {
  if (isAdmin()) return true;
  if (!module) return false;
  return !!session.user?.permissions?.[module]?.[action];
}

export function readOnly() {
  return !!session.user?.subscription?.read_only && !session.user?.support_mode;
}
