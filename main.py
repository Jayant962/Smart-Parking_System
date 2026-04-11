from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import random
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── ADMIN CREDENTIALS ──
ADMIN_EMAIL    = "admin@gmail.com"
ADMIN_PASSWORD = "smartpark@123"

# ── PRICING ──
RATE_PER_HOUR = 10  # ₹10 per hour


# ── HELPERS ──
def generate_user_code():
    """Generate a short readable user ID like USR-4821"""
    while True:
        code = "USR-" + str(random.randint(1000, 9999))
        if not User.query.filter_by(user_code=code).first():
            return code


def send_booking_email(user, booking, vehicle_type, start_time, end_time, end_type, advance, ref):
    sender_email = os.environ.get("MAIL_USER")
    sender_pass  = os.environ.get("MAIL_PASS")
    if not sender_email or not sender_pass:
        return

    vehicle_label = "4-Wheeler" if vehicle_type == "4w" else "2-Wheeler"
    start_fmt = start_time.strftime("%d %b %Y, %I:%M %p")
    end_fmt   = "Flexible (exit within 24 hrs)" if end_type == "flexible" or not end_time else end_time.strftime("%d %b %Y, %I:%M %p")

    body = f"""Hi {user.name},

Your SmartPark booking is confirmed!

  Booking Ref : {ref}
  User ID     : {user.user_code}
  Slot        : {booking.slot_id}
  Vehicle     : {vehicle_label}
  Start       : {start_fmt}
  End         : {end_fmt}
  Advance Paid: Rs.{advance}

Show your User ID ({user.user_code}) to the guard on entry & exit.
Balance will be settled at exit based on actual hours parked.

— SmartPark Team
"""

    msg = MIMEMultipart()
    msg["Subject"] = f"SmartPark Booking Confirmed — {ref}"
    msg["From"]    = sender_email
    msg["To"]      = user.email
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_pass)
        server.sendmail(sender_email, user.email, msg.as_string())


# ── MODELS ──

class User(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_code = db.Column(db.String(10), unique=True, nullable=False)
    name      = db.Column(db.String(100), nullable=False)
    email     = db.Column(db.String(100), unique=True, nullable=False)
    password  = db.Column(db.String(100), nullable=False)
    bookings  = db.relationship('Booking', backref='user', lazy=True)


class Booking(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slot_id      = db.Column(db.String(10), nullable=False)
    vehicle_type = db.Column(db.String(5), nullable=False)
    start_time   = db.Column(db.DateTime, nullable=False)
    end_time     = db.Column(db.DateTime, nullable=True)
    end_type     = db.Column(db.String(10), nullable=False)
    advance_paid = db.Column(db.Integer, nullable=False)
    booking_ref  = db.Column(db.String(20), unique=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    is_active    = db.Column(db.Boolean, default=True)


# ── ROUTES ──

@app.route("/")
def start():
    return redirect("/login")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if User.query.filter_by(email=email).first():
            return render_template("signup.html", error="Email already registered. Please login.")

        user_code = generate_user_code()
        new_user  = User(user_code=user_code, name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        session['user_id']   = new_user.id
        session['user_name'] = new_user.name
        session['user_code'] = new_user.user_code
        return redirect("/booking")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect("/admin")

        user = User.query.filter_by(email=email, password=password).first()
        if user:
            session['user_id']   = user.id
            session['user_name'] = user.name
            session['user_code'] = user.user_code
            return redirect("/booking")
        else:
            return render_template("login.html", error="Invalid email or password. Please try again.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/booking")
def booking():
    if 'user_id' not in session:
        return redirect("/login")
    return render_template("booking.html",
                           user_name=session.get('user_name', ''),
                           user_code=session.get('user_code', ''))


# ── ADMIN ──

@app.route("/admin")
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect("/login")
    return render_template("admin_dashboard.html")


@app.route("/api/admin/booking-details")
def admin_booking_details():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403

    query = request.args.get("q", "").strip().upper()
    if not query:
        return jsonify({"error": "No query provided"}), 400

    booking = None

    # 1. Try booking_ref
    booking = Booking.query.filter_by(booking_ref=query, is_active=True).first()

    # 2. Try slot_id
    if not booking:
        booking = Booking.query.filter_by(slot_id=query, is_active=True).first()

    # 3. Try user_code — return latest active booking for that user
    if not booking:
        user = User.query.filter_by(user_code=query).first()
        if user:
            booking = (Booking.query
                       .filter_by(user_id=user.id, is_active=True)
                       .order_by(Booking.created_at.desc())
                       .first())

    if not booking:
        return jsonify({"error": "No active booking found. Try User Code (USR-XXXX), Booking Ref, or Slot ID."}), 404

    user = User.query.get(booking.user_id)

    now           = datetime.utcnow()
    hours_parked  = max((now - booking.start_time).total_seconds() / 3600, 0)
    total_amount  = round(hours_parked * RATE_PER_HOUR, 2)
    remaining     = max(round(total_amount - booking.advance_paid, 2), 0)

    return jsonify({
        "booking_ref":      booking.booking_ref,
        "slot_id":          booking.slot_id,
        "vehicle_type":     booking.vehicle_type,
        "user_code":        user.user_code if user else "—",
        "user_name":        user.name if user else "Unknown",
        "user_email":       user.email if user else "Unknown",
        "start_time":       booking.start_time.isoformat(),
        "end_time":         booking.end_time.isoformat() if booking.end_time else None,
        "end_type":         booking.end_type,
        "advance_paid":     booking.advance_paid,
        "rate_per_hour":    RATE_PER_HOUR,
        "hours_parked":     round(hours_parked, 4),
        "total_amount":     total_amount,
        "remaining_amount": remaining,
        "server_time":      now.isoformat()
    })


@app.route("/api/admin/checkout", methods=["POST"])
def admin_checkout():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    ref  = data.get("booking_ref", "").strip().upper()

    booking = Booking.query.filter_by(booking_ref=ref, is_active=True).first()
    if not booking:
        return jsonify({"error": "Booking not found or already checked out"}), 404

    booking.is_active = False
    booking.end_time  = datetime.utcnow()
    db.session.commit()

    return jsonify({"success": True, "message": f"Booking {ref} checked out."})


# ── FORGOT PASSWORD ──

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user  = User.query.filter_by(email=email).first()

        if not user:
            return render_template("forgot_password.html",
                                   error="No account found with that email address.")
        try:
            sender_email = os.environ.get("MAIL_USER")
            sender_pass  = os.environ.get("MAIL_PASS")

            if not sender_email or not sender_pass:
                return render_template("forgot_password.html",
                                       error="Mail service is not configured. Contact support.")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "SmartPark — Password Recovery"
            msg["From"]    = sender_email
            msg["To"]      = email

            body = f"""Hi {user.name},

Your SmartPark login details:

Password : {user.password}
User Code: {user.user_code}

— SmartPark Team
"""
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender_email, sender_pass)
                server.sendmail(sender_email, email, msg.as_string())

            return render_template("forgot_password.html", success=True, email=email)

        except smtplib.SMTPAuthenticationError:
            return render_template("forgot_password.html",
                                   error="Mail authentication failed.")
        except Exception as e:
            return render_template("forgot_password.html",
                                   error=f"Could not send email: {str(e)}")

    return render_template("forgot_password.html")


# ── API: Occupied slots ──
@app.route("/api/occupied-slots")
def occupied_slots():
    active = Booking.query.filter_by(is_active=True).all()
    result = {}
    for b in active:
        result.setdefault(b.vehicle_type, []).append(b.slot_id)
    return jsonify(result)


# ── API: Book slot ──
@app.route("/api/book", methods=["POST"])
def book_slot():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    data         = request.get_json()
    slot_id      = data.get("slot_id")
    vehicle_type = data.get("vehicle_type")
    start_str    = data.get("start_time")
    end_str      = data.get("end_time")
    end_type     = data.get("end_type")
    advance      = data.get("advance_paid")

    existing = Booking.query.filter_by(slot_id=slot_id, vehicle_type=vehicle_type, is_active=True).first()
    if existing:
        return jsonify({"error": "Slot already taken"}), 409

    start_time = datetime.fromisoformat(start_str)
    end_time   = datetime.fromisoformat(end_str) if end_str else None
    ref        = "SP" + secrets.token_hex(3).upper()

    new_booking = Booking(
        user_id=session['user_id'],
        slot_id=slot_id,
        vehicle_type=vehicle_type,
        start_time=start_time,
        end_time=end_time,
        end_type=end_type,
        advance_paid=advance,
        booking_ref=ref,
        is_active=True
    )
    db.session.add(new_booking)
    db.session.commit()

    user = User.query.get(session['user_id'])

    # ── Send booking slip email (non-fatal) ──
    try:
        send_booking_email(user, new_booking, vehicle_type, start_time, end_time, end_type, advance, ref)
    except Exception as e:
        print(f"[Email] Failed to send booking slip: {e}")

    return jsonify({"success": True, "booking_ref": ref, "user_code": user.user_code if user else ""})


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)