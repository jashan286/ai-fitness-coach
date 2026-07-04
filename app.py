"""
AI-Fitness-Coach
A Flask web app with user auth, BMI calculator, calorie calculator,
workout planner, and a rule-based fitness chatbot.
"""

import os
import random
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# Uses Postgres in production (Render sets DATABASE_URL automatically once
# you attach a Postgres database) and falls back to local SQLite when
# running on your own PC, where DATABASE_URL isn't set.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'fitness.db')}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ----------------------------------------------------------------------
# Groq (Llama) API setup
# ----------------------------------------------------------------------
# PASTE YOUR REAL GROQ KEY between the quotes below.
# Get a free key at: https://console.groq.com/keys (no credit card needed)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "gsk_your-actual-groq-key-here")

# Model used for the chatbot. llama-3.3-70b-versatile is a strong free
# general-purpose model on Groq's free tier.
GROQ_MODEL = "llama-3.3-70b-versatile"

groq_client = None
if GROQ_API_KEY and not GROQ_API_KEY.startswith("gsk_your-actual"):
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("[DEBUG] Groq client initialized.")
else:
    print("[DEBUG] Groq client NOT initialized — paste a real key into GROQ_API_KEY.")

CHATBOT_SYSTEM_PROMPT = (
    "You are an encouraging, knowledgeable AI fitness coach inside a web app "
    "called AI Fitness Coach. Give practical, concise advice about workouts, "
    "nutrition, weight loss/gain, motivation, sleep, and hydration.\n\n"
    "FORMAT YOUR ANSWERS LIKE THIS:\n"
    "- Start with one short sentence introducing the answer.\n"
    "- Then give 3-6 bullet points, each starting with '- ', one clear tip per line.\n"
    "- Use **bold** on 1-3 key words per bullet (e.g. key numbers or actions).\n"
    "- Keep each bullet to a single short sentence. No long paragraphs.\n"
    "- Optionally end with one short closing sentence of encouragement.\n\n"
    "Avoid medical diagnoses and recommend consulting a doctor for injuries "
    "or medical conditions. Keep a warm, motivating tone."
)

# In-memory chat history per user session (resets when the server restarts).
# Key: user_id -> list of {"role": ..., "content": ...} messages.
chat_histories = {}


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Record(db.Model):
    """Stores BMI / calorie / workout history per user."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    record_type = db.Column(db.String(20))  # 'bmi', 'calories', 'workout'
    summary = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ----------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------
def login_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.name
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    chat_histories.pop(session.get("user_id"), None)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# Protected pages
# ----------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    recent = (
        Record.query.filter_by(user_id=user.id)
        .order_by(Record.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template("dashboard.html", recent=recent)


@app.route("/bmi", methods=["GET", "POST"])
@login_required
def bmi():
    result = None
    if request.method == "POST":
        try:
            weight = float(request.form.get("weight"))  # kg
            height_cm = float(request.form.get("height"))  # cm
            height_m = height_cm / 100
            bmi_value = round(weight / (height_m ** 2), 1)

            if bmi_value < 18.5:
                category = "Underweight"
            elif bmi_value < 25:
                category = "Normal weight"
            elif bmi_value < 30:
                category = "Overweight"
            else:
                category = "Obese"

            result = {"bmi": bmi_value, "category": category}

            record = Record(
                user_id=session["user_id"],
                record_type="bmi",
                summary=f"BMI {bmi_value} ({category})",
            )
            db.session.add(record)
            db.session.commit()
        except (TypeError, ValueError):
            flash("Please enter valid numbers for weight and height.", "danger")

    return render_template("bmi.html", result=result)


@app.route("/calories", methods=["GET", "POST"])
@login_required
def calories():
    result = None
    if request.method == "POST":
        try:
            gender = request.form.get("gender")
            age = float(request.form.get("age"))
            weight = float(request.form.get("weight"))  # kg
            height_cm = float(request.form.get("height"))  # cm
            activity = request.form.get("activity")
            goal = request.form.get("goal")

            # Mifflin-St Jeor Equation
            if gender == "male":
                bmr = 10 * weight + 6.25 * height_cm - 5 * age + 5
            else:
                bmr = 10 * weight + 6.25 * height_cm - 5 * age - 161

            activity_multipliers = {
                "sedentary": 1.2,
                "light": 1.375,
                "moderate": 1.55,
                "active": 1.725,
                "very_active": 1.9,
                "extra_active": 2.0,
            }
            maintenance = bmr * activity_multipliers.get(activity, 1.2)

            goal_adjustments = {
                "lose_fast": -750,
                "lose": -500,
                "lose_mild": -250,
                "maintain": 0,
                "gain_mild": 250,
                "gain": 500,
                "gain_fast": 750,
            }
            goal_labels = {
                "lose_fast": "Lose Weight (Fast)",
                "lose": "Lose Weight",
                "lose_mild": "Lose Weight (Mild)",
                "maintain": "Maintain Weight",
                "gain_mild": "Gain Weight (Mild)",
                "gain": "Gain Weight",
                "gain_fast": "Gain Weight (Fast)",
            }
            target_calories = round(maintenance + goal_adjustments.get(goal, 0))
            goal_display = goal_labels.get(goal, goal)

            result = {
                "bmr": round(bmr),
                "maintenance": round(maintenance),
                "target": target_calories,
                "goal": goal_display,
            }

            record = Record(
                user_id=session["user_id"],
                record_type="calories",
                summary=f"Target {target_calories} kcal/day ({goal_display})",
            )
            db.session.add(record)
            db.session.commit()
        except (TypeError, ValueError):
            flash("Please enter valid numbers.", "danger")

    return render_template("calories.html", result=result)


WORKOUT_PLANS = {
    "lose_weight": {
        "title": "Fat Loss Circuit",
        "days": [
            ("Monday", ["Jumping jacks - 3x30s", "Bodyweight squats - 3x15", "Mountain climbers - 3x30s", "Plank - 3x30s"]),
            ("Tuesday", ["Brisk walk/jog - 30 min", "Burpees - 3x10", "Lunges - 3x12/leg"]),
            ("Wednesday", ["Rest or light stretching"]),
            ("Thursday", ["Jump rope - 10 min", "Push-ups - 3x12", "Squat jumps - 3x15"]),
            ("Friday", ["Cycling/brisk walk - 30 min", "Plank - 3x40s", "Bicycle crunches - 3x20"]),
            ("Saturday", ["Full body HIIT - 20 min"]),
            ("Sunday", ["Rest"]),
        ],
    },
    "build_muscle": {
        "title": "Muscle Building Split",
        "days": [
            ("Monday", ["Push-ups - 4x12", "Bench press / dumbbell press - 4x10", "Shoulder press - 3x10"]),
            ("Tuesday", ["Pull-ups / rows - 4x10", "Bicep curls - 3x12", "Deadlifts - 4x8"]),
            ("Wednesday", ["Rest or mobility work"]),
            ("Thursday", ["Squats - 4x10", "Lunges - 3x12/leg", "Leg press - 4x10"]),
            ("Friday", ["Core circuit - planks, leg raises, crunches - 3 rounds"]),
            ("Saturday", ["Full body strength - 45 min"]),
            ("Sunday", ["Rest"]),
        ],
    },
    "stay_fit": {
        "title": "General Fitness Maintenance",
        "days": [
            ("Monday", ["Full body workout - 30 min"]),
            ("Tuesday", ["Cardio - 25 min", "Stretching - 10 min"]),
            ("Wednesday", ["Yoga / mobility - 30 min"]),
            ("Thursday", ["Strength training - 30 min"]),
            ("Friday", ["Cardio - 25 min"]),
            ("Saturday", ["Light activity - walk, swim, or sport"]),
            ("Sunday", ["Rest"]),
        ],
    },
    "improve_endurance": {
        "title": "Endurance Builder",
        "days": [
            ("Monday", ["Steady-state jog/cycle - 30 min", "Core circuit - 10 min"]),
            ("Tuesday", ["Interval sprints - 8x30s on/90s off", "Stretching - 10 min"]),
            ("Wednesday", ["Active recovery walk - 20 min", "Mobility work - 10 min"]),
            ("Thursday", ["Tempo run/cycle - 35 min"]),
            ("Friday", ["Circuit training - jump rope, burpees, mountain climbers - 3 rounds"]),
            ("Saturday", ["Long steady cardio - 45-60 min (run, swim, or cycle)"]),
            ("Sunday", ["Rest or light yoga"]),
        ],
    },
    "flexibility": {
        "title": "Flexibility & Mobility",
        "days": [
            ("Monday", ["Full body stretching routine - 25 min", "Deep breathing - 5 min"]),
            ("Tuesday", ["Yoga flow (sun salutations) - 30 min"]),
            ("Wednesday", ["Foam rolling - 15 min", "Hip & shoulder mobility drills - 15 min"]),
            ("Thursday", ["Dynamic stretching - 20 min", "Light walk - 15 min"]),
            ("Friday", ["Yoga flow (focus: hamstrings & back) - 30 min"]),
            ("Saturday", ["Full body stretch + foam rolling - 30 min"]),
            ("Sunday", ["Rest or gentle stretching"]),
        ],
    },
}


@app.route("/workout", methods=["GET", "POST"])
@login_required
def workout():
    plan = None
    if request.method == "POST":
        goal = request.form.get("goal", "stay_fit")
        plan = WORKOUT_PLANS.get(goal, WORKOUT_PLANS["stay_fit"])

        record = Record(
            user_id=session["user_id"],
            record_type="workout",
            summary=f"Generated plan: {plan['title']}",
        )
        db.session.add(record)
        db.session.commit()

    return render_template("workout.html", plan=plan)


@app.route("/chatbot")
@login_required
def chatbot():
    return render_template("chatbot.html")


# ----------------------------------------------------------------------
# Rule-based fitness chatbot API
# ----------------------------------------------------------------------
CHATBOT_RESPONSES = {
    "greeting": [
        "Hey there! I'm your AI Fitness Coach. Ask me about workouts, diet, or motivation!",
        "Hi! Ready to crush your fitness goals today?",
    ],
    "bmi": [
        "You can calculate your BMI on the BMI page. A healthy BMI range is typically 18.5-24.9.",
    ],
    "diet": [
        "Focus on whole foods: lean protein, vegetables, fruits, and whole grains. Stay hydrated and avoid excess sugar.",
        "A good rule of thumb: fill half your plate with vegetables, a quarter with protein, and a quarter with whole grains.",
    ],
    "weight_loss": [
        "For weight loss, aim for a calorie deficit of about 500 kcal/day combined with regular cardio and strength training.",
    ],
    "muscle_gain": [
        "To build muscle, eat in a slight calorie surplus, prioritize protein (about 1.6-2.2g per kg bodyweight), and follow a progressive strength program.",
    ],
    "motivation": [
        "Remember: consistency beats intensity. Small steps every day add up to big results!",
        "You don't have to be extreme, just consistent. Keep going!",
    ],
    "workout": [
        "Check out the Workout page for a personalized plan based on your goal.",
    ],
    "water": [
        "Aim for about 2-3 liters of water per day, more if you're very active or it's hot out.",
    ],
    "sleep": [
        "Aim for 7-9 hours of quality sleep. Recovery is when your muscles actually grow and repair.",
    ],
    "default": [
        "I'm not sure about that yet, but I can help with workouts, diet tips, BMI, calories, or motivation!",
    ],
}

KEYWORD_MAP = {
    "greeting": ["hi", "hello", "hey"],
    "bmi": ["bmi", "body mass"],
    "diet": ["diet", "food", "eat", "nutrition", "meal"],
    "weight_loss": ["lose weight", "fat loss", "cutting", "lose fat"],
    "muscle_gain": ["muscle", "bulk", "gain weight", "strength"],
    "motivation": ["motivat", "tired", "give up", "lazy"],
    "workout": ["workout", "exercise", "routine", "training plan"],
    "water": ["water", "hydrate", "hydration"],
    "sleep": ["sleep", "rest", "recovery"],
}


def classify_message(message: str) -> str:
    text = message.lower()
    for intent, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in text:
                return intent
    return "default"


@app.route("/api/chatbot", methods=["POST"])
@login_required
def api_chatbot():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"reply": "Say something and I'll do my best to help!"})

    # If no API key has been set, fall back to the simple rule-based bot.
    if groq_client is None:
        intent = classify_message(message)
        reply = random.choice(CHATBOT_RESPONSES.get(intent, CHATBOT_RESPONSES["default"]))
        return jsonify({"reply": reply, "source": "rule-based"})

    user_id = session["user_id"]
    history = chat_histories.setdefault(user_id, [])
    history.append({"role": "user", "content": message})

    # Keep only the last 10 messages so requests stay small and fast.
    trimmed_history = history[-10:]

    # Groq uses the OpenAI-style format: system prompt goes in the
    # messages list itself, not as a separate parameter.
    groq_messages = [{"role": "system", "content": CHATBOT_SYSTEM_PROMPT}] + trimmed_history

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=400,
            messages=groq_messages,
        )
        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        return jsonify({"reply": reply, "source": "groq"})
    except Exception as e:
        # Print the real error to the terminal so it's easy to diagnose
        # (e.g. invalid API key, rate limit, wrong model name, etc).
        print(f"[ERROR] Groq API call failed: {e}")
        # Remove the failed user message so it doesn't corrupt history next turn.
        history.pop()
        return jsonify({
            "reply": "Sorry, I couldn't reach the AI right now. Please check "
                      "your API key or try again in a moment.",
            "source": "error",
        }), 200


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_local = os.environ.get("RENDER") is None

    if is_local and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        import threading
        import webbrowser
        threading.Timer(1.25, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    app.run(host="0.0.0.0", port=port, debug=is_local)
