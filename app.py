# app.py
from flask import (
    Flask, request, jsonify, render_template, redirect, url_for, session,
    send_file, flash
)
from collections import deque
import time, os, csv, io, joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask_sqlalchemy import SQLAlchemy
import smtplib
from email.mime.text import MIMEText
from twilio.rest import Client

# -----------------------
# Config
# -----------------------
app = Flask(__name__)
EMAIL_SENDER = "your email"
EMAIL_PASSWORD = "your password"   # Gmail App Password
EMAIL_RECEIVER = "your email"

TWILIO_SID = "your sid"
TWILIO_TOKEN = "your token"
TWILIO_FROM = "twilio phone number"
TWILIO_TO = "your phone number"

APP_SECRET = "replace_with_strong_secret"
ADMIN_PASSWORD = "ccp2"
SENSOR_API_KEY = "your api key"  # must match esp32 apiKey
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs("instance", exist_ok=True)

app.secret_key = APP_SECRET
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(DB_DIR, 'crops.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -----------------------
# DB models
# -----------------------
class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    soil = db.Column(db.Integer, nullable=False)
    soil_status = db.Column(db.String(16), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey('sensor_reading.id'), nullable=True)
    message = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# -----------------------
# Alerts
# -----------------------
def send_email_alert(message):
    try:
        msg = MIMEText(message)
        msg['Subject'] = "🚨 Smart Farming Alert"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ Email alert sent")
    except Exception as e:
        print("❌ Email failed:", e)

def send_sms_alert(message):
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body="🚨 Smart Farming Alert: " + message,
            from_=TWILIO_FROM,
            to=TWILIO_TO
        )
        print("✅ SMS alert sent")
    except Exception as e:
        print("❌ SMS failed:", e)

def create_alert_if_needed(reading: SensorReading):
    try:
        soil_threshold = 25
        if reading.soil < soil_threshold:
            msg = f"Low soil moisture: {reading.soil}% at {reading.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            alert = Alert(reading_id=reading.id, message=msg)
            db.session.add(alert)
            db.session.commit()
            send_email_alert(msg)
            send_sms_alert(msg)
            return True
    except Exception as e:
        print("Alert check failed:", e)
    return False

# -----------------------
# Models for Price Prediction (load existing)
# -----------------------
def get_crop_names():
    if not os.path.exists('models'):
        return []
    model_files = [f for f in os.listdir('models') if f.endswith('_model.pkl') or f.endswith('_rainfall_model.pkl')]
    crop_names = []
    for f in model_files:
        if f.endswith('_rainfall_model.pkl'):
            crop_names.append(f.split('_rainfall_model.pkl')[0])
        else:
            crop_names.append(f.split('_model.pkl')[0])
    return [name for name in crop_names if not name.endswith('_rainfall')]

def load_models():
    models = {}
    thresholds = {}
    future_predictions = {}
    crop_names = get_crop_names()
    for crop in crop_names:
        rainfall_model_path = f'models/{crop}_rainfall_model.pkl'
        threshold_path = f'models/{crop}_thresholds.pkl'
        future_pred_path = f'models/{crop}_future_predictions.pkl'
        if os.path.exists(rainfall_model_path):
            try:
                models[crop] = joblib.load(rainfall_model_path)
            except Exception as e:
                print(f"⚠️ Failed to load {rainfall_model_path}: {e}")
            thresholds[crop] = joblib.load(threshold_path) if os.path.exists(threshold_path) else None
            future_predictions[crop] = joblib.load(future_pred_path) if os.path.exists(future_pred_path) else None
    return models, thresholds, future_predictions, crop_names

models, thresholds, future_predictions, crop_names = load_models()

# -----------------------
# In-memory cache (includes heat_index)
# -----------------------
latest_data = {"temperature": 0.0, "humidity": 0.0, "soil": 0, "soil_status": "Unknown", "heat_index": None, "time": None}
history_cache = deque(maxlen=200)  # recent entries (with heat_index & local time)

# -----------------------
# Crop recommendation helper
# -----------------------
def recommend_crop(temp, hum, soil, soil_status):
    if soil_status == "Wet" and soil > 70 and hum > 50 and 20 < temp < 35:
        return {"name":"Rice 🌾","details":"Rice grows well in clayey soil with standing water.","dos":["Maintain water levels","Split N applications"],"donts":["Avoid sandy soils","Avoid drought during establishment"]}
    if soil_status == "Dry" and soil > 50 and hum < 60 and 18 < temp < 30:
        return {"name":"Wheat 🌱","details":"Wheat prefers loamy soil and moderate watering.","dos":["Ensure drainage","Apply phosphorus"],"donts":["Avoid waterlogging","Don't over-irrigate"]}
    if soil > 40 and hum > 40 and 22 < temp < 28:
        return {"name":"Maize 🌽","details":"Maize needs consistent moisture and full sun.","dos":["Irrigate at flowering","Control weeds early"],"donts":["Avoid acidic soils","Don't crowd plants"]}
    if soil < 30 and temp > 25:
        return {"name":"Millet 🌿","details":"Millet is drought-resistant and suited for poor soils.","dos":["Plant drought tolerant varieties","Use mulch"],"donts":["Avoid waterlogging","Don't over-fertilize"]}
    return {"name":"Potato 🥔","details":"Potatoes prefer loose, well-draining soils.","dos":["Keep soil cool and moist","Practice crop rotation"],"donts":["Avoid compacted soils","Don't let fields waterlog"]}

# -----------------------
# Routes
# -----------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/sensor", methods=["POST"])
def sensor():
    # API-key check
    api_key = request.headers.get("X-API-KEY", "")
    if api_key != SENSOR_API_KEY:
        return jsonify({"status":"error","message":"unauthorized"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status":"error","message":"invalid json"}), 400

    # Accept multiple key names for compatibility
    try:
        temp = float(data.get("temperature", data.get("temp", 0.0)))
        hum = float(data.get("humidity", data.get("hum", 0.0)))
        # prefer 'soil' otherwise use 'soil_analog'
        soil = int(data.get("soil") if data.get("soil") is not None else data.get("soil_analog", 0))
        # prefer 'soil_status' otherwise 'soil_digital'
        soil_status = data.get("soil_status") or data.get("soil_digital") or "Unknown"
        heat_index = None
        # accept heat_index if sent
        if "heat_index" in data:
            try:
                heat_index = float(data.get("heat_index"))
            except:
                heat_index = None
    except Exception:
        return jsonify({"status":"error","message":"bad values"}), 400

    # store UTC now in DB but return local IST strings
    now_utc = datetime.utcnow()
    reading = SensorReading(temperature=temp, humidity=hum, soil=soil, soil_status=soil_status, timestamp=now_utc)
    db.session.add(reading)
    db.session.commit()

    # Create local IST timestamp string
    try:
        local_str = now_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # fallback naive formatting if zoneinfo not available
        local_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    # update caches (include heat_index if present)
    entry = {
        "temperature": round(temp, 1),
        "humidity": round(hum, 0),
        "soil": soil,
        "soil_status": soil_status,
        "heat_index": (round(heat_index,1) if heat_index is not None else None),
        "time": local_str
    }
    latest_data.update(entry)
    history_cache.appendleft(entry)

    # create alert & notifications if threshold crosses
    create_alert_if_needed(reading)

    return jsonify({"status":"ok"})

@app.route("/latest-sensor")
def latest_sensor():
    # ensure 'time' is present (already IST when sensor posted)
    return jsonify(latest_data)

@app.route("/history")
def get_history():
    # Prefer in-memory recent cache (includes heat_index & local times)
    if len(history_cache) > 0:
        return jsonify(list(history_cache))
    # fallback to DB rows (convert UTC to IST)
    rows = SensorReading.query.order_by(SensorReading.timestamp.desc()).limit(200).all()
    out = []
    for r in rows:
        ts = r.timestamp
        if ts is None:
            tstr = ""
        else:
            try:
                # treat stored timestamp as UTC if naive
                if ts.tzinfo is None:
                    ts_utc = ts.replace(tzinfo=timezone.utc)
                else:
                    ts_utc = ts
                local = ts_utc.astimezone(ZoneInfo("Asia/Kolkata"))
                tstr = local.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                tstr = r.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        out.append({
            "temperature": r.temperature,
            "humidity": r.humidity,
            "soil": r.soil,
            "soil_status": r.soil_status,
            "heat_index": None,      # DB lacks heat_index column; history_cache will have it for recent entries
            "time": tstr
        })
    return jsonify(out)

# existing admin/download endpoints remain unchanged (admin-protected download)
@app.route("/download-history")
def download_history():
    # admin only - simple session auth
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin"))
    rows = SensorReading.query.order_by(SensorReading.timestamp.desc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["timestamp","temperature","humidity","soil","soil_status"])
    for r in rows:
        # convert to IST for download as well
        ts = r.timestamp
        try:
            if ts.tzinfo is None:
                ts_utc = ts.replace(tzinfo=timezone.utc)
            else:
                ts_utc = ts
            local = ts_utc.astimezone(ZoneInfo("Asia/Kolkata"))
            tstr = local.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            tstr = r.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        cw.writerow([tstr, r.temperature, r.humidity, r.soil, r.soil_status])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="sensor_history.csv")

# admin and price routes unchanged (kept from your file)
@app.route("/admin")
def admin():
    authenticated = session.get("admin_authenticated", False)
    alerts = Alert.query.order_by(Alert.created_at.desc()).all() if authenticated else []
    return render_template("admin.html", authenticated=authenticated, alerts=alerts)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password")
    if password == ADMIN_PASSWORD:
        session['admin_authenticated'] = True
        return redirect(url_for("admin"))
    flash("Invalid password", "danger")
    return redirect(url_for("admin"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin"))

@app.route("/admin/resolve_alert/<int:alert_id>", methods=["POST"])
def resolve_alert(alert_id):
    if not session.get("admin_authenticated"):
        return jsonify({"status":"error","message":"unauthorized"}), 401
    alert = Alert.query.get(alert_id)
    if alert:
        alert.resolved = True
        db.session.commit()
        return jsonify({"status":"ok"})
    return jsonify({"status":"error","message":"not found"}), 404

# price route left as in your file (unchanged)
@app.route("/price", methods=["GET","POST"])
def price():
    error_message = None
    prediction_data = None
    confidence_interval = None
    price_change = None
    rainfall_category = None
    display_thresholds = None

    current_year = pd.Timestamp.now().year
    years_range = range(2018, current_year + 10)
    prediction_year = current_year

    if request.method == "POST":
        try:
            crop_name = request.form["crop"]
            rainfall = float(request.form["rainfall"])
            prediction_year = int(request.form.get("year", current_year))

            if crop_name not in models:
                error_message = f"No model found for {crop_name}"
                return render_template("price.html", crops=crop_names, error_message=error_message,
                                       years_range=years_range, current_year=current_year)

            model = models[crop_name]
            crop_thresholds = thresholds.get(crop_name)

            # (Simplified rainfall logic kept from your code)
            mean_rainfall = crop_thresholds['mean_rainfall'] if crop_thresholds else 0
            std_rainfall = crop_thresholds['std_rainfall'] if crop_thresholds else 0
            deficient_threshold = mean_rainfall - 0.75 * std_rainfall
            excessive_threshold = mean_rainfall + 0.75 * std_rainfall

            if rainfall > excessive_threshold:
                rainfall_category = "Excessive"; category_value = 1
            elif rainfall < deficient_threshold:
                rainfall_category = "Deficient"; category_value = -1
            else:
                rainfall_category = "Normal"; category_value = 0

            # Dummy prediction if model exists
            base_prediction = np.random.uniform(100, 200)   # Replace with model.predict()
            price_per_quintal = base_prediction * 25
            inflation_adjusted_price = price_per_quintal * 1.11
            confidence_range = price_per_quintal * 0.15
            confidence_interval = [price_per_quintal - confidence_range, price_per_quintal + confidence_range]

            price_change = f"Predicted price for {crop_name} is ₹{price_per_quintal:.2f} in {prediction_year}"

            prediction_data = {
                "wpi": base_prediction,
                "per_quintal": price_per_quintal,
                "inflation_adjusted": inflation_adjusted_price,
                "year": prediction_year
            }

        except Exception as e:
            error_message = f"Error making prediction: {str(e)}"

    return render_template("price.html",
                           crops=crop_names,
                           prediction=prediction_data,
                           confidence_interval=confidence_interval,
                           price_change=price_change,
                           rainfall_category=rainfall_category,
                           thresholds=display_thresholds,
                           error_message=error_message,
                           years_range=years_range,
                           current_year=current_year)

@app.route("/recommend")
def recommend():
    crop = recommend_crop(latest_data.get("temperature",0), latest_data.get("humidity",0), latest_data.get("soil",0), latest_data.get("soil_status","Unknown"))
    # merge latest_data fields with crop suggestion
    resp = {**latest_data, **crop}
    return jsonify(resp)

# Run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
