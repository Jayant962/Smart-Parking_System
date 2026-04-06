from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets

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

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            return render_template("signup.html", error="Email already registered. Please login.")

        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()

        # Log them in immediately
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


# ── API: Get occupied slots ──
@app.route("/api/occupied-slots")
def occupied_slots():
    active = Booking.query.filter_by(is_active=True).all()
    result = {}
    for b in active:
        key = b.vehicle_type  # "4w" or "2w"
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

    # Double-check slot not taken
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