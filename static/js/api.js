/**
 * Shared API client.
 *
 * The legacy dashboard shipped `const API_KEY = 'dev-api-key-2026'` — a live
 * credential handed to every visitor and committed to the repo. This module
 * instead performs an OAuth2 password grant against the demo account and keeps
 * the resulting short-lived JWT in a module-scoped variable: never in
 * localStorage, never in the URL, never written to disk.
 */

let accessToken = null;
let tokenRole = null;

/** Fetch the read-only demo login the server advertises while DEMO_MODE is on. */
async function demoCredentials() {
  const response = await fetch('/demo-credentials');
  if (!response.ok) {
    throw new Error('Demo mode is disabled on this deployment; sign in with your own account.');
  }
  return response.json();
}

/** Exchange the demo credentials for a bearer token. */
export async function login() {
  if (accessToken) return accessToken;

  const creds = await demoCredentials();
  const body = new URLSearchParams();
  body.set('username', creds.username);
  body.set('password', creds.password);

  const response = await fetch('/api/v1/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) {
    throw new Error(`Login failed (${response.status})`);
  }
  const payload = await response.json();
  accessToken = payload.access_token;
  tokenRole = payload.role;
  return accessToken;
}

export function currentRole() {
  return tokenRole;
}

export function currentToken() {
  return accessToken;
}

/** Authenticated GET returning parsed JSON, throwing on a problem document. */
export async function apiGet(path) {
  const token = await login();
  const response = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(problem.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

/** Authenticated POST that returns the raw response so callers can inspect 4xx. */
export async function apiPost(path, payload) {
  const token = await login();
  return fetch(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/** Format the analytics summary into the KPI strip shared by both pages. */
export function renderKpis(summary) {
  const set = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  };
  set('kpi-students', summary.total_students.toLocaleString());
  set('kpi-sessions', summary.total_sessions.toLocaleString());
  set('kpi-events', summary.total_events.toLocaleString());
  set('kpi-duration', `${summary.avg_session_duration} min`);
  set('kpi-score', summary.avg_engagement_score.toFixed(2));
}

/** Update the connection pill. */
export function setState(state, label) {
  const pill = document.getElementById('api-state');
  if (!pill) return;
  pill.dataset.state = state;
  pill.textContent = label;
}
