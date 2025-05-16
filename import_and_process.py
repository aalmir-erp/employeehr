"""
Script to import MIR CSV data and process all logs for demonstration purposes
"""

import os
import csv
from datetime import datetime, date, timedelta
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a minimal Flask app for database operations
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Use the existing database structure
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

with app.app_context():
    # Import models after db is initialized
    from models import Employee, AttendanceDevice, AttendanceLog, AttendanceRecord

    def parse_mir_csv(file_path):
        """Parse MIR format CSV file and extract attendance data"""
        records = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                reader = csv.reader(file)
                
                # Process each row
                for row in reader:
                    # Check if we have a valid row with enough data
                    if len(row) < 25:
                        continue
                    
                    # Extract employee details
                    try:
                        # Extract employee_id and employee_name
                        employee_id = row[10]
                        employee_name = row[14]
                        
                        # Extract punch data
                        punch_date_str = row[20]
                        punch_time_str = row[25] if len(row) > 25 else None
                        log_type = row[24] if len(row) > 24 else None
                        
                        # Skip rows without necessary data
                        if not employee_id or not punch_date_str or not punch_time_str or not log_type:
                            continue
                        
                        # Convert and validate employee_id
                        try:
                            employee_id = int(employee_id)
                        except ValueError:
                            continue
                        
                        # Parse date and time
                        try:
                            # Remove any extra spaces in dates and times
                            punch_date_str = punch_date_str.strip()
                            punch_time_str = punch_time_str.strip()
                            
                            # Handle various date formats
                            if '-' in punch_date_str:
                                punch_date = datetime.strptime(punch_date_str, '%d-%b-%y').date()
                            elif '/' in punch_date_str:
                                punch_date = datetime.strptime(punch_date_str, '%d/%m/%Y').date()
                            else:
                                logger.warning(f"Unrecognized date format: {punch_date_str}")
                                continue
                            
                            # Parse time (format: DD-MMM-YY HH:MM am/pm)
                            if 'am' in punch_time_str.lower() or 'pm' in punch_time_str.lower():
                                # Parse time in 12-hour format
                                time_parts = punch_time_str.split()
                                if len(time_parts) >= 2:
                                    time_str = time_parts[-2] + ' ' + time_parts[-1]
                                    time_obj = datetime.strptime(time_str, '%I:%M %p').time()
                                else:
                                    logger.warning(f"Invalid time format: {punch_time_str}")
                                    continue
                            else:
                                # Assume 24-hour format
                                time_obj = datetime.strptime(punch_time_str.split()[-1], '%H:%M').time()
                            
                            # Combine date and time
                            timestamp = datetime.combine(punch_date, time_obj)
                            
                            records.append({
                                'employee_id': employee_id,
                                'employee_name': employee_name,
                                'timestamp': timestamp,
                                'log_type': log_type,
                                'device_name': row[23] if len(row) > 23 else 'Unknown'
                            })
                            
                        except (ValueError, IndexError) as e:
                            logger.error(f"Error parsing date/time: {e} - {punch_date_str}/{punch_time_str}")
                            continue
                    
                    except Exception as e:
                        logger.error(f"Error processing row: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Error opening or processing file: {e}")
            return []
            
        logger.info(f"Successfully parsed {len(records)} records from MIR CSV")
        return records
    
    def get_or_create_employee(employee_id, employee_name):
        """Look up an employee by ID or create if not exists"""
        employee = Employee.query.filter_by(employee_code=str(employee_id)).first()
        if not employee:
            employee = Employee(
                employee_code=str(employee_id),
                name=employee_name,
                email=f"emp{employee_id}@example.com",
                department="Imported",
                position="Imported",
                is_active=True
            )
            db.session.add(employee)
            db.session.commit()
            logger.info(f"Created new employee: {employee_name} (ID: {employee_id})")
        return employee
    
    def get_or_create_device(device_name):
        """Get or create a device by name"""
        device = AttendanceDevice.query.filter_by(name=device_name).first()
        if not device:
            device = AttendanceDevice(
                name=device_name,
                device_type="MIR Import",
                ip_address="0.0.0.0",
                port=0,
                is_active=True
            )
            db.session.add(device)
            db.session.commit()
            logger.info(f"Created new device: {device_name}")
        return device
    
    def import_attendance_logs(records):
        """Import attendance logs into the database"""
        logs_created = 0
        
        for record in records:
            employee = get_or_create_employee(record['employee_id'], record['employee_name'])
            device = get_or_create_device(record['device_name'])
            
            # Check if log already exists
            existing_log = AttendanceLog.query.filter_by(
                employee_id=employee.id,
                device_id=device.id,
                timestamp=record['timestamp']
            ).first()
            
            if not existing_log:
                log = AttendanceLog(
                    employee_id=employee.id,
                    device_id=device.id,
                    log_type=record['log_type'],
                    timestamp=record['timestamp'],
                    is_processed=False
                )
                db.session.add(log)
                logs_created += 1
        
        db.session.commit()
        logger.info(f"Created {logs_created} new attendance logs")
        return logs_created
    
    def process_all_logs():
        """Process all unprocessed logs"""
        unprocessed_logs = AttendanceLog.query.filter_by(is_processed=False).all()
        processed_count = 0
        
        # Process each log
        for log in unprocessed_logs:
            # Get the date for this log
            log_date = log.timestamp.date()
            
            # Find or create an attendance record for this employee and date
            attendance_record = AttendanceRecord.query.filter_by(
                employee_id=log.employee_id,
                date=log_date
            ).first()
            
            if not attendance_record:
                attendance_record = AttendanceRecord(
                    employee_id=log.employee_id,
                    date=log_date,
                    status='present'
                )
                db.session.add(attendance_record)
            
            # Update check-in or check-out time based on log type
            if log.log_type == 'IN':
                if not attendance_record.check_in or log.timestamp < attendance_record.check_in:
                    attendance_record.check_in = log.timestamp
            elif log.log_type == 'OUT':
                if not attendance_record.check_out or log.timestamp > attendance_record.check_out:
                    attendance_record.check_out = log.timestamp
            
            # Calculate work hours if both check-in and check-out are available
            if attendance_record.check_in and attendance_record.check_out:
                # Calculate duration (check_out - check_in) in hours
                duration = (attendance_record.check_out - attendance_record.check_in).total_seconds() / 3600
                attendance_record.work_hours = duration
                
                # Update status based on work hours
                if duration >= 8:  # Full day
                    attendance_record.status = 'present'
                elif duration >= 4:  # Half day
                    attendance_record.status = 'half-day'
                else:
                    attendance_record.status = 'present'
            
            # Mark the log as processed
            log.is_processed = True
            processed_count += 1
        
        # Commit changes
        db.session.commit()
        logger.info(f"Successfully processed {processed_count} logs")
        return processed_count
    
    def display_examples():
        """Display examples of day and night shift attendance records for March 2025"""
        # Get March 2025 date range
        march_start = date(2025, 3, 1)
        march_end = date(2025, 3, 31)
        
        # Get day shift records (check-in between 6:00 - 12:00)
        from sqlalchemy import extract
        day_shift = AttendanceRecord.query.filter(
            AttendanceRecord.date >= march_start,
            AttendanceRecord.date <= march_end,
            AttendanceRecord.check_in.isnot(None),
            extract('hour', AttendanceRecord.check_in) >= 6,
            extract('hour', AttendanceRecord.check_in) < 12
        ).order_by(AttendanceRecord.date).limit(10).all()
        
        # Get night shift records (check-in after 18:00)
        night_shift = AttendanceRecord.query.filter(
            AttendanceRecord.date >= march_start,
            AttendanceRecord.date <= march_end,
            AttendanceRecord.check_in.isnot(None),
            extract('hour', AttendanceRecord.check_in) >= 18
        ).order_by(AttendanceRecord.date).limit(10).all()
        
        # Display day shift examples
        print("\n=== DAY SHIFT EXAMPLES (March 2025) ===")
        print(f"{'Date':<12} {'Employee':<20} {'Check-In':<20} {'Check-Out':<20} {'Work Hours':<12} {'Status':<10}")
        print("=" * 95)
        for record in day_shift:
            employee = Employee.query.get(record.employee_id)
            check_in = record.check_in.strftime("%H:%M") if record.check_in else "N/A"
            check_out = record.check_out.strftime("%H:%M") if record.check_out else "N/A"
            print(f"{record.date.strftime('%Y-%m-%d'):<12} {employee.name[:18]:<20} {check_in:<20} {check_out:<20} {record.work_hours or 0:<12.2f} {record.status:<10}")
        
        if not day_shift:
            print("No day shift records found for March 2025")
        
        # Display night shift examples
        print("\n=== NIGHT SHIFT EXAMPLES (March 2025) ===")
        print(f"{'Date':<12} {'Employee':<20} {'Check-In':<20} {'Check-Out':<20} {'Work Hours':<12} {'Status':<10}")
        print("=" * 95)
        for record in night_shift:
            employee = Employee.query.get(record.employee_id)
            check_in = record.check_in.strftime("%H:%M") if record.check_in else "N/A"
            check_out = record.check_out.strftime("%H:%M") if record.check_out else "N/A"
            print(f"{record.date.strftime('%Y-%m-%d'):<12} {employee.name[:18]:<20} {check_in:<20} {check_out:<20} {record.work_hours or 0:<12.2f} {record.status:<10}")
        
        if not night_shift:
            print("No night shift records found for March 2025")
    
    def main():
        """Main import and process function"""
        csv_file_path = 'attached_assets/rptViewer (1).csv'
        
        # Parse CSV
        records = parse_mir_csv(csv_file_path)
        
        if not records:
            logger.error("No valid records found in the CSV file")
            return
        
        # Import logs
        logs_created = import_attendance_logs(records)
        
        # Process logs
        processed_count = process_all_logs()
        
        # Display examples
        display_examples()
        
        logger.info(f"Import and processing complete. Created {logs_created} logs, processed {processed_count} logs.")
    
    # Run the main function
    if __name__ == "__main__":
        main()
    else:
        main()