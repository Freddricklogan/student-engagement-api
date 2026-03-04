# Student Engagement Analytics API

A RESTful API built with Flask for tracking and analyzing student engagement metrics in educational platforms. Includes a built-in analytics dashboard and OpenAPI documentation.

## Features

- **RESTful API** -- Full CRUD endpoints for students, sessions, and engagement events
- **Analytics Endpoints** -- Pre-built aggregations for engagement trends, course comparisons, and top performers
- **Built-in Dashboard** -- Real-time analytics dashboard at the root URL
- **API Key Authentication** -- Simple API key-based access control
- **Seed Data Generator** -- Generates realistic sample data for 40 students, 600+ sessions, and 2,500+ events
- **SQLite Database** -- Zero-configuration database, no external dependencies
- **OpenAPI Spec** -- Full API documentation in OpenAPI 3.0 format

## Tech Stack

| Technology | Purpose |
|:-----------|:--------|
| Python 3 | Runtime |
| Flask | Web framework |
| SQLAlchemy | ORM and database |
| SQLite | Database engine |
| Chart.js | Dashboard visualizations |
| OpenAPI 3.0 | API documentation |

## Getting Started

```bash
git clone https://github.com/Freddricklogan/student-engagement-api.git
cd student-engagement-api
pip install -r requirements.txt
python seed_data.py    # Generate sample data
python app.py          # Start server on port 5000
```

Open `http://localhost:5000` for the dashboard.

## API Endpoints

All endpoints require an `X-API-Key` header. Default dev key: `dev-api-key-2026`

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| GET | `/api/students` | List students (filterable by major, status) |
| GET | `/api/students/:id` | Get student by ID |
| POST | `/api/students` | Create a new student |
| GET | `/api/sessions` | List sessions (filterable by student, course) |
| POST | `/api/sessions` | Create a new session |
| GET | `/api/events` | List engagement events |
| POST | `/api/events` | Record an engagement event |
| GET | `/api/analytics/overview` | Engagement overview metrics |
| GET | `/api/analytics/sessions-by-course` | Session counts by course |
| GET | `/api/analytics/engagement-trend` | Daily engagement score trend |
| GET | `/api/analytics/top-students` | Top students by engagement score |

## Example Request

```bash
curl -H "X-API-Key: dev-api-key-2026" http://localhost:5000/api/analytics/overview
```

```json
{
    "total_students": 40,
    "total_sessions": 648,
    "total_events": 2847,
    "avg_session_duration": 62.3,
    "avg_engagement_score": 0.52
}
```

## Data Model

```
Student (1) ──── (N) Session (1) ──── (N) EngagementEvent
```

- **Student**: student_id, name, email, major, enrollment_date, status
- **Session**: course_id, start/end time, duration, platform
- **EngagementEvent**: event_type, event_data, engagement_score, timestamp

## License

MIT License

## Author

**Freddrick Logan**
- [GitHub](https://github.com/Freddricklogan)
- [LinkedIn](https://linkedin.com/in/freddricklogan)
