"""
Schema updater that directly adds required columns using SQL
This avoids circular import issues by not importing any models
"""
import os
import sqlite3

def create_sqlite_database():
    """Create a new SQLite database with required tables"""
    print("Creating SQLite database...")
    
    # Connect to the SQLite database (creates it if it doesn't exist)
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Check if system_config table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
    if not cursor.fetchone():
        print("Creating system_config table")
        # Create the system_config table with required_approvals column
        cursor.execute('''
        CREATE TABLE system_config (
            id INTEGER PRIMARY KEY,
            system_name TEXT,
            weekend_days TEXT, -- JSON
            default_work_hours REAL,
            timezone TEXT,
            date_format TEXT,
            time_format TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            openai_api_key TEXT,
            ai_assistant_enabled BOOLEAN DEFAULT 0,
            ai_model TEXT DEFAULT 'gpt-4o',
            minimum_break_duration INTEGER DEFAULT 15,
            maximum_break_duration INTEGER DEFAULT 300,
            default_shift_id INTEGER,
            ai_enabled BOOLEAN DEFAULT 0,
            ai_provider TEXT DEFAULT 'openai',
            ai_api_key TEXT,
            enable_employee_assistant BOOLEAN DEFAULT 0,
            enable_report_insights BOOLEAN DEFAULT 0,
            enable_anomaly_detection BOOLEAN DEFAULT 0,
            enable_predictive_scheduling BOOLEAN DEFAULT 0,
            max_tokens INTEGER DEFAULT 1000,
            temperature REAL DEFAULT 0.7,
            prompt_template TEXT,
            ai_total_queries INTEGER DEFAULT 0,
            ai_monthly_tokens INTEGER DEFAULT 0,
            ai_success_rate REAL DEFAULT 0.0,
            required_approvals INTEGER DEFAULT 2
        )
        ''')
        
        # Insert initial configuration
        cursor.execute('''
        INSERT INTO system_config (
            system_name, weekend_days, default_work_hours, 
            timezone, date_format, time_format, required_approvals
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            'MIR Attendance Management System', 
            '[5, 6]',  # Saturday, Sunday as JSON
            8.0, 
            'UTC', 
            'DD/MM/YYYY', 
            'HH:mm',
            2
        ))
    else:
        # Add the required_approvals column if it doesn't exist
        try:
            cursor.execute("SELECT required_approvals FROM system_config LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding required_approvals column to system_config table")
            cursor.execute('''
            ALTER TABLE system_config 
            ADD COLUMN required_approvals INTEGER DEFAULT 2
            ''')
    
    # Create a simple user table if it doesn't exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
    if not cursor.fetchone():
        print("Creating user table")
        cursor.execute('''
        CREATE TABLE user (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            is_admin BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            odoo_id INTEGER,
            created_at TIMESTAMP,
            last_login TIMESTAMP,
            force_password_change BOOLEAN DEFAULT 0,
            role TEXT DEFAULT 'employee',
            department TEXT
        )
        ''')
        
        # Insert admin user
        from werkzeug.security import generate_password_hash
        cursor.execute('''
        INSERT INTO user (username, email, password_hash, is_admin, role)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            'admin',
            'admin@example.com',
            generate_password_hash('admin123'),
            1,
            'admin'
        ))
        
    # Check if bonus_submission table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bonus_submission'")
    if cursor.fetchone():
        # Add supervisor_id column to bonus_submission if it exists
        try:
            cursor.execute("SELECT supervisor_id FROM bonus_submission LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding supervisor_id column to bonus_submission table")
            cursor.execute('''
            ALTER TABLE bonus_submission 
            ADD COLUMN supervisor_id INTEGER
            ''')
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print("Database schema update completed")

if __name__ == "__main__":
    create_sqlite_database()