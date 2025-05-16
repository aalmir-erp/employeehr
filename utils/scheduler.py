import logging
import threading
import time
import os
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import app, db
from models import AttendanceDevice, DeviceLog, Employee, AttendanceRecord, Shift, ShiftAssignment
from utils.odoo_connector import odoo_connector
from utils.hikvision_connector import hikvision_connector

logger = logging.getLogger(__name__)

# Create scheduler
scheduler = BackgroundScheduler()

def sync_odoo_employees():
    """Sync employees from Odoo to local database"""
    with app.app_context():
        logger.info("Starting scheduled sync of Odoo employees")
        success = odoo_connector.sync_employees()
        if success:
            logger.info("Employee sync completed successfully")
        else:
            logger.error("Employee sync failed")

def check_device_status():
    """Check status of all attendance devices"""
    with app.app_context():
        logger.info("Checking status of attendance devices")
        devices = AttendanceDevice.query.filter_by(is_active=True).all()
        
        for device in devices:
            try:
                # Perform real device check based on device type
                is_online, error_message = check_device_connection(device)
                
                old_status = device.status
                device.status = 'online' if is_online else 'offline'
                device.last_ping = datetime.utcnow()
                
                # Log status change or connection error
                if old_status != device.status:
                    message = f"Device status changed from {old_status} to {device.status}"
                    if not is_online and error_message:
                        message += f". Error: {error_message}"
                        
                    log = DeviceLog(
                        device_id=device.id,
                        log_type='connection',
                        message=message
                    )
                    db.session.add(log)
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error checking device {device.name}: {str(e)}")
                # Create error log with detailed error message
                device.status = 'error'
                log = DeviceLog(
                    device_id=device.id,
                    log_type='error',
                    message=f"Error checking device status: {str(e)}"
                )
                db.session.add(log)
                db.session.commit()

def generate_daily_attendance_records():
    """Generate empty attendance records for all active employees for today"""
    with app.app_context():
        logger.info("Generating daily attendance records")
        today = date.today()
        
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).all()
        
        for employee in employees:
            # Check if record already exists for today
            existing_record = AttendanceRecord.query.filter_by(
                employee_id=employee.id,
                date=today
            ).first()
            
            if not existing_record:
                # Get employee's current shift
                current_shift = None
                if employee.current_shift_id:
                    current_shift = employee.current_shift_id
                else:
                    # Check shift assignments
                    assignment = ShiftAssignment.query.filter(
                        ShiftAssignment.employee_id == employee.id,
                        ShiftAssignment.start_date <= today,
                        (ShiftAssignment.end_date >= today) | (ShiftAssignment.end_date.is_(None)),
                        ShiftAssignment.is_active == True
                    ).first()
                    
                    if assignment:
                        current_shift = assignment.shift_id
                
                # Create empty attendance record
                record = AttendanceRecord(
                    employee_id=employee.id,
                    shift_id=current_shift,
                    date=today,
                    status='pending',
                    is_weekend=today.weekday() >= 5  # 5 = Saturday, 6 = Sunday
                )
                
                db.session.add(record)
        
        db.session.commit()
        logger.info("Daily attendance records generated")

def process_attendance_logs():
    """Process raw attendance logs and update attendance records"""
    with app.app_context():
        logger.info("Processing attendance logs")
        # Implementation would convert raw logs into attendance records
        # This would involve pairing IN/OUT punches and calculating work hours
        # For brevity, this implementation is omitted but would be critical in a real system

def check_device_connection(device):
    """Check the connection to a specific attendance device
    Returns a tuple of (is_online, error_message)
    """
    try:
        import socket
        import requests
        import subprocess
        import shlex
        import json
        
        # Special handling for Hikvision devices
        if device.device_type.lower() == 'hikvision':
            # Check if IP and credentials are configured
            if not device.ip_address:
                return False, "Device has no IP address configured"
            if not device.username or not device.password:
                return False, "Device has no credentials configured"
                
            logger.info(f"Checking connection to Hikvision device at {device.ip_address}:{device.port}")
            
            # Initialize the connector with device credentials
            temp_connector = hikvision_connector.__class__(
                ip_address=device.ip_address,  # Now accepts full URLs with protocol and path
                port=device.port,
                username=device.username,
                password=device.password
            )
            
            # Log the constructed base URL for debugging
            logger.debug(f"Connecting to Hikvision device using base URL: {temp_connector.base_url}")
            
            # Test connection by getting device info
            device_info = temp_connector.get_device_info()
            if device_info:
                # If we have model info, update the device information
                if device.model in ['', None] and 'model' in device_info:
                    device.model = device_info.get('model')
                if device.serial_number in ['', None] and 'serial_number' in device_info:
                    device.serial_number = device_info.get('serial_number')
                if device.firmware_version in ['', None] and 'firmware_version' in device_info:
                    device.firmware_version = device_info.get('firmware_version')
                db.session.commit()
                return True, ""
            else:
                return False, "Could not retrieve device info from Hikvision device"
                
        # Special handling for ZKTeco devices using pyzk library
        elif device.device_type.lower() in ['zkteco', 'biometric', 'fingerprint']:
            # Check if IP and port are configured
            if not device.ip_address:
                return False, "Device has no IP address configured"
                
            # Handle URL format (http://erp.mir.ae:4077/)
            ip_address = device.ip_address
            port = device.port or 4370  # Default ZKTeco port
            
            # Clean up the IP/hostname
            if ip_address.startswith('http://') or ip_address.startswith('https://'):
                # Extract the domain from URL
                ip_address = ip_address.split('//', 1)[1].split('/', 1)[0]
                
            # Check if port is included in the IP address
            if ':' in ip_address and not device.port:
                # Extract port from IP address if it's not set separately
                ip_address, port_str = ip_address.split(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    pass
                    
            # Update the device record with clean values
            device.ip_address = ip_address
            device.port = port
            db.session.commit()
                
            logger.info(f"Checking connection to ZKTeco device at {ip_address}:{port}")
                
            # For ZKTeco devices, use the ZKDevice connector to check connectivity
            try:
                from utils.zk_device import ZKDevice
                zk_device = ZKDevice(device)
                success, error = zk_device.connect()
                
                if success:
                    # Make sure to disconnect after checking
                    zk_device.disconnect()
                    return True, ""
                else:
                    return False, error
            except Exception as e:
                return False, f"Error connecting to ZKTeco device: {str(e)}"
                
        # For other device types (RFID, etc.), use socket connectivity
        elif device.device_type in ['rfid']:
            # For devices with IP address, try ping first
            if device.ip_address:
                if device.port:
                    # Try to establish a socket connection to check if port is open
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)  # 3 second timeout
                    result = sock.connect_ex((device.ip_address, device.port))
                    sock.close()
                    
                    if result != 0:
                        return False, f"Port {device.port} is not open on {device.ip_address}"
                
                # If socket check passed or no port specified, use socket to check device reachability
                # This is more reliable than using ping which may not be available in all environments
                try:
                    # Create a socket to test basic connectivity
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)  # 2 second timeout
                    
                    # Try connecting to a common port (80 for HTTP) to check reachability
                    # If the port is not specified, we just want to check if the host is up
                    test_port = device.port if device.port else 80
                    result = sock.connect_ex((device.ip_address, test_port))
                    sock.close()
                    
                    if result != 0:
                        # Try ICMP echo (equivalent to ping) using the requests library
                        try:
                            # Use a very short timeout to check reachability
                            response = requests.get(f'http://{device.ip_address}', timeout=2)
                            # If we get here, the device is reachable
                            return True, ""
                        except requests.RequestException:
                            return False, f"Device at {device.ip_address} is not reachable"
                    
                    # If we got here, the connection was successful
                    return True, ""
                except Exception as e:
                    return False, f"Error checking device connectivity: {str(e)}"
            else:
                return False, "Device has no IP address configured"
        
        elif device.device_type in ['web', 'mobile']:
            # For web/mobile based devices, try API endpoint
            if not device.api_key:
                return False, "No API key configured for this device"
                
            # Try a sample GET request with API key authentication
            headers = {
                'Authorization': f'Bearer {device.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Construct URL based on device type and configuration
            # This is a placeholder and should be updated with actual API URL
            api_url = f"https://api.mirplastic.com/devices/{device.device_id}/status"
            
            # Updated API URL for MIR AMS
            api_url = f"https://api.mir-ams.com/devices/{device.device_id}/status"
            
            try:
                response = requests.get(api_url, headers=headers, timeout=5)
                if response.status_code == 200:
                    return True, ""
                else:
                    return False, f"API returned error: {response.status_code} - {response.text}"
            except requests.RequestException as e:
                return False, f"API connection error: {str(e)}"
        
        else:
            # Unknown device type
            return False, f"Unknown device type: {device.device_type}"
            
        # If we got here, all checks passed
        return True, ""
        
    except Exception as e:
        logger.error(f"Error checking device {device.name}: {str(e)}")
        return False, str(e)

def simulate_device_check(device):
    """Simulate checking if a device is online (for testing only)"""
    # In a real implementation, this would ping the device or make an API call
    # For simulation, we'll return a random status with bias toward online
    import random
    is_online = random.random() < 0.8  # 80% chance of being online
    return (is_online, "" if is_online else "Simulated device is offline")

def start_scheduled_tasks():
    """Start all scheduled tasks"""
    # Add jobs to scheduler
    scheduler.add_job(
        sync_odoo_employees,
        CronTrigger(hour=1, minute=0),  # Run at 1 AM daily
        id='sync_odoo_employees',
        replace_existing=True
    )
    
    scheduler.add_job(
        check_device_status,
        CronTrigger(minute='*/5'),  # Run every 5 minutes
        id='check_device_status',
        replace_existing=True
    )
    
    scheduler.add_job(
        generate_daily_attendance_records,
        CronTrigger(hour=0, minute=1),  # Run at 12:01 AM daily
        id='generate_daily_attendance_records',
        replace_existing=True
    )
    
    scheduler.add_job(
        process_attendance_logs,
        CronTrigger(minute='*/15'),  # Run every 15 minutes
        id='process_attendance_logs',
        replace_existing=True
    )
    
    # Start the scheduler if it's not already running
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started with background tasks")

def shutdown_scheduled_tasks():
    """Shutdown the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")
