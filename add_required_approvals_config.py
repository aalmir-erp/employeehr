"""
Direct SQL migration script to add required_approvals column to system_config table.
This column determines how many HR approvals are needed for bonus submissions.
"""
import os
import psycopg2
import sys
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def get_db_connection():
    """Connect to the database using environment variables"""
    db_url = os.environ.get("DATABASE_URL")
    
    if not db_url:
        print("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table_name, column_name)
        )
        return cursor.fetchone() is not None

def add_required_approvals_column(conn):
    """Add required_approvals column to the system_config table"""
    with conn.cursor() as cursor:
        # Add required_approvals column if it doesn't exist
        if not check_column_exists(conn, "system_config", "required_approvals"):
            print("Adding required_approvals column to system_config table...")
            cursor.execute(
                "ALTER TABLE system_config ADD COLUMN required_approvals INTEGER DEFAULT 2"
            )
            print("required_approvals column added successfully")
        else:
            print("required_approvals column already exists")

def main():
    """Main function to execute the migration"""
    print("Starting migration to add required_approvals column...")
    conn = get_db_connection()
    
    try:
        add_required_approvals_column(conn)
        print("Migration completed successfully")
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()