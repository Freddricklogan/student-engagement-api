/**
 * Dashboard controller.
 *
 * Two changes from the legacy version beyond the framework swap:
 *   1. No hard-coded API key — authentication goes through `api.js`.
 *   2. No `innerHTML` with interpolated data. The old `loadTopStudents` built
 *      table rows by string concatenation from `s.name` and `s.major`, both of
 *      which any writer could set via POST /api/students — a stored XSS sink.
 *      Rows are built with createElement/textContent here.
 */

import { apiGet, apiPost, renderKpis, setState } from './api.js';
import { barChart, lineChart } from './charts.js';

const TOUR_STEPS = [
  {
    target: 'tour-kpis',
    title: 'Live headline metrics',
    body: 'These five numbers come from GET /api/v1/analytics/summary on this page load — nothing is baked into the HTML.',
    action: loadSummary,
  },
  {
    target: 'tour-courses',
    title: 'Where the time goes',
    body: 'Session volume and mean duration per course, aggregated in SQL by GET /api/v1/analytics/sessions-by-course.',
    action: loadCourses,
  },
  {
    target: 'tour-trend',
    title: 'Engagement over time',
    body: 'Daily mean engagement score across the last 180 days. The window is a bounded query parameter, not a full-table scan.',
    action: () => loadTrend(180),
  },
  {
    target: 'tour-table',
    title: 'Who to talk to first',
    body: 'Students ranked by mean event score. Names and majors are rendered as text nodes, never interpolated into markup.',
    action: loadTopStudents,
  },
  {
    target: 'tour-rbac',
    title: 'The demo token is read-only',
    body: 'This runs a real write against the API with the viewer token and shows you the RFC 9457 denial it returns.',
    action: attemptWrite,
  },
];

// --- data loading ---------------------------------------------------------

async function loadSummary() {
  renderKpis(await apiGet('/api/v1/analytics/summary'));
}

async function loadCourses() {
  const rows = await apiGet('/api/v1/analytics/sessions-by-course');
  barChart(
    document.getElementById('courseChart'),
    rows.map((row) => ({ label: row.course_id, value: row.session_count })),
  );
}

async function loadTrend(days = 180) {
  const rows = await apiGet(`/api/v1/analytics/engagement-trend?days=${days}`);
  // Thin the series so the axis stays legible on a phone.
  const stride = Math.max(1, Math.ceil(rows.length / 60));
  const sampled = rows.filter((_, index) => index % stride === 0);
  lineChart(
    document.getElementById('trendChart'),
    sampled.map((row) => ({ label: row.date.slice(5), value: row.avg_score })),
  );
}

async function loadTopStudents() {
  const rows = await apiGet('/api/v1/analytics/top-students?limit=10');
  const body = document.getElementById('top-students-body');
  body.replaceChildren();

  rows.forEach((row, index) => {
    const tr = document.createElement('tr');

    const cells = [
      String(index + 1),
      row.name,
      row.major ?? '—',
      String(row.session_count),
    ];
    for (const value of cells) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.appendChild(td);
    }

    const scoreCell = document.createElement('td');
    const bar = document.createElement('span');
    bar.className = 'score-bar';
    bar.style.width = `${Math.round(row.avg_engagement_score * 72)}px`;
    scoreCell.appendChild(bar);
    scoreCell.appendChild(
      document.createTextNode(` ${row.avg_engagement_score.toFixed(2)}`),
    );
    tr.appendChild(scoreCell);

    body.appendChild(tr);
  });

  document.getElementById('rbac-note').textContent =
    `Ranked from ${rows.length} students, computed in SQL by the analytics repository.`;
}

// --- RBAC demonstration ----------------------------------------------------

async function attemptWrite() {
  const out = document.getElementById('problem-out');
  const response = await apiPost('/api/v1/students', {
    student_id: 'STU00000',
    first_name: 'Read',
    last_name: 'Only',
    email: 'read.only@example.edu',
  });
  const problem = await response.json();
  out.textContent = `HTTP ${response.status} ${response.headers.get('content-type')}\n\n${JSON.stringify(problem, null, 2)}`;
  out.hidden = false;
}

// --- guided tour ------------------------------------------------------------

let tourIndex = 0;

function highlight(id) {
  document.querySelectorAll('.is-highlighted').forEach((node) => node.classList.remove('is-highlighted'));
  const node = document.getElementById(id);
  if (node) {
    node.classList.add('is-highlighted');
    node.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'center',
    });
  }
}

async function showStep(index) {
  tourIndex = Math.max(0, Math.min(TOUR_STEPS.length - 1, index));
  const step = TOUR_STEPS[tourIndex];

  document.getElementById('tour-step').textContent = `Step ${tourIndex + 1} of ${TOUR_STEPS.length}`;
  document.getElementById('tour-title').textContent = step.title;
  document.getElementById('tour-body').textContent = step.body;
  document.getElementById('tour-prev').disabled = tourIndex === 0;
  document.getElementById('tour-next').textContent =
    tourIndex === TOUR_STEPS.length - 1 ? 'Finish' : 'Next';

  highlight(step.target);
  try {
    await step.action();
  } catch (error) {
    document.getElementById('tour-body').textContent = `${step.body}\n\n(${error.message})`;
  }
}

function openTour() {
  document.getElementById('tour-backdrop').hidden = false;
  document.getElementById('tour-card').hidden = false;
  document.getElementById('tour-next').focus();
  showStep(0);
}

function closeTour() {
  document.getElementById('tour-backdrop').hidden = true;
  document.getElementById('tour-card').hidden = true;
  document.querySelectorAll('.is-highlighted').forEach((n) => n.classList.remove('is-highlighted'));
  document.getElementById('btn-tour').focus();
}

function onKeydown(event) {
  if (document.getElementById('tour-card').hidden) return;
  if (event.key === 'Escape') closeTour();
  if (event.key === 'ArrowRight') showStep(tourIndex + 1);
  if (event.key === 'ArrowLeft') showStep(tourIndex - 1);
}

// --- bootstrap ---------------------------------------------------------------

async function init() {
  try {
    setState('checking', 'Connecting…');
    await Promise.all([loadSummary(), loadCourses(), loadTrend(180), loadTopStudents()]);
    setState('ok', 'Connected · viewer');
  } catch (error) {
    setState('error', 'API unavailable');
    const note = document.getElementById('rbac-note');
    if (note) note.textContent = error.message;
  }

  document.getElementById('btn-tour').addEventListener('click', openTour);
  document.getElementById('tour-next').addEventListener('click', () => {
    if (tourIndex === TOUR_STEPS.length - 1) closeTour();
    else showStep(tourIndex + 1);
  });
  document.getElementById('tour-prev').addEventListener('click', () => showStep(tourIndex - 1));
  document.getElementById('tour-close').addEventListener('click', closeTour);
  document.getElementById('tour-backdrop').addEventListener('click', closeTour);
  document.getElementById('btn-rbac').addEventListener('click', () => {
    attemptWrite().catch((error) => {
      const out = document.getElementById('problem-out');
      out.textContent = error.message;
      out.hidden = false;
    });
  });
  document.addEventListener('keydown', onKeydown);
}

document.addEventListener('DOMContentLoaded', init);
