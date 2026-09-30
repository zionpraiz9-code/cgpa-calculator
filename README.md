# CGPA Calculator

A simple Flask web app for university students to calculate, save, and review their cumulative grade point average (CGPA). The app supports fresh calculations and continuation-based updates, and keeps a record of each saved result in SQLite.

---

## Features

- User registration and login with secure password hashing
- Fresh CGPA calculation for a new academic record
- Continuation mode to add new semester data on top of previous results
- Persistent result history saved in SQLite
- Dashboard overview of CGPA history and latest performance
- Profile view of saved results with semester breakdowns
- Clean, simple academic interface

---

## Repository Structure

- App.py — Main Flask app and route logic
- users_fixed.db — SQLite database file created automatically
- templates/ — HTML pages for login, register, dashboard, calculator, and profile views
- static/ — CSS and uploaded static assets
- README.md — Project documentation

---

## Requirements

- Python 3.10+
- Flask
- Flask-SQLAlchemy
- Werkzeug

Install dependencies with:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install flask flask_sqlalchemy
```

---

## Setup & Run

1. Open a terminal in the project folder.
2. Activate the virtual environment:

```powershell
.\.venv\Scripts\activate
```

3. Install the dependencies:

```powershell
python -m pip install flask flask_sqlalchemy
```

4. Start the app:

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

- / — Landing page
- /register — Create a new account
- /login — Sign in

### Authenticated pages

- /home — Dashboard with saved CGPA history
- /calculator — Start a fresh calculation
- /continue-calculation — Continue from the latest saved result
- /profile — View the latest or selected result

### Form flow

1. Enter student information and number of semesters
2. Enter course counts for each semester
3. Enter course codes, units, and scores or grades
4. Submit and save the result
5. Review the result on the profile page or dashboard

---

## Data Model

### User

- full_name
- matric
- email
- faculty
- department
- programme
- password

### CGPAResult

- user_id
- cgpa
- classification
- total_units
- total_points
- semesters_json
- student_json
- is_continuation
- date_created

---

## Notes

- The app uses an SQLite database file named users_fixed.db, which is created automatically on first run.
- Session lifetime is set to 7 days.
- The app keeps both fresh and continuation-based calculations so students can update their CGPA without losing their previous record.

---

