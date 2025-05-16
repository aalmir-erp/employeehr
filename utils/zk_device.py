import logging
import time
from datetime import datetime
from app import db
from models import Employee, AttendanceLog, DeviceLog
from zk import ZK, const

logger = logging.getLogger(__name__)

class ZKDevice:
    def __init__(self, device):
        """
        Initialize ZK device connector
        :param device: AttendanceDevice model instance with device details
        """
        self.device = device
        self.zk = None
        self.conn = None
    
    def connect(self):
        """
        Connect to the ZK device
        :return: (success, error_message)
        """
        try:
            # Handle URL formats (like http://erp.mir.ae:4077/)
            ip_address = self.device.ip_address
            # Remove http:// or https:// if present
            if ip_address.startswith('http://') or ip_address.startswith('https://'):
                ip_address = ip_address.split('//', 1)[1].split('/', 1)[0]  # Extract domain from URL
                
            # Remove port from IP if it's included in the address
            if ':' in ip_address:
                ip_address, port_str = ip_address.split(':', 1)
                # Only override port if it's not already set in the device record
                if not self.device.port:
                    try:
                        self.device.port = int(port_str)
                    except ValueError:
                        pass
                        
            # Create ZK instance with the device's IP and port
            # API key is not used for direct socket connection to ZKTeco devices
            logger.info(f"Connecting to ZKTeco device at {ip_address}:{self.device.port}")
            self.zk = ZK(ip_address, port=self.device.port, timeout=5)
            
            # Connect to the device
            logger.info(f"Connecting to device {self.device.name} at {self.device.ip_address}:{self.device.port}")
            self.conn = self.zk.connect()
            
            # Log successful connection
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='connection',
                message=f'Successfully connected to device {self.device.name}'
            )
            db.session.add(device_log)
            db.session.commit()
            
            logger.info(f"Successfully connected to device {self.device.name}")
            return True, ""
            
        except Exception as e:
            error_msg = f"Error connecting to device {self.device.name}: {str(e)}"
            logger.error(error_msg)
            
            # Log connection error
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='error',
                message=error_msg
            )
            db.session.add(device_log)
            db.session.commit()
            
            return False, error_msg
    
    def disconnect(self):
        """
        Disconnect from the ZK device
        """
        if self.conn:
            logger.info(f"Disconnecting from device {self.device.name}")
            self.conn.disconnect()
            self.conn = None
    
    def get_device_info(self):
        """
        Get device information
        :return: dict with device info or None on error
        """
        if not self.conn:
            success, error = self.connect()
            if not success:
                return None
        
        try:
            info = {
                'firmware_version': self.conn.get_firmware_version(),
                'serial_number': self.conn.get_serialnumber(),
                'platform': self.conn.get_platform(),
                'device_name': self.conn.get_device_name(),
                'work_code': self.conn.get_workcode(),
                'oem_vendor': self.conn.get_oem_vendor(),
                'fingerprint_algorithm': self.conn.get_fp_version()
            }
            return info
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")
            return None
        finally:
            self.disconnect()
    
    def get_users(self):
        """
        Get users/employees from the device
        :return: (success, users/error_message)
        """
        if not self.conn:
            success, error = self.connect()
            if not success:
                return False, error
        
        try:
            # Get users from the device
            logger.info(f"Fetching users from device {self.device.name}")
            users = self.conn.get_users()
            
            if not users:
                logger.warning(f"No users found on device {self.device.name}")
                return True, []
            
            # Log the fetched users
            user_count = len(users)
            logger.info(f"Successfully fetched {user_count} users from device {self.device.name}")
            
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='sync',
                message=f'Successfully fetched {user_count} users from device {self.device.name}'
            )
            db.session.add(device_log)
            db.session.commit()
            
            return True, users
            
        except Exception as e:
            error_msg = f"Error fetching users from device {self.device.name}: {str(e)}"
            logger.error(error_msg)
            
            # Log the error
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='error',
                message=error_msg
            )
            db.session.add(device_log)
            db.session.commit()
            
            return False, error_msg
        finally:
            self.disconnect()
    
    def get_attendance(self):
        """
        Get attendance logs from the device
        :return: (success, attendance_records/error_message)
        """
        if not self.conn:
            success, error = self.connect()
            if not success:
                return False, error
        
        try:
            # Get attendance records from the device
            logger.info(f"Fetching attendance logs from device {self.device.name}")
            attendance_records = self.conn.get_attendance()
            
            if not attendance_records:
                logger.warning(f"No attendance records found on device {self.device.name}")
                return True, []
            
            # Log the fetched attendance records
            record_count = len(attendance_records)
            logger.info(f"Successfully fetched {record_count} attendance records from device {self.device.name}")
            
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='sync',
                message=f'Successfully fetched {record_count} attendance records from device {self.device.name}'
            )
            db.session.add(device_log)
            db.session.commit()
            
            return True, attendance_records
            
        except Exception as e:
            error_msg = f"Error fetching attendance from device {self.device.name}: {str(e)}"
            logger.error(error_msg)
            
            # Log the error
            device_log = DeviceLog(
                device_id=self.device.id,
                log_type='error',
                message=error_msg
            )
            db.session.add(device_log)
            db.session.commit()
            
            return False, error_msg
        finally:
            self.disconnect()
    
    def sync_users_to_db(self):
        """
        Sync users from the device to the database
        :return: (success, message)
        """
        success, result = self.get_users()
        if not success:
            return False, result
        
        users = result
        if not users:
            return True, "No users found on the device"
        
        # Process each user from the device
        sync_count = 0
        for user in users:
            # Check if the employee already exists in our database
            employee_code = f"ZK{user.uid}"
            employee = Employee.query.filter_by(employee_code=employee_code).first()
            
            if employee:
                # Update existing employee
                employee.name = user.name
                employee.last_sync = datetime.utcnow()
            else:
                # Create new employee
                employee = Employee(
                    name=user.name,
                    employee_code=employee_code,
                    is_active=True,
                    last_sync=datetime.utcnow()
                )
                db.session.add(employee)
            
            sync_count += 1
        
        # Commit changes to the database
        db.session.commit()
        
        return True, f"Successfully synced {sync_count} employees from device {self.device.name}"
    
    def sync_attendance_to_db(self):
        """
        Sync attendance logs from the device to the database
        :return: (success, message)
        """
        success, result = self.get_attendance()
        if not success:
            return False, result
        
        attendance_records = result
        if not attendance_records:
            return True, "No attendance records found on the device"
        
        # Process each attendance record from the device
        sync_count = 0
        for record in attendance_records:
            # Get the corresponding employee
            employee_code = f"ZK{record.user_id}"
            employee = Employee.query.filter_by(employee_code=employee_code).first()
            
            if not employee:
                # Create the employee if not found
                employee = Employee(
                    name=f"Employee {record.user_id}",  # Temporary name
                    employee_code=employee_code,
                    is_active=True,
                    last_sync=datetime.utcnow()
                )
                db.session.add(employee)
                db.session.flush()  # Get the employee ID
            
            # Check if this attendance log already exists
            existing_log = AttendanceLog.query.filter_by(
                employee_id=employee.id,
                device_id=self.device.id,
                timestamp=record.timestamp
            ).first()
            
            if not existing_log:
                # Determine log type (IN/OUT) based on the record
                # For ZKTeco, we need to use the status field or guess based on time
                log_type = 'IN'
                hour = record.timestamp.hour
                if hour >= 12:  # Assume afternoon punches are OUT
                    log_type = 'OUT'
                
                # Create a new attendance log
                attendance_log = AttendanceLog(
                    employee_id=employee.id,
                    device_id=self.device.id,
                    timestamp=record.timestamp,
                    log_type=log_type,
                    is_processed=False
                )
                db.session.add(attendance_log)
                sync_count += 1
        
        # Commit changes to the database
        db.session.commit()
        
        return True, f"Successfully synced {sync_count} attendance records from device {self.device.name}"
