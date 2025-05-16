#!/usr/bin/env python
"""
Apply database migrations tool for MIR AMS
To use: python apply_migrations.py
"""

import os
import sys
import subprocess
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from db import db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_app():
    """Create a minimal Flask app for migrations"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Import the main module to ensure models are registered
    # Avoid circular imports by not importing models directly
    import main  # noqa
    
    return app

def run_migrations(app):
    """Run Flask-Migrate migrations"""
    try:
        # Initialize Flask-Migrate
        migrate = Migrate(app, db)
        
        # Check if migrations directory exists
        if not os.path.exists('migrations'):
            logger.info("Initializing migrations directory...")
            with app.app_context():
                subprocess.run(['flask', 'db', 'init'], check=True)
        
        # Run the migration
        logger.info("Applying migrations...")
        with app.app_context():
            subprocess.run(['flask', 'db', 'upgrade'], check=True)
        
        logger.info("Migrations applied successfully!")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"An error occurred during migration: {str(e)}")
        return False

def apply_specific_migration():
    """Apply our latest migration directly using SQL if Flask-Migrate fails"""
    try:
        from sqlalchemy import create_engine, text
        
        # Get database URL from environment
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable is not set")
            return False
            
        # Ensure we're using the correct database URL format
        if database_url and database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        # Create engine
        engine = create_engine(database_url)
        
        # Define the SQL statements
        statements = [
            # Create index on attendance_log
            """
            CREATE INDEX IF NOT EXISTS ix_attendance_log_employee_timestamp_log_type 
            ON attendance_log(employee_id, timestamp, log_type);
            """,
            
            # Add required_approvals column to system_config if it doesn't exist
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='system_config' AND column_name='required_approvals'
                ) THEN
                    ALTER TABLE system_config ADD COLUMN required_approvals INTEGER DEFAULT 2;
                END IF;
            END $$;
            """,
            
            # Add supervisor_id column to bonus_submission if it doesn't exist
            """
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='bonus_submission' AND column_name='supervisor_id'
                ) THEN
                    ALTER TABLE bonus_submission ADD COLUMN supervisor_id INTEGER;
                    ALTER TABLE bonus_submission ADD CONSTRAINT bonus_submission_supervisor_id_fkey 
                    FOREIGN KEY (supervisor_id) REFERENCES employee (id);
                END IF;
            END $$;
            """,
            
            # Create index on attendance_record for date
            """
            CREATE INDEX IF NOT EXISTS ix_attendance_record_date 
            ON attendance_record(date);
            """,
            
            # Create index on attendance_record for employee_id and date
            """
            CREATE INDEX IF NOT EXISTS ix_attendance_record_employee_id_date 
            ON attendance_record(employee_id, date);
            """
        ]
        
        # Execute each statement
        with engine.connect() as connection:
            for statement in statements:
                connection.execute(text(statement))
                connection.commit()
        
        logger.info("SQL migration statements applied successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to apply SQL migration statements: {str(e)}")
        return False

def main():
    """Main function"""
    logger.info("Starting database migration process")
    
    # Check if DATABASE_URL is set
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL environment variable is not set")
        return 1
    
    # Create the app
    app = create_app()
    
    # Try to run migration using Flask-Migrate
    success = run_migrations(app)
    
    # If Flask-Migrate failed, try applying SQL directly
    if not success:
        logger.info("Falling back to direct SQL migration...")
        success = apply_specific_migration()
    
    if success:
        logger.info("Migration completed successfully")
        return 0
    else:
        logger.error("Migration failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())