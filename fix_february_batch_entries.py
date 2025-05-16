"""
Fix February batch attendance entry records and verify their existence in the database.

This script:
1. Checks for existing February 2025 records for Employee A (ID 260)
2. If records exist but have issues, it fixes them
3. If records don't exist, it creates them with proper values
4. Verifies that records are properly set up with all required fields
"""

import os
from datetime import datetime, date, timedelta
from flask import Flask
from sqlalchemy import and_, extract

# Import the app and db from the main app
from main import app
from db import db

# Import models within app context
with app.app_context():
    from models import AttendanceRecord, Employee, Shift
    from utils.overtime_engine import calculate_overtime

def fix_february_batch_entries():
    """Find and fix February attendance records for Employee A"""
    fixed_record_ids = []
    created_record_ids = []
    
    with app.app_context():
        # Employee A ID is known to be 260
        employee_id = 260
        employee = Employee.query.get(employee_id)
        
        if not employee:
            print(f"Error: Employee A with ID {employee_id} not found")
            return
        
        print(f"Processing records for employee: {employee.name} (ID: {employee_id})")
        
        # Get February 2025 dates
        february_dates = []
        start_date = date(2025, 2, 1)
        end_date = date(2025, 2, 28)
        current_date = start_date
        
        while current_date <= end_date:
            february_dates.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"Processing {len(february_dates)} days in February 2025")
        
        # Find existing records for February 2025
        existing_records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee_id,
            extract('month', AttendanceRecord.date) == 2,
            extract('year', AttendanceRecord.date) == 2025
        ).all()
        
        existing_dates = [record.date for record in existing_records]
        print(f"Found {len(existing_records)} existing records for February 2025")
        
        # Process existing records first
        for record in existing_records:
            print(f"Fixing existing record ID {record.id} for {record.date}")
            fixed_record_ids.append(record.id)
            
            # Set proper values for existing records
            if record.status == 'present':
                # Set check-in and check-out if missing
                if record.check_in is None:
                    record.check_in = datetime.combine(record.date, datetime.min.time().replace(hour=9))
                
                if record.check_out is None:
                    record.check_out = datetime.combine(record.date, datetime.min.time().replace(hour=18))
                
                # Set work hours if missing
                if not record.work_hours or record.work_hours == 0:
                    record.work_hours = 8.0
                
                # Set break duration if missing
                if not record.break_duration or record.break_duration == 0:
                    record.break_duration = 1.0
                
                # Set shift type if missing
                if not record.shift_type:
                    record.shift_type = 'day'
                
                # Try to assign shift_id if missing
                if not record.shift_id and employee.current_shift_id:
                    record.shift_id = employee.current_shift_id
                
                # Calculate overtime
                if record.work_hours > 8.0:
                    calculate_overtime(record, recalculate=True, commit=False)
        
        # Create records for missing dates
        missing_dates = [d for d in february_dates if d not in existing_dates]
        print(f"Creating {len(missing_dates)} new records for missing dates")
        
        for missing_date in missing_dates:
            print(f"Creating new record for {missing_date}")
            
            # Create record with default values
            new_record = AttendanceRecord(
                employee_id=employee_id,
                date=missing_date,
                check_in=datetime.combine(missing_date, datetime.min.time().replace(hour=9)),
                check_out=datetime.combine(missing_date, datetime.min.time().replace(hour=18)),
                status='present',
                work_hours=8.0,
                break_duration=1.0,
                shift_type='day'
            )
            
            # Set shift ID if available
            if employee.current_shift_id:
                new_record.shift_id = employee.current_shift_id
                
                # Set shift type based on the employee's shift
                shift = Shift.query.get(employee.current_shift_id)
                if shift:
                    if 'night' in shift.name.lower():
                        new_record.shift_type = 'night'
                    elif 'day' in shift.name.lower():
                        new_record.shift_type = 'day'
            
            # Check for weekend/holiday
            from utils.attendance_processor import check_holiday_and_weekend
            is_holiday, is_weekend = check_holiday_and_weekend(new_record, employee)
            new_record.is_holiday = is_holiday
            new_record.is_weekend = is_weekend
            
            # Calculate overtime if applicable
            if new_record.work_hours > 8.0:
                calculate_overtime(new_record, recalculate=True, commit=False)
            
            db.session.add(new_record)
            db.session.flush()
            created_record_ids.append(new_record.id)
        
        # Commit all changes
        db.session.commit()
        
        # Verification
        print("\nVerifying records after changes...")
        all_record_ids = fixed_record_ids + created_record_ids
        
        # Query the database for these records to verify
        if all_record_ids:
            verification_records = AttendanceRecord.query.filter(
                AttendanceRecord.id.in_(all_record_ids)
            ).all()
            
            print(f"Found {len(verification_records)} records in verification query")
            for record in verification_records[:5]:  # Print just a sample
                print(f"Record {record.id}: date={record.date}, status={record.status}, "
                      f"check_in={record.check_in}, check_out={record.check_out}, "
                      f"work_hours={record.work_hours}, break_duration={record.break_duration}")
        
        # Count final records for February 2025
        final_count = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee_id,
            extract('month', AttendanceRecord.date) == 2,
            extract('year', AttendanceRecord.date) == 2025
        ).count()
        
        print(f"\nFinal count of records for February 2025: {final_count}")
        print(f"Fixed {len(fixed_record_ids)} existing records")
        print(f"Created {len(created_record_ids)} new records")

if __name__ == "__main__":
    fix_february_batch_entries()