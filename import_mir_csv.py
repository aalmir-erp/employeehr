"""
Import MIR format CSV file directly into the database
"""
import os
import csv
import re
from datetime import datetime, timedelta
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get database URL from environment
DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    logger.error("DATABASE_URL environment variable not set")
    exit(1)

# Configure the CSV file path
CSV_FILE_PATH = '/tmp/import.csv'

# Create database connection
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

def parse_mir_csv(file_path):
    """Parse MIR format CSV file and extract attendance data"""
    records = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.reader(file)
            
            # Check first row to confirm MIR format
            first_row = next(reader, None)
            is_mir_format = first_row and len(first_row) > 0 and first_row[0] == "Event Viewer Report"
            
            if not is_mir_format:
                logger.error("Not a valid MIR format CSV file")
                return []
                
            # Reset to beginning of file and re-create reader
            file.seek(0)
            reader = csv.reader(file)
            
            # Track successfully parsed rows
            success_count = 0
            error_count = 0
            
            # Process each row
            for row_idx, row in enumerate(reader):
                if not row or len(row) < 10:  # Ensure we have enough data
                    continue
                
                try:
                    # Extract employee ID
                    employee_id = None
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee ID:":
                            employee_id = row[i+1].strip()
                            break
                    
                    # Extract employee name
                    employee_name = None
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee Name:":
                            raw_name = row[i+1].strip()
                            employee_name = ''.join(c for c in raw_name if ord(c) < 128)  # Remove non-ASCII chars
                            break
                    
                    # Find event type (IN/OUT)
                    event_type = None
                    event_positions = [i for i, val in enumerate(row) if val in ["IN", "OUT"]]
                    if event_positions:
                        event_type = row[event_positions[0]]
                    
                    # Find timestamp
                    timestamp = None
                    
                    # Look for cells with time format (containing am/pm)
                    punch_timestamps = []
                    for i in range(len(row)):
                        if isinstance(row[i], str) and (" am" in row[i].lower() or " pm" in row[i].lower()):
                            # Only consider cells with date format
                            if re.search(r'\d{2}-[A-Za-z]{3}-\d{2}', row[i]):
                                punch_timestamps.append(row[i])
                    
                    # Try to parse timestamps
                    if punch_timestamps:
                        for ts in punch_timestamps:
                            try:
                                # Try with double space
                                timestamp = datetime.strptime(ts, '%d-%b-%y  %I:%M %p')
                                break
                            except ValueError:
                                try:
                                    # Try with single space
                                    timestamp = datetime.strptime(ts, '%d-%b-%y %I:%M %p')
                                    break
                                except ValueError:
                                    continue
                    
                    # If no timestamp yet, try alternative approach with date+punch fields
                    if not timestamp:
                        # Find date field
                        date_str = None
                        for i in range(len(row) - 1):
                            if row[i] == "Date" and i+1 < len(row):
                                date_value = row[i+1].strip()
                                if re.match(r'\d{2}-[A-Za-z]{3}-\d{2}', date_value):
                                    date_str = date_value
                                    break
                        
                        # Find punch time
                        time_str = None
                        for i in range(len(row) - 1):
                            if row[i] == "Punch" and i+1 < len(row):
                                punch_value = row[i+1].strip()
                                time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m)', punch_value, re.IGNORECASE)
                                if time_match:
                                    time_str = time_match.group(1)
                                    break
                        
                        # Combine date and time
                        if date_str and time_str:
                            combined_ts = f"{date_str}  {time_str}"
                            try:
                                timestamp = datetime.strptime(combined_ts, '%d-%b-%y  %I:%M %p')
                            except ValueError:
                                try:
                                    combined_ts = f"{date_str} {time_str}"
                                    timestamp = datetime.strptime(combined_ts, '%d-%b-%y %I:%M %p')
                                except ValueError:
                                    pass
                    
                    # If we have all required data, add to records
                    if employee_id and event_type and timestamp:
                        records.append({
                            'employee_id': employee_id,
                            'employee_name': employee_name,
                            'log_type': event_type,
                            'timestamp': timestamp
                        })
                        success_count += 1
                        
                        if success_count % 100 == 0:
                            logger.info(f"Processed {success_count} records")
                    else:
                        missing = []
                        if not employee_id: missing.append("employee_id")
                        if not event_type: missing.append("event_type")
                        if not timestamp: missing.append("timestamp")
                        logger.warning(f"Row {row_idx}: Missing required data: {', '.join(missing)}")
                        error_count += 1
                
                except Exception as e:
                    logger.error(f"Error processing row {row_idx}: {str(e)}")
                    error_count += 1
            
            logger.info(f"Successfully parsed {success_count} records, encountered {error_count} errors")
    
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    
    return records

def get_or_create_employee(employee_code, employee_name):
    """Look up an employee by code or create if not exists"""
    try:
        # Check if employee exists
        result = session.execute(
            text("SELECT id FROM employee WHERE employee_code = :code"),
            {"code": employee_code}
        )
        employee = result.fetchone()
        
        if employee:
            return employee[0]
        
        # Create new employee
        result = session.execute(
            text("""
                INSERT INTO employee
                (employee_code, name, is_active, created_at, last_sync)
                VALUES (:code, :name, TRUE, NOW(), NOW())
                RETURNING id
            """),
            {"code": employee_code, "name": employee_name or f"Employee {employee_code}"}
        )
        
        new_id = result.fetchone()[0]
        session.commit()
        logger.info(f"Created new employee: {employee_code}, {employee_name}")
        return new_id
    
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating employee {employee_code}: {str(e)}")
        return None

def get_default_device():
    """Get the first available device or create a test device"""
    try:
        result = session.execute(text("SELECT id FROM attendance_device LIMIT 1"))
        device = result.fetchone()
        
        if device:
            return device[0]
        
        # Create a test device if none exists
        result = session.execute(
            text("""
                INSERT INTO attendance_device
                (name, device_id, device_type, model, location, is_active, status, created_at, updated_at)
                VALUES ('Test Device', 'test-001', 'biometric', 'Test', 'Default', TRUE, 'online', NOW(), NOW())
                RETURNING id
            """)
        )
        
        new_id = result.fetchone()[0]
        session.commit()
        logger.info("Created default test device")
        return new_id
    
    except Exception as e:
        session.rollback()
        logger.error(f"Error getting/creating device: {str(e)}")
        return None

def import_attendance_logs(records):
    """Import attendance logs into the database"""
    try:
        # Get default device
        device_id = get_default_device()
        if not device_id:
            logger.error("No device available for import")
            return 0
        
        # Process records in batches
        batch_size = 100
        total_imported = 0
        total_records = len(records)
        
        for i in range(0, total_records, batch_size):
            batch = records[i:i+batch_size]
            batch_imported = 0
            
            for record in batch:
                try:
                    # Get or create employee
                    employee_id = get_or_create_employee(
                        record['employee_id'], 
                        record['employee_name']
                    )
                    
                    if not employee_id:
                        continue
                    
                    # Check for duplicate
                    timestamp = record['timestamp']
                    five_min_before = (timestamp.replace(second=0, microsecond=0) - 
                                      timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                    five_min_after = (timestamp.replace(second=0, microsecond=0) + 
                                     timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                    
                    result = session.execute(
                        text("""
                            SELECT COUNT(*) FROM attendance_log
                            WHERE employee_id = :emp_id
                            AND device_id = :dev_id
                            AND log_type = :log_type
                            AND timestamp BETWEEN :five_min_before AND :five_min_after
                        """),
                        {
                            "emp_id": employee_id,
                            "dev_id": device_id,
                            "log_type": record['log_type'],
                            "five_min_before": five_min_before,
                            "five_min_after": five_min_after
                        }
                    )
                    
                    if result.fetchone()[0] > 0:
                        # Skip duplicate
                        continue
                    
                    # Create attendance log
                    session.execute(
                        text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, timestamp, log_type, is_processed, created_at)
                            VALUES
                            (:emp_id, :dev_id, :timestamp, :log_type, FALSE, NOW())
                        """),
                        {
                            "emp_id": employee_id,
                            "dev_id": device_id,
                            "timestamp": timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                            "log_type": record['log_type']
                        }
                    )
                    
                    batch_imported += 1
                
                except Exception as e:
                    logger.error(f"Error importing record: {str(e)}")
            
            # Commit the batch
            session.commit()
            total_imported += batch_imported
            logger.info(f"Imported batch {i//batch_size + 1}: {batch_imported} records")
        
        return total_imported
    
    except Exception as e:
        session.rollback()
        logger.error(f"Error in import process: {str(e)}")
        return 0

def main():
    """Main import function"""
    if not os.path.exists(CSV_FILE_PATH):
        logger.error(f"CSV file not found at {CSV_FILE_PATH}")
        return
    
    logger.info(f"Starting import from {CSV_FILE_PATH}")
    
    # Parse the CSV
    records = parse_mir_csv(CSV_FILE_PATH)
    logger.info(f"Parsed {len(records)} records from CSV")
    
    if not records:
        logger.warning("No valid records found, import aborted")
        return
    
    # Import to database
    imported_count = import_attendance_logs(records)
    logger.info(f"Successfully imported {imported_count} attendance logs")

if __name__ == "__main__":
    main()
    session.close()