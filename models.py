from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='job_seeker')
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Profile picture (shared)
    profile_picture = db.Column(db.String(255), nullable=True)

    # Common fields
    bio = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

    # Social links
    linkedin = db.Column(db.String(200), nullable=True)
    github = db.Column(db.String(200), nullable=True)
    website = db.Column(db.String(200), nullable=True)

    # Job Seeker specific
    headline = db.Column(db.String(200), nullable=True)
    skills = db.Column(db.Text, nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    education = db.Column(db.String(200), nullable=True)
    availability = db.Column(db.String(50), nullable=True)

    # Employer specific
    company_name = db.Column(db.String(150), nullable=True)
    company_description = db.Column(db.Text, nullable=True)
    company_website = db.Column(db.String(200), nullable=True)
    company_location = db.Column(db.String(150), nullable=True)
    company_size = db.Column(db.String(50), nullable=True)
    industry = db.Column(db.String(100), nullable=True)

    # Relationships
    posted_jobs = db.relationship('Job', backref='employer', lazy=True, cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='applicant', lazy=True, cascade='all, delete-orphan')
    saved_jobs = db.relationship('SavedJob', backref='user', lazy=True, cascade='all, delete-orphan')
    job_alerts = db.relationship('JobAlert', backref='user', lazy=True, cascade='all, delete-orphan')

    def skills_list(self):
        """Return skills as a list."""
        if not self.skills:
            return []
        return [s.strip() for s in self.skills.split(',') if s.strip()]

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    salary = db.Column(db.String(100))
    job_type = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relationship
    applications = db.relationship('Application', backref='job', lazy=True, cascade='all, delete-orphan')
    saved_by = db.relationship('SavedJob', backref='job', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Job {self.title} at {self.company}>'


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cover_letter = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))
    resume_original_name = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default='pending')
    applied_at = db.Column(db.DateTime, default=datetime.now)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Application by {self.applicant.username} for {self.job.title}>'


class SavedJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    saved_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)

    def __repr__(self):
        return f'<SavedJob by {self.user.username}>'


class JobAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(150), nullable=True)
    job_type = db.Column(db.String(30), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<JobAlert {self.keyword} by {self.user.username}>'