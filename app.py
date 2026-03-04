import os
import logging
import threading
import psycopg2
import select
from time import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from scheduler import init_scheduler_custom
from db import db
from models import AttendanceLog, User, FCMToken, AttendanceNotification,AttendanceDispute,AttendanceRecord
from extensions import socketio

import firebase_admin
from firebase_admin import credentials, messaging
from datetime import date
import calendar



# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------
# Create Flask App
# -------------------------------------------------
app = Flask(__name__)
app.config['SCHEDULER_API_ENABLED'] = True

# -------------------------------------------------
# Basic Config
# -------------------------------------------------
app.secret_key = os.environ.get("SESSION_SECRET", "fallback_secret_key_for_development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['WTF_CSRF_ENABLED'] = False

app.config["SQLALCHEMY_DATABASE_URI"] = \
    'postgresql://attendance_app:attendance_app@localhost/attendance_live'

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# -------------------------------------------------
# Initialize Extensions
# -------------------------------------------------
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

csrf = CSRFProtect()
csrf.init_app(app)

# 🔥 INIT SOCKETIO AFTER APP
socketio.init_app(app)

# -------------------------------------------------
# Scheduler
# -------------------------------------------------
init_scheduler_custom(app)

# -------------------------------------------------
# Import Models
# -------------------------------------------------
with app.app_context():
    import models
    db.create_all()

from models import User, AttendanceNotification

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------------------------------
# Register Blueprints
# -------------------------------------------------
from routes.index import bp as index_bp
from routes.auth import bp as auth_bp
from routes.admin import bp as admin_bp
from routes.attendance import bp as attendance_bp
from routes.devices import bp as devices_bp
from routes.shifts import bp as shifts_bp
from routes.reports import bp as reports_bp
from routes.overtime import bp as overtime_bp
from routes.admin_debug import bp as admin_debug_bp
from routes.bonus import bp as bonus_bp
from routes.supervisor_management import bp as supervisor_bp
from routes.employees import bp as employees_bp
from routes.notifications import bp as notifications_bp
from routes.api import bp as api_bp 

app.register_blueprint(index_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(attendance_bp, url_prefix='/attendance')
app.register_blueprint(devices_bp, url_prefix='/devices')
app.register_blueprint(shifts_bp, url_prefix='/shifts')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(overtime_bp, url_prefix='/overtime')
app.register_blueprint(admin_debug_bp, url_prefix='/admin/debug')
app.register_blueprint(bonus_bp, url_prefix='/bonus')
app.register_blueprint(supervisor_bp, url_prefix='/supervisor')
app.register_blueprint(employees_bp, url_prefix='/employees')
app.register_blueprint(notifications_bp, url_prefix='/notifications')
app.register_blueprint(api_bp, url_prefix='/api')

# -------------------------------------------------
# Template Context
# -------------------------------------------------
from datetime import datetime
import calendar

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.context_processor
def inject_notification_preview():
    if not current_user.is_authenticated:
        return {
            'unread_notifications_count': 0,
            'latest_notifications': []
        }

    role_filter = 'hr'
    if not current_user.is_admin:
        role_filter = current_user.role

    role_notifications = AttendanceNotification.query.filter(
        AttendanceNotification.role == role_filter
    )

    unread_count = role_notifications.filter(
        AttendanceNotification.is_read.is_(False)
    ).count()

    latest_notifications = role_notifications.order_by(
        AttendanceNotification.created_at.desc()
    ).limit(5).all()

    return {
        'unread_notifications_count': unread_count,
        'latest_notifications': latest_notifications
    }

@app.template_filter('month_name')
def month_name_filter(month_number):
    try:
        return calendar.month_name[int(month_number)]
    except:
        return ""

@app.template_filter('format_date')
def format_date_filter(date):
    if not date:
        return ""
    try:
        if isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d').date()
        return date.strftime('%d/%m/%Y')
    except:
        return str(date)

@app.context_processor
def inject_pending_dispute_count():
    try:
        if current_user.is_authenticated and (
            current_user.has_role('hr') or
            current_user.has_role('supervisor')
        ):
            pending_count = AttendanceDispute.query.filter_by(
                status="PENDING"
            ).count()
        else:
            pending_count = 0

        return dict(pending_dispute_count=pending_count)

    except Exception:
        return dict(pending_dispute_count=0)        

# -------------------------------------------------
# 🔥 PostgreSQL LISTEN/NOTIFY Realtime Thread
# -------------------------------------------------

if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)
    print("✅ Firebase initialized successfully")

executor = ThreadPoolExecutor(max_workers=3)

# =========================================================
# FIREBASE SEND
# =========================================================
def send_fcm_notification(token, title, body):
    try:
        print("📲 Sending FCM...")

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            token=token,
            android=messaging.AndroidConfig(priority="high"),
        )

        response = messaging.send(message)
        print("✅ Notification sent:", response)

    except Exception as e:
        print("❌ FCM error:", e)


def send_notification_async(token, title, body):
    executor.submit(send_fcm_notification, token, title, body)

# =========================================================
# DUPLICATE BLOCKER
# =========================================================
_recent_notifications = {}

def should_send(attendance_id, window_sec=10):
    now = time()
    last = _recent_notifications.get(attendance_id, 0)

    if now - last < window_sec:
        print("⏭ Duplicate blocked:", attendance_id)
        return False

    _recent_notifications[attendance_id] = now
    return True

# =========================================================
# POSTGRES LISTENER
# =========================================================
def listen_for_attendance_notifications(app):
    print("🔥 Listening for DB notifications... PID:", os.getpid())

    conn = psycopg2.connect(
        dbname="attendance_live",
        user="attendance_app",
        password="attendance_app",
        host="localhost",
        port="5432"
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("LISTEN attendance_channel;")

    while True:
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()

        while conn.notifies:
            notify = conn.notifies.pop(0)
            attendance_id = notify.payload
            print("🚀 Notify received:", attendance_id)

            if not should_send(attendance_id):
                continue

            socketio.emit("attendance_update", {"id": attendance_id})

            with app.app_context():
                latest_log = AttendanceLog.query.get(attendance_id)
                if not latest_log:
                    continue

                # ============================
                # AttendanceRecord create/update
                # ============================
                record_date = latest_log.timestamp.date() if latest_log.timestamp else date.today()
                emp_id = latest_log.employee_id
                check_in = latest_log.timestamp if latest_log.log_type == "IN" else None

                record = AttendanceRecord.query.filter_by(
                    employee_id=emp_id,
                    date=record_date
                ).first()

                if not record and latest_log.log_type == "IN":
                    record = AttendanceRecord(
                        employee_id=emp_id,
                        date=record_date,
                        check_in=check_in if latest_log.log_type == "IN" else None,
                        status='in_progress'
                    )
                    db.session.add(record)
                    db.session.flush()

                db.session.commit()

                # ============================
                # Notification logic
                # ============================
                user = User.query.filter_by(employee_id=latest_log.employee_id).first()
                if not user:
                    continue

                fcm = FCMToken.query.filter_by(user_id=user.id).first()
                if not fcm:
                    continue

                log_time = latest_log.timestamp.strftime('%H:%M') if latest_log.timestamp else "Unknown"
                action = "Checkin" if latest_log.log_type == "IN" else "Checkout"

                today = date.today()
                start_date = date(today.year, today.month, 1)
                end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

                records = AttendanceRecord.query.filter(
                    AttendanceRecord.employee_id == latest_log.employee_id,
                    AttendanceRecord.date.between(start_date, end_date)
                ).all()

                present = sum(1 for r in records if r.status == 'present')
                absent = sum(1 for r in records if r.status == 'absent')
                late = sum(1 for r in records if r.status == 'late')
                overtime = sum(r.overt_time_weighted or 0 for r in records)

                title = f"MIR AMS - {action}"
                body = (
                    f"You marked {action} at {log_time}\n\n"
                    f"📊 Monthly Summary:\n"
                    f"Present: {present}\n"
                    f"Absent: {absent}\n"
                    f"Late: {late}\n"
                    f"Overtime: {round(overtime, 2)} hrs"
                )

                print("📲 Triggering FCM...")
                send_notification_async(fcm.token, title, body)

# =========================================================
# START LISTENER ONCE
# =========================================================
def start_listener_once(app):
    if os.environ.get("LISTENER_STARTED") == "1":
        return

    os.environ["LISTENER_STARTED"] = "1"

    threading.Thread(
        target=listen_for_attendance_notifications,
        args=(app,),
        daemon=True
    ).start()

    print("✅ Listener started (single instance)")

start_listener_once(app)

# -------------------------------------------------
# Scheduler Optional Init
# -------------------------------------------------
try:
    from utils.scheduler import init_scheduler
    init_scheduler(app)
    logger.info("Scheduler initialized successfully")
except ImportError:
    logger.warning("Scheduler module not found")
