/** Landing page: live KPI strip plus a one-click demo token for the explorer. */

import { apiGet, currentToken, login, renderKpis, setState } from './api.js';

async function loadKpis() {
  try {
    setState('checking', 'Checking API…');
    renderKpis(await apiGet('/api/v1/analytics/summary'));
    setState('ok', 'API online');
  } catch (error) {
    setState('error', 'API unavailable');
    const out = document.getElementById('token-out');
    out.textContent = error.message;
    out.hidden = false;
  }
}

async function showCredentials() {
  try {
    const response = await fetch('/demo-credentials');
    if (!response.ok) return;
    const creds = await response.json();
    document.getElementById('cred-user').textContent = creds.username;
    document.getElementById('cred-pass').textContent = creds.password;
  } catch {
    /* Demo mode is off; the documented defaults in the markup still apply. */
  }
}

async function mintToken() {
  const out = document.getElementById('token-out');
  const copyBtn = document.getElementById('btn-copy');
  try {
    await login();
    out.textContent = currentToken();
    out.hidden = false;
    copyBtn.disabled = false;
  } catch (error) {
    out.textContent = error.message;
    out.hidden = false;
  }
}

async function copyToken() {
  const token = currentToken();
  if (!token) return;
  const button = document.getElementById('btn-copy');
  try {
    await navigator.clipboard.writeText(token);
    button.textContent = 'Copied';
  } catch {
    button.textContent = 'Select it manually';
  }
  setTimeout(() => {
    button.textContent = 'Copy token';
  }, 2000);
}

document.addEventListener('DOMContentLoaded', () => {
  showCredentials();
  loadKpis();
  document.getElementById('btn-token').addEventListener('click', mintToken);
  document.getElementById('btn-copy').addEventListener('click', copyToken);
});
