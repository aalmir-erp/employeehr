"""
Initialize the database by creating all tables and adding initial data
"""
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

# Create a new minimal Flask app just for database initialization
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Use SQLite for simplicity and avoiding connection issues
print("Using SQLite database for this session")
database_url = "sqlite:///attendance.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

# Import the schema (for SQLAlchemy 2.0, we need the model classes defined)
from models import (
    User, Employee, Department, AttendanceDevice, AttendanceLog, 
    AttendanceRecord, Shift, ShiftAssignment, OvertimeRule, Holiday,
    OTPVerification, SystemConfig, OdooConfig, BonusQuestion,
    BonusEvaluationPeriod, BonusSubmission, BonusEvaluation, BonusAuditLog
)

def add_required_approvals():
    """Add required_approvals column to system_config table if it doesn't exist"""
    with app.app_context():
        conn = db.engine.connect()
        try:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'system_config' AND column_name = 'required_approvals'
            """))
            if result.rowcount == 0:
                # Add the column
                conn.execute(text("""
                    ALTER TABLE system_config 
                    ADD COLUMN IF NOT EXISTS required_approvals INTEGER DEFAULT 2
                """))
                print("Added required_approvals column to system_config table")
            conn.commit()
        except Exception as e:
            print(f"Error adding required_approvals column: {e}")
        finally:
            conn.close()

def add_supervisor_id():
    """Add supervisor_id column to bonus_submission table if it doesn't exist"""
    with app.app_context():
        conn = db.engine.connect()
        try:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'bonus_submission' AND column_name = 'supervisor_id'
            """))
            if result.rowcount == 0:
                # Add the column
                conn.execute(text("""
                    ALTER TABLE bonus_submission 
                    ADD COLUMN IF NOT EXISTS supervisor_id INTEGER,
                    ADD CONSTRAINT bonus_submission_supervisor_id_fkey 
                    FOREIGN KEY (supervisor_id) REFERENCES employee (id)
                """))
                print("Added supervisor_id column to bonus_submission table")
            conn.commit()
        except Exception as e:
            print(f"Error adding supervisor_id column: {e}")
        finally:
            conn.close()

def create_admin_user():
    """Create admin user if it doesn't exist"""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@example.com",
                account_active=True,
                role="admin"
            )
            admin.set_password("admin123")  # For testing only
            db.session.add(admin)
            db.session.commit()
            print("Created admin user")

def create_tables():
    """Create all database tables"""
    with app.app_context():
        db.create_all()
        print("Created all database tables")

def create_system_config():
    """Create system configuration if it doesn't exist"""
    with app.app_context():
        config = SystemConfig.query.first()
        if not config:
            config = SystemConfig(
                system_name="MIR Attendance Management System",
                weekend_days=[5, 6],  # Saturday, Sunday
                default_work_hours=8.0,
                timezone="UTC",
                date_format="DD/MM/YYYY",
                time_format="HH:mm",
                required_approvals=2
            )
            db.session.add(config)
            db.session.commit()
            print("Created system configuration")

def main():
    """Main function to initialize the database"""
    print("Initializing database...")
    
    try:
        # Create all tables
        create_tables()
        
        # Apply specific migrations
        add_required_approvals()
        add_supervisor_id()
        
        # Create initial data
        create_system_config()
        create_admin_user()
        
        print("Database initialization completed successfully")
        return 0
    except Exception as e:
        print(f"Error initializing database: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())