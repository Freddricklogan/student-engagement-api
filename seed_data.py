"""Generate sample data for the Student Engagement Analytics API."""

import random
from datetime import datetime, timedelta
from app import app, db
from models import Student, Session, EngagementEvent

random.seed(42)

MAJORS = [
    'Computer Science', 'Information Technology', 'Data Science',
    'Cybersecurity', 'Electrical Engineering', 'Business Analytics',
    'Digital Media', 'Software Engineering'
]

COURSES = ['CS101', 'CS201', 'IT330', 'DS410', 'CYB200', 'SE350', 'BA220', 'IT430']

PLATFORMS = ['Canvas LMS', 'Zoom', 'Lab Workstation', 'Mobile App', 'Library Portal']

EVENT_TYPES = [
    'page_view', 'video_watch', 'quiz_attempt', 'discussion_post',
    'assignment_submit', 'resource_download', 'lab_exercise', 'peer_review'
]

FIRST_NAMES = [
    'Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Quinn', 'Avery',
    'Cameron', 'Drew', 'Skyler', 'Reese', 'Dakota', 'Sage', 'Finley', 'Emery',
    'Hayden', 'Rowan', 'Phoenix', 'Blake', 'Kai', 'Arden', 'Jesse', 'Noor',
    'Amara', 'Priya', 'Wei', 'Min', 'Yuki', 'Ravi'
]

LAST_NAMES = [
    'Chen', 'Williams', 'Johnson', 'Patel', 'Kim', 'Garcia', 'Nguyen', 'Brown',
    'Martinez', 'Lee', 'Taylor', 'Anderson', 'Thomas', 'Jackson', 'White',
    'Harris', 'Martin', 'Thompson', 'Robinson', 'Clark', 'Lewis', 'Walker',
    'Hall', 'Allen', 'Young', 'King', 'Wright', 'Scott', 'Hill', 'Green'
]


def generate_students(n=40):
    students = []
    used_ids = set()
    used_emails = set()

    for _ in range(n):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)

        sid = f'STU{random.randint(10000, 99999)}'
        while sid in used_ids:
            sid = f'STU{random.randint(10000, 99999)}'
        used_ids.add(sid)

        email = f'{first.lower()}.{last.lower()}{random.randint(1, 99)}@iit.edu'
        while email in used_emails:
            email = f'{first.lower()}.{last.lower()}{random.randint(1, 999)}@iit.edu'
        used_emails.add(email)

        enrollment = datetime(2025, 8, 15) + timedelta(days=random.randint(0, 30))

        student = Student(
            student_id=sid,
            first_name=first,
            last_name=last,
            email=email,
            major=random.choice(MAJORS),
            enrollment_date=enrollment.date(),
            status='active'
        )
        students.append(student)

    return students


def generate_sessions(students, per_student_range=(8, 25)):
    sessions = []
    for student in students:
        num_sessions = random.randint(*per_student_range)
        for _ in range(num_sessions):
            start = datetime(2025, 9, 1) + timedelta(
                days=random.randint(0, 180),
                hours=random.randint(8, 22),
                minutes=random.randint(0, 59)
            )
            duration = random.uniform(10, 120)
            end = start + timedelta(minutes=duration)

            session = Session(
                student_id=student.id,
                course_id=random.choice(COURSES),
                start_time=start,
                end_time=end,
                duration_minutes=round(duration, 1),
                platform=random.choice(PLATFORMS)
            )
            sessions.append(session)

    return sessions


def generate_events(sessions, per_session_range=(2, 8)):
    events = []
    for session in sessions:
        num_events = random.randint(*per_session_range)
        for i in range(num_events):
            offset = timedelta(minutes=random.uniform(0, session.duration_minutes or 30))
            event_type = random.choice(EVENT_TYPES)

            # Higher scores for active participation types
            if event_type in ('discussion_post', 'assignment_submit', 'peer_review'):
                score = random.uniform(0.6, 1.0)
            elif event_type in ('quiz_attempt', 'lab_exercise'):
                score = random.uniform(0.4, 0.9)
            else:
                score = random.uniform(0.1, 0.7)

            event = EngagementEvent(
                session_id=session.id,
                event_type=event_type,
                event_data=f'{{"action": "{event_type}", "index": {i}}}',
                engagement_score=round(score, 3),
                timestamp=session.start_time + offset
            )
            events.append(event)

    return events


def seed():
    with app.app_context():
        db.drop_all()
        db.create_all()

        print('Generating students...')
        students = generate_students(40)
        db.session.add_all(students)
        db.session.commit()
        print(f'  Created {len(students)} students')

        print('Generating sessions...')
        sessions = generate_sessions(students)
        db.session.add_all(sessions)
        db.session.commit()
        print(f'  Created {len(sessions)} sessions')

        print('Generating engagement events...')
        events = generate_events(sessions)
        db.session.add_all(events)
        db.session.commit()
        print(f'  Created {len(events)} events')

        print('Done. Database seeded successfully.')


if __name__ == '__main__':
    seed()
