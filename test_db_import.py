from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import csv
import re
from datetime import datetime
import os

# Get database URL from environment
DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    print("Error: DATABASE_URL environment variable not set")
    exit(1)

# Create a simple engine and session
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Define a simplified function to parse the CSV file
def parse_csv(file_path):
    records = []
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        reader = csv.reader(file)
        
        # Process rows for testing
        for idx, row in enumerate(reader):
            if idx >= 20:  # Process 20 rows for testing
                break
                
            if not row or len(row) < 10:  # Ensure we have enough columns
                continue
            
            # Check if this is a MIR format row
            is_mir_format = len(row) > 0 and row[0] == "Event Viewer Report"
            if is_mir_format:
                if idx == 0:
                    print("Detected MIR format CSV")
                
                # Extract data for MIR format
                try:
                    # Based on the exact structure of the provided CSV
                    employee_id = None
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee ID:":
                            employee_id = row[i+1].strip()
                            break
                    
                    employee_name = None
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee Name:":
                            employee_name = row[i+1].strip()
                            break
                    
                    # Find the Event field which indicates IN/OUT
                    event_type = None
                    event_idx = None
                    for i in range(len(row)):
                        if row[i] == "Event":
                            event_idx = i
                            break
                    
                    if event_idx is not None and event_idx + 1 < len(row):
                        # The event type (IN/OUT) is after the "Event" column
                        event_positions = [i for i, val in enumerate(row) if val in ["IN", "OUT"]]
                        if event_positions:
                            event_type = row[event_positions[0]]
                    
                    # Find the date and time
                    # Expected format: row contains a value like "01-Mar-25  08:23 am"
                    timestamp = None
                    
                    # Look for the punch timestamp (which has am/pm in it)
                    punch_timestamps = []
                    for i in range(len(row)):
                        if isinstance(row[i], str) and (" am" in row[i].lower() or " pm" in row[i].lower()):
                            punch_timestamps.append(row[i])
                    
                    if punch_timestamps:
                        # Try to parse the timestamp
                        try:
                            # Expected format is like "01-Mar-25  08:23 am"
                            timestamp = datetime.strptime(punch_timestamps[0], '%d-%b-%y  %I:%M %p')
                        except ValueError:
                            try:
                                # Try without the double space
                                timestamp = datetime.strptime(punch_timestamps[0], '%d-%b-%y %I:%M %p')
                            except ValueError:
                                print(f"Could not parse timestamp: {punch_timestamps[0]}")
                    
                    # Create a record if we have all required information
                    if employee_id and event_type and timestamp:
                        record = {
                            'employee_id': employee_id,
                            'employee_name': employee_name, 
                            'log_type': event_type,
                            'timestamp': timestamp
                        }
                        records.append(record)
                        print(f"Parsed record: {employee_id}, {employee_name}, {event_type}, {timestamp}")
                
                except Exception as e:
                    print(f"Error parsing row {idx}: {e}")
                    print(f"Row content: {row[:10]}...")
            
            else:
                # Standard format processing would go here
                if idx == 0:
                    print("Standard format CSV")
    
    return records

# Execute a simple query to check if we can access the database
def check_database():
    try:
        result = session.execute(text("SELECT current_database(), current_user, version();"))
        row = result.fetchone()
        print(f"Connected to database: {row[0]}")
        print(f"Current user: {row[1]}")
        print(f"Database version: {row[2]}")
        return True
    except Exception as e:
        print(f"Database connection error: {e}")
        return False

# Check if we have existing records
def check_existing_records():
    try:
        # Check employees table
        result = session.execute(text("SELECT COUNT(*) FROM employee;"))
        employee_count = result.fetchone()[0]
        print(f"Found {employee_count} employees in database")
        
        # Check attendance logs table
        result = session.execute(text("SELECT COUNT(*) FROM attendance_log;"))
        log_count = result.fetchone()[0]
        print(f"Found {log_count} attendance logs in database")
        
        # Check attendance records table
        result = session.execute(text("SELECT COUNT(*) FROM attendance_record;"))
        record_count = result.fetchone()[0]
        print(f"Found {record_count} attendance records in database")
        
        return True
    except Exception as e:
        print(f"Error checking records: {e}")
        return False

# Find or create a default device for testing
def get_default_device():
    try:
        # Check if we have a device
        result = session.execute(text("SELECT id, name FROM attendance_device LIMIT 1;"))
        device = result.fetchone()
        
        if device:
            print(f"Using existing device: {device[0]}, {device[1]}")
            return device[0]
        else:
            # Create a default device
            result = session.execute(text("""
                INSERT INTO attendance_device 
                (name, device_id, device_type, model, location, is_active, status, created_at, updated_at)
                VALUES
                ('Test Device', 'test-device', 'zkteco', 'Test', 'Test Location', TRUE, 'online', NOW(), NOW())
                RETURNING id;
            """))
            device_id = result.fetchone()[0]
            session.commit()
            print(f"Created test device with ID: {device_id}")
            return device_id
    except Exception as e:
        print(f"Error getting default device: {e}")
        session.rollback()
        return None

# Main execution
if __name__ == "__main__":
    if check_database():
        # Check existing records
        check_existing_records()
        
        # Get default device
        device_id = get_default_device()
        
        if device_id:
            # Parse the CSV file
            print("\nParsing CSV file...")
            records = parse_csv('/tmp/import.csv')
            print(f"Parsed {len(records)} records from CSV")
            
            # We're not inserting records, just checking if parsing works
            print("\nSample records from CSV:")
            for i, record in enumerate(records):
                print(f"{i+1}. Employee ID: {record['employee_id']}, Name: {record['employee_name']}, Type: {record['log_type']}, Time: {record['timestamp']}")
                if i >= 4:  # Show first 5 records
                    break
    
    # Close the session
    session.close()