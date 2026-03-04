const API_KEY = 'dev-api-key-2026';
const headers = { 'X-API-Key': API_KEY };

document.addEventListener('DOMContentLoaded', async () => {
    try {
        await Promise.all([loadOverview(), loadCourseData(), loadTrend(), loadTopStudents()]);
        const status = document.getElementById('api-status');
        status.textContent = 'Connected';
        status.classList.add('connected');
    } catch (err) {
        document.getElementById('api-status').textContent = 'Error';
        console.error('API Error:', err);
    }
});

async function loadOverview() {
    const res = await fetch('/api/analytics/overview', { headers });
    const data = await res.json();

    document.getElementById('total-students').textContent = data.total_students;
    document.getElementById('total-sessions').textContent = data.total_sessions.toLocaleString();
    document.getElementById('avg-duration').textContent = data.avg_session_duration + ' min';
    document.getElementById('avg-engagement').textContent = data.avg_engagement_score.toFixed(2);
}

async function loadCourseData() {
    const res = await fetch('/api/analytics/sessions-by-course', { headers });
    const data = await res.json();

    new Chart(document.getElementById('courseChart'), {
        type: 'bar',
        data: {
            labels: data.map(d => d.course_id),
            datasets: [{
                label: 'Sessions',
                data: data.map(d => d.session_count),
                backgroundColor: 'rgba(99, 102, 241, 0.6)',
                borderColor: '#6366f1',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' } },
                y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' }, beginAtZero: true }
            },
            plugins: { legend: { display: false } }
        }
    });
}

async function loadTrend() {
    const res = await fetch('/api/analytics/engagement-trend', { headers });
    const data = await res.json();

    // Sample every 3rd point for readability
    const sampled = data.filter((_, i) => i % 3 === 0);

    new Chart(document.getElementById('trendChart'), {
        type: 'line',
        data: {
            labels: sampled.map(d => d.date),
            datasets: [{
                label: 'Avg Engagement Score',
                data: sampled.map(d => d.avg_score),
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { color: '#1e293b' }, ticks: { color: '#64748b', maxTicksLimit: 10, font: { size: 10 } } },
                y: { grid: { color: '#1e293b' }, ticks: { color: '#64748b' }, min: 0, max: 1 }
            },
            plugins: { legend: { labels: { color: '#94a3b8' } } }
        }
    });
}

async function loadTopStudents() {
    const res = await fetch('/api/analytics/top-students?limit=10', { headers });
    const data = await res.json();

    const tbody = document.getElementById('top-students-tbody');
    tbody.innerHTML = data.map((s, i) => `
        <tr>
            <td>${i + 1}</td>
            <td><strong>${s.name}</strong></td>
            <td>${s.major}</td>
            <td>${s.session_count}</td>
            <td>
                <span class="score-bar" style="width: ${s.avg_engagement_score * 80}px"></span>
                ${s.avg_engagement_score.toFixed(2)}
            </td>
        </tr>
    `).join('');
}
