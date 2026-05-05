import os
import re
from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ─────────────────────────────────────────────────────────────────────────────
#  APP & DATABASE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# FIX 1: Use a fixed secret key — os.urandom(24) generates a NEW key on every
# restart, which invalidates all existing sessions and causes unpredictable
# session behaviour. In production, load this from an environment variable.
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production-please")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'users_fixed.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ─────────────────────────────────────────────────────────────────────────────
#  USER MODEL
# ─────────────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer,     primary_key=True)
    full_name  = db.Column(db.String(100), nullable=False)
    matric     = db.Column(db.String(20),  unique=True, nullable=False)
    email      = db.Column(db.String(120), nullable=False)
    faculty    = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    programme  = db.Column(db.String(100), nullable=False)
    password   = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<User {self.matric} — {self.full_name}>"

# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE INITIALISATION
# FIX 2: Only create tables once at startup, not on every single request.
#         before_request runs hundreds of times — use with app.app_context()
#         inside the __main__ block instead, or use before_first_request
#         (deprecated in Flask 2.3+, so the with-block approach is best).
# ─────────────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_PATTERN  = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATRIC_PATTERN = re.compile(r"^[A-Z0-9/\-]{3,20}$")

# ─────────────────────────────────────────────────────────────────────────────
#  AUTH DECORATOR
# FIX 3: This decorator was correct in your original — kept exactly as-is.
#         If /dashboard was still accessible, the problem was NOT here.
# ─────────────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Strictly checks the session flag set only after successful DB login
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────────────────────────────────────
#  CGPA HELPER FUNCTIONS  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def get_grade_and_point(score: int) -> tuple[str, int]:
    if 70 <= score <= 100:
        return "A", 5
    elif 60 <= score < 70:
        return "B", 4
    elif 50 <= score < 60:
        return "C", 3
    elif 45 <= score < 50:
        return "D", 2
    elif 40 <= score < 45:
        return "E", 1
    else:
        return "F", 0


def calculate_gpa(courses: list[dict]) -> tuple[float, int, int]:
    total_units  = 0
    total_points = 0
    for course in courses:
        unit  = course["unit"]
        _, gp = get_grade_and_point(course["score"])
        total_units  += unit
        total_points += unit * gp
    gpa = total_points / total_units if total_units > 0 else 0.0
    return round(gpa, 2), total_units, total_points


def classify_cgpa(cgpa: float) -> str:
    if cgpa >= 4.50:
        return "First Class"
    elif cgpa >= 3.50:
        return "Second Class Upper"
    elif cgpa >= 2.40:
        return "Second Class Lower"
    elif cgpa >= 1.50:
        return "Third Class"
    elif cgpa >= 1.00:
        return "Pass"
    else:
        return "Fail"

# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATION HELPERS  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def validate_registration(form) -> dict:
    errors = {}

    full_name  = form.get("full_name",  "").strip()
    matric     = form.get("matric",     "").strip().upper()
    email      = form.get("email",      "").strip()
    faculty    = form.get("faculty",    "").strip()
    department = form.get("department", "").strip()
    programme  = form.get("programme",  "").strip()
    pw         = form.get("password",   "")
    pw_confirm = form.get("confirm_pw", "")

    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) < 3:
        errors["full_name"] = "Full name must be at least 3 characters."

    if not matric:
        errors["matric"] = "Matric number is required."
    elif not MATRIC_PATTERN.match(matric):
        errors["matric"] = "Invalid matric format (e.g. CSC/2023/001)."
    else:
        if User.query.filter_by(matric=matric).first():
            errors["matric"] = "This matric number is already registered."

    if not email:
        errors["email"] = "Email address is required."
    elif not EMAIL_PATTERN.match(email):
        errors["email"] = "Enter a valid email address."

    if not faculty:
        errors["faculty"] = "Please select your faculty."

    if not department:
        errors["department"] = "Department is required."
    elif len(department) < 2:
        errors["department"] = "Enter a valid department name."

    if not programme:
        errors["programme"] = "Programme is required."

    if not pw:
        errors["password"] = "Password is required."
    elif len(pw) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if not errors.get("password") and pw != pw_confirm:
        errors["confirm_pw"] = "Passwords do not match."

    return errors


def parse_positive_int(value, label: str) -> tuple:
    try:
        n = int(value)
        if n < 1:
            raise ValueError
        return n, None
    except (ValueError, TypeError):
        return None, f"{label} must be a whole number greater than 0."

# ─────────────────────────────────────────────────────────────────────────────
#  LANDING ROUTE
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def landing():
    return render_template("landing.html")

# ─────────────────────────────────────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    # Already logged in? Go straight to dashboard.
    if session.get("logged_in"):
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("login.html")

    # ── Collect form data ──────────────────────────────────────────────────
    matric = request.form.get("matric", "").strip().upper()
    pw     = request.form.get("password", "")

    # FIX 4: Validate that both fields were actually submitted before touching
    # the database. Missing fields → show error, stay on login page.
    if not matric or not pw:
        flash("Matric number and password are required.", "danger")
        return render_template("login.html")

    # ── Database lookup ────────────────────────────────────────────────────
    # Query the database for a user with this matric number.
    user = User.query.filter_by(matric=matric).first()

    # FIX 5: TWO conditions must BOTH be true to allow login:
    #   (a) A user with that matric number exists in the DB.
    #   (b) The submitted password matches the stored hash.
    # If either check fails, show the SAME generic error message.
    # Never reveal whether the matric number exists — that's a security leak.
    if not user or not check_password_hash(user.password, pw):
        flash("Invalid matric number or password.", "danger")
        # Stay on the login page — do NOT redirect to dashboard.
        return render_template("login.html")

    # ── Both checks passed — create the session ────────────────────────────
    # Only after a successful DB lookup AND password verification do we set
    # session["logged_in"] = True. The login_required decorator checks this.
    session["logged_in"]   = True
    session["user_matric"] = user.matric
    session["user_name"]   = user.full_name

    flash(f"Welcome back, {user.full_name}!", "success")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    name = session.get("user_name", "")
    # FIX 6: session.clear() removes ALL session data, including logged_in,
    # user_matric, student info, etc. The user is fully signed out.
    session.clear()
    flash(f"You have been logged out{', ' + name if name else ''}. See you soon!", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("register.html")

    errors = validate_registration(request.form)

    if errors:
        return render_template("register.html", errors=errors, form=request.form)

    matric    = request.form.get("matric",    "").strip().upper()
    full_name = request.form.get("full_name", "").strip()

    new_user = User(
        full_name  = full_name,
        matric     = matric,
        email      = request.form.get("email",      "").strip(),
        faculty    = request.form.get("faculty",    "").strip(),
        department = request.form.get("department", "").strip(),
        programme  = request.form.get("programme",  "").strip(),
        # Passwords are ALWAYS stored as a hash — never plain text.
        password   = generate_password_hash(request.form.get("password", "")),
    )

    db.session.add(new_user)
    db.session.commit()

    flash(f"Account created for {full_name}. You can now log in.", "success")
    return redirect(url_for("login"))

# ─────────────────────────────────────────────────────────────────────────────
#  PROTECTED DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

# FIX 7: @login_required on this route means ANY direct visit to /dashboard
# without a valid session immediately redirects to /login. No bypass possible.
@app.route("/dashboard", methods=["GET"])
@login_required
def index():
    return render_template("index.html", step="info")

# ─────────────────────────────────────────────────────────────────────────────
#  REMAINING ROUTES  (all protected, all unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/semesters", methods=["POST"])
@login_required
def semesters():
    name       = request.form.get("name",       "").strip()
    matric_no  = request.form.get("matric_no",  "").strip()
    programme  = request.form.get("programme",  "").strip()
    department = request.form.get("department", "").strip()
    faculty    = request.form.get("faculty",    "").strip()

    if not all([name, matric_no, programme, department, faculty]):
        flash("All student information fields are required.", "danger")
        return render_template("index.html", step="info")

    num_semesters, err = parse_positive_int(
        request.form.get("num_semesters"), "Number of semesters"
    )
    if err:
        flash(err, "danger")
        return render_template("index.html", step="info")

    session["student"] = {
        "name":          name,
        "matric_no":     matric_no,
        "programme":     programme,
        "department":    department,
        "faculty":       faculty,
        "num_semesters": num_semesters,
    }

    return render_template("index.html", step="course_counts",
                           student=session["student"],
                           num_semesters=num_semesters)


@app.route("/courses", methods=["POST"])
@login_required
def courses():
    student = session.get("student")
    if not student:
        flash("Session expired. Please start again.", "warning")
        return redirect(url_for("index"))

    num_semesters = student["num_semesters"]
    errors        = []
    course_counts = []

    for s in range(1, num_semesters + 1):
        count, err = parse_positive_int(
            request.form.get(f"sem_{s}_course_count"), f"Semester {s} course count"
        )
        if err:
            errors.append(f"Semester {s}: {err}")
        else:
            course_counts.append(count)

    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template("index.html", step="course_counts",
                               student=student,
                               num_semesters=num_semesters)

    session["course_counts"] = course_counts

    return render_template("index.html", step="semesters",
                           student=student,
                           num_semesters=num_semesters,
                           course_counts=course_counts)


@app.route("/results", methods=["POST"])
@login_required
def results():
    student = session.get("student")
    if not student:
        flash("Session expired. Please start again.", "warning")
        return redirect(url_for("index"))

    num_semesters     = student["num_semesters"]
    semesters_data    = []
    errors            = []
    cumulative_units  = 0
    cumulative_points = 0

    for s in range(1, num_semesters + 1):
        num_courses, err = parse_positive_int(
            request.form.get(f"sem_{s}_num_courses"), f"Semester {s} course count"
        )
        if err:
            errors.append(err)
            continue

        courses_list = []

        for c in range(1, num_courses + 1):
            code = request.form.get(f"sem_{s}_course_{c}_code", f"COURSE{c}").strip()

            unit, unit_err = parse_positive_int(
                request.form.get(f"sem_{s}_course_{c}_unit"), f"Unit for {code}"
            )
            if unit_err:
                errors.append(f"Semester {s}, {code}: {unit_err}")
                continue

            raw_score = request.form.get(f"sem_{s}_course_{c}_score", "").strip()
            try:
                score = int(raw_score)
                if not (0 <= score <= 100):
                    raise ValueError
            except (ValueError, TypeError):
                errors.append(f"Semester {s}, {code}: score must be between 0 and 100.")
                continue

            grade, gp = get_grade_and_point(score)
            courses_list.append({
                "code": code, "unit": unit, "score": score,
                "grade": grade, "gp": gp,
            })

        gpa, sem_units, sem_points = calculate_gpa(courses_list)
        cumulative_units  += sem_units
        cumulative_points += sem_points

        semesters_data.append({
            "number":  s,
            "courses": courses_list,
            "units":   sem_units,
            "points":  sem_points,
            "gpa":     gpa,
        })

    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template("index.html", step="semesters",
                               student=student,
                               num_semesters=num_semesters,
                               course_counts=session.get("course_counts", []))

    cgpa = (
        round(cumulative_points / cumulative_units, 2)
        if cumulative_units > 0 else 0.0
    )

    return render_template("index.html", step="results",
                           student=student,
                           semesters=semesters_data,
                           cumulative_units=cumulative_units,
                           cumulative_points=cumulative_points,
                           cgpa=cgpa,
                           classification=classify_cgpa(cgpa))

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)