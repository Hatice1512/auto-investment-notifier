from flask import Flask, render_template, request, redirect, session
from dotenv import load_dotenv
import os
import sqlite3

from stock_service import get_current_price, check_stock_discount
from email_service import send_email

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
STOCK_API_KEY = os.getenv("STOCK_API_KEY")

app = Flask(__name__)
app.secret_key = "SECRET_KEY_CHANGE_LATER"

def get_db():
    return sqlite3.connect("database.db")

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
        """)
        db.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stock TEXT,
            threshold REAL
        )
        """)
        db.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stock TEXT
        )
        """)

init_db()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO users (email, password) VALUES (?, ?)",
                    (email, password)
                )
            return redirect("/login")

        except sqlite3.IntegrityError:
            error = "This email is already registered."

    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        ).fetchone()

        if user:
            session["user_id"] = user[0]
            session["email"] = user[1]
            return redirect("/dashboard")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        stock = request.form["stock"].upper()
        threshold = float(request.form["threshold"])

        db.execute(
            "INSERT INTO alerts (user_id, stock, threshold) VALUES (?, ?, ?)",
            (session["user_id"], stock, threshold)
        )
        db.commit()

    alerts_db = db.execute(
        "SELECT id, stock, threshold FROM alerts WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    alerts = []
    for a in alerts_db:
        alerts.append({
            "id": a[0],
            "stock": a[1],
            "threshold": a[2],
            "price": get_current_price(a[1], STOCK_API_KEY)
        })

    favorites_db = db.execute(
        "SELECT id, stock FROM favorites WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    favorites = []
    for f in favorites_db:
        favorites.append({
            "id": f[0],
            "stock": f[1],
            "price": get_current_price(f[1], STOCK_API_KEY)
        })

    return render_template(
        "dashboard.html",
        alerts=alerts,
        favorites=favorites
    )

@app.route("/add-favorite/<stock>", methods=["POST"])
def add_favorite(stock):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    exists = db.execute(
        "SELECT 1 FROM favorites WHERE user_id=? AND stock=?",
        (session["user_id"], stock)
    ).fetchone()

    if not exists:
        db.execute(
            "INSERT INTO favorites (user_id, stock) VALUES (?, ?)",
            (session["user_id"], stock)
        )
        db.commit()

    return redirect("/dashboard")

@app.route("/remove-favorite/<int:fav_id>", methods=["POST"])
def remove_favorite(fav_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    db.execute(
        "DELETE FROM favorites WHERE id=? AND user_id=?",
        (fav_id, session["user_id"])
    )
    db.commit()

    return redirect("/dashboard")

@app.route("/delete-alert/<int:alert_id>", methods=["POST"])
def delete_alert(alert_id):
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    db.execute(
        "DELETE FROM alerts WHERE id=? AND user_id=?",
        (alert_id, session["user_id"])
    )
    db.commit()

    return redirect("/dashboard")

@app.route("/check-alerts")
def check_alerts():
    db = get_db()
    rows = db.execute("""
        SELECT alerts.stock, alerts.threshold, users.email
        FROM alerts
        JOIN users ON alerts.user_id = users.id
    """).fetchall()

    for stock, threshold, email in rows:
        result = check_stock_discount(stock, threshold, STOCK_API_KEY)
        if result:
            send_email(
                EMAIL_ADDRESS,
                EMAIL_APP_PASSWORD,
                email,
                result
            )

    return "Alerts checked"

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)