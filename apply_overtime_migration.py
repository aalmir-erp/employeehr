"""
Direct SQL migration script to add overtime eligibility columns to employee table.
"""
import os
import psycopg2
from datetime import datetime

def get_db_connection():
    """Connect to the database using environment variables"""
    db_url = os.environ.get('DATABASE_URL')
    return psycopg2.connect(db_url)

def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = %s
            );
        """, (table_name, column_name))
        return cur.fetchone()[0]

def add_overtime_eligibility_columns(conn):
    """Add the overtime eligibility columns to the employee table"""
    with conn.cursor() as cur:
        # Check if columns exist before adding them
        if not check_column_exists(conn, 'employee', 'eligible_for_weekday_overtime'):
            print("Adding eligible_for_weekday_overtime column...")
            cur.execute("""
                ALTER TABLE employee
                ADD COLUMN eligible_for_weekday_overtime BOOLEAN DEFAULT TRUE;
            """)
        else:
            print("Column eligible_for_weekday_overtime already exists.")
            
        if not check_column_exists(conn, 'employee', 'eligible_for_weekend_overtime'):
            print("Adding eligible_for_weekend_overtime column...")
            cur.execute("""
                ALTER TABLE employee
                ADD COLUMN eligible_for_weekend_overtime BOOLEAN DEFAULT TRUE;
            """)
        else:
            print("Column eligible_for_weekend_overtime already exists.")
            
        if not check_column_exists(conn, 'employee', 'eligible_for_holiday_overtime'):
            print("Adding eligible_for_holiday_overtime column...")
            cur.execute("""
                ALTER TABLE employee
                ADD COLUMN eligible_for_holiday_overtime BOOLEAN DEFAULT TRUE;
            """)
        else:
            print("Column eligible_for_holiday_overtime already exists.")
    
    # Commit the transaction
    conn.commit()

def main():
    """Main function to execute the migration"""
    try:
        conn = get_db_connection()
        add_overtime_eligibility_columns(conn)
        print("Migration completed successfully.")
        conn.close()
    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    main()