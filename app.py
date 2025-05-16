import os
import logging

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# Import the db instance from db.py to fix circular imports
from db import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback_secret_key_for_development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure database
# Use SQLite for simplicity and avoiding connection issues
logger.info("Using SQLite database for this session")
# database_url = "sqlite:///attendance.db"
# database_url = "postgresql+psycopg2://employee:employee@localhost:5432/employee"
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:<password>@localhost/<your_db_name>'



app.config['WTF_CSRF_ENABLED'] = False


app.config["SQLALCHEMY_DATABASE_URI"] = 'postgresql://employee:employee@localhost/employee'
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Configure Odoo connection settings
app.config["ODOO_HOST"] = os.environ.get("PGHOST", "localhost")
app.config["ODOO_PORT"] = os.environ.get("PGPORT", "5432")
app.config["ODOO_USER"] = os.environ.get("PGUSER", "odoo")
app.config["ODOO_PASSWORD"] = os.environ.get("PGPASSWORD", "odoo")
app.config["ODOO_DATABASE"] = os.environ.get("PGDATABASE", "odoo9")

# Initialize extensions with app
db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
csrf.init_app(app)

# Import models after initializing the app and db
with app.app_context():
    # Import models here to ensure they're registered with SQLAlchemy
    import models  # noqa: F401
    
    # Create all tables
    db.create_all()

# Import User model after models are imported
# Fixes the circular import
from models import User

# Setup login manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register blueprints
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

# Add template context processors
from datetime import datetime
import calendar

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Add custom template filters
@app.template_filter('month_name')
def month_name_filter(month_number):
    """Convert month number to month name"""
    try:
        return calendar.month_name[int(month_number)]
    except (ValueError, IndexError):
        return ""

@app.template_filter('format_date')
def format_date_filter(date):
    """Format date as DD/MM/YYYY"""
    if not date:
        return ""
    try:
        if isinstance(date, str):
            # Try to parse string dates
            from datetime import datetime
            date = datetime.strptime(date, '%Y-%m-%d').date()
        return date.strftime('%d/%m/%Y')
    except (ValueError, AttributeError):
        return str(date)

# Initialize scheduler
try:
    from utils.scheduler import init_scheduler
    init_scheduler(app)
    logger.info("Scheduler initialized successfully")
except ImportError:
    logger.warning("Scheduler module not found, skipping task initialization")
