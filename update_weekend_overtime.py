"""
Script to update weekend and holiday overtime calculation.
This script ensures that ALL hours worked on weekends and holidays are considered overtime,
not just hours beyond the standard workday (8 hours).
"""
import os
import sys
from datetime import datetime, timedelta
from flask import Flask
from main import app  # Import the Flask app
from app import db
from models import AttendanceRecord, Employee

def update_weekend_holiday_overtime():
    """
    Update all weekend and holiday attendance records to ensure all hours
    are counted as overtime at the appropriate rate.
    """
    print("Fixing weekend and holiday overtime in attendance records...")
    
    try:
        # Get all weekend and holiday attendance records
        records = AttendanceRecord.query.filter(
            (AttendanceRecord.is_weekend == True) | (AttendanceRecord.is_holiday == True)
        ).all()
        
        update_count = 0
        
        for record in records:
            # Skip records with no work hours
            if not record.work_hours or record.work_hours <= 0:
                continue
                
            # Get employee to check overtime eligibility
            employee = record.employee
                
            if record.is_holiday:
                # For holidays, check if employee is eligible for holiday overtime
                if employee and employee.eligible_for_holiday_overtime:
                    if record.holiday_overtime_hours != record.work_hours:
                        record.holiday_overtime_hours = record.work_hours
                        record.overtime_hours = record.work_hours
                        record.overtime_rate = 2.0  # Standard holiday rate
                        
                        # Update night overtime if it's a night shift
                        if record.shift_type == 'night':
                            record.overtime_night_hours = record.work_hours
                            
                        db.session.add(record)
                        update_count += 1
                        
            elif record.is_weekend:
                # For weekends, check if employee is eligible for weekend overtime
                if employee and employee.eligible_for_weekend_overtime:
                    if record.weekend_overtime_hours != record.work_hours:
                        record.weekend_overtime_hours = record.work_hours
                        record.overtime_hours = record.work_hours
                        record.overtime_rate = 2.0  # Standard weekend rate
                        
                        # Update night overtime if it's a night shift
                        if record.shift_type == 'night':
                            record.overtime_night_hours = record.work_hours
                            
                        db.session.add(record)
                        update_count += 1
        
        # Commit all changes
        db.session.commit()
        print(f"Updated overtime calculation for {update_count} weekend/holiday records")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating weekend/holiday overtime: {str(e)}")

def main():
    """Main function to execute the script"""
    print("Starting weekend/holiday overtime update...")
    
    # Use the Flask application context
    with app.app_context():
        update_weekend_holiday_overtime()
    
    print("Done!")
    
if __name__ == "__main__":
    main()