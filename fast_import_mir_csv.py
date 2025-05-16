"""
Fast import script for MIR format CSV files.
This version is optimized for speed and uses bulk imports.
"""
import os
import csv
import re
import logging
from datetime import datetime, timedelta
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

def parse_mir_csv(file_path, limit=None):
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
                if limit and success_count >= limit:
                    break
                    
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
                            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        success_count += 1
                        
                        if success_count % 500 == 0:
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

def ensure_device_exists():
    """Make sure we have at least one device"""
    try:
        result = session.execute(text("SELECT id FROM attendance_device LIMIT 1"))
        device = result.fetchone()
        
        if device:
            return device[0]
        
        # Create device if none exists
        logger.info("No device found, creating a default device")
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
        return new_id
    except Exception as e:
        session.rollback()
        logger.error(f"Error ensuring device: {str(e)}")
        return None

def create_all_employees(records):
    """Create all employees found in the records"""
    # Extract unique employee codes and names
    employee_map = {}
    for record in records:
        employee_code = record['employee_id']
        employee_name = record['employee_name']
        if employee_code and employee_code not in employee_map:
            employee_map[employee_code] = employee_name
    
    logger.info(f"Creating {len(employee_map)} employees if needed")
    
    # First, get existing employees
    existing_map = {}
    try:
        result = session.execute(text("SELECT id, employee_code FROM employee"))
        for row in result.fetchall():
            existing_map[row[1]] = row[0]
    except Exception as e:
        logger.error(f"Error getting existing employees: {str(e)}")
    
    # Create employees in bulk
    created_count = 0
    employee_id_map = {}  # Maps employee_code to id
    
    for employee_code, employee_name in employee_map.items():
        try:
            # Check if exists
            if employee_code in existing_map:
                employee_id_map[employee_code] = existing_map[employee_code]
                continue
            
            # Create
            result = session.execute(
                text("""
                    INSERT INTO employee
                    (employee_code, name, is_active, created_at, last_sync)
                    VALUES (:code, :name, TRUE, NOW(), NOW())
                    ON CONFLICT (employee_code) DO UPDATE
                    SET updated_at = NOW()
                    RETURNING id
                """),
                {"code": employee_code, "name": employee_name or f"Employee {employee_code}"}
            )
            new_id = result.fetchone()[0]
            employee_id_map[employee_code] = new_id
            created_count += 1
            
            # Commit every 100 employees
            if created_count % 100 == 0:
                session.commit()
                logger.info(f"Created {created_count} employees so far")
        except Exception as e:
            logger.error(f"Error creating employee {employee_code}: {str(e)}")
            session.rollback()
    
    # Final commit
    try:
        session.commit()
        logger.info(f"Successfully created {created_count} employees")
    except Exception as e:
        session.rollback()
        logger.error(f"Error in final commit: {str(e)}")
    
    return employee_id_map

def bulk_import_logs(records, employee_id_map):
    """Import logs in bulk for better performance"""
    device_id = ensure_device_exists()
    if not device_id:
        logger.error("No device available")
        return 0
    
    # Split into smaller batches to avoid memory issues
    batch_size = 500
    total_records = len(records)
    total_imported = 0
    
    for i in range(0, total_records, batch_size):
        batch = records[i:min(i+batch_size, total_records)]
        batch_imported = 0
        
        # Bulk insert using parameterized query
        try:
            # Start transaction
            conn = engine.connect()
            trans = conn.begin()
            
            # First check for existing records to avoid duplicates
            for record in batch:
                try:
                    employee_code = record['employee_id']
                    employee_id = employee_id_map.get(employee_code)
                    
                    if not employee_id:
                        logger.warning(f"No employee ID found for code {employee_code}")
                        continue
                    
                    # Check for duplicate within 5 minutes
                    timestamp = record['timestamp']
                    log_type = record['log_type']
                    
                    # Calculate time window directly in Python 
                    # instead of using PostgreSQL functions that cause SQL syntax errors
                    from datetime import datetime
                    ts = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    ts_minus = (ts - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                    ts_plus = (ts + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
                    
                    result = conn.execute(
                        text("""
                            SELECT id FROM attendance_log
                            WHERE employee_id = :employee_id
                            AND device_id = :device_id
                            AND log_type = :log_type
                            AND timestamp BETWEEN :ts_minus AND :ts_plus
                            LIMIT 1
                        """),
                        {
                            "employee_id": employee_id,
                            "device_id": device_id,
                            "log_type": log_type,
                            "ts_minus": ts_minus,
                            "ts_plus": ts_plus
                        }
                    )
                    
                    # Skip if duplicate exists
                    if result.fetchone():
                        continue
                    
                    # Insert new record
                    conn.execute(
                        text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, timestamp, log_type, is_processed, created_at)
                            VALUES
                            (:employee_id, :device_id, :timestamp, :log_type, FALSE, NOW())
                        """),
                        {
                            "employee_id": employee_id,
                            "device_id": device_id,
                            "timestamp": timestamp,
                            "log_type": log_type
                        }
                    )
                    batch_imported += 1
                except Exception as e:
                    logger.error(f"Error processing record: {str(e)}")
            
            # Commit batch
            trans.commit()
            total_imported += batch_imported
            logger.info(f"Imported batch {i//batch_size + 1}/{(total_records-1)//batch_size + 1}: {batch_imported} records")
            
        except Exception as e:
            logger.error(f"Error in bulk import: {str(e)}")
            try:
                trans.rollback()
            except:
                pass
    
    return total_imported

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
    
    # Create employees first
    employee_id_map = create_all_employees(records)
    
    # Import logs
    imported_count = bulk_import_logs(records, employee_id_map)
    logger.info(f"Successfully imported {imported_count} attendance logs")
    
    # Calculate success rate
    if records:
        success_rate = (imported_count / len(records)) * 100
        logger.info(f"Import success rate: {success_rate:.2f}%")

if __name__ == "__main__":
    try:
        main()
    finally:
        session.close()