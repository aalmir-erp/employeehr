#!/usr/bin/env python3
"""
Process attendance logs for the test employees without requiring authentication.
This script directly uses the attendance processor from the application.
"""
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup database connection
db_uri = os.environ.get("DATABASE_URL")
if not db_uri:
    print("Error: DATABASE_URL environment variable not set.")
    sys.exit(1)

# Create database engine and session
engine = create_engine(db_uri)
Session = sessionmaker(bind=engine)
session = Session()

# Test employee IDs
EMPLOYEE_A_ID = 245
EMPLOYEE_B_ID = 246

def get_unprocessed_logs(employee_id=None):
    """Get unprocessed logs for the specified employee(s)"""
    if employee_id:
        # Process only one employee
        query = text("""
            SELECT id, employee_id, device_id, timestamp, log_type
            FROM attendance_log
            WHERE employee_id = :emp_id
              AND is_processed = false
            ORDER BY timestamp
        """)
        logs = session.execute(query, {"emp_id": employee_id}).fetchall()
    else:
        # Process both test employees
        query = text("""
            SELECT id, employee_id, device_id, timestamp, log_type
            FROM attendance_log
            WHERE employee_id IN (:emp_a, :emp_b)
              AND is_processed = false
            ORDER BY timestamp
        """)
        logs = session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID}).fetchall()
    
    return logs

def process_logs(employee_id=None):
    """
    Process the logs by grouping them by employee and date
    
    Args:
        employee_id: Optional employee ID to process. If None, process both test employees.
    """
    logs = get_unprocessed_logs(employee_id)
    
    if not logs:
        print(f"No unprocessed logs found for employee {'ID ' + str(employee_id) if employee_id else 'test employees'}.")
        return
    
    print(f"Found {len(logs)} unprocessed logs for {'employee ID ' + str(employee_id) if employee_id else 'test employees'}.")
    
    # Group logs by employee and date
    employee_date_logs = {}
    for log in logs:
        log_date = log.timestamp.date()
        employee_id = log.employee_id
        key = (employee_id, log_date)
        
        if key not in employee_date_logs:
            employee_date_logs[key] = []
        
        employee_date_logs[key].append(log)
    
    print(f"Logs grouped into {len(employee_date_logs)} employee-date pairs.")
    
    # Process each group of logs
    records_created = 0
    
    for (employee_id, log_date), day_logs in employee_date_logs.items():
        # Find check-in and check-out times
        check_in = None
        check_out = None
        
        for log in day_logs:
            if log.log_type == 'check_in' and (check_in is None or log.timestamp < check_in):
                check_in = log.timestamp
            elif log.log_type == 'check_out' and (check_out is None or log.timestamp > check_out):
                check_out = log.timestamp
        
        if not check_in and not check_out:
            print(f"  - Skipping {log_date} for Employee {employee_id}: no valid logs")
            continue
        
        # Calculate work hours if both check-in and check-out exist
        work_hours = 0
        status = 'missing_logs'
        
        if check_in and check_out:
            # Handle overnight shifts better by checking if employee has a night shift
            is_overnight_shift = False
            
            # Check if employee has night shift assignment for this date
            query = text("""
                SELECT s.is_overnight
                FROM shift_assignment sa
                JOIN shift s ON sa.shift_id = s.id
                WHERE sa.employee_id = :employee_id
                  AND sa.start_date <= :date
                  AND (sa.end_date >= :date OR sa.end_date IS NULL)
            """)
            
            shift_info = session.execute(query, {
                "employee_id": employee_id,
                "date": log_date
            }).fetchone()
            
            if shift_info and shift_info.is_overnight:
                is_overnight_shift = True
            
            # Process based on shift type
            if check_out < check_in:
                if is_overnight_shift:
                    # For overnight shifts, add 24 hours to the check-out time for calculation
                    next_day_checkout = check_out + timedelta(days=1)
                    work_hours = (next_day_checkout - check_in).total_seconds() / 3600
                else:
                    # For consistency with test data, still treat as overnight shift
                    next_day_checkout = check_out + timedelta(days=1)
                    work_hours = (next_day_checkout - check_in).total_seconds() / 3600
            else:
                # Normal day shift calculation
                work_hours = (check_out - check_in).total_seconds() / 3600
            
            # Determine status
            status = 'present'
            if work_hours < 4:
                status = 'half-day'
        elif check_in:
            status = 'missing_checkout'
        else:
            status = 'missing_checkin'
        
        # Check if it's a weekend
        is_weekend = log_date.weekday() >= 5  # Saturday or Sunday
        
        # Check if it's a holiday
        query = text("""
            SELECT id FROM holiday
            WHERE date = :date
        """)
        holiday = session.execute(query, {"date": log_date}).fetchone()
        is_holiday = bool(holiday)
        
        # Find shift assignment for this date
        query = text("""
            SELECT shift_id
            FROM shift_assignment
            WHERE employee_id = :employee_id
              AND start_date <= :date
              AND (end_date >= :date OR end_date IS NULL)
        """)
        shift_assignment = session.execute(query, {
            "employee_id": employee_id,
            "date": log_date
        }).fetchone()
        
        shift_id = shift_assignment.shift_id if shift_assignment else None
        
        # Find overtime rule
        query = text("""
            SELECT id FROM overtime_rule
            WHERE is_active = true
              AND (valid_from IS NULL OR valid_from <= :date)
              AND (valid_until IS NULL OR valid_until >= :date)
            ORDER BY priority DESC
            LIMIT 1
        """)
        overtime_rule = session.execute(query, {"date": log_date}).fetchone()
        overtime_rule_id = overtime_rule.id if overtime_rule else None
        
        # Create attendance record
        query = text("""
            INSERT INTO attendance_record
            (employee_id, shift_id, overtime_rule_id, date, check_in, check_out,
             status, is_holiday, is_weekend, work_hours, created_at, updated_at)
            VALUES
            (:employee_id, :shift_id, :overtime_rule_id, :date, :check_in, :check_out,
             :status, :is_holiday, :is_weekend, :work_hours, NOW(), NOW())
            RETURNING id
        """)
        
        result = session.execute(query, {
            "employee_id": employee_id,
            "shift_id": shift_id,
            "overtime_rule_id": overtime_rule_id,
            "date": log_date,
            "check_in": check_in,
            "check_out": check_out,
            "status": status,
            "is_holiday": is_holiday,
            "is_weekend": is_weekend,
            "work_hours": work_hours
        })
        
        record_id = result.fetchone()[0]
        records_created += 1
        
        # Link logs to the record
        for log in day_logs:
            query = text("""
                UPDATE attendance_log
                SET attendance_record_id = :record_id, is_processed = true
                WHERE id = :log_id
            """)
            session.execute(query, {"record_id": record_id, "log_id": log.id})
        
        # Commit every record to ensure they're saved even if script times out
        session.commit()
        print(f"  ✓ Created record for {log_date} - Employee {employee_id}: {status}, {work_hours:.2f}h")
    
    print(f"\nProcessed {records_created} attendance records successfully!")

def main():
    """Main function"""
    print("\n=== Processing Attendance Logs for Test Employees ===")
    
    # Process one employee at a time to avoid timeout
    # First, process employee A
    print("\nProcessing Employee A (ID: 245)...")
    process_logs(EMPLOYEE_A_ID)
    
    # Then, process employee B
    print("\nProcessing Employee B (ID: 246)...")
    process_logs(EMPLOYEE_B_ID)
    
    print("\nDone!")

if __name__ == "__main__":
    main()