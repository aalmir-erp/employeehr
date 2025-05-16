#!/usr/bin/env python3
"""
Migration script to add break_start and break_end columns to the attendance_record table.
"""
import os
import sys
from datetime import datetime
import psycopg2

def main():
    """Main function to execute the migration"""
    # Get database connection string from environment variable
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        sys.exit(1)
    
    # Connect to the database
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False  # Using a transaction
        cursor = conn.cursor()
        print("Connected to the database.")
    except psycopg2.Error as e:
        print(f"ERROR: Could not connect to the database: {e}")
        sys.exit(1)
    
    try:
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'attendance_record' 
            AND column_name IN ('break_start', 'break_end')
        """)
        existing_columns = [col[0] for col in cursor.fetchall()]
        
        if 'break_start' not in existing_columns:
            print("Adding break_start column...")
            cursor.execute("""
                ALTER TABLE attendance_record 
                ADD COLUMN break_start TIMESTAMP NULL
            """)
            print("break_start column added successfully.")
        else:
            print("break_start column already exists. Skipping.")
        
        if 'break_end' not in existing_columns:
            print("Adding break_end column...")
            cursor.execute("""
                ALTER TABLE attendance_record 
                ADD COLUMN break_end TIMESTAMP NULL
            """)
            print("break_end column added successfully.")
        else:
            print("break_end column already exists. Skipping.")
        
        # Commit the transaction
        conn.commit()
        print("Migration completed successfully.")
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"ERROR: Failed to execute migration: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()