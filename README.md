# 💼 Job Board

A full-featured job board platform where employers post jobs and job seekers apply with resumes — with analytics, rich profiles, email notifications, and job alerts.

## ✨ Features

### 👔 For Employers
- Register with company details
- Post, edit, delete job listings
- View applications with resumes (PDF/DOC/DOCX)
- Download resumes
- Update application status (pending → reviewed → accepted/rejected)
- **Analytics dashboard** with charts
- Rich company profile

### 🎯 For Job Seekers
- Register as job seeker
- Browse jobs with advanced filters
- Apply with resume + cover letter
- Track applications
- Save/bookmark jobs
- **Create job alerts** — email when matching jobs posted
- Rich profile (headline, skills, experience, education)
- Profile picture upload

### 📧 Email Notifications
- Employer notified on new application
- Job seeker notified on status change
- Job seekers notified when matching alerts trigger

## 🛠️ Technologies

- **Backend:** Flask (Python)
- **Database:** SQLite + SQLAlchemy
- **Auth:** Flask-Bcrypt, Sessions
- **Roles:** Employer / Job Seeker
- **Email:** Flask-Mail (Gmail SMTP)
- **Frontend:** Bootstrap 5, Chart.js, Font Awesome
- **Deployment:** Render

## 🚀 Live Demo

🔗 [View Live App](https://job-board.onrender.com)

## 🏁 Local Setup

1. Clone:
   ```bash
   git clone https://github.com/guyodika6891-lgtm/job_board.git
   cd job_board
