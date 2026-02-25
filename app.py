import os
import logging
import threading
import psycopg2
import select

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from scheduler import init_scheduler_custom

from db import db
from extensions import socketio   # ✅ IMPORTANT

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

# -------------------------------------------------
# 🔥 PostgreSQL LISTEN/NOTIFY Realtime Thread
# -------------------------------------------------
def listen_for_attendance_notifications():
    print("🔥 Listening for DB notifications...")

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
        print("SDSDSDSDSD")
        if select.select([conn], [], [], 5) == ([], [], []):
            continue

        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            print("🚀 New attendance insert detected:", notify.payload)

            socketio.emit("attendance_update", {"id": notify.payload})
            print("📡 Socket event emitted")
        with app.app_context():
                # from utils.attendance_processor import process_unprocessed_logs

                try:
                    
                    # process_unprocessed_logs(date_from=date.today())
                    print("✅ Attendance processing triggered")
                except Exception as e:
                    print("❌ Attendance processing failed:", e)


listener_thread = threading.Thread(
    target=listen_for_attendance_notifications,
    daemon=True
)
listener_thread.start()

# -------------------------------------------------
# Scheduler Optional Init
# -------------------------------------------------
try:
    from utils.scheduler import init_scheduler
    init_scheduler(app)
    logger.info("Scheduler initialized successfully")
except ImportError:
    logger.warning("Scheduler module not found")
