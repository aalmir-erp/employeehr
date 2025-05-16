"""
Fix existing batch attendance entry records to ensure they have proper values.

This script updates all attendance records that have a status of 'present' but are missing
check-in, check-out times, work hours, or shift information.
"""

import os
from datetime import datetime, timedelta
from flask import Flask
from sqlalchemy import and_

# Import the app and db from the main app
from main import app
from db import db

# Import needed models inside app context
with app.app_context():
    from models import AttendanceRecord, Employee

def fix_batch_entry_records():
    """Find and fix attendance records with missing data"""
    # Keep track of record IDs to verify later
    fixed_record_ids = []
    
    with app.app_context():
        # Query for attendance records that need fixing
        # (status 'present' but missing check-in/out or work hours)
        records_to_fix = AttendanceRecord.query.filter(
            AttendanceRecord.status == 'present'
        ).filter(
            AttendanceRecord.check_in.is_(None) | 
            AttendanceRecord.check_out.is_(None) | 
            (AttendanceRecord.work_hours == 0)
        ).all()
        
        # Save the record IDs for later verification
        fixed_record_ids = [r.id for r in records_to_fix]
        
        print(f"Found {len(records_to_fix)} records to fix")
        
        # Process each record
        for record in records_to_fix:
            print(f"Fixing record ID {record.id} for employee {record.employee_id} on {record.date}")
            
            # Set default check-in and check-out times if missing
            if record.check_in is None:
                print(f"Setting check-in for record {record.id}")
                record.check_in = datetime.combine(record.date, datetime.min.time().replace(hour=9))
            
            if record.check_out is None:
                print(f"Setting check-out for record {record.id}")
                record.check_out = datetime.combine(record.date, datetime.min.time().replace(hour=18))
            
            # Set work hours if missing
            if record.work_hours == 0:
                print(f"Setting work_hours for record {record.id}")
                # Default to 8 hours with 1 hour break
                record.work_hours = 8.0
                record.break_duration = 1.0
            
            # Set shift type if missing
            if not record.shift_type or record.shift_type == '':
                # Determine shift type based on check-in time
                check_in_hour = record.check_in.hour
                if 6 <= check_in_hour < 12:
                    record.shift_type = 'day'
                elif 12 <= check_in_hour < 18:
                    record.shift_type = 'afternoon'
                elif 18 <= check_in_hour or check_in_hour < 6:
                    record.shift_type = 'night'
                else:
                    record.shift_type = 'day'  # Default to day shift
            
            # Try to assign shift_id if missing
            if not record.shift_id:
                employee = Employee.query.get(record.employee_id)
                if employee and employee.current_shift_id:
                    record.shift_id = employee.current_shift_id
            
            # Explicitly flush changes for this record
            db.session.flush()
            
            # Calculate overtime if applicable
            if record.work_hours > 8.0:
                # Calculate specific overtime types based on day type
                is_weekend = record.is_weekend
                is_holiday = record.is_holiday
                
                # Reset overtime values
                record.regular_overtime_hours = 0.0
                record.weekend_overtime_hours = 0.0
                record.holiday_overtime_hours = 0.0
                record.overtime_night_hours = 0.0
                
                overtime_hours = record.work_hours - 8.0
                
                # Check employee eligibility for different overtime types
                employee = Employee.query.get(record.employee_id)
                
                # Categorize overtime based on day type
                if is_holiday and employee and employee.eligible_for_holiday_overtime:
                    record.holiday_overtime_hours = overtime_hours
                elif is_weekend and employee and employee.eligible_for_weekend_overtime:
                    record.weekend_overtime_hours = overtime_hours
                elif employee and employee.eligible_for_weekday_overtime:
                    record.regular_overtime_hours = overtime_hours
                
                # Set night overtime if applicable
                is_night_shift = record.shift_type == 'night'
                if is_night_shift and (record.regular_overtime_hours > 0 or 
                                    record.weekend_overtime_hours > 0 or 
                                    record.holiday_overtime_hours > 0):
                    record.overtime_night_hours = max(record.regular_overtime_hours,
                                                    record.weekend_overtime_hours,
                                                    record.holiday_overtime_hours)
                    
                # Update total overtime hours
                record.overtime_hours = (record.regular_overtime_hours + 
                                        record.weekend_overtime_hours + 
                                        record.holiday_overtime_hours)
                
                # Set overtime rate based on day type
                if is_holiday:
                    record.overtime_rate = 3.0
                elif is_weekend:
                    record.overtime_rate = 2.0
                else:
                    record.overtime_rate = 1.5
        
        # Commit all changes
        db.session.commit()
        print(f"Successfully fixed {len(records_to_fix)} attendance records")
    
    # Use a separate SQL connection to verify our changes
    print("\nVerifying changes with direct SQL query...")
    import psycopg2
    import os
    
    # Get database connection details from environment variables
    database_url = os.environ.get('DATABASE_URL')
    if database_url and fixed_record_ids:
        try:
            # Parse database URL
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()
            
            # Create query with the list of record IDs
            record_ids_str = ", ".join(str(rid) for rid in fixed_record_ids)
            query = f"SELECT id, check_in, check_out, work_hours FROM attendance_record WHERE id IN ({record_ids_str})"
            
            # Execute query
            cursor.execute(query)
            
            # Print results
            rows = cursor.fetchall()
            for row in rows:
                print(f"Record {row[0]}: check_in={row[1]}, check_out={row[2]}, work_hours={row[3]}")
            
            # If we still have null values, apply a direct SQL update
            if any(row[1] is None or row[2] is None or row[3] == 0 for row in rows):
                print("\nSome records still need fixing. Applying direct SQL updates...")
                for record_id in fixed_record_ids:
                    # Set check_in, check_out times and work_hours via direct SQL
                    sql_update = """
                    UPDATE attendance_record
                    SET check_in = date + interval '9 hours',
                        check_out = date + interval '18 hours',
                        work_hours = 8.0,
                        break_duration = 1.0,
                        shift_type = 'day'
                    WHERE id = %s
                    """
                    cursor.execute(sql_update, (record_id,))
                
                # Commit the direct SQL updates
                conn.commit()
                print("Direct SQL updates applied successfully")
                
                # Verify the updates again
                cursor.execute(query)
                print("\nAfter direct SQL update:")
                for row in cursor.fetchall():
                    print(f"Record {row[0]}: check_in={row[1]}, check_out={row[2]}, work_hours={row[3]}")
            
            # Close connection
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error verifying records: {e}")

if __name__ == "__main__":
    fix_batch_entry_records()