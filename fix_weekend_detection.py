"""
Script to fix the weekend detection for Employee A (ID 260) on April 13th, 2025.
"""
import os
import sys
from datetime import datetime
from flask import Flask
from main import app
from models import db, AttendanceRecord, Employee
from utils.overtime_engine import calculate_overtime

def fix_weekend_overtime_for_employee_a():
    """Fix weekend overtime for Employee A on April 13th"""
    print("Fixing weekend detection for Employee A (ID 260) on April 13th, 2025...")
    
    try:
        # Get the specific record
        record = AttendanceRecord.query.filter_by(
            employee_id=260,
            date='2025-04-13'
        ).first()
        
        if not record:
            print("Record not found!")
            return
            
        print(f"Found record: ID={record.id}, date={record.date}, is_weekend={record.is_weekend}")
        print(f"Current overtime: total={record.overtime_hours}, regular={record.regular_overtime_hours}, weekend={record.weekend_overtime_hours}")
        
        # Set the is_weekend flag to True
        record.is_weekend = True
        
        # Get the employee
        employee = Employee.query.get(260)
        if not employee:
            print("Employee not found!")
            return
        
        # Save the change
        db.session.commit()
        print(f"Updated is_weekend to {record.is_weekend}")
        
        # Recalculate overtime
        try:
            # Check employee eligibility
            if employee.eligible_for_weekend_overtime:
                print(f"Employee is eligible for weekend overtime")
                
                # Move hours from regular overtime to weekend overtime
                hours = record.work_hours - 8  # Assuming 8-hour standard day
                if hours > 0:
                    record.regular_overtime_hours = 0
                    record.weekend_overtime_hours = hours
                    record.overtime_hours = hours
                    
                    db.session.commit()
                    print(f"Updated overtime hours: regular={record.regular_overtime_hours}, weekend={record.weekend_overtime_hours}, total={record.overtime_hours}")
                else:
                    print(f"No overtime hours to update (work_hours={record.work_hours})")
            else:
                print(f"Employee is NOT eligible for weekend overtime")
        except Exception as e:
            db.session.rollback()
            print(f"Error recalculating overtime: {str(e)}")
    except Exception as e:
        db.session.rollback()
        print(f"Error processing record: {str(e)}")

def main():
    """Main function"""
    with app.app_context():
        fix_weekend_overtime_for_employee_a()

if __name__ == "__main__":
    main()