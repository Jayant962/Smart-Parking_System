from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# DATABASE CONFIG
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ── MODELS ──

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    bookings = db.relationship('Booking', backref='user', lazy=True)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slot_id = db.Column(db.String(10), nullable=False)        # e.g. "A3"
    vehicle_type = db.Column(db.String(5), nullable=False)    # "4w" or "2w"
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)          # None = flexible
    end_type = db.Column(db.String(10), nullable=False)       # "fixed" / "flexible"
    advance_paid = db.Column(db.Integer, nullable=False)
    booking_ref = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)           # False when checked out


# ── ROUTES ──

@app.route("/")
def start():
    return redirect("/login")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if User.query.filter_by(email=email).first():
            return render_template("signup.html", error="Email already registered. Please login.")

        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        session['user_id'] = new_user.id
        session['user_name'] = new_user.name
        return redirect("/booking")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email, password=password).first()

        if user:
            session['user_id'] = user.id
            session['user_name'] = user.name
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
    return render_template("booking.html", user_name=session.get('user_name', ''))


# ── FORGOT PASSWORD ──

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            return render_template("forgot_password.html",
                                   error="No account found with that email address.")

        try:
            sender_email = os.environ.get("MAIL_USER")   # your Gmail address
            sender_pass  = os.environ.get("MAIL_PASS")   # your Gmail App Password

            if not sender_email or not sender_pass:
                return render_template("forgot_password.html",
                                       error="Mail service is not configured. Contact support.")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = "SmartPark — Password Recovery"
            msg["From"]    = sender_email
            msg["To"]      = email

            html_body = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0b1622;font-family:'DM Sans',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:40px 20px;">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#111e2d;border-radius:16px;
                      border:1px solid rgba(10,132,255,0.2);
                      padding:36px 40px;">
          <tr>
            <td>
              <!-- Brand -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
                <tr>
                  <td style="background:#0a84ff;width:36px;height:36px;border-radius:9px;
                              text-align:center;vertical-align:middle;">
                    <span style="color:#fff;font-weight:700;font-size:14px;">P</span>
                  </td>
                  <td style="padding-left:10px;font-size:18px;letter-spacing:2px;
                              color:#ddeeff;font-weight:700;">
                    SMART<span style="color:#30b0ff;">PARK</span>
                  </td>
                </tr>
              </table>

              <h2 style="color:#ddeeff;font-size:22px;margin:0 0 6px 0;">
                Password Recovery
              </h2>
              <p style="color:#5a7a9a;font-size:13px;margin:0 0 24px 0;">
                Hi <strong style="color:#ddeeff;">{user.name}</strong>, here is your password as requested.
              </p>

              <!-- Password box -->
              <div style="background:#0b1622;border:1px solid rgba(10,132,255,0.35);
                          border-radius:12px;padding:18px 24px;margin-bottom:24px;
                          text-align:center;">
                <p style="color:#5a7a9a;font-size:10px;letter-spacing:1px;
                           text-transform:uppercase;margin:0 0 8px 0;">YOUR PASSWORD</p>
                <p style="color:#fff;font-size:22px;letter-spacing:3px;
                           font-weight:600;margin:0;">{user.password}</p>
              </div>

              <p style="color:#5a7a9a;font-size:12px;line-height:1.6;margin:0 0 20px 0;">
                If you did not request this, please ignore this email.
                For security, consider changing your password after logging in.
              </p>

              <!-- CTA button -->
              <a href="http://127.0.0.1:5000/login"
                 style="display:inline-block;background:linear-gradient(135deg,#30b0ff,#0a84ff);
                         color:#fff;text-decoration:none;padding:12px 28px;
                         border-radius:10px;font-size:14px;font-weight:700;
                         letter-spacing:.3px;">
                Login to SmartPark →
              </a>

              <hr style="border:none;border-top:1px solid rgba(30,100,180,0.15);margin:28px 0 16px 0;">
              <p style="color:#3a5a7a;font-size:11px;margin:0;">
                © SmartPark. This is an automated message, please do not reply.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
            """

            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender_email, sender_pass)
                server.sendmail(sender_email, email, msg.as_string())

            return render_template("forgot_password.html", success=True, email=email)

        except smtplib.SMTPAuthenticationError:
            return render_template("forgot_password.html",
                                   error="Mail authentication failed. Check MAIL_USER and MAIL_PASS env vars.")
        except Exception as e:
            return render_template("forgot_password.html",
                                   error=f"Could not send email: {str(e)}")

    return render_template("forgot_password.html")


# ── API: Get occupied slots ──
@app.route("/api/occupied-slots")
def occupied_slots():
    active = Booking.query.filter_by(is_active=True).all()
    result = {}
    for b in active:
        key = b.vehicle_type
        if key not in result:
            result[key] = []
        result[key].append(b.slot_id)
    return jsonify(result)


# ── API: Confirm booking ──
@app.route("/api/book", methods=["POST"])
def book_slot():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    slot_id = data.get("slot_id")
    vehicle_type = data.get("vehicle_type")
    start_str = data.get("start_time")
    end_str = data.get("end_time")
    end_type = data.get("end_type")
    advance = data.get("advance_paid")

    existing = Booking.query.filter_by(slot_id=slot_id, vehicle_type=vehicle_type, is_active=True).first()
    if existing:
        return jsonify({"error": "Slot already taken"}), 409

    start_time = datetime.fromisoformat(start_str)
    end_time = datetime.fromisoformat(end_str) if end_str else None

    ref = "SP" + secrets.token_hex(3).upper()

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

    return jsonify({"success": True, "booking_ref": ref})


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)