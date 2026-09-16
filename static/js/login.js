import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);
let csrf = '';
let me = null;

document.querySelectorAll('[data-icon]').forEach((el) => { el.innerHTML = icon(el.dataset.icon, 18); });

/** Only allow same-site relative redirects (prevents open-redirects via ?next=). */
function safeNext(fallback) {
  const next = new URLSearchParams(location.search).get('next') || '';
  if (/^\/(?!\/)[\w\-./#?=&%]*$/.test(next) && !next.startsWith('/login') && !next.startsWith('/api/')) return next;
  return fallback;
}

function destination(user) {
  const next = safeNext(user.home);
  const area = next.startsWith('/app') ? '/app' : next.startsWith('/portal') ? '/portal'
    : next.startsWith('/console') ? '/console' : null;
  // Only follow ?next= into the area this account actually lands in.
  if (area && area !== user.home) return user.home;
  return next;
}

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = !msg;
}

function busy(btn, on, label) {
  btn.disabled = on;
  if (label) btn.textContent = label;
}

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: JSON.stringify(body),
  });
  let data = {};
  try { data = await r.json(); } catch { /* empty */ }
  if (!r.ok) {
    const d = data.detail;
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? 'Please check the form and try again.' : 'Something went wrong. Please try again.';
    throw Object.assign(new Error(msg), { status: r.status });
  }
  return data;
}

// ---- password visibility + caps lock
document.querySelectorAll('[data-toggle]').forEach((b) => {
  b.addEventListener('click', () => {
    const input = $(b.dataset.toggle);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    b.innerHTML = icon(show ? 'eyeoff' : 'eye', 18);
    b.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  });
});
$('password').addEventListener('keyup', (e) => { $('caps').hidden = !e.getModifierState?.('CapsLock'); });

// ---- sign in
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  showError($('login-error'), '');
  const identifier = $('identifier').value.trim();
  const password = $('password').value;
  if (!identifier || !password) {
    showError($('login-error'), 'Enter your email (or CNIC) and password.');
    return;
  }
  busy($('login-btn'), true, 'Signing in…');
  try {
    me = await post('/api/auth/login', { identifier, password });
    csrf = me.csrf_token;
    if (me.must_change_password) {
      showPasswordForm(password);
    } else {
      location.replace(destination(me));
    }
  } catch (err) {
    showError($('login-error'), err.message);
    $('password').select();
  } finally {
    busy($('login-btn'), false, 'Sign in');
  }
});

// ---- change password
function strength(pw) {
  let s = 0;
  if (pw.length >= 10) s += 1;
  if (pw.length >= 14) s += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s += 1;
  if (/\d/.test(pw)) s += 1;
  if (/[^A-Za-z0-9]/.test(pw)) s += 1;
  return s;
}

function updateRules() {
  const pw = $('new-password').value;
  const rules = {
    len: pw.length >= 10,
    mix: /[A-Za-z]/.test(pw) && /\d/.test(pw),
    diff: pw.length > 0 && pw !== $('current').value,
  };
  document.querySelectorAll('#rules li').forEach((li) => li.classList.toggle('ok', rules[li.dataset.rule]));
  const s = strength(pw);
  const m = $('meter');
  m.style.width = `${(s / 5) * 100}%`;
  m.style.background = s <= 2 ? 'var(--red)' : s === 3 ? 'var(--amber)' : 'var(--green)';
  return Object.values(rules).every(Boolean);
}
['new-password', 'current'].forEach((id) => $(id).addEventListener('input', updateRules));

function showPasswordForm(prefill) {
  $('login-form').hidden = true;
  $('pw-form').hidden = false;
  $('pw-username').value = me?.email || '';
  if (prefill) $('current').value = prefill;
  $('pw-sub').textContent = me?.must_change_password
    ? 'You signed in with a temporary password. Choose your own password to continue.'
    : 'Choose a new password for your account.';
  ($('current').value ? $('new-password') : $('current')).focus();
}

$('pw-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  showError($('pw-error'), '');
  if (!updateRules()) {
    showError($('pw-error'), 'Your new password does not meet the requirements yet.');
    return;
  }
  if ($('new-password').value !== $('confirm').value) {
    showError($('pw-error'), 'The two new passwords do not match.');
    return;
  }
  busy($('pw-btn'), true, 'Saving…');
  try {
    me = await post('/api/auth/change-password', {
      current_password: $('current').value,
      new_password: $('new-password').value,
    });
    location.replace(destination(me));
  } catch (err) {
    showError($('pw-error'), err.status === 401 ? 'Your session expired. Please sign in again.' : err.message);
    if (err.status === 401) setTimeout(() => location.replace('/login'), 1500);
  } finally {
    busy($('pw-btn'), false, 'Save and continue');
  }
});

$('pw-cancel').addEventListener('click', async (e) => {
  e.preventDefault();
  try { await post('/api/auth/logout', {}); } catch { /* ignore */ }
  location.replace('/login');
});

// ---- initial state
(async () => {
  try {
    const st = await (await fetch('/api/setup/status')).json();
    if (st.needed) { location.replace('/setup'); return; }
  } catch { /* ignore */ }
  const params = new URLSearchParams(location.search);
  if (params.get('reason') === 'expired') {
    $('login-note').textContent = 'Your session ended. Please sign in again.';
    $('login-note').hidden = false;
  } else if (params.get('reason') === 'suspended') {
    $('login-note').textContent = "Your company's account is suspended. Please contact platform support.";
    $('login-note').hidden = false;
  } else if (params.get('reason') === 'signedout') {
    $('login-note').textContent = 'You have been signed out.';
    $('login-note').hidden = false;
  }
  try {
    const r = await fetch('/api/auth/session');
    const probe = await r.json();
    if (!probe.authenticated) {
      if (location.pathname === '/account/password') location.replace('/login');
      return;
    }
    me = probe;
    csrf = me.csrf_token;
    if (location.pathname === '/account/password' || me.must_change_password) {
      showPasswordForm('');
    } else {
      location.replace(destination(me));
    }
  } catch { /* stay on sign-in */ }
})();
