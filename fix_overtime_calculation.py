"""
Direct SQL script to fix overtime calculation in attendance_record table.
This script ensures that overtime_hours is correctly set as the sum of 
regular_overtime_hours, weekend_overtime_hours, and holiday_overtime_hours.
"""
import os
import sys
from datetime import datetime, timedelta
from flask import Flask
from main import app  # Import the Flask app
from app import db
from models import AttendanceRecord

def fix_overtime_calculation():
    """
    Update all attendance records to ensure overtime_hours is correctly calculated
    as the sum of all overtime category hours.
    """
    print("Fixing overtime calculation in attendance records...")
    
    try:
        # Get all attendance records
        records = AttendanceRecord.query.all()
        update_count = 0
        
        for record in records:
            # Calculate the correct total overtime
            total_overtime = (
                record.regular_overtime_hours +
                record.weekend_overtime_hours +
                record.holiday_overtime_hours
            )
            
            # Check if the current value is incorrect
            if record.overtime_hours != total_overtime:
                record.overtime_hours = total_overtime
                db.session.add(record)
                update_count += 1
        
        # Commit all changes
        db.session.commit()
        print(f"Updated overtime_hours for {update_count} records")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error fixing overtime calculation: {str(e)}")

def fix_night_shift_overtime():
    """
    Update night shift records to ensure overtime_night_hours is correctly set 
    when shift_type is 'night'.
    """
    print("Fixing night shift overtime in attendance records...")
    
    try:
        # Get all night shift attendance records with overtime
        night_records = AttendanceRecord.query.filter(
            AttendanceRecord.shift_type == 'night',
            AttendanceRecord.overtime_hours > 0
        ).all()
        
        update_count = 0
        
        for record in night_records:
            # For night shifts, set overtime_night_hours equal to total overtime
            if record.overtime_night_hours != record.overtime_hours:
                record.overtime_night_hours = record.overtime_hours
                db.session.add(record)
                update_count += 1
        
        # Commit all changes
        db.session.commit()
        print(f"Updated overtime_night_hours for {update_count} night shift records")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error fixing night shift overtime: {str(e)}")

def main():
    """Main function to execute the script"""
    print("Starting overtime calculation fix...")
    
    # Use the Flask application context
    with app.app_context():
        # Fix regular overtime calculation
        fix_overtime_calculation()
        
        # Fix night shift overtime
        fix_night_shift_overtime()
    
    print("Done!")
    
if __name__ == "__main__":
    main()