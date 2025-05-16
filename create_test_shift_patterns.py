#!/usr/bin/env python3
"""
Creates test shift patterns for employees with varying scenarios including:
- Day shift employees
- Night shift employees
- Mixed shift patterns
- Weekend working patterns
- Different break durations

This script helps visualize and test different attendance scenarios.
"""
import os
import sys
import random
from datetime import datetime, timedelta
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup database connection
db_uri = os.environ.get("DATABASE_URL")
if not db_uri:
    print("Error: DATABASE_URL environment variable not set.")
    sys.exit(1)

# Create a minimal Flask app to use the same database configuration
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Create database engine and session
engine = create_engine(db_uri)
Session = sessionmaker(bind=engine)
session = Session()

# Constants
SHIFT_A_ID = 1  # Day shift (9 AM - 5 PM)
NIGHT_SHIFT_ID = 2  # Night shift (8 PM - 8 AM)
DEVICE_ID = 3  # ZKTeco CSV Import device

# Helper function to get employees from specified departments
def get_employees_by_department(department, limit=5):
    """Get a list of employees from a specific department"""
    query = text("""
        SELECT id, name, employee_code, department, position 
        FROM employee 
        WHERE department = :department
        ORDER BY id
        LIMIT :limit
    """)
    result = session.execute(query, {"department": department, "limit": limit})
    employees = []
    for row in result:
        employees.append({
            "id": row.id,
            "name": row.name,
            "employee_code": row.employee_code,
            "department": row.department,
            "position": row.position
        })
    return employees

# Function to create shift assignments for an employee
def create_shift_assignments(employee_id, shift_id, start_date, end_date, days_of_week=None):
    """
    Create shift assignments for an employee
    
    Args:
        employee_id: ID of the employee
        shift_id: ID of the shift
        start_date: Start date for assignments
        end_date: End date for assignments
        days_of_week: List of day numbers (0=Monday, 6=Sunday) to create assignments for
                     If None, assignments will be created for all days
    """
    if days_of_week is None:
        days_of_week = list(range(7))  # All days
        
    # Convert to datetime objects if they're strings
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
    # Delete existing assignments in this date range
    delete_query = text("""
        DELETE FROM shift_assignment
        WHERE employee_id = :employee_id
        AND start_date >= :start_date
        AND start_date <= :end_date
    """)
    session.execute(delete_query, {
        "employee_id": employee_id,
        "start_date": start_date,
        "end_date": end_date
    })
    
    current_date = start_date
    assignments = []
    
    while current_date <= end_date:
        # Only create assignment if the day of week is in the specified list
        if current_date.weekday() in days_of_week:
            insert_query = text("""
                INSERT INTO shift_assignment 
                (employee_id, shift_id, start_date, end_date, created_at, updated_at)
                VALUES (:employee_id, :shift_id, :start_date, :start_date, NOW(), NOW())
                RETURNING id
            """)
            result = session.execute(insert_query, {
                "employee_id": employee_id,
                "shift_id": shift_id,
                "start_date": current_date
            })
            assignment_id = result.fetchone()[0]
            assignments.append({
                "id": assignment_id,
                "date": current_date.strftime("%Y-%m-%d"),
                "shift_id": shift_id
            })
            
        current_date += timedelta(days=1)
        
    session.commit()
    return assignments

# Function to generate clock in/out times with variations
def generate_attendance_times(shift_id, date_str, employee_id, variations=True):
    """Generate clock-in and clock-out times based on shift with realistic variations"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # Get shift details
    shift_query = text("SELECT start_time, end_time, is_overnight FROM shift WHERE id = :shift_id")
    shift = session.execute(shift_query, {"shift_id": shift_id}).fetchone()
    
    if not shift:
        print(f"Shift with ID {shift_id} not found")
        return None
        
    # Parse shift times
    start_time = datetime.strptime(str(shift.start_time), "%H:%M:%S").time()
    end_time = datetime.strptime(str(shift.end_time), "%H:%M:%S").time()
    is_overnight = shift.is_overnight
    
    # Create datetime objects for clock in/out
    check_in_time = datetime.combine(date_obj, start_time)
    
    if is_overnight:
        next_day = date_obj + timedelta(days=1)
        check_out_time = datetime.combine(next_day, end_time)
    else:
        check_out_time = datetime.combine(date_obj, end_time)
    
    # Add realistic variations if requested
    if variations:
        # Random early/late arrival (-10 to +15 minutes)
        check_in_variation = random.randint(-10, 15)
        check_in_time += timedelta(minutes=check_in_variation)
        
        # Random early/late departure (-5 to +20 minutes)
        check_out_variation = random.randint(-5, 20)
        check_out_time += timedelta(minutes=check_out_variation)
    
    return {
        "check_in": check_in_time,
        "check_out": check_out_time,
        "employee_id": employee_id,
        "date": date_obj
    }

# Create attendance logs for the given times
def create_attendance_logs(attendance_data):
    """Create attendance logs (clock in and out) for an employee"""
    if not attendance_data:
        return None
        
    # Clock in log
    clock_in_query = text("""
        INSERT INTO attendance_log
        (employee_id, device_id, log_type, timestamp, is_processed, created_at)
        VALUES
        (:employee_id, :device_id, 'check_in', :timestamp, false, NOW())
        RETURNING id
    """)
    
    # Clock out log
    clock_out_query = text("""
        INSERT INTO attendance_log
        (employee_id, device_id, log_type, timestamp, is_processed, created_at)
        VALUES
        (:employee_id, :device_id, 'check_out', :timestamp, false, NOW())
        RETURNING id
    """)
    
    # Insert clock in log
    clock_in_id = session.execute(clock_in_query, {
        "employee_id": attendance_data["employee_id"],
        "device_id": DEVICE_ID,
        "timestamp": attendance_data["check_in"]
    }).fetchone()[0]
    
    # Insert clock out log
    clock_out_id = session.execute(clock_out_query, {
        "employee_id": attendance_data["employee_id"],
        "device_id": DEVICE_ID,
        "timestamp": attendance_data["check_out"]
    }).fetchone()[0]
    
    session.commit()
    
    return {
        "clock_in_id": clock_in_id,
        "clock_out_id": clock_out_id,
        "check_in": attendance_data["check_in"],
        "check_out": attendance_data["check_out"]
    }

# Main function
def main():
    # Define date range for test data (past month)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    print(f"Creating test shift patterns from {start_date} to {end_date}")
    
    # Create different patterns for employees
    
    # 1. Day shift employees - Production department
    print("\n1. Creating standard day shift patterns for Production employees")
    production_employees = get_employees_by_department("Production", limit=2)
    for employee in production_employees:
        print(f"  - Creating weekday shifts for {employee['name']}")
        # Monday to Friday day shifts
        assignments = create_shift_assignments(
            employee['id'], 
            SHIFT_A_ID, 
            start_date, 
            end_date, 
            days_of_week=[0, 1, 2, 3, 4]  # Monday to Friday
        )
        
        # Create attendance records for each assignment
        for assignment in assignments:
            attendance_data = generate_attendance_times(
                SHIFT_A_ID, 
                assignment['date'], 
                employee['id']
            )
            create_attendance_logs(attendance_data)
            
        print(f"    Created {len(assignments)} day shifts with attendance logs")
    
    # 2. Night shift employees - Packaging department
    print("\n2. Creating night shift patterns for Packaging employees")
    packaging_employees = get_employees_by_department("Packaging", limit=2)
    for employee in packaging_employees:
        print(f"  - Creating night shifts for {employee['name']}")
        # Sunday to Thursday night shifts (common in Middle East)
        assignments = create_shift_assignments(
            employee['id'], 
            NIGHT_SHIFT_ID, 
            start_date, 
            end_date, 
            days_of_week=[6, 0, 1, 2, 3]  # Sunday to Thursday
        )
        
        # Create attendance records for each assignment
        for assignment in assignments:
            attendance_data = generate_attendance_times(
                NIGHT_SHIFT_ID, 
                assignment['date'], 
                employee['id']
            )
            create_attendance_logs(attendance_data)
            
        print(f"    Created {len(assignments)} night shifts with attendance logs")
    
    # 3. Mixed shift patterns - Quality Control department
    print("\n3. Creating mixed shift patterns for QC employees")
    qc_employees = get_employees_by_department("Quality Control", limit=2)
    if qc_employees:
        employee = qc_employees[0]
        print(f"  - Creating rotating shifts for {employee['name']}")
        
        # Week 1: Day shifts
        week1_start = start_date
        week1_end = start_date + timedelta(days=6)
        day_assignments = create_shift_assignments(
            employee['id'], 
            SHIFT_A_ID, 
            week1_start, 
            week1_end
        )
        
        # Week 2: Night shifts
        week2_start = start_date + timedelta(days=7)
        week2_end = start_date + timedelta(days=13)
        night_assignments = create_shift_assignments(
            employee['id'], 
            NIGHT_SHIFT_ID, 
            week2_start, 
            week2_end
        )
        
        # Create attendance records for each assignment
        for assignment in day_assignments + night_assignments:
            shift_id = assignment['shift_id']
            attendance_data = generate_attendance_times(
                shift_id, 
                assignment['date'], 
                employee['id']
            )
            create_attendance_logs(attendance_data)
            
        print(f"    Created {len(day_assignments)} day shifts and {len(night_assignments)} night shifts")
    
    # 4. Weekend worker - Another QC employee
    if len(qc_employees) > 1:
        employee = qc_employees[1]
        print(f"  - Creating weekend-focused shifts for {employee['name']}")
        
        # Mostly weekend shifts with some weekdays
        weekend_assignments = create_shift_assignments(
            employee['id'], 
            SHIFT_A_ID, 
            start_date, 
            end_date, 
            days_of_week=[3, 4, 5, 6]  # Thursday to Sunday
        )
        
        # Create attendance records for each assignment
        for assignment in weekend_assignments:
            attendance_data = generate_attendance_times(
                SHIFT_A_ID, 
                assignment['date'], 
                employee['id']
            )
            create_attendance_logs(attendance_data)
            
        print(f"    Created {len(weekend_assignments)} weekend-focused shifts")
    
    print("\nTest shift patterns created successfully!")
    print("Please run the attendance processing to view these in reports: /attendance/process_all_logs")

if __name__ == "__main__":
    main()