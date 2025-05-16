"""
Direct SQL migration script to add approval_level and approvers columns to bonus_submission table.
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

def add_multi_level_approval_columns(conn):
    """Add approval_level and approvers columns to the bonus_submission table"""
    with conn.cursor() as cursor:
        # Add approval_level column if it doesn't exist
        if not check_column_exists(conn, "bonus_submission", "approval_level"):
            print("Adding approval_level column to bonus_submission table...")
            cursor.execute(
                "ALTER TABLE bonus_submission ADD COLUMN approval_level INTEGER DEFAULT 0"
            )
            print("approval_level column added successfully")
        else:
            print("approval_level column already exists")
        
        # Add approvers column if it doesn't exist
        if not check_column_exists(conn, "bonus_submission", "approvers"):
            print("Adding approvers column to bonus_submission table...")
            cursor.execute(
                "ALTER TABLE bonus_submission ADD COLUMN approvers JSONB DEFAULT '[]'::jsonb"
            )
            print("approvers column added successfully")
        else:
            print("approvers column already exists")

def main():
    """Main function to execute the migration"""
    print("Starting migration to add multi-level approval columns...")
    conn = get_db_connection()
    
    try:
        add_multi_level_approval_columns(conn)
        print("Migration completed successfully")
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()