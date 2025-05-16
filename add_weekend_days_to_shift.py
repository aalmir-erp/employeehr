"""
Add weekend_days column to shift table.
This script is meant to be run directly to add the missing weekend_days column.
"""
import psycopg2
import os
import sys

def get_db_connection():
    """Connect to the database using environment variables"""
    try:
        conn = psycopg2.connect(
            host=os.environ.get('PGHOST'),
            database=os.environ.get('PGDATABASE'),
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD'),
            port=os.environ.get('PGPORT')
        )
        return conn
    except psycopg2.Error as e:
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

def add_weekend_days_column(conn):
    """Add the weekend_days column to the shift table"""
    with conn.cursor() as cur:
        try:
            # Check if column exists already
            if check_column_exists(conn, 'shift', 'weekend_days'):
                print("Column 'weekend_days' already exists in 'shift' table. No action needed.")
                return

            # Add the column
            cur.execute("""
                ALTER TABLE shift 
                ADD COLUMN weekend_days JSONB;
            """)
            conn.commit()
            print("Successfully added 'weekend_days' column to 'shift' table.")
        except psycopg2.Error as e:
            print(f"Error adding column: {e}")
            conn.rollback()
            sys.exit(1)

def main():
    """Main function to execute the migration"""
    conn = get_db_connection()
    try:
        add_weekend_days_column(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()