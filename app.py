import os
import uuid
import threading
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message as MailMessage
from werkzeug.utils import secure_filename
from models import db, User, Job, Application, SavedJob, JobAlert
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-me')


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///jobboard.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ============================================
# EMAIL CONFIGURATION
# ============================================
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@jobboard.com')

# ============================================
# FILE UPLOAD CONFIGURATION
# ============================================
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'resumes')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB max

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PROFILE_PIC_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'profiles')
app.config['PROFILE_PIC_FOLDER'] = PROFILE_PIC_FOLDER
os.makedirs(PROFILE_PIC_FOLDER, exist_ok=True)

ALLOWED_RESUME_EXT = {'pdf', 'doc', 'docx'}
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


db.init_app(app)
bcrypt = Bcrypt(app)
mail = Mail(app)

with app.app_context():
    db.create_all()
    print("✅ Job Board database created successfully!")


# ============================================
# HELPER FUNCTIONS
# ============================================
def allowed_resume(filename):
    """Check if resume file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_RESUME_EXT


def allowed_image(filename):
    """Check if image file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXT


def find_matching_jobs(alert):
    """Find jobs that match a JobAlert's filters."""
    query = Job.query.filter_by(is_active=True)

    if alert.keyword:
        query = query.filter(
            db.or_(
                Job.title.ilike(f'%{alert.keyword}%'),
                Job.description.ilike(f'%{alert.keyword}%'),
                Job.company.ilike(f'%{alert.keyword}%')
            )
        )
    if alert.location:
        query = query.filter(Job.location.ilike(f'%{alert.location}%'))
    if alert.job_type:
        query = query.filter_by(job_type=alert.job_type)
    if alert.category:
        query = query.filter_by(category=alert.category)

    return query.all()


# ============================================
# EMAIL HELPER FUNCTIONS
# ============================================
def send_email_async(app, msg):
    """Send email in a background thread so it doesn't slow down the app."""
    def send():
        with app.app_context():
            try:
                mail.send(msg)
                print(f'✅ Email sent to {msg.recipients}')
            except Exception as e:
                print(f'❌ Email failed: {e}')
    thread = threading.Thread(target=send)
    thread.daemon = True
    thread.start()


def send_new_application_email(employer, job, applicant):
    """Notify employer that a new application was received."""
    subject = f"New application for '{job.title}'"
    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f1f5f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
            <div style="background: linear-gradient(135deg, #4f46e5, #6366f1); padding: 30px; text-align: center; color: white;">
                <h1 style="margin: 0; font-size: 1.5rem;">💼 New Application</h1>
            </div>
            <div style="padding: 30px;">
                <p>Hi <strong>{employer.username}</strong>,</p>
                <p>You have a new application for your job posting:</p>
                <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4f46e5;">
                    <h2 style="margin: 0 0 8px 0; color: #1e293b; font-size: 1.2rem;">{job.title}</h2>
                    <p style="margin: 0; color: #64748b;">{job.company} • {job.location}</p>
                </div>
                <p><strong>Applicant:</strong> {applicant.username}</p>
                <p><strong>Email:</strong> {applicant.email}</p>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="http://127.0.0.1:5000/job/{job.id}/applications" style="background: linear-gradient(135deg, #4f46e5, #6366f1); color: white; padding: 14px 28px; text-decoration: none; border-radius: 30px; font-weight: 600; display: inline-block;">
                        View Application
                    </a>
                </div>
            </div>
            <div style="background: #f1f5f9; padding: 20px; text-align: center; color: #64748b; font-size: 0.85rem;">
                Job Board — Automated Notification
            </div>
        </div>
    </body>
    </html>
    """
    msg = MailMessage(subject, recipients=[employer.email])
    msg.html = html
    send_email_async(app, msg)


def send_application_status_email(applicant, job, status):
    """Notify job seeker when their application status changes."""
    status_emojis = {
        'reviewed': '👁️',
        'accepted': '🎉',
        'rejected': '❌',
        'pending': '⏳'
    }
    status_colors = {
        'reviewed': '#1e40af',
        'accepted': '#065f46',
        'rejected': '#991b1b',
        'pending': '#b45309'
    }
    emoji = status_emojis.get(status, '📋')
    color = status_colors.get(status, '#4f46e5')

    subject = f"Your application for '{job.title}' is now {status.upper()}"
    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f1f5f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
            <div style="background: linear-gradient(135deg, #10b981, #059669); padding: 30px; text-align: center; color: white;">
                <h1 style="margin: 0; font-size: 1.5rem;">{emoji} Application Update</h1>
            </div>
            <div style="padding: 30px;">
                <p>Hi <strong>{applicant.username}</strong>,</p>
                <p>Your application status has been updated:</p>
                <div style="background: {color}; color: white; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center;">
                    <p style="margin: 0; font-size: 0.85rem; opacity: 0.9;">Status</p>
                    <h2 style="margin: 8px 0 0 0; font-size: 1.5rem; text-transform: uppercase;">{status}</h2>
                </div>
                <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 8px 0; color: #1e293b; font-size: 1.1rem;">{job.title}</h3>
                    <p style="margin: 0; color: #64748b;">{job.company} • {job.location}</p>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="http://127.0.0.1:5000/my_applications" style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 14px 28px; text-decoration: none; border-radius: 30px; font-weight: 600; display: inline-block;">
                        View My Applications
                    </a>
                </div>
            </div>
            <div style="background: #f1f5f9; padding: 20px; text-align: center; color: #64748b; font-size: 0.85rem;">
                Job Board — Automated Notification
            </div>
        </div>
    </body>
    </html>
    """
    msg = MailMessage(subject, recipients=[applicant.email])
    msg.html = html
    send_email_async(app, msg)


def send_job_alert_email(user, alert, new_job):
    """Notify job seeker about a new matching job."""
    subject = f"🔔 New job matching your alert: {new_job.title}"
    filter_summary = []
    if alert.keyword:
        filter_summary.append(f"keyword: <strong>{alert.keyword}</strong>")
    if alert.location:
        filter_summary.append(f"location: <strong>{alert.location}</strong>")
    if alert.job_type:
        filter_summary.append(f"type: <strong>{alert.job_type}</strong>")
    if alert.category:
        filter_summary.append(f"category: <strong>{alert.category}</strong>")

    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f1f5f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
            <div style="background: linear-gradient(135deg, #f59e0b, #f97316); padding: 30px; text-align: center; color: white;">
                <h1 style="margin: 0; font-size: 1.5rem;">🔔 New Job Alert</h1>
            </div>
            <div style="padding: 30px;">
                <p>Hi <strong>{user.username}</strong>,</p>
                <p>A new job matches your alert ({', '.join(filter_summary)}):</p>
                <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                    <h2 style="margin: 0 0 8px 0; color: #1e293b; font-size: 1.2rem;">{new_job.title}</h2>
                    <p style="margin: 0 0 4px 0; color: #64748b;"><strong>{new_job.company}</strong> • {new_job.location}</p>
                    <p style="margin: 8px 0 0 0; color: #64748b;">{new_job.job_type} • {new_job.category}</p>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="http://127.0.0.1:5000/job/{new_job.id}" style="background: linear-gradient(135deg, #f59e0b, #f97316); color: white; padding: 14px 28px; text-decoration: none; border-radius: 30px; font-weight: 600; display: inline-block;">
                        View Job
                    </a>
                </div>
            </div>
            <div style="background: #f1f5f9; padding: 20px; text-align: center; color: #64748b; font-size: 0.85rem;">
                Job Board — Automated Alert
            </div>
        </div>
    </body>
    </html>
    """
    msg = MailMessage(subject, recipients=[user.email])
    msg.html = html
    send_email_async(app, msg)


# ============================================
# DECORATORS
# ============================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def employer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'employer':
            flash('Only employers can access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def job_seeker_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'job_seeker':
            flash('Only job seekers can access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# HOME ROUTE
# ============================================
@app.route('/')
def index():
    recent_jobs = Job.query.filter_by(is_active=True).order_by(
        Job.created_at.desc()
    ).limit(6).all()

    if not session.get('logged_in'):
        return render_template('index.html', jobs=recent_jobs, role=None)

    role = session.get('role')

    if role == 'employer':
        user_id = session['user_id']

        my_jobs = Job.query.filter_by(employer_id=user_id).order_by(
            Job.created_at.desc()
        ).all()
        my_jobs_count = len(my_jobs)
        active_jobs_count = sum(1 for j in my_jobs if j.is_active)

        all_applications = Application.query.join(Job).filter(
            Job.employer_id == user_id
        ).order_by(Application.applied_at.desc()).all()
        my_applications_count = len(all_applications)

        avg_applications = round(my_applications_count / my_jobs_count, 1) if my_jobs_count > 0 else 0

        pending_count = sum(1 for a in all_applications if a.status == 'pending')
        reviewed_count = sum(1 for a in all_applications if a.status == 'reviewed')
        accepted_count = sum(1 for a in all_applications if a.status == 'accepted')
        rejected_count = sum(1 for a in all_applications if a.status == 'rejected')

        today = datetime.now().date()
        daily_data = []
        daily_labels = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            daily_labels.append(day.strftime('%b %d'))
            count = sum(1 for a in all_applications if a.applied_at.date() == day)
            daily_data.append(count)

        job_labels = []
        job_data = []
        for job in my_jobs[:8]:
            count = Application.query.filter_by(job_id=job.id).count()
            if count > 0:
                label = job.title[:20] + ('...' if len(job.title) > 20 else '')
                job_labels.append(label)
                job_data.append(count)

        recent_applications = all_applications[:5]

        return render_template(
            'index.html',
            jobs=recent_jobs,
            role='employer',
            my_jobs_count=my_jobs_count,
            my_applications_count=my_applications_count,
            active_jobs_count=active_jobs_count,
            avg_applications=avg_applications,
            pending_count=pending_count,
            reviewed_count=reviewed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            daily_labels=daily_labels,
            daily_data=daily_data,
            job_labels=job_labels,
            job_data=job_data,
            recent_applications=recent_applications
        )
    else:
        my_applications_count = Application.query.filter_by(
            applicant_id=session['user_id']
        ).count()
        saved_jobs_count = SavedJob.query.filter_by(user_id=session['user_id']).count()
        return render_template(
            'index.html',
            jobs=recent_jobs,
            role='job_seeker',
            my_applications_count=my_applications_count,
            saved_jobs_count=saved_jobs_count
        )


# ============================================
# AUTHENTICATION ROUTES
# ============================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        role = request.form.get('role', 'job_seeker').strip()

        if role not in ['employer', 'job_seeker']:
            role = 'job_seeker'

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters')
        elif User.query.filter_by(username=username).first():
            errors.append('This username is already taken')

        if not email or '@' not in email or '.' not in email:
            errors.append('Please enter a valid email')
        elif User.query.filter_by(email=email).first():
            errors.append('This email is already registered')

        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters')

        if password != confirm_password:
            errors.append('Passwords do not match')

        company_name = ''
        company_description = ''
        if role == 'employer':
            company_name = request.form.get('company_name', '').strip()
            company_description = request.form.get('company_description', '').strip()
            if not company_name:
                errors.append('Company name is required for employers')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html',
                                 username=username,
                                 email=email,
                                 role=role,
                                 company_name=company_name,
                                 company_description=company_description)

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            role=role,
            company_name=company_name if company_name else None,
            company_description=company_description if company_description else None
        )
        db.session.add(new_user)
        db.session.commit()

        flash(f'Registration successful! You registered as a {role.replace("_", " ")}.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['logged_in'] = True

            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ============================================
# PROFILE ROUTES
# ============================================
@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])

    if user.role == 'employer':
        total_jobs = Job.query.filter_by(employer_id=user.id).count()
        total_applications = Application.query.join(Job).filter(
            Job.employer_id == user.id
        ).count()
        return render_template('profile.html',
                             user=user,
                             total_jobs=total_jobs,
                             total_applications=total_applications)
    else:
        total_applications = Application.query.filter_by(applicant_id=user.id).count()
        saved_jobs = SavedJob.query.filter_by(user_id=user.id).count()
        return render_template('profile.html',
                             user=user,
                             total_applications=total_applications,
                             saved_jobs=saved_jobs)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        user.bio = request.form.get('bio', '').strip() or None
        user.location = request.form.get('location', '').strip() or None
        user.phone = request.form.get('phone', '').strip() or None
        user.linkedin = request.form.get('linkedin', '').strip() or None
        user.github = request.form.get('github', '').strip() or None
        user.website = request.form.get('website', '').strip() or None

        if user.role == 'job_seeker':
            user.headline = request.form.get('headline', '').strip() or None
            user.skills = request.form.get('skills', '').strip() or None
            exp = request.form.get('experience_years', '').strip()
            user.experience_years = int(exp) if exp.isdigit() else None
            user.education = request.form.get('education', '').strip() or None
            user.availability = request.form.get('availability', '').strip() or None
        else:
            user.company_name = request.form.get('company_name', '').strip() or None
            user.company_description = request.form.get('company_description', '').strip() or None
            user.company_website = request.form.get('company_website', '').strip() or None
            user.company_location = request.form.get('company_location', '').strip() or None
            user.company_size = request.form.get('company_size', '').strip() or None
            user.industry = request.form.get('industry', '').strip() or None

        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '':
                if not allowed_image(file.filename):
                    flash('Profile picture must be a PNG, JPG, GIF, or WEBP file.', 'error')
                    return redirect(url_for('edit_profile'))

                if user.profile_picture:
                    try:
                        old = os.path.join(app.config['PROFILE_PIC_FOLDER'], user.profile_picture)
                        if os.path.exists(old):
                            os.remove(old)
                    except Exception as e:
                        print(f'Old picture delete error: {e}')

                original_name = file.filename
                safe_name = secure_filename(original_name)
                ext = safe_name.rsplit('.', 1)[1].lower()
                unique_name = f"profile_{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                filepath = os.path.join(app.config['PROFILE_PIC_FOLDER'], unique_name)

                try:
                    file.save(filepath)
                    user.profile_picture = unique_name
                except Exception as e:
                    print(f'Profile picture save error: {e}')
                    flash('Failed to save profile picture.', 'error')

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)


# ============================================
# JOBS ROUTES
# ============================================
@app.route('/jobs')
def jobs():
    search = request.args.get('q', '').strip()
    location = request.args.get('location', '').strip()
    job_type = request.args.get('job_type', '').strip()
    category = request.args.get('category', '').strip()

    query = Job.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Job.title.ilike(f'%{search}%'),
                Job.company.ilike(f'%{search}%'),
                Job.description.ilike(f'%{search}%')
            )
        )
    if location:
        query = query.filter(Job.location.ilike(f'%{location}%'))
    if job_type:
        query = query.filter_by(job_type=job_type)
    if category:
        query = query.filter_by(category=category)

    all_jobs = query.order_by(Job.created_at.desc()).all()

    categories = db.session.query(Job.category).distinct().all()
    categories = [c[0] for c in categories]
    job_types = db.session.query(Job.job_type).distinct().all()
    job_types = [t[0] for t in job_types]

    return render_template('jobs.html',
                         jobs=all_jobs,
                         search=search,
                         location=location,
                         job_type=job_type,
                         category=category,
                         categories=categories,
                         job_types=job_types)


@app.route('/job/<int:job_id>')
def view_job(job_id):
    job = Job.query.get_or_404(job_id)

    already_applied = False
    is_saved = False
    if session.get('logged_in') and session.get('role') == 'job_seeker':
        already_applied = Application.query.filter_by(
            job_id=job_id,
            applicant_id=session['user_id']
        ).first() is not None
        is_saved = SavedJob.query.filter_by(
            job_id=job_id,
            user_id=session['user_id']
        ).first() is not None

    return render_template(
        'view_job.html',
        job=job,
        already_applied=already_applied,
        is_saved=is_saved
    )


@app.route('/job/new', methods=['GET', 'POST'])
@employer_required
def new_job():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        company = request.form.get('company', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        requirements = request.form.get('requirements', '').strip()
        salary = request.form.get('salary', '').strip()
        job_type = request.form.get('job_type', '').strip()
        category = request.form.get('category', '').strip()

        errors = []
        if not title:
            errors.append('Job title is required')
        if not company:
            errors.append('Company name is required')
        if not location:
            errors.append('Location is required')
        if not description:
            errors.append('Description is required')
        if not job_type:
            errors.append('Job type is required')
        if not category:
            errors.append('Category is required')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('new_job.html',
                                 title=title,
                                 company=company,
                                 location=location,
                                 description=description,
                                 requirements=requirements,
                                 salary=salary,
                                 job_type=job_type,
                                 category=category)

        new_job = Job(
            title=title,
            company=company,
            location=location,
            description=description,
            requirements=requirements if requirements else None,
            salary=salary if salary else None,
            job_type=job_type,
            category=category,
            employer_id=session['user_id']
        )
        db.session.add(new_job)
        db.session.commit()

        # 🔔 Notify job seekers whose alerts match this job
        try:
            all_alerts = JobAlert.query.all()
            for alert in all_alerts:
                matches = find_matching_jobs(alert)
                if new_job in matches:
                    send_job_alert_email(alert.user, alert, new_job)
        except Exception as e:
            print(f'Alert notification error: {e}')

        flash('Job posted successfully!', 'success')
        return redirect(url_for('view_job', job_id=new_job.id))

    return render_template('new_job.html')


@app.route('/job/<int:job_id>/edit', methods=['GET', 'POST'])
@employer_required
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)

    if job.employer_id != session['user_id']:
        flash('You can only edit your own jobs.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        company = request.form.get('company', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        requirements = request.form.get('requirements', '').strip()
        salary = request.form.get('salary', '').strip()
        job_type = request.form.get('job_type', '').strip()
        category = request.form.get('category', '').strip()
        is_active = request.form.get('is_active') == 'on'

        errors = []
        if not title:
            errors.append('Job title is required')
        if not company:
            errors.append('Company name is required')
        if not location:
            errors.append('Location is required')
        if not description:
            errors.append('Description is required')
        if not job_type:
            errors.append('Job type is required')
        if not category:
            errors.append('Category is required')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('edit_job.html', job=job)

        job.title = title
        job.company = company
        job.location = location
        job.description = description
        job.requirements = requirements if requirements else None
        job.salary = salary if salary else None
        job.job_type = job_type
        job.category = category
        job.is_active = is_active
        db.session.commit()

        flash('Job updated successfully!', 'success')
        return redirect(url_for('view_job', job_id=job.id))

    return render_template('edit_job.html', job=job)


@app.route('/job/<int:job_id>/delete', methods=['POST'])
@employer_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)

    if job.employer_id != session['user_id']:
        flash('You can only delete your own jobs.', 'error')
        return redirect(url_for('index'))

    for application in job.applications:
        if application.resume_filename:
            try:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], application.resume_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f'Failed to delete resume: {e}')

    db.session.delete(job)
    db.session.commit()

    flash(f'Job "{job.title}" deleted.', 'info')
    return redirect(url_for('my_jobs'))


@app.route('/my_jobs')
@employer_required
def my_jobs():
    jobs = Job.query.filter_by(employer_id=session['user_id']).order_by(
        Job.created_at.desc()
    ).all()

    jobs_with_counts = []
    for job in jobs:
        application_count = Application.query.filter_by(job_id=job.id).count()
        jobs_with_counts.append({
            'job': job,
            'application_count': application_count
        })

    return render_template('my_jobs.html', jobs=jobs_with_counts)


@app.route('/job/<int:job_id>/applications')
@employer_required
def job_applications(job_id):
    job = Job.query.get_or_404(job_id)

    if job.employer_id != session['user_id']:
        flash('You can only view applications for your own jobs.', 'error')
        return redirect(url_for('index'))

    applications = Application.query.filter_by(job_id=job_id).order_by(
        Application.applied_at.desc()
    ).all()

    return render_template('job_applications.html', job=job, applications=applications)


# ============================================
# JOB SEEKER ROUTES
# ============================================
@app.route('/job/<int:job_id>/apply', methods=['GET', 'POST'])
@job_seeker_required
def apply_job(job_id):
    job = Job.query.get_or_404(job_id)

    if not job.is_active:
        flash('This job is no longer accepting applications.', 'error')
        return redirect(url_for('view_job', job_id=job.id))

    existing = Application.query.filter_by(
        job_id=job_id,
        applicant_id=session['user_id']
    ).first()
    if existing:
        flash('You have already applied to this job.', 'warning')
        return redirect(url_for('view_job', job_id=job.id))

    if request.method == 'POST':
        cover_letter = request.form.get('cover_letter', '').strip()

        if 'resume' not in request.files:
            flash('Please upload your resume.', 'error')
            return render_template('apply_job.html', job=job, cover_letter=cover_letter)

        file = request.files['resume']
        if not file or file.filename == '':
            flash('Please select a resume file.', 'error')
            return render_template('apply_job.html', job=job, cover_letter=cover_letter)

        if not allowed_resume(file.filename):
            flash('Resume must be a PDF, DOC, or DOCX file.', 'error')
            return render_template('apply_job.html', job=job, cover_letter=cover_letter)

        original_name = file.filename
        safe_name = secure_filename(original_name)
        ext = safe_name.rsplit('.', 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)

        try:
            file.save(filepath)
        except Exception as e:
            print(f'File save error: {e}')
            flash('Failed to save resume. Please try again.', 'error')
            return render_template('apply_job.html', job=job, cover_letter=cover_letter)

        application = Application(
            cover_letter=cover_letter if cover_letter else None,
            resume_filename=unique_name,
            resume_original_name=original_name,
            job_id=job_id,
            applicant_id=session['user_id'],
            status='pending'
        )
        db.session.add(application)
        db.session.commit()

        # 📧 Send email notification to employer
        try:
            applicant = User.query.get(session['user_id'])
            send_new_application_email(job.employer, job, applicant)
        except Exception as e:
            print(f'Email notification failed: {e}')

        flash(f'Application submitted for "{job.title}"!', 'success')
        return redirect(url_for('my_applications'))

    return render_template('apply_job.html', job=job)


@app.route('/my_applications')
@job_seeker_required
def my_applications():
    applications = Application.query.filter_by(
        applicant_id=session['user_id']
    ).order_by(Application.applied_at.desc()).all()

    return render_template('my_applications.html', applications=applications)


@app.route('/application/<int:app_id>/withdraw', methods=['POST'])
@job_seeker_required
def withdraw_application(app_id):
    application = Application.query.get_or_404(app_id)

    if application.applicant_id != session['user_id']:
        flash('You can only withdraw your own applications.', 'error')
        return redirect(url_for('my_applications'))

    if application.resume_filename:
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], application.resume_filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f'Failed to delete resume: {e}')

    db.session.delete(application)
    db.session.commit()

    flash('Application withdrawn.', 'info')
    return redirect(url_for('my_applications'))


@app.route('/job/<int:job_id>/save', methods=['POST'])
@job_seeker_required
def save_job(job_id):
    job = Job.query.get_or_404(job_id)

    existing = SavedJob.query.filter_by(
        job_id=job_id,
        user_id=session['user_id']
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash('Job removed from saved.', 'info')
    else:
        saved = SavedJob(
            user_id=session['user_id'],
            job_id=job_id
        )
        db.session.add(saved)
        db.session.commit()
        flash('Job saved!', 'success')

    return redirect(url_for('view_job', job_id=job_id))


@app.route('/saved_jobs')
@job_seeker_required
def saved_jobs():
    saved = SavedJob.query.filter_by(
        user_id=session['user_id']
    ).order_by(SavedJob.saved_at.desc()).all()

    jobs = [s.job for s in saved if s.job.is_active]

    return render_template('saved_jobs.html', jobs=jobs)


# ============================================
# JOB ALERTS
# ============================================
@app.route('/alerts')
@job_seeker_required
def my_alerts():
    alerts = JobAlert.query.filter_by(user_id=session['user_id']).order_by(
        JobAlert.created_at.desc()
    ).all()

    alerts_with_counts = []
    for alert in alerts:
        count = len(find_matching_jobs(alert))
        alerts_with_counts.append({
            'alert': alert,
            'count': count
        })

    return render_template('alerts.html', alerts=alerts_with_counts)


@app.route('/alert/new', methods=['POST'])
@job_seeker_required
def new_alert():
    keyword = request.form.get('keyword', '').strip()
    location = request.form.get('location', '').strip()
    job_type = request.form.get('job_type', '').strip()
    category = request.form.get('category', '').strip()

    if not any([keyword, location, job_type, category]):
        flash('Please provide at least one filter for your alert.', 'warning')
        return redirect(url_for('jobs'))

    alert = JobAlert(
        keyword=keyword or None,
        location=location or None,
        job_type=job_type or None,
        category=category or None,
        user_id=session['user_id']
    )
    db.session.add(alert)
    db.session.commit()

    flash('Alert created! You will be notified when matching jobs are posted.', 'success')
    return redirect(url_for('my_alerts'))


@app.route('/alert/<int:alert_id>/delete', methods=['POST'])
@job_seeker_required
def delete_alert(alert_id):
    alert = JobAlert.query.get_or_404(alert_id)

    if alert.user_id != session['user_id']:
        flash('You can only delete your own alerts.', 'error')
        return redirect(url_for('my_alerts'))

    db.session.delete(alert)
    db.session.commit()

    flash('Alert deleted.', 'info')
    return redirect(url_for('my_alerts'))


# ============================================
# EMPLOYER: APPLICATION MANAGEMENT
# ============================================
@app.route('/download_resume/<filename>')
@employer_required
def download_resume(filename):
    application = Application.query.filter_by(resume_filename=filename).first()

    if not application:
        flash('Resume not found.', 'error')
        return redirect(url_for('index'))

    if application.job.employer_id != session['user_id']:
        flash('You do not have permission to access this resume.', 'error')
        return redirect(url_for('index'))

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=application.resume_original_name
    )


@app.route('/application/<int:app_id>')
@employer_required
def view_application(app_id):
    application = Application.query.get_or_404(app_id)

    if application.job.employer_id != session['user_id']:
        flash('You do not have permission to view this application.', 'error')
        return redirect(url_for('index'))

    return render_template('view_application.html', application=application)


@app.route('/application/<int:app_id>/status', methods=['POST'])
@employer_required
def update_application_status(app_id):
    application = Application.query.get_or_404(app_id)

    if application.job.employer_id != session['user_id']:
        flash('You do not have permission to update this application.', 'error')
        return redirect(url_for('index'))

    new_status = request.form.get('status', '').strip()

    if new_status not in ['pending', 'reviewed', 'accepted', 'rejected']:
        flash('Invalid status.', 'error')
        return redirect(url_for('view_application', app_id=app_id))

    application.status = new_status
    db.session.commit()

    # 📧 Send email notification to job seeker
    try:
        send_application_status_email(application.applicant, application.job, new_status)
    except Exception as e:
        print(f'Email notification failed: {e}')

    flash(f'Application status updated to "{new_status}".', 'success')
    return redirect(url_for('view_application', app_id=app_id))


# ============================================
# ERROR HANDLERS
# ============================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True)