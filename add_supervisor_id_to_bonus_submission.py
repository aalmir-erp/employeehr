"""
Direct SQL migration script to add supervisor_id column to bonus_submission table.
"""
import os
import sys
import psycopg2
from psycopg2 import sql


def get_db_connection():
    """Connect to the database using environment variables"""
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    return psycopg2.connect(DATABASE_URL)


def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        result = cursor.fetchone()
        return result is not None


def add_supervisor_id_column(conn):
    """Add supervisor_id column to the bonus_submission table"""
    if check_column_exists(conn, 'bonus_submission', 'supervisor_id'):
        print("Column 'supervisor_id' already exists in 'bonus_submission' table")
        return False
    
    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("""
            ALTER TABLE bonus_submission 
            ADD COLUMN supervisor_id INTEGER REFERENCES employee(id)
        """))
        
        print("Added 'supervisor_id' column to 'bonus_submission' table")
        return True


def main():
    """Main function to execute the migration"""
    try:
        conn = get_db_connection()
        print("Connected to the database")
        
        modified = add_supervisor_id_column(conn)
        
        if modified:
            conn.commit()
            print("Migration successful")
        else:
            print("No changes were made")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            print("Database connection closed")


if __name__ == "__main__":
    main()