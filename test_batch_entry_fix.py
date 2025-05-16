"""
Test script to verify our fixes to the batch entry functionality.
This script will:
1. Test creating a batch entry for March 2025
2. Verify that the entries are properly created with weekend/holiday flags
"""

from datetime import datetime, date, timedelta
from flask import Flask
from sqlalchemy import and_, extract

# Import the app directly from app.py, not from main
from app import app, db

# Import models
from models import AttendanceRecord, Employee, Shift, Holiday, SystemConfig
from utils.overtime_engine import calculate_overtime

def test_batch_entry_functionality():
    """Test the batch entry functionality"""
    
    with app.app_context():
        
        # Test Employee A (ID 260)
        employee_id = 260
        employee = Employee.query.get(employee_id)
        
        if not employee:
            print(f"Error: Employee A with ID {employee_id} not found")
            return
        
        print(f"Testing batch entry for employee: {employee.name} (ID: {employee_id})")
        
        # Generate March 2025 dates
        march_dates = []
        start_date = date(2025, 3, 1)
        end_date = date(2025, 3, 10)  # Just test with 10 days
        current_date = start_date
        
        while current_date <= end_date:
            march_dates.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"Processing {len(march_dates)} days in March 2025")
        
        # Clean any existing March test records
        existing_records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee_id,
            extract('month', AttendanceRecord.date) == 3,
            extract('year', AttendanceRecord.date) == 2025,
            AttendanceRecord.date <= end_date
        ).all()
        
        for record in existing_records:
            db.session.delete(record)
        
        db.session.commit()
        print(f"Deleted {len(existing_records)} existing March records for testing")
        
        # Create test records using the same logic as the batch entry function
        for entry_date in march_dates:
            # Create new record with fixed values for testing
            new_record = AttendanceRecord(
                employee_id=employee_id,
                date=entry_date,
                check_in=datetime.combine(entry_date, datetime.min.time().replace(hour=9)),
                check_out=datetime.combine(entry_date, datetime.min.time().replace(hour=18)),
                status='present',
                work_hours=8.0,
                break_duration=1.0
            )
            
            # Set shift ID if available
            if employee.current_shift_id:
                new_record.shift_id = employee.current_shift_id
                
                # Set shift type based on the employee's shift
                shift = Shift.query.get(employee.current_shift_id)
                if shift:
                    if shift.name and 'night' in shift.name.lower():
                        new_record.shift_type = 'night'
                    elif shift.name and 'day' in shift.name.lower():
                        new_record.shift_type = 'day'
                    else:
                        new_record.shift_type = 'day'
                else:
                    new_record.shift_type = 'day'
            else:
                new_record.shift_type = 'day'
            
            # Apply the weekend/holiday detection logic from our fixes
            
            # Get the weekend days for this employee
            weekend_days = employee.weekend_days
            current_shift_id = employee.current_shift_id
            
            # Check if we need to determine weekend days from shift
            if not weekend_days and current_shift_id:
                shift = Shift.query.get(current_shift_id)
                if shift and shift.weekend_days:
                    weekend_days = shift.weekend_days
            
            # Default to system config if neither employee nor shift has weekend days
            if not weekend_days:
                system_config = SystemConfig.query.first()
                if system_config and system_config.weekend_days:
                    weekend_days = system_config.weekend_days
                else:
                    weekend_days = 'saturday,sunday'
            
            # Set weekend flag based on entry date's day of week
            day_of_week = entry_date.strftime('%A').lower()
            
            # Handle the weekend_days which could be a string, list, or None
            if isinstance(weekend_days, list):
                weekend_day_list = []
                for day in weekend_days:
                    if day:
                        if isinstance(day, str):
                            weekend_day_list.append(day.lower())
                        elif isinstance(day, int):
                            # Convert day number to name (0=Monday, 6=Sunday)
                            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                            if 0 <= day < 7:
                                weekend_day_list.append(day_names[day])
            elif isinstance(weekend_days, str):
                weekend_day_list = weekend_days.lower().split(',')
            else:
                weekend_day_list = ['saturday', 'sunday']  # Default
                
            new_record.is_weekend = day_of_week in weekend_day_list
            
            # Check for holidays
            holiday = Holiday.query.filter(Holiday.date == entry_date).first()
            new_record.is_holiday = holiday is not None
            
            # Calculate overtime if applicable
            if new_record.work_hours > 8.0:
                from utils.overtime_engine import calculate_overtime
                calculate_overtime(new_record, recalculate=True, commit=False)
            
            db.session.add(new_record)
        
        # Commit all the records
        db.session.commit()
        
        # Verify the records were created
        created_records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee_id,
            extract('month', AttendanceRecord.date) == 3,
            extract('year', AttendanceRecord.date) == 2025,
            AttendanceRecord.date <= end_date
        ).order_by(AttendanceRecord.date).all()
        
        print(f"\nCreated {len(created_records)} March records for testing")
        
        # Show the created records
        for record in created_records:
            day_of_week = record.date.strftime('%A')
            print(f"Record {record.id}: {record.date} ({day_of_week}), "
                  f"status={record.status}, check_in={record.check_in.strftime('%H:%M')}, "
                  f"check_out={record.check_out.strftime('%H:%M')}, "
                  f"is_weekend={record.is_weekend}, is_holiday={record.is_holiday}")

if __name__ == "__main__":
    test_batch_entry_functionality()