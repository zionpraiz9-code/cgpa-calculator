import os
from dotenv import load_dotenv

load_dotenv()

import re
import json
import secrets
from io import BytesIO
from datetime import datetime, timedelta
from flask import (Flask, render_template, request, session,
                   redirect, url_for, flash, send_file)
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable)
from reportlab.lib.enums import TA_CENTER

# ───────────────── ────────────────────────────────────────────────────────────
#  APP & DATABASE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production-please")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["DEV_MODE"] = os.environ.get("DEV_MODE", "false").lower() in ("1", "true", "yes")
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PICS_DIR = os.path.join(BASE_DIR, "static", "uploads", "profile_pics")
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'users_fixed.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
mail = Mail(app)

# ─────────────────────────────────────────────────────────────────────────────
#  MODELS
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
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)

    results      = db.relationship("CGPAResult",    backref="user", lazy=True, cascade="all, delete-orphan")
    reset_tokens = db.relationship("PasswordReset", backref="user", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.matric} — {self.full_name}>"


class EmailOTP(db.Model):
    __tablename__ = "email_otps"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    otp_code   = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("email_otps", lazy=True,
                                                        cascade="all, delete-orphan"))


class CGPAResult(db.Model):
    """Stores every CGPA calculation permanently per user."""
    __tablename__ = "cgpa_results"

    id             = db.Column(db.Integer,  primary_key=True)
    user_id        = db.Column(db.Integer,  db.ForeignKey("users.id"), nullable=False)
    cgpa           = db.Column(db.Float,    nullable=False)
    classification = db.Column(db.String(50), nullable=False)
    total_units    = db.Column(db.Integer,  nullable=False)
    total_points   = db.Column(db.Integer,  nullable=False)
    semesters_json = db.Column(db.Text,     nullable=False)
    student_json   = db.Column(db.Text,     nullable=False)
    is_continuation= db.Column(db.Boolean,  default=False)
    date_created   = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def semesters(self):
        return json.loads(self.semesters_json)

    @property
    def student(self):
        return json.loads(self.student_json)

    @property
    def date_display(self):
        return self.date_created.strftime("%d %b %Y, %I:%M %p")

    def __repr__(self):
        return f"<CGPAResult user={self.user_id} cgpa={self.cgpa}>"


class PasswordReset(db.Model):
    """Stores password reset tokens."""
    __tablename__ = "password_resets"

    id         = db.Column(db.Integer,     primary_key=True)
    user_id    = db.Column(db.Integer,     db.ForeignKey("users.id"), nullable=False)
    token      = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime,   nullable=False)
    used       = db.Column(db.Boolean,    default=False)

    @property
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


with app.app_context():
    db.create_all()

    # ── ONE-TIME MIGRATIONS: preserve existing data while adding new fields ──
    from sqlalchemy import text, inspect as sa_inspect
    with db.engine.connect() as conn:
        inspector = sa_inspect(db.engine)
        user_cols = [c["name"] for c in inspector.get_columns("users")]
        if "is_verified" not in user_cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0"
            ))
            # Existing accounts predate OTP verification and remain usable.
            conn.execute(text("UPDATE users SET is_verified = 1"))
            conn.commit()

        result_cols = [c["name"] for c in inspector.get_columns("cgpa_results")]
        if "is_continuation" not in result_cols:
            conn.execute(text(
                "ALTER TABLE cgpa_results ADD COLUMN is_continuation BOOLEAN DEFAULT 0"
            ))
            conn.commit()

        if "profile_picture" not in user_cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN profile_picture VARCHAR(255)"
            ))
            conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_PATTERN  = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATRIC_PATTERN = re.compile(r"^[A-Z0-9/\-]{3,20}$")
SCHOOL_EMAIL_DOMAIN = "@tech-u.edu.ng"

# ─────────────────────────────────────────────────────────────────────────────
#  AUTH DECORATOR
# ─────────────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        if not session.get("user_id"):
            session.clear()
            flash("Your session is invalid. Please log in again.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────────────────────────────────────
#  GRADE CALCULATION HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

GRADE_POINT_MAP = {
    "A": 5, "B": 4, "C": 3,
    "D": 2, "E": 1, "F": 0,
}
GRADE_REP_SCORE = {
    "A": 85, "B": 65, "C": 55,
    "D": 47, "E": 42, "F": 20,
}

def get_grade_and_point(score: int) -> tuple[str, int]:
    if 70 <= score <= 100: return "A", 5
    elif 60 <= score < 70: return "B", 4
    elif 50 <= score < 60: return "C", 3
    elif 45 <= score < 50: return "D", 2
    elif 40 <= score < 45: return "E", 1
    else:                  return "F", 0


def get_grade_point_and_rep_score(letter: str) -> tuple[int, int]:
    letter = letter.strip().upper()
    if letter not in GRADE_POINT_MAP:
        raise ValueError("Invalid grade letter")
    return GRADE_POINT_MAP[letter], GRADE_REP_SCORE[letter]


def calculate_gpa(courses: list[dict]) -> tuple[float, int, int]:
    total_units = total_points = 0
    for course in courses:
        unit  = course["unit"]
        _, gp = get_grade_and_point(course["score"])
        total_units  += unit
        total_points += unit * gp
    gpa = total_points / total_units if total_units > 0 else 0.0
    return round(gpa, 2), total_units, total_points


def classify_cgpa(cgpa: float) -> str:
    if cgpa >= 4.50:   return "First Class"
    elif cgpa >= 3.50: return "Second Class Upper"
    elif cgpa >= 2.40: return "Second Class Lower"
    elif cgpa >= 1.50: return "Third Class"
    elif cgpa >= 1.00: return "Pass"
    else:              return "Fail"

# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATION HELPERS
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

    if not full_name:           errors["full_name"]   = "Full name is required."
    elif len(full_name) < 3:    errors["full_name"]   = "Full name must be at least 3 characters."
    if not matric:              errors["matric"]      = "Matric number is required."
    elif not MATRIC_PATTERN.match(matric): errors["matric"] = "Invalid matric format (e.g. CSC/2023/001)."
    elif User.query.filter_by(matric=matric).first(): errors["matric"] = "This matric number is already registered."
    if not email:               errors["email"]       = "Email address is required."
    elif not EMAIL_PATTERN.match(email): errors["email"] = "Enter a valid email address."
    elif not email.lower().endswith(SCHOOL_EMAIL_DOMAIN):
        errors["email"] = f"Registration is restricted to {SCHOOL_EMAIL_DOMAIN} email addresses."
    if not faculty:             errors["faculty"]     = "Please select your faculty."
    if not department:          errors["department"]  = "Department is required."
    elif len(department) < 2:   errors["department"]  = "Enter a valid department name."
    if not programme:           errors["programme"]   = "Programme is required."
    if not pw:                  errors["password"]    = "Password is required."
    elif len(pw) < 8:           errors["password"]    = "Password must be at least 8 characters."
    if not errors.get("password") and pw != pw_confirm:
        errors["confirm_pw"] = "Passwords do not match."
    return errors


def parse_positive_int(value, label: str) -> tuple:
    try:
        n = int(value)
        if n < 1: raise ValueError
        return n, None
    except (ValueError, TypeError):
        return None, f"{label} must be a whole number greater than 0."


def issue_email_otp(user: User) -> str:
    """Invalidate older codes, create a fresh code, and deliver it."""
    EmailOTP.query.filter_by(user_id=user.id, used=False).update({"used": True})
    otp_code = f"{secrets.randbelow(1_000_000):06d}"
    otp = EmailOTP(
        user_id=user.id,
        otp_code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(otp)
    db.session.commit()

    if app.config["DEV_MODE"]:
        app.logger.info("DEV_MODE OTP for %s: %s", user.email, otp_code)
        flash(f"[DEV MODE] Your verification code is {otp_code}", "info")
        return otp_code

    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        raise RuntimeError("SMTP credentials are not configured.")

    message = Message(
        subject="Your Z GRADE CALC verification code",
        sender=("Z GRADE CALC", app.config["MAIL_DEFAULT_SENDER"]),
        recipients=[user.email],
        body=(
            f"Your Z GRADE CALC verification code is {otp_code}. "
            "It expires in 10 minutes."
        ),
    )
    try:
        mail.send(message)
    except Exception as exc:
        print(f"OTP email sending failed: {type(exc).__name__}: {exc}", flush=True)
        raise
    return otp_code

# ─────────────────────────────────────────────────────────────────────────────
#  REPORTLAB PDF GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

DARK_BLUE  = colors.HexColor("#0a1628")
BRAND_BLUE = colors.HexColor("#1a56db")
AMBER      = colors.HexColor("#f59f0b71")
SLATE      = colors.HexColor("#475569")
LIGHT_BG   = colors.HexColor("#f8fafc6a")
WHITE      = colors.white


def _build_styles():
    base = getSampleStyleSheet()
    return {
        "title":        ParagraphStyle("RPTitle",    fontName="Helvetica-Bold", fontSize=20, textColor=DARK_BLUE,  spaceAfter=2),
        "subtitle":     ParagraphStyle("RPSubtitle", fontName="Helvetica",      fontSize=12, textColor=BRAND_BLUE, spaceAfter=14),
        "label":        ParagraphStyle("RPLabel",    fontName="Helvetica-Bold", fontSize=9,  textColor=SLATE),
        "value":        ParagraphStyle("RPValue",    fontName="Helvetica",      fontSize=9,  textColor=DARK_BLUE),
        "section_head": ParagraphStyle("RPSection",  fontName="Helvetica-Bold", fontSize=11, textColor=WHITE),
        "footer":       ParagraphStyle("RPFooter",   fontName="Helvetica",      fontSize=8,  textColor=SLATE, alignment=TA_CENTER),
        "normal":       base["Normal"],
    }


def generate_pdf_bytes(result: CGPAResult) -> bytes:
    buffer  = BytesIO()
    doc     = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm,  bottomMargin=2*cm,
                                title="Academic Performance Report")
    S       = _build_styles()
    story   = []
    W       = A4[0] - 4 * cm
    student   = result.student
    semesters = result.semesters

    story.append(Paragraph("Academic Performance Report", S["title"]))
    story.append(Paragraph("Official Performance Report", S["subtitle"]))
    story.append(HRFlowable(width=W, thickness=2, color=BRAND_BLUE, spaceAfter=14))

    col_w = W / 4
    info_data = [
        [Paragraph("Full Name",  S["label"]), Paragraph(student.get("name","—"),       S["value"]),
         Paragraph("Matric No",  S["label"]), Paragraph(student.get("matric_no","—"),  S["value"])],
        [Paragraph("Programme",  S["label"]), Paragraph(student.get("programme","—"),  S["value"]),
         Paragraph("Department", S["label"]), Paragraph(student.get("department","—"), S["value"])],
        [Paragraph("Faculty",    S["label"]), Paragraph(student.get("faculty","—"),    S["value"]),
         Paragraph("Date",       S["label"]), Paragraph(result.date_display,           S["value"])],
    ]
    info_table = Table(info_data, colWidths=[col_w*.6, col_w*1.4, col_w*.6, col_w*1.4])
    info_table.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4),("LINEBELOW",(0,0),(-1,-1),.5,colors.HexColor("#e2e8f0")),
    ]))
    story.append(info_table)
    story.append(Spacer(1,14))

    # Show continuation note if applicable
    if result.is_continuation:
        note = Paragraph("⚠ This is an incremental update — cumulative totals include all previous semesters.", S["label"])
        story.append(note)
        story.append(Spacer(1, 8))

    banner_data = [[
        Paragraph(f"<b>CGPA</b><br/>{result.cgpa} / 5.00<br/>{result.classification}", S["section_head"]),
        Paragraph(f"<b>TOTAL UNITS</b><br/>{result.total_units}", S["section_head"]),
        Paragraph(f"<b>QUALITY POINTS</b><br/>{result.total_points}", S["section_head"]),
        Paragraph(f"<b>SEMESTERS</b><br/>{len(semesters)}", S["section_head"]),
    ]]
    banner = Table(banner_data, colWidths=[W*.35, W*.22, W*.25, W*.18])
    banner.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),DARK_BLUE),("TEXTCOLOR",(0,0),(-1,-1),WHITE),
        ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),10),
        ("PADDING",(0,0),(-1,-1),14),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(banner)
    story.append(Spacer(1,18))

    header = ["Semester","Course Code","Units","Score","Grade","GP","Weighted"]
    table_data = [header]
    for sem in semesters:
        for course in sem["courses"]:
            score_display = (
                f"Grade: {course['grade']}" if course.get("input_mode", "score") == "grade"
                else str(course["score"])
            )
            table_data.append([
                f"Semester {sem['number']}", course["code"],
                str(course["unit"]), score_display,
                course["grade"], str(course["gp"]), str(course["weighted"]),
            ])

    col_widths = [W*.14, W*.22, W*.09, W*.10, W*.10, W*.08, W*.13]
    course_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    course_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),BRAND_BLUE),("TEXTCOLOR",(0,0),(-1,0),WHITE),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),9),
        ("BOTTOMPADDING",(0,0),(-1,0),10),("TOPPADDING",(0,0),(-1,0),10),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),("FONTSIZE",(0,1),(-1,-1),8.5),
        ("TOPPADDING",(0,1),(-1,-1),7),("BOTTOMPADDING",(0,1),(-1,-1),7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT_BG]),
        ("LINEBELOW",(0,0),(-1,-1),.4,colors.HexColor("#e2e8f0")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(2,0),(-1,-1),"CENTER"),
    ]))
    story.append(course_table)
    story.append(Spacer(1,20))
    story.append(HRFlowable(width=W, thickness=.5, color=SLATE, spaceAfter=8))
    story.append(Paragraph(f"Generated by Z GRADE CALC &nbsp;·&nbsp; {result.date_display}", S["footer"]))

    doc.build(story)
    return buffer.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
#  LANDING
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def landing():
    return render_template("landing.html")

# ─────────────────────────────────────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("login.html")

    matric = request.form.get("matric", "").strip().upper()
    pw     = request.form.get("password", "")

    if not matric or not pw:
        flash("Matric number and password are required.", "danger")
        return render_template("login.html")

    user = User.query.filter_by(matric=matric).first()
    if not user or not check_password_hash(user.password, pw):
        flash("Invalid matric number or password.", "danger")
        return render_template("login.html")

    if not user.is_verified:
        session["pending_verification_user_id"] = user.id
        latest_otp = (EmailOTP.query
                      .filter_by(user_id=user.id, used=False)
                      .order_by(EmailOTP.created_at.desc())
                      .first())
        if not latest_otp or latest_otp.expires_at <= datetime.utcnow():
            try:
                issue_email_otp(user)
            except Exception:
                app.logger.exception("Could not send verification OTP to %s", user.email)
                flash("We could not send your verification code. Please try again later.", "danger")
                return render_template("login.html")
        flash("Please verify your school email before signing in.", "warning")
        return redirect(url_for("verify_otp"))

    session.permanent      = True
    session["logged_in"]   = True
    session["user_id"]     = user.id
    session["user_matric"] = user.matric
    session["user_name"]   = user.full_name

    flash(f"Welcome back, {user.full_name}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    name = session.get("user_name", "")
    session.clear()
    flash(f"You have been logged out{', ' + name if name else ''}. See you soon!", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

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
        password   = generate_password_hash(request.form.get("password", "")),
    )
    db.session.add(new_user)
    db.session.commit()

    session["pending_verification_user_id"] = new_user.id
    try:
        issue_email_otp(new_user)
    except Exception:
        app.logger.exception("Could not send verification OTP to %s", new_user.email)
        flash("Account created, but we could not send the verification code. Please try again.", "danger")
        return redirect(url_for("login"))

    flash(f"Account created for {full_name}. Check your school email for the verification code.", "success")
    return redirect(url_for("verify_otp"))


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    user_id = session.get("pending_verification_user_id")
    user = User.query.get(user_id) if user_id else None
    if not user:
        flash("Please register or log in before verifying your email.", "warning")
        return redirect(url_for("login"))
    if user.is_verified:
        session.pop("pending_verification_user_id", None)
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        submitted_code = request.form.get("otp_code", "").strip()
        latest_otp = (EmailOTP.query
                      .filter_by(user_id=user.id, used=False)
                      .order_by(EmailOTP.created_at.desc())
                      .first())

        if not latest_otp or submitted_code != latest_otp.otp_code:
            flash("The verification code is invalid.", "danger")
            return render_template("verify_otp.html", email=user.email)
        if latest_otp.expires_at <= datetime.utcnow():
            flash("The verification code has expired. Please request a new code.", "warning")
            return render_template("verify_otp.html", email=user.email)

        latest_otp.used = True
        user.is_verified = True
        db.session.commit()
        session.pop("pending_verification_user_id", None)
        session.permanent      = True
        session["logged_in"]   = True
        session["user_id"]     = user.id
        session["user_matric"] = user.matric
        session["user_name"]   = user.full_name
        flash("Email verified successfully. Welcome to your dashboard!", "success")
        return redirect(url_for("dashboard"))

    return render_template("verify_otp.html", email=user.email)


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    user_id = session.get("pending_verification_user_id")
    user = User.query.get(user_id) if user_id else None
    if not user or user.is_verified:
        flash("Please register or log in before requesting a verification code.", "warning")
        return redirect(url_for("login"))

    try:
        issue_email_otp(user)
    except Exception:
        app.logger.exception("Could not resend verification OTP to %s", user.email)
        flash("We could not send a new verification code. Please try again later.", "danger")
        return redirect(url_for("verify_otp"))

    flash("A new verification code has been sent.", "success")
    return redirect(url_for("verify_otp"))

# ─────────────────────────────────────────────────────────────────────────────
#  PASSWORD RESET
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip()
    if not email or not EMAIL_PATTERN.match(email):
        flash("Please enter a valid email address.", "danger")
        return render_template("forgot_password.html")

    user = User.query.filter_by(email=email).first()
    if user:
        PasswordReset.query.filter_by(user_id=user.id, used=False).delete()
        db.session.commit()

        token = secrets.token_urlsafe(64)
        reset = PasswordReset(
            user_id    = user.id,
            token      = token,
            expires_at = datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(reset)
        db.session.commit()

        reset_link = url_for("reset_password", token=token, _external=True)
        flash(f"[DEV MODE] Reset link: {reset_link}", "info")

    flash("If that email exists, a reset link has been sent.", "success")
    return redirect(url_for("login"))


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    reset = PasswordReset.query.filter_by(token=token).first()
    if not reset or not reset.is_valid:
        flash("This reset link is invalid or has expired.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "GET":
        return render_template("reset_password.html", token=token)

    pw         = request.form.get("password",   "")
    pw_confirm = request.form.get("confirm_pw", "")

    if not pw or len(pw) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return render_template("reset_password.html", token=token)

    if pw != pw_confirm:
        flash("Passwords do not match.", "danger")
        return render_template("reset_password.html", token=token)

    user = User.query.get(reset.user_id)
    user.password = generate_password_hash(pw)
    reset.used    = True
    db.session.commit()

    flash("Password reset successfully. You can now log in.", "success")
    return redirect(url_for("login"))

# ─────────────────────────────────────────────────────────────────────────────
#  CALCULATOR — FRESH START
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/calculator", methods=["GET"])
@login_required
def index():
    # Clear any leftover continuation state so it's a clean start
    session.pop("is_continuation",    None)
    session.pop("prev_total_units",   None)
    session.pop("prev_total_points",  None)
    session.pop("prev_semester_count",None)

    user = User.query.get(session.get("user_id"))
    prefill = {
        "name": user.full_name,
        "matric_no": user.matric,
        "programme": user.programme,
        "department": user.department,
        "faculty": user.faculty,
    } if user else None
    return render_template("index.html", step="info", prefill=prefill)

# ─────────────────────────────────────────────────────────────────────────────
#  CONTINUE CALCULATION — add new semesters on top of existing record
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/continue-calculation")
@login_required
def continue_calc():
    user_id = session.get("user_id")

    # Fetch the most recent result for this user
    latest = (CGPAResult.query
              .filter_by(user_id=user_id)
              .order_by(CGPAResult.date_created.desc())
              .first())

    if not latest:
        flash("No previous record found. Please start a fresh calculation.", "warning")
        return redirect(url_for("index"))

    # Pull student info from the last saved record
    student_data = latest.student

    # Store continuation context in session
    session["is_continuation"]     = True
    session["prev_total_units"]     = latest.total_units
    session["prev_total_points"]    = latest.total_points
    session["prev_semester_count"]  = len(latest.semesters)

    # Pre-fill student info so the form is auto-filled
    session["student"] = {
        "name":          student_data.get("name", ""),
        "matric_no":     student_data.get("matric_no", ""),
        "programme":     student_data.get("programme", ""),
        "department":    student_data.get("department", ""),
        "faculty":       student_data.get("faculty", ""),
        "num_semesters": 1,  # default — user will adjust
    }

    flash(
        f"Continuing from your last record — CGPA: {latest.cgpa} "
        f"({latest.total_units} units, {latest.total_points} pts). "
        f"Just enter your NEW semester(s) below.",
        "info"
    )
    return render_template("index.html", step="info", prefill=session["student"], continuation=True)

# ─────────────────────────────────────────────────────────────────────────────
#  SEMESTERS STEP
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
        return render_template("index.html", step="info", prefill=session.get("student"))

    num_semesters, err = parse_positive_int(
        request.form.get("num_semesters"), "Number of semesters"
    )
    if err:
        flash(err, "danger")
        return render_template("index.html", step="info", prefill=session.get("student"))

    session["student"] = {
        "name": name, "matric_no": matric_no, "programme": programme,
        "department": department, "faculty": faculty,
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
    errors = []
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
                               student=student, num_semesters=num_semesters)

    session["course_counts"] = course_counts
    return render_template("index.html", step="semesters",
                           student=student, num_semesters=num_semesters,
                           course_counts=course_counts)

# ─────────────────────────────────────────────────────────────────────────────
#  RESULTS — handles both fresh and continuation
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/results", methods=["POST"])
@login_required
def results():
    student = session.get("student")
    if not student:
        flash("Session expired. Please start again.", "warning")
        return redirect(url_for("index"))

    user_id = session.get("user_id")
    if not user_id:
        session.clear()
        flash("Your session expired. Please log in again.", "danger")
        return redirect(url_for("login"))

    is_continuation    = session.get("is_continuation", False)
    prev_total_units   = session.get("prev_total_units",  0)
    prev_total_points  = session.get("prev_total_points", 0)
    prev_sem_count     = session.get("prev_semester_count", 0)

    num_semesters     = student["num_semesters"]
    semesters_data    = []
    errors            = []
    new_units         = 0
    new_points        = 0

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

            raw_input_mode = request.form.get(
                f"sem_{s}_course_{c}_input_mode", "score"
            ).strip().lower()
            raw_score = request.form.get(f"sem_{s}_course_{c}_score", "").strip()
            raw_grade = request.form.get(f"sem_{s}_course_{c}_grade", "").strip().upper()

            score = None
            grade = None
            gp = None
            input_mode = raw_input_mode if raw_input_mode in ("score", "grade") else "score"

            if input_mode == "score":
                if not raw_score:
                    errors.append(f"Semester {s}, {code}: score is required when Enter Score is selected.")
                    continue
                try:
                    score = int(raw_score)
                    if not (0 <= score <= 100): raise ValueError
                except (ValueError, TypeError):
                    errors.append(f"Semester {s}, {code}: score must be between 0 and 100.")
                    continue
                grade, gp = get_grade_and_point(score)
            else:
                if not raw_grade:
                    errors.append(f"Semester {s}, {code}: grade is required when Enter Grade is selected.")
                    continue
                try:
                    gp, score = get_grade_point_and_rep_score(raw_grade)
                    grade = raw_grade
                except ValueError:
                    errors.append(f"Semester {s}, {code}: invalid grade selected.")
                    continue
            courses_list.append({
                "code": code, "unit": unit, "score": score,
                "grade": grade, "gp": gp, "weighted": unit * gp,
                "input_mode": input_mode,
            })

        # Label new semesters correctly even when continuing
        sem_number = prev_sem_count + s if is_continuation else s

        gpa, sem_units, sem_points = calculate_gpa(courses_list)
        new_units  += sem_units
        new_points += sem_points
        semesters_data.append({
            "number": sem_number, "courses": courses_list,
            "units": sem_units, "points": sem_points, "gpa": gpa,
        })

    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template("index.html", step="semesters",
                               student=student, num_semesters=num_semesters,
                               course_counts=session.get("course_counts", []))

    # ── CUMULATIVE CALCULATION ────────────────────────────────────────────────
    cumulative_units  = prev_total_units  + new_units
    cumulative_points = prev_total_points + new_points

    cgpa = round(cumulative_points / cumulative_units, 2) if cumulative_units > 0 else 0.0

    # ── SAVE TO DATABASE ──────────────────────────────────────────────────────
    new_result = CGPAResult(
        user_id         = user_id,
        cgpa            = cgpa,
        classification  = classify_cgpa(cgpa),
        total_units     = cumulative_units,
        total_points    = cumulative_points,
        semesters_json  = json.dumps(semesters_data),
        student_json    = json.dumps(student),
        is_continuation = is_continuation,
    )
    db.session.add(new_result)
    db.session.commit()

    # Clear continuation flags after saving
    session.pop("is_continuation",    None)
    session.pop("prev_total_units",   None)
    session.pop("prev_total_points",  None)
    session.pop("prev_semester_count",None)

    if is_continuation:
        flash(f"New semester(s) added! Updated CGPA: {cgpa} ({classify_cgpa(cgpa)})", "success")
    else:
        flash("CGPA calculated and saved successfully!", "success")

    return redirect(url_for("profile", result_id=new_result.id))

# ─────────────────────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/home")
@login_required
def dashboard():
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    all_results = (CGPAResult.query
                   .filter_by(user_id=user_id)
                   .order_by(CGPAResult.date_created.desc())
                   .all())
    latest = all_results[0] if all_results else None
    return render_template("dashboard.html", results=all_results, latest=latest,
                           profile_picture=user.profile_picture if user else None)

# ─────────────────────────────────────────────────────────────────────────────
#  PROFILE
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/profile")
@app.route("/profile/<int:result_id>")
@login_required
def profile(result_id=None):
    user_id = session.get("user_id")

    if result_id:
        result = CGPAResult.query.filter_by(id=result_id, user_id=user_id).first()
        if not result:
            flash("Result not found.", "danger")
            return redirect(url_for("dashboard"))
    else:
        result = (CGPAResult.query
                  .filter_by(user_id=user_id)
                  .order_by(CGPAResult.date_created.desc())
                  .first())
        if not result:
            flash("No results found. Please calculate your CGPA first.", "warning")
            return redirect(url_for("index"))

    user = User.query.get(user_id)

    return render_template("profile.html", data={
        "student":           result.student,
        "semesters":         result.semesters,
        "cumulative_units":  result.total_units,
        "cumulative_points": result.total_points,
        "cgpa":              result.cgpa,
        "classification":    result.classification,
        "date":              result.date_display,
        "is_continuation":   result.is_continuation,
        "profile_picture":   user.profile_picture if user else None,
    }, result_id=result.id)


@app.route("/upload-profile-picture", methods=["POST"])
@login_required
def upload_profile_picture():
    user = User.query.get(session.get("user_id"))
    uploaded_file = request.files.get("profile_picture")
    allowed_extensions = {"png", "jpg", "jpeg", "webp"}

    if not user or not uploaded_file or not uploaded_file.filename:
        flash("Please choose a profile picture to upload.", "danger")
        return redirect(url_for("profile"))

    original_name = uploaded_file.filename.lower()
    extension = original_name.rsplit(".", 1)[-1] if "." in original_name else ""
    if extension not in allowed_extensions:
        flash("Profile pictures must be PNG, JPG, JPEG, or WEBP files.", "danger")
        return redirect(url_for("profile"))

    if user.profile_picture:
        old_picture = os.path.join(PROFILE_PICS_DIR, os.path.basename(user.profile_picture))
        if os.path.isfile(old_picture):
            os.remove(old_picture)

    filename = f"user_{user.id}_{secrets.token_hex(16)}.{extension}"
    uploaded_file.save(os.path.join(PROFILE_PICS_DIR, filename))
    user.profile_picture = filename
    db.session.commit()

    flash("Profile picture updated successfully.", "success")
    return redirect(url_for("profile"))

# ─────────────────────────────────────────────────────────────────────────────
#  PDF DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/download-result/<int:result_id>")
@login_required
def download_result(result_id):
    user_id = session.get("user_id")
    result  = CGPAResult.query.filter_by(id=result_id, user_id=user_id).first()

    if not result:
        flash("Result not found or you do not have permission to download it.", "danger")
        return redirect(url_for("dashboard"))

    try:
        pdf_bytes = generate_pdf_bytes(result)
    except Exception as e:
        app.logger.error(f"PDF generation failed for result {result_id}: {e}")
        flash("Could not generate the PDF. Please try again.", "danger")
        return redirect(url_for("profile", result_id=result_id))

    filename = f"CGPA_Result_{result.student.get('matric_no', result_id)}_{result_id}.pdf"
    return send_file(BytesIO(pdf_bytes), mimetype="application/pdf",
                     as_attachment=True, download_name=filename)

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)