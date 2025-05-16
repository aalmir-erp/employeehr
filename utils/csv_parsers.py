"""
CSV Parsers for various formats of attendance data
This module provides parsers for different CSV formats, including:
- ZKTeco standard format
- MIR Event Viewer Report format
- Hikvision format
"""

import csv
import re
import io
import logging
import os
from datetime import datetime, timedelta
from flask import current_app

# Set up logging
logger = logging.getLogger(__name__)

def auto_detect_and_parse_csv(file_path):
    """
    Auto-detect CSV format and parse using the appropriate parser
    Returns a list of attendance records
    """
    # First try to detect format based on first few lines
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        sample = file.read(1024)  # Read first 1KB to detect format
        
    # Check for MIR Event Viewer Report format
    if "Event Viewer Report" in sample:
        logger.info("Auto-detected MIR Event Viewer Report format")
        return parse_mir_csv_file(file_path)
        
    # Check for standard ZKTeco format
    elif "User ID" in sample and "Time" in sample:
        logger.info("Auto-detected standard ZKTeco format")
        return parse_zkteco_standard_file(file_path)
        
    # Check for Hikvision format
    elif "Card No" in sample or "Access Control" in sample:
        logger.info("Auto-detected Hikvision format")
        return parse_hikvision_csv_file(file_path)
        
    # If no specific format detected, try generic parsers in order of likelihood
    else:
        logger.warning("Could not auto-detect format, trying all parsers")
        # Try MIR format first (most complex, so if it works with this, great)
        mir_records = parse_mir_csv_file(file_path)
        if mir_records:
            logger.info(f"Successfully parsed as MIR format, found {len(mir_records)} records")
            return mir_records
            
        # Try standard ZKTeco format
        zk_records = parse_zkteco_standard_file(file_path)
        if zk_records:
            logger.info(f"Successfully parsed as ZKTeco format, found {len(zk_records)} records")
            return zk_records
            
        # Try Hikvision format
        hik_records = parse_hikvision_csv_file(file_path)
        if hik_records:
            logger.info(f"Successfully parsed as Hikvision format, found {len(hik_records)} records")
            return hik_records
    
    # If nothing worked, return empty list
    logger.error("Failed to parse CSV with any available parser")
    return []

def parse_mir_csv_file(file_path):
    """
    Parse the MIR format CSV file and extract attendance data
    This handles the complex 'Event Viewer Report' format with metadata headers
    """
    records = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.reader(file)
            
            # Check first row to confirm MIR format
            first_row = next(reader, None)
            is_mir_format = first_row and len(first_row) > 0 and first_row[0] == "Event Viewer Report"
            
            if not is_mir_format:
                logger.warning("File is not in MIR Event Viewer Report format")
                return []
                
            # Reset to beginning of file
            file.seek(0)
            reader = csv.reader(file)
            
            # Track for debugging
            success_count = 0
            error_count = 0
            
            # Variables to store employee info across multiple rows
            current_employee_id = None
            current_employee_name = None
            
            # Process each row
            for row_idx, row in enumerate(reader):
                if not row or len(row) < 3:  # Skip empty or very short rows
                    continue
                
                try:
                    # Extract Employee ID and Name
                    # Look for "Employee ID:" field
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee ID:":
                            current_employee_id = row[i+1].strip()
                            break
                    
                    # Look for "Employee Name:" field
                    for i in range(len(row)):
                        if i < len(row) - 1 and row[i] == "Employee Name:":
                            raw_name = row[i+1].strip()
                            current_employee_name = ''.join(c for c in raw_name if ord(c) < 128)  # Remove non-ASCII
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
                    if current_employee_id and event_type and timestamp:
                        records.append({
                            'employee_id': current_employee_id,
                            'employee_name': current_employee_name,
                            'log_type': event_type,
                            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })
                        success_count += 1
                        
                        if success_count % 500 == 0:
                            logger.info(f"Processed {success_count} records")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing row {row_idx}: {str(e)}")
            
            logger.info(f"Successfully parsed {success_count} records, encountered {error_count} errors")
                
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    
    return records

def parse_zkteco_standard_file(file_path):
    """
    Parse standard ZKTeco format CSV file
    Format: "User ID","Name","Time","Status","Terminal","Verification Type"
    """
    records = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.reader(file)
            header = next(reader, None)
            
            # Identify column positions
            uid_col = name_col = time_col = status_col = -1
            
            if header:
                for i, col_name in enumerate(header):
                    col_lower = col_name.lower()
                    if "user id" in col_lower or "userid" in col_lower:
                        uid_col = i
                    elif "name" in col_lower:
                        name_col = i
                    elif "time" in col_lower or "date" in col_lower:
                        time_col = i
                    elif "status" in col_lower or "event" in col_lower:
                        status_col = i
            
            # If columns not identified, try standard positions
            if uid_col == -1:
                uid_col = 0
            if name_col == -1:
                name_col = 1
            if time_col == -1:
                time_col = 2
            if status_col == -1:
                status_col = 3
            
            # Process each row
            for row in reader:
                if len(row) <= max(uid_col, name_col, time_col, status_col):
                    continue  # Skip rows without enough columns
                
                try:
                    employee_id = row[uid_col].strip()
                    employee_name = row[name_col].strip()
                    timestamp_str = row[time_col].strip()
                    status = row[status_col].strip() if status_col < len(row) else ""
                    
                    # Normalize log type
                    log_type = "IN"
                    if status.upper() in ["OUT", "CHECKOUT", "EXIT"]:
                        log_type = "OUT"
                    
                    # Parse timestamp
                    timestamp = None
                    
                    # Try common formats
                    formats = [
                        '%Y-%m-%d %H:%M:%S',
                        '%m/%d/%Y %H:%M:%S',
                        '%d/%m/%Y %H:%M:%S',
                        '%d-%m-%Y %H:%M:%S',
                        '%Y/%m/%d %H:%M:%S',
                        '%d-%b-%Y %H:%M:%S',
                        '%d-%b-%Y %I:%M:%S %p',
                        '%d-%b-%y %I:%M %p'
                    ]
                    
                    for fmt in formats:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if not timestamp:
                        logger.warning(f"Could not parse timestamp: {timestamp_str}")
                        continue
                    
                    records.append({
                        'employee_id': employee_id,
                        'employee_name': employee_name,
                        'log_type': log_type,
                        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing row: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    
    return records

def parse_hikvision_csv_file(file_path):
    """
    Parse Hikvision format CSV file
    Format varies, but typically includes card number, name, time, and event
    """
    records = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.reader(file)
            header = next(reader, None)
            
            # Identify column positions
            card_col = name_col = time_col = event_col = -1
            
            if header:
                for i, col_name in enumerate(header):
                    col_lower = col_name.lower()
                    if "card" in col_lower or "id" in col_lower:
                        card_col = i
                    elif "name" in col_lower or "person" in col_lower:
                        name_col = i
                    elif "time" in col_lower or "date" in col_lower:
                        time_col = i
                    elif "event" in col_lower or "direction" in col_lower or "access" in col_lower:
                        event_col = i
            
            # If columns not identified, try standard positions
            if card_col == -1:
                card_col = 0
            if name_col == -1:
                name_col = 1
            if time_col == -1:
                time_col = 2
            if event_col == -1:
                event_col = 3
            
            # Process each row
            for row in reader:
                if len(row) <= max(card_col, name_col, time_col):
                    continue  # Skip rows without enough columns
                
                try:
                    employee_id = row[card_col].strip()
                    employee_name = row[name_col].strip() if name_col < len(row) else ""
                    timestamp_str = row[time_col].strip()
                    event = row[event_col].strip() if event_col < len(row) else ""
                    
                    # Normalize log type based on event text
                    log_type = "IN"  # Default to IN if we can't determine
                    event_lower = event.lower()
                    if "out" in event_lower or "exit" in event_lower or "leave" in event_lower:
                        log_type = "OUT"
                    
                    # Parse timestamp
                    timestamp = None
                    
                    # Try common formats
                    formats = [
                        '%Y-%m-%d %H:%M:%S',
                        '%m/%d/%Y %H:%M:%S',
                        '%d/%m/%Y %H:%M:%S',
                        '%Y/%m/%d %H:%M:%S',
                        '%d-%m-%Y %H:%M:%S',
                        '%Y.%m.%d %H:%M:%S'
                    ]
                    
                    for fmt in formats:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if not timestamp:
                        logger.warning(f"Could not parse timestamp: {timestamp_str}")
                        continue
                    
                    records.append({
                        'employee_id': employee_id,
                        'employee_name': employee_name,
                        'log_type': log_type,
                        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing row: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
    
    return records

def get_or_create_employee(session, employee_code, employee_name):
    """
    Look up an employee by code or create if not exists
    This is a utility function used by import processes
    """
    from models import Employee
    
    # Normalize employee code
    if employee_code:
        employee_code = str(employee_code).strip()
    
    if not employee_code:
        logger.warning(f"Missing employee code for {employee_name}")
        return None
    
    # First look for existing employee
    employee = session.query(Employee).filter_by(employee_code=employee_code).first()
    
    if not employee:
        # Create new employee
        employee = Employee(
            employee_code=employee_code,
            name=employee_name if employee_name else f"Employee {employee_code}",
            is_active=True
        )
        session.add(employee)
        session.commit()
        logger.info(f"Created new employee: {employee_name} (Code: {employee_code})")
    
    return employee.id

def import_attendance_records(session, records, device_id, create_missing=True):
    """
    Import attendance records into the database
    Returns count of logs created and records updated
    """
    if not records:
        return 0, 0
    
    from models import AttendanceLog, Employee
    
    logs_created = 0
    records_updated = 0
    batch_size = 100
    
    # Process in batches
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        
        try:
            for record in batch:
                # Get or create employee
                employee_code = record.get('employee_id')
                print (employee_code)
                employee_name = record.get('employee_name')
                
                if create_missing:
                    employee_id = get_or_create_employee(session, employee_code, employee_name)
                else:
                    # If not creating missing employees, look up by code
                    employee = session.query(Employee).filter_by(odoo_id=employee_code).first()
                    employee_id = employee.id if employee else None
                
                if not employee_id:
                    logger.warning(f"Skipping record for unknown employee: {employee_code}")
                    continue
                
                # Check for existing log (avoid duplicates)
                timestamp = record.get('timestamp')
                log_type = record.get('log_type')
                
                # Parse timestamp string back to datetime
                ts = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                
                # Look for existing log within 5 minutes
                ts_minus = ts - timedelta(minutes=5)
                ts_plus = ts + timedelta(minutes=5)
                
                existing_log = session.query(AttendanceLog).filter(
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.log_type == log_type,
                    AttendanceLog.timestamp.between(ts_minus, ts_plus)
                ).first()
                
                if existing_log:
                    logger.debug(f"Duplicate log found for {employee_code} at {timestamp}")
                    continue
                
                # Create new log
                log = AttendanceLog(
                    employee_id=employee_id,
                    device_id=device_id,
                    timestamp=ts,
                    log_type=log_type,
                    is_processed=False
                )
                session.add(log)
                logs_created += 1
            
            # Commit batch
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error importing batch: {str(e)}")
    
    logger.info(f"Import complete: {logs_created} logs created, {records_updated} records updated")
    return logs_created, records_updated