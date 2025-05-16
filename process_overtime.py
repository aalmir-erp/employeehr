"""
Process overtime for all attendance records.
This script calculates overtime for all attendance records.
"""
import os
import sys
from datetime import datetime, time, date, timedelta
from flask import Flask
from main import app  # Import the Flask app
from app import db
from models import Employee, AttendanceRecord
from utils.overtime_engine import process_attendance_records

def main():
    """Main function to execute the script"""
    print("Processing overtime calculations for all attendance records...")
    
    # Use the Flask application context
    with app.app_context():
        # Process all attendance records
        count = process_attendance_records(recalculate=True)
        print(f"Successfully processed {count} attendance records")
        
        # Also update employee current_shift_id based on assignments
        update_current_shifts()
    
    print("Done!")
    
def update_current_shifts():
    """Update employee current_shift_id based on latest assignments"""
    from models import ShiftAssignment
    from sqlalchemy import func
    
    print("Updating employee current shifts...")
    
    try:
        # Get all employees
        employees = Employee.query.all()
        update_count = 0
        
        for employee in employees:
            # Get the most recent shift assignment
            latest_assignment = ShiftAssignment.query.filter(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.is_active == True
            ).order_by(ShiftAssignment.start_date.desc()).first()
            
            if latest_assignment and latest_assignment.shift_id != employee.current_shift_id:
                employee.current_shift_id = latest_assignment.shift_id
                db.session.add(employee)
                update_count += 1
        
        # Commit all changes
        db.session.commit()
        print(f"Updated current shift for {update_count} employees")
    except Exception as e:
        db.session.rollback()
        print(f"Error updating current shifts: {str(e)}")

if __name__ == "__main__":
    main()