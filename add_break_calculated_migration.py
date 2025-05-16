"""
Direct SQL migration script to add break_calculated column to attendance_record table.
"""
import os
import sys
import psycopg2
from psycopg2 import sql


def get_db_connection():
    """Connect to the database using environment variables"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("Error: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cur.fetchone() is not None


def add_break_calculated_column(conn):
    """Add the break_calculated column to the attendance_record table"""
    with conn.cursor() as cur:
        try:
            # Check if column already exists
            if check_column_exists(conn, 'attendance_record', 'break_calculated'):
                print("Column 'break_calculated' already exists in table 'attendance_record'")
                return False
            
            # Add column
            cur.execute("""
                ALTER TABLE attendance_record
                ADD COLUMN break_calculated BOOLEAN DEFAULT FALSE
            """)
            conn.commit()
            print("Added 'break_calculated' column to 'attendance_record' table")
            return True
        except Exception as e:
            conn.rollback()
            print(f"Error adding column: {e}")
            return False


def main():
    """Main function to execute the migration"""
    conn = get_db_connection()
    if not conn:
        print("Error: Could not connect to database")
        sys.exit(1)
    
    try:
        success = add_break_calculated_column(conn)
        if success:
            print("Migration completed successfully")
        else:
            print("Migration was not necessary or failed")
    finally:
        conn.close()


if __name__ == "__main__":
    main()