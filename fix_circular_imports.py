#!/usr/bin/env python
"""
This script fixes circular import issues in the Flask application.

Usage:
  python fix_circular_imports.py
"""

import os
import sys
import shutil

def backup_file(file_path):
    """Create a backup of a file"""
    if os.path.exists(file_path):
        backup_path = f"{file_path}.bak"
        shutil.copy2(file_path, backup_path)
        print(f"Backed up {file_path} to {backup_path}")
        return True
    return False

def fix_step_1():
    """Step 1: Create a centralized db.py file"""
    db_file = 'db.py'
    if os.path.exists(db_file):
        print(f"{db_file} already exists, skipping creation")
    else:
        with open(db_file, 'w') as f:
            f.write("""\
"""Contains database instance to avoid circular imports

This file creates and exports only the SQLAlchemy database instance.
It's used by both models.py and app.py to avoid circular imports.
"""

import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Create database instance without binding to an app yet
db = SQLAlchemy(model_class=Base)
"""""")
        print(f"Created {db_file}")

def fix_step_2():
    """Step 2: Fix models.py to use the centralized db"""
    models_file = 'models.py'
    backup_file(models_file)
    
    try:
        with open(models_file, 'r') as f:
            content = f.read()
        
        # Replace imports that cause circular dependencies
        if 'from app import db' in content:
            content = content.replace('from app import db', 'from db import db')
            
            with open(models_file, 'w') as f:
                f.write(content)
            
            print(f"Updated {models_file} to use db from db.py")
    except Exception as e:
        print(f"Error updating {models_file}: {e}")

def fix_step_3():
    """Step 3: Create a simple app.py that imports from main.py"""
    app_file = 'app.py'
    backup_file(app_file)
    
    with open(app_file, 'w') as f:
        f.write("""\
# Simple redirect file to maintain compatibility
# This avoids circular imports by not importing main.py

from db import db

# For compatibility with older files that import from app
import logging
import os
from datetime import datetime
import calendar

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# These will be properly initialized when main.py runs
app = None
login_manager = None
"""""")
    print(f"Updated {app_file} to be a simple compatibility layer")

def create_main_py():
    """Create or update main.py with the Flask application"""
    main_file = 'main.py'
    backup_file(main_file)
    
    with open(main_file, 'w') as f:
        f.write("""\
 import os
import logging
from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

# Import the db instance from db.py
from db import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize extensions outside of create_app
login_manager = LoginManager()

# Create the Flask application
def create_app():
    app = Flask(__name__)
    
    # Configure app
    app.secret_key = os.environ.get("SESSION_SECRET", "fallback_secret_key_for_development")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https
    
    # Configure database
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not found, using SQLite as fallback")
        database_url = "sqlite:///attendance.db"
    
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
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
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Setup migrations
    migrate = Migrate(app, db)
    
    # Add template context processors
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}
    
    # Add custom template filters
    @app.template_filter('month_name')
    def month_name_filter(month_number):
        """Convert month number to month name"""
        import calendar
        try:
            return calendar.month_name[int(month_number)]
        except (ValueError, IndexError):
            return ""
    
    # Configure user loader for Flask-Login
    from models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    return app

# Create application instance
app = create_app()

# Make app and login_manager available to other modules
import app as app_module
app_module.app = app
app_module.login_manager = login_manager

# Create database tables within application context
with app.app_context():
    import models
    db.create_all()

# Now that all models are imported and the app is fully set up,
# we can register the blueprints
with app.app_context():
    try:
        # This section only runs if blueprints are available
        from routes.index import bp as index_bp
        app.register_blueprint(index_bp)
        
        from routes.auth import bp as auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
        
        from routes.admin import bp as admin_bp
        app.register_blueprint(admin_bp, url_prefix='/admin')
        
        from routes.attendance import bp as attendance_bp
        app.register_blueprint(attendance_bp, url_prefix='/attendance')
        
        from routes.devices import bp as devices_bp
        app.register_blueprint(devices_bp, url_prefix='/devices')
        
        from routes.shifts import bp as shifts_bp
        app.register_blueprint(shifts_bp, url_prefix='/shifts')
        
        from routes.reports import bp as reports_bp
        app.register_blueprint(reports_bp, url_prefix='/reports')
    except ImportError as e:
        # In case some blueprints are missing, log the error but continue
        logger.warning(f"Could not import all blueprints: {e}")

# Add scheduled tasks (only run in main process)
if __name__ == '__main__':
    try:
        from utils.scheduler import init_scheduler
        init_scheduler(app)
    except ImportError:
        logger.warning("Scheduler module not found, skipping task initialization")

# Run the application
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
"""""")
    print(f"Created or updated {main_file} with proper application setup")

def main():
    print("======================================================")
    print("       Flask Circular Import Fix Script                ")
    print("======================================================")
    print("\nThis script will fix circular import issues by:\n")
    print("1. Creating a centralized db.py file")
    print("2. Updating models.py to use db from db.py")
    print("3. Making app.py a simple compatibility layer")
    print("4. Creating a proper main.py file for application initialization\n")
    
    confirm = input("Continue? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Execute steps
    fix_step_1()
    fix_step_2()
    fix_step_3()
    create_main_py()
    
    print("\n======================================================")
    print("                  Fix Complete                      ")
    print("======================================================\n")
    print("To run the application, use:\n")
    print("  gunicorn --bind 0.0.0.0:5000 main:app  # For production")
    print("  python main.py  # For development with auto-reload\n")
    print("All original files have been backed up with .bak extension.")

if __name__ == "__main__":
    main()
