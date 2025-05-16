"""
Direct SQL script to fix February batch entry issues for Employee B.
"""

import os
import psycopg2
from datetime import datetime, date, timedelta

def get_db_connection():
    """Connect to the database using environment variables"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)

def fix_february_records():
    """Fix February records for Employee B (ID 261) using direct SQL"""
    employee_id = 261  # Employee B ID

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # First, check if records exist
        cursor.execute("""
            SELECT COUNT(*) 
            FROM attendance_record 
            WHERE employee_id = %s 
            AND EXTRACT(MONTH FROM date) = 2 
            AND EXTRACT(YEAR FROM date) = 2025
        """, (employee_id,))
        
        count = cursor.fetchone()[0]
        print(f"Found {count} existing February records for Employee B")

        # Generate all February dates
        february_dates = []
        start_date = date(2025, 2, 1)
        end_date = date(2025, 2, 28)
        current_date = start_date
        
        while current_date <= end_date:
            february_dates.append(current_date.isoformat())
            current_date += timedelta(days=1)
        
        # For each date, check if a record exists and create/update as needed
        for date_str in february_dates:
            cursor.execute("""
                SELECT id 
                FROM attendance_record 
                WHERE employee_id = %s AND date = %s
            """, (employee_id, date_str))
            
            record_id = cursor.fetchone()
            
            if record_id:
                # Update existing record
                record_id = record_id[0]
                print(f"Updating existing record ID {record_id} for {date_str}")
                
                cursor.execute("""
                    UPDATE attendance_record
                    SET 
                        check_in = %s::date + interval '9 hours',
                        check_out = %s::date + interval '18 hours',
                        status = 'present',
                        work_hours = 8.0,
                        break_duration = 1.0,
                        shift_type = 'day',
                        is_weekend = (EXTRACT(DOW FROM %s::date) = 0 OR EXTRACT(DOW FROM %s::date) = 6)
                    WHERE id = %s
                """, (date_str, date_str, date_str, date_str, record_id))
            else:
                # Insert new record
                print(f"Creating new record for {date_str}")
                
                cursor.execute("""
                    INSERT INTO attendance_record 
                    (employee_id, date, check_in, check_out, status, work_hours, 
                     break_duration, shift_type, is_weekend)
                    VALUES 
                    (%s, %s, %s::date + interval '9 hours', 
                     %s::date + interval '18 hours', 'present', 8.0, 
                     1.0, 'day', 
                     (EXTRACT(DOW FROM %s::date) = 0 OR EXTRACT(DOW FROM %s::date) = 6))
                """, (employee_id, date_str, date_str, date_str, date_str, date_str))
        
        # Commit the transaction
        conn.commit()
        
        # Verify the result
        cursor.execute("""
            SELECT COUNT(*) 
            FROM attendance_record 
            WHERE employee_id = %s 
            AND EXTRACT(MONTH FROM date) = 2 
            AND EXTRACT(YEAR FROM date) = 2025
        """, (employee_id,))
        
        final_count = cursor.fetchone()[0]
        print(f"After fixes, found {final_count} February records for Employee B")
        
        # Show some sample records
        cursor.execute("""
            SELECT id, date, check_in, check_out, status, work_hours, break_duration, shift_type, is_weekend
            FROM attendance_record 
            WHERE employee_id = %s 
            AND EXTRACT(MONTH FROM date) = 2 
            AND EXTRACT(YEAR FROM date) = 2025
            ORDER BY date
            LIMIT 5
        """, (employee_id,))
        
        samples = cursor.fetchall()
        print("\nSample records:")
        for record in samples:
            print(f"Record {record[0]}: date={record[1]}, check_in={record[2]}, check_out={record[3]}, "
                  f"status={record[4]}, work_hours={record[5]}, break_duration={record[6]}, "
                  f"shift_type={record[7]}, is_weekend={record[8]}")
    
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_february_records()