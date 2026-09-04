# Z GRADE CALC

A Flask-based web app for university students to calculate, store, and download their cumulative grade point average (CGPA). The project includes user registration, secure login, password reset, semester-by-semester CGPA calculation, continuation of previous records, result history tracking, and PDF export.

---

## Features

- User registration and login with secure password hashing
- School-email registration restricted to `@tech-u.edu.ng` with OTP verification
- Password reset flow using time-limited tokens
- Fresh CGPA calculation for a new academic record
- Continuation mode to add new semester data on top of previous CGPA
- Persistent result history saved in SQLite
- Dashboard overview of CGPA history and latest performance
- Profile view of individual saved results
- Profile picture upload with secure filenames and letter-avatar fallback
- PDF download of a formatted CGPA report

---

## Repository Structure

- `App.py` — Main Flask application and route definitions
- `users_fixed.db` — SQLite database file generated automatically
- `templates/` — HTML templates for the web UI
  - `landing.html`
  - `login.html`
  - `register.html`
  - `dashboard.html`
  - `index.html`
  - `profile.html`
  - `forgot_password.html`
  - `reset_password.html`
- `static/style.css` — Shared CSS styles (if used by templates)
- `templates/SQLite.sql` — Database setup / reference SQL file

---

## Requirements

- Python 3.10+ recommended
- Flask
- Flask-SQLAlchemy
- Werkzeug
- reportlab
- Flask-Mail
- python-dotenv

If you are using a virtual environment, install dependencies like this:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install flask flask-sqlalchemy flask-mail python-dotenv reportlab
```

> Note: `werkzeug` is typically installed as a dependency of `flask`.

---

## Setup & Run

1. Open a terminal in the repository root:

```powershell
cd "c:\Users\User pc\Desktop\200 level second semester\COS 202\CGPA_PROJECT"
```

2. Activate the virtual environment:

```powershell
.\.venv\Scripts\activate
```

3. Install dependencies:

```powershell
python -m pip install flask flask-sqlalchemy flask-mail python-dotenv reportlab
```

4. Run the app:

```powershell
python App.py
```

5. Open the browser at:

```text
http://127.0.0.1:5000/
```

---

## Application Flow

### Public pages

- `/` — Landing page
- `/register` — Create a new account
- `/login` — Sign in
- `/verify-otp` — Verify a school email with a six-digit OTP
- `/resend-otp` — Send a replacement OTP
- `/forgot-password` — Request password reset
- `/reset-password/<token>` — Reset password using token

### Authenticated pages

- `/home` — User dashboard and CGPA history
- `/calculator` — Start a fresh CGPA calculation
- `/continue-calculation` — Continue from previous saved results
- `/profile` — View latest or selected result
- `/download-result/<result_id>` — Download PDF of a saved result

### Form flow

1. Enter student information and number of semesters
2. Enter course counts for each semester
3. Enter course codes, units, and scores
4. Submit and save results
5. View profile or dashboard, then optionally download a PDF

---

## Data Model

### `User`

- `full_name`
- `matric`
- `email`
- `faculty`
- `department`
- `programme`
- `password` (hashed)
- `is_verified`
- `profile_picture` (nullable uploaded filename)

### `CGPAResult`

- `user_id`
- `cgpa`
- `classification`
- `total_units`
- `total_points`
- `semesters_json` — stored semester/course details
- `student_json` — stored student profile data
- `is_continuation` — whether this result continues a previous record
- `date_created`

### `PasswordReset`

- `user_id`
- `token`
- `expires_at`
- `used`

### `EmailOTP`

- `user_id`
- `otp_code`
- `expires_at` — ten minutes after creation
- `used`
- `created_at`

---

## Libraries Used

### External libraries

| Library | Use in the application |
|---|---|
| `Flask` | Web server, routing, templates, sessions, redirects, flash messages, and file downloads |
| `Flask-SQLAlchemy` | Database connection, models, relationships, queries, and transactions |
| `Flask-Mail` | OTP email creation and SMTP delivery |
| `python-dotenv` | Loads `.env` values into environment variables at startup |
| `Werkzeug` | Password hashing and password verification |
| `ReportLab` | PDF reports, styles, tables, colors, and page layout |

### Python standard-library modules

| Module | Use in the application |
|---|---|
| `os` | Environment variables, application paths, upload folders, and file deletion |
| `re` | Email and matric-number validation |
| `json` | Serializing and reading student and semester data |
| `secrets` | OTP codes, reset tokens, and secure upload filenames |
| `io.BytesIO` | Holding generated PDFs in memory |
| `datetime` | Session lifetime, OTP expiry, reset expiry, and result dates |
| `functools.wraps` | Preserving metadata in `login_required` |

## Application Functions

- `login_required` protects authenticated routes.
- `get_grade_and_point` converts a numeric score to a grade and grade point.
- `get_grade_point_and_rep_score` converts a letter grade to its point and representative score.
- `calculate_gpa` calculates total units, quality points, and GPA.
- `classify_cgpa` assigns the degree classification for a CGPA.
- `validate_registration` validates registration fields and duplicate matric numbers.
- `parse_positive_int` validates positive whole-number inputs.
- `issue_email_otp` invalidates old codes, creates a six-digit OTP, and sends it through Flask-Mail.
- `_build_styles` creates the ReportLab paragraph styles.
- `generate_pdf_bytes` builds a formatted academic performance report in memory.
- `upload_profile_picture` validates, replaces, and stores a user's profile picture.

## Route Reference

### Public and authentication routes

| Method | Route | Functionality |
|---|---|---|
| `GET` | `/` | Landing page |
| `GET`, `POST` | `/register` | Create an account and send an OTP |
| `GET`, `POST` | `/login` | Sign in |
| `GET`, `POST` | `/verify-otp` | Verify a six-digit OTP |
| `POST` | `/resend-otp` | Resend an OTP |
| `GET` | `/logout` | Clear the session |
| `GET`, `POST` | `/forgot-password` | Request a password-reset token |
| `GET`, `POST` | `/reset-password/<token>` | Change a password with a valid token |

### Authenticated routes

| Method | Route | Functionality |
|---|---|---|
| `GET` | `/home` | Dashboard and result history |
| `GET` | `/calculator` | Start a new calculation |
| `GET` | `/continue-calculation` | Continue from the latest result |
| `POST` | `/semesters` | Save student details and semester count in session |
| `POST` | `/courses` | Save course counts in session |
| `POST` | `/results` | Calculate and save a result |
| `GET` | `/profile` | Display the latest saved result |
| `GET` | `/profile/<result_id>` | Display a selected result |
| `POST` | `/upload-profile-picture` | Upload or replace a profile picture |
| `GET` | `/download-result/<result_id>` | Download a PDF report |

## Configuration

Create `.env` in the project root and keep it out of version control:

```env
DEV_MODE=false
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-gmail-address@gmail.com
MAIL_PASSWORD=your-gmail-app-password
MAIL_DEFAULT_SENDER=your-gmail-address@gmail.com
SECRET_KEY=replace-with-a-long-random-secret
```

`DEV_MODE=false` sends real OTP email. `DEV_MODE=true` is for local testing only and flashes the OTP instead. `MAIL_PASSWORD` must be a Gmail App Password.

## Data Models and Storage

- `User` stores identity, academic details, a hashed password, verification state, and nullable `profile_picture` filename.
- `EmailOTP` stores OTP codes, expiry, used state, and creation time. Codes expire after ten minutes.
- `PasswordReset` stores one-hour password-reset tokens.
- `CGPAResult` stores CGPA, classification, totals, serialized course data, continuation state, and creation date.
- `users_fixed.db` is the SQLite database located beside `App.py`.
- `static/uploads/profile_pics/` stores generated profile-picture filenames. Only PNG, JPG, JPEG, and WEBP files up to 3 MB are accepted.

At startup, the app creates missing tables and safely adds the `is_verified`, `is_continuation`, and `profile_picture` columns to existing databases with `ALTER TABLE` migrations.

## PythonAnywhere Deployment

Upload `App.py`, `templates/`, `static/`, and `users_fixed.db`. Install the dependencies in the web app's virtual environment:

```bash
pip install flask flask-sqlalchemy flask-mail python-dotenv reportlab
```

Either upload `.env` beside `App.py` through the Files tab, or define the same variables in the WSGI configuration before importing the app:

```python
from App import app
```

Reload the web app after changing configuration. Ensure `static/uploads/profile_pics/` is writable.

## Notes and Development

- The app uses an SQLite database file `users_fixed.db` created automatically on first run.
- The password reset route shows the reset link in a flash message when `DEV_MODE=true`.
- OTP delivery defaults to real email sending. Set `DEV_MODE=true` only for local OTP testing. Configure SMTP before use:

```powershell
$env:DEV_MODE="false"
$env:MAIL_SERVER="smtp.gmail.com"
$env:MAIL_PORT="587"
$env:MAIL_USERNAME="your-school-email@tech-u.edu.ng"
$env:MAIL_PASSWORD="your-email-app-password"
$env:MAIL_USE_TLS="true"
$env:MAIL_DEFAULT_SENDER="your-school-email@tech-u.edu.ng"
```

For Gmail, `MAIL_PASSWORD` must be a Gmail App Password, not your normal Gmail password. Create it in your Google Account security settings after enabling 2-Step Verification, then set that App Password in `$env:MAIL_PASSWORD` (or in the environment used to start the app). `App.py` reads it in the mail configuration block and passes it to `Mail(app)`.

- In `DEV_MODE=true`, the OTP is flashed on the verification page and logged by the application instead of being sent.
- On startup, the app adds the `users.is_verified` column and `email_otps` table without deleting existing data. Existing users are marked verified so they are not locked out by the new registration requirement; only new accounts require OTP verification.
- Session lifetime is configured for 7 days.
- The PDF generator uses `reportlab` to produce a styled academic report.

---

## Improvements

Some useful future enhancements:

- Add a `requirements.txt` for exact dependency versions
- Add proper email sending for password reset links
- Improve validation on course inputs and field names
- Add unit tests for CGPA calculations and route behavior
- Add responsive UI and mobile layout testing

---

