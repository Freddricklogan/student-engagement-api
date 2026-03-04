"""Student Engagement Analytics API -- Flask REST API with built-in dashboard."""

import os
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, abort
from models import db, Student, Session, EngagementEvent
from sqlalchemy import func

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///engagement.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['API_KEY'] = os.environ.get('API_KEY', 'dev-api-key-2026')

db.init_app(app)


# --- Authentication ---

def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key != app.config['API_KEY']:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated


# --- Dashboard ---

@app.route('/')
def dashboard():
    return send_from_directory('static', 'dashboard.html')


# --- Student Endpoints ---

@app.route('/api/students', methods=['GET'])
@require_api_key
def get_students():
    """List all students with optional filtering."""
    major = request.args.get('major')
    status = request.args.get('status', 'active')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Student.query
    if major:
        query = query.filter(Student.major == major)
    if status:
        query = query.filter(Student.status == status)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'students': [s.to_dict() for s in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })


@app.route('/api/students/<int:student_id>', methods=['GET'])
@require_api_key
def get_student(student_id):
    """Get a single student by ID."""
    student = Student.query.get_or_404(student_id)
    return jsonify(student.to_dict())


@app.route('/api/students', methods=['POST'])
@require_api_key
def create_student():
    """Create a new student."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    required = ['student_id', 'first_name', 'last_name', 'email']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    student = Student(
        student_id=data['student_id'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data['email'],
        major=data.get('major'),
        enrollment_date=datetime.fromisoformat(data['enrollment_date']) if data.get('enrollment_date') else None,
        status=data.get('status', 'active')
    )
    db.session.add(student)
    db.session.commit()
    return jsonify(student.to_dict()), 201


# --- Session Endpoints ---

@app.route('/api/sessions', methods=['GET'])
@require_api_key
def get_sessions():
    """List sessions with optional filtering."""
    student_id = request.args.get('student_id', type=int)
    course_id = request.args.get('course_id')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Session.query
    if student_id:
        query = query.filter(Session.student_id == student_id)
    if course_id:
        query = query.filter(Session.course_id == course_id)

    query = query.order_by(Session.start_time.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'sessions': [s.to_dict() for s in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })


@app.route('/api/sessions', methods=['POST'])
@require_api_key
def create_session():
    """Create a new session."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    session = Session(
        student_id=data['student_id'],
        course_id=data['course_id'],
        start_time=datetime.fromisoformat(data['start_time']),
        end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else None,
        duration_minutes=data.get('duration_minutes'),
        platform=data.get('platform')
    )
    db.session.add(session)
    db.session.commit()
    return jsonify(session.to_dict()), 201


# --- Engagement Event Endpoints ---

@app.route('/api/events', methods=['GET'])
@require_api_key
def get_events():
    """List engagement events."""
    session_id = request.args.get('session_id', type=int)
    event_type = request.args.get('event_type')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = EngagementEvent.query
    if session_id:
        query = query.filter(EngagementEvent.session_id == session_id)
    if event_type:
        query = query.filter(EngagementEvent.event_type == event_type)

    query = query.order_by(EngagementEvent.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'events': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })


@app.route('/api/events', methods=['POST'])
@require_api_key
def create_event():
    """Record a new engagement event."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    event = EngagementEvent(
        session_id=data['session_id'],
        event_type=data['event_type'],
        event_data=data.get('event_data'),
        engagement_score=data.get('engagement_score')
    )
    db.session.add(event)
    db.session.commit()
    return jsonify(event.to_dict()), 201


# --- Analytics Endpoints ---

@app.route('/api/analytics/overview', methods=['GET'])
@require_api_key
def analytics_overview():
    """Get overall engagement analytics."""
    total_students = Student.query.filter_by(status='active').count()
    total_sessions = Session.query.count()
    total_events = EngagementEvent.query.count()
    avg_duration = db.session.query(func.avg(Session.duration_minutes)).scalar() or 0
    avg_score = db.session.query(func.avg(EngagementEvent.engagement_score)).scalar() or 0

    return jsonify({
        'total_students': total_students,
        'total_sessions': total_sessions,
        'total_events': total_events,
        'avg_session_duration': round(float(avg_duration), 1),
        'avg_engagement_score': round(float(avg_score), 2)
    })


@app.route('/api/analytics/sessions-by-course', methods=['GET'])
@require_api_key
def sessions_by_course():
    """Get session counts and avg duration by course."""
    results = db.session.query(
        Session.course_id,
        func.count(Session.id).label('session_count'),
        func.avg(Session.duration_minutes).label('avg_duration')
    ).group_by(Session.course_id).all()

    return jsonify([{
        'course_id': r.course_id,
        'session_count': r.session_count,
        'avg_duration': round(float(r.avg_duration or 0), 1)
    } for r in results])


@app.route('/api/analytics/engagement-trend', methods=['GET'])
@require_api_key
def engagement_trend():
    """Get daily engagement scores over time."""
    results = db.session.query(
        func.date(EngagementEvent.timestamp).label('date'),
        func.avg(EngagementEvent.engagement_score).label('avg_score'),
        func.count(EngagementEvent.id).label('event_count')
    ).group_by(func.date(EngagementEvent.timestamp)).order_by('date').all()

    return jsonify([{
        'date': str(r.date),
        'avg_score': round(float(r.avg_score or 0), 2),
        'event_count': r.event_count
    } for r in results])


@app.route('/api/analytics/top-students', methods=['GET'])
@require_api_key
def top_students():
    """Get top students by engagement score."""
    limit = request.args.get('limit', 10, type=int)

    results = db.session.query(
        Student.id,
        Student.first_name,
        Student.last_name,
        Student.major,
        func.avg(EngagementEvent.engagement_score).label('avg_score'),
        func.count(Session.id.distinct()).label('session_count')
    ).join(Session, Student.id == Session.student_id)\
     .join(EngagementEvent, Session.id == EngagementEvent.session_id)\
     .group_by(Student.id)\
     .order_by(func.avg(EngagementEvent.engagement_score).desc())\
     .limit(limit).all()

    return jsonify([{
        'student_id': r.id,
        'name': f'{r.first_name} {r.last_name}',
        'major': r.major,
        'avg_engagement_score': round(float(r.avg_score or 0), 2),
        'session_count': r.session_count
    } for r in results])


# --- API Documentation ---

@app.route('/api/docs')
def api_docs():
    return send_from_directory('docs', 'openapi.yaml', mimetype='text/yaml')


# --- Error Handlers ---

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
