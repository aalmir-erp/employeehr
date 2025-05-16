"""
Test script to verify break time detection and storage.

This script:
1. Creates a test attendance record with explicit break start/end times
2. Verifies that these timestamps are correctly stored in the database
3. Tests the break detection algorithm with a set of test logs

To run:
$ python test_break_detection.py
"""
import os
import sys
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add the current directory to the path so we can import our models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import models
from models import AttendanceRecord, AttendanceLog, Employee, db, Base
from utils.attendance_processor import estimate_break_duration

# Get database URL from environment
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Create engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def test_direct_break_time_storage():
    """Test direct storage of break_start and break_end fields"""
    print("\n=== Testing direct break time storage ===")
    
    # Test date - use a future date to avoid conflicts
    test_date = date(2025, 6, 1)
    
    # Check if record already exists
    existing = session.query(AttendanceRecord).filter(
        AttendanceRecord.employee_id == 260,
        AttendanceRecord.date == test_date
    ).first()
    
    if existing:
        # Update existing record
        record = existing
        print(f"Updating existing record {record.id} for break time test")
    else:
        # Create new record
        record = AttendanceRecord()
        record.employee_id = 260
        record.date = test_date
        record.shift_type = 'day'
        record.status = 'present'
        print(f"Creating new record for break time test")
    
    # Set explicit check-in and check-out times
    record.check_in = datetime(2025, 6, 1, 8, 0, 0)
    record.check_out = datetime(2025, 6, 1, 17, 0, 0)
    
    # Set explicit break times
    record.break_start = datetime(2025, 6, 1, 12, 0, 0)
    record.break_end = datetime(2025, 6, 1, 13, 0, 0)
    record.break_duration = 1.0
    
    # Calculate total hours
    record.total_duration = 9.0
    record.work_hours = 8.0
    
    # Save the record
    session.add(record)
    
    try:
        session.commit()
        print(f"Successfully saved test record with break_start={record.break_start}, break_end={record.break_end}")
        
        # Verify the record was saved correctly
        saved = session.query(AttendanceRecord).get(record.id)
        print(f"Verification: break_start={saved.break_start}, break_end={saved.break_end}")
        
        if saved.break_start and saved.break_end:
            print("SUCCESS: Break times were saved correctly")
        else:
            print("ERROR: Break times were not saved correctly")
    except Exception as e:
        session.rollback()
        print(f"Failed to save test record: {str(e)}")
    
    return record.id if record else None

def create_test_logs():
    """Create test logs with a clear break pattern"""
    print("\n=== Creating test logs with a break pattern ===")
    
    # Define test date - use a future date to avoid conflicts
    test_date = date(2025, 6, 2)
    
    # Clear any existing logs for this date and employee
    session.query(AttendanceLog).filter(
        AttendanceLog.employee_id == 260,
        func.date(AttendanceLog.timestamp) == test_date
    ).delete()
    
    # Clear any existing attendance record
    session.query(AttendanceRecord).filter(
        AttendanceRecord.employee_id == 260,
        AttendanceRecord.date == test_date
    ).delete()
    
    # Create test logs: 
    # - Start work at 8:00 AM
    # - Go to lunch at 12:00 PM
    # - Return from lunch at 1:00 PM
    # - Leave work at 5:00 PM
    logs = [
        AttendanceLog(
            employee_id=260,
            device_id=3,
            timestamp=datetime(2025, 6, 2, 8, 0, 0),
            log_type='check_in',
            is_processed=False
        ),
        AttendanceLog(
            employee_id=260,
            device_id=3,
            timestamp=datetime(2025, 6, 2, 12, 0, 0),
            log_type='check_out',
            is_processed=False
        ),
        AttendanceLog(
            employee_id=260,
            device_id=3,
            timestamp=datetime(2025, 6, 2, 13, 0, 0),
            log_type='check_in',
            is_processed=False
        ),
        AttendanceLog(
            employee_id=260,
            device_id=3,
            timestamp=datetime(2025, 6, 2, 17, 0, 0),
            log_type='check_out',
            is_processed=False
        )
    ]
    
    # Add logs to the session
    for log in logs:
        session.add(log)
    
    # Save the logs
    try:
        session.commit()
        print(f"Successfully created {len(logs)} test logs for 2025-06-02")
    except Exception as e:
        session.rollback()
        print(f"Failed to create test logs: {str(e)}")
    
    return [log.id for log in logs]

def test_break_detection_algorithm():
    """Test the break detection algorithm directly"""
    print("\n=== Testing break detection algorithm ===")
    
    # Get the logs we created
    logs = session.query(AttendanceLog).filter(
        AttendanceLog.employee_id == 260,
        func.date(AttendanceLog.timestamp) == date(2025, 6, 2)
    ).all()
    
    if not logs or len(logs) < 3:
        print(f"ERROR: Not enough logs to test (found {len(logs) if logs else 0})")
        return
    
    # Call the break detection function
    break_duration, break_start, break_end = estimate_break_duration(logs)
    
    # Print the results
    print(f"Break detection results:")
    print(f"  Break duration: {break_duration} hours")
    print(f"  Break start: {break_start}")
    print(f"  Break end: {break_end}")
    
    # Verify results
    if break_duration >= 0.9 and break_duration <= 1.1:
        print("SUCCESS: Break duration detected correctly")
    else:
        print(f"ERROR: Break duration incorrect: {break_duration} (expected ~1.0)")
    
    if break_start and break_start.hour == 12:
        print("SUCCESS: Break start time detected correctly")
    else:
        print(f"ERROR: Break start time incorrect: {break_start} (expected ~12:00)")
    
    if break_end and break_end.hour == 13:
        print("SUCCESS: Break end time detected correctly")
    else:
        print(f"ERROR: Break end time incorrect: {break_end} (expected ~13:00)")

def test_break_detection_with_logs():
    """Test the full break detection process with logs"""
    print("\n=== Testing full break detection process ===")
    
    # Get the logs we created
    logs = session.query(AttendanceLog).filter(
        AttendanceLog.employee_id == 260,
        func.date(AttendanceLog.timestamp) == date(2025, 6, 2)
    ).all()
    
    # Process the logs manually
    check_in = logs[0].timestamp
    check_out = logs[-1].timestamp
    
    # Detect break times
    break_duration, break_start, break_end = estimate_break_duration(logs)
    
    # Create attendance record
    record = AttendanceRecord()
    record.employee_id = 260
    record.date = date(2025, 6, 2)
    record.check_in = check_in
    record.check_out = check_out
    record.break_duration = break_duration
    record.break_start = break_start
    record.break_end = break_end
    record.shift_type = 'day'
    record.status = 'present'
    record.total_duration = (check_out - check_in).total_seconds() / 3600
    record.work_hours = record.total_duration - break_duration
    
    # Save the record
    session.add(record)
    
    try:
        session.commit()
        print(f"Successfully saved attendance record with break times")
        
        # Verify the record was saved correctly
        saved = session.query(AttendanceRecord).get(record.id)
        print(f"Verification: break_start={saved.break_start}, break_end={saved.break_end}")
        
        if saved.break_start and saved.break_end:
            print("SUCCESS: Break times were saved correctly")
        else:
            print("ERROR: Break times were not saved correctly")
    except Exception as e:
        session.rollback()
        print(f"Failed to save attendance record: {str(e)}")
    
    # Mark logs as processed
    for log in logs:
        log.is_processed = True
        log.attendance_record_id = record.id
    
    try:
        session.commit()
        print(f"Successfully marked logs as processed")
    except Exception as e:
        session.rollback()
        print(f"Failed to mark logs as processed: {str(e)}")
    
    return record.id if record else None

def main():
    """Run all tests"""
    print("=== Break Time Detection Test Suite ===")
    
    # Test direct storage of break times
    record_id = test_direct_break_time_storage()
    
    # Create test logs
    log_ids = create_test_logs()
    
    # Test break detection algorithm
    test_break_detection_algorithm()
    
    # Test full break detection process
    test_break_detection_with_logs()
    
    print("\n=== All tests completed ===")

if __name__ == "__main__":
    main()