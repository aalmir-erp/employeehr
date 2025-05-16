import os
import requests
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from requests.auth import HTTPDigestAuth, HTTPBasicAuth
import urllib3
import json
import re

# Disable insecure request warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class HikvisionConnector:
    """Connector for Hikvision DS-K1T342MFWX-E1 face recognition terminal"""
    
    def __init__(self, ip_address=None, port=None, username=None, password=None):
        """Initialize the connector with device credentials"""
        self.ip_address = ip_address or os.environ.get('DEVICE_IP_ADDRESS')
        self.port = port or os.environ.get('DEVICE_PORT', '80')
        self.username = username or os.environ.get('DEVICE_USERNAME')
        self.password = password or os.environ.get('DEVICE_PASSWORD')
        self.session = requests.Session()
        # Disable SSL verification for testing with self-signed certificates
        # In production, this should be set to True if using a valid certificate
        self.session.verify = False
        
        # Parse URL and build base_url
        self.parse_url()
    
    def parse_url(self):
        """Parse the IP address/URL and set the base_url properly"""
        # Default base URL if nothing else is available
        default_url = os.environ.get('DEVICE_API_URL', 'https://erp.mir.ae:4082')
        
        if not self.ip_address:
            self.base_url = default_url
            return
            
        # Check if it's already a URL with protocol
        if self.ip_address.startswith('http://') or self.ip_address.startswith('https://'):
            # Extract protocol
            protocol = 'https' if self.ip_address.startswith('https://') else 'http'
            
            # Remove protocol from the URL
            url_without_protocol = self.ip_address.replace('http://', '').replace('https://', '')
            
            # Extract host and path
            if '/' in url_without_protocol:
                host_part = url_without_protocol.split('/', 1)[0]
                path = '/' + url_without_protocol.split('/', 1)[1]
            else:
                host_part = url_without_protocol
                path = ''
            
            # Extract port if present in host part
            if ':' in host_part:
                hostname, port_str = host_part.split(':', 1)
                try:
                    self.port = int(port_str)
                except ValueError:
                    pass  # Keep default port if parsing fails
                self.ip_address = hostname
            else:
                self.ip_address = host_part
                
            # Build the base URL
            self.base_url = f"{protocol}://{self.ip_address}:{self.port}{path}"
        else:
            # Just an IP or hostname, use http:// protocol
            self.base_url = f"http://{self.ip_address}:{self.port}"
    
    def authenticate(self):
        """Authenticate with the device"""
        if not self.username or not self.password:
            logger.error("Device credentials not configured")
            return False
        
        try:
            # First try digest authentication (commonly used by Hikvision)
            self.session.auth = HTTPDigestAuth(self.username, self.password)
            
            # Set common headers
            headers = {
                'Accept': 'application/xml',
                'Content-Type': 'application/xml'
            }
            
            self.session.headers.update(headers)
            
            # Test authentication with a simple device info request
            response = self.session.get(f"{self.base_url}/ISAPI/System/deviceInfo")
            
            # If digest auth fails, try basic auth
            if response.status_code == 401:
                logger.info("Digest authentication failed, trying Basic authentication")
                self.session.auth = HTTPBasicAuth(self.username, self.password)
                response = self.session.get(f"{self.base_url}/ISAPI/System/deviceInfo")
            
            if response.status_code == 200:
                logger.info("Successfully authenticated with Hikvision device")
                return True
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error during authentication: {str(e)}")
            return False
    
    def get_device_info(self):
        """Get device information"""
        if not self.authenticate():
            return None
            
        try:
            response = self.session.get(f"{self.base_url}/ISAPI/System/deviceInfo")
            
            if response.status_code == 200:
                # Parse XML response
                root = ET.fromstring(response.content)
                device_info = {
                    'device_name': self._find_xml_text(root, 'deviceName'),
                    'device_id': self._find_xml_text(root, 'deviceID'),
                    'model': self._find_xml_text(root, 'model'),
                    'serial_number': self._find_xml_text(root, 'serialNumber'),
                    'firmware_version': self._find_xml_text(root, 'firmwareVersion'),
                    'mac_address': self._find_xml_text(root, 'macAddress')
                }
                return device_info
            else:
                logger.error(f"Failed to get device info: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")
            return None
    
    def get_attendance_logs(self, start_date=None, end_date=None, max_results=50):
        """Get attendance logs from the Hikvision device"""
        if not self.authenticate():
            return []
        
        try:
            # Default to past 24 hours if no dates specified
            if not start_date:
                start_date = datetime.now() - timedelta(days=1)
            if not end_date:
                end_date = datetime.now()
                
            # Format dates for Hikvision API
            start_time = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_time = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Prepare XML request
            xml_data = f"""
            <AcsEventCond>
                <searchID>1</searchID>
                <searchResultPosition>0</searchResultPosition>
                <maxResults>{max_results}</maxResults>
                <major>5</major>
                <minor>75</minor>
                <startTime>{start_time}</startTime>
                <endTime>{end_time}</endTime>
            </AcsEventCond>
            """.strip()
            
            # First try standard ISAPI endpoint for attendance records
            standard_endpoint = f"{self.base_url}/ISAPI/AccessControl/AcsEvent?format=json"
            response = self.session.post(
                standard_endpoint,
                data=xml_data,
                headers={
                    'Content-Type': 'application/xml'
                }
            )
            
            if response.status_code == 200:
                try:
                    # Try to parse as JSON
                    data = response.json()
                    return self._process_attendance_json(data)
                except json.JSONDecodeError:
                    # If not JSON, try to parse as XML
                    root = ET.fromstring(response.content)
                    return self._process_attendance_xml(root)
            else:
                # If standard endpoint fails, try alternative endpoint (for web portal)
                logger.warning(f"Standard attendance endpoint failed: {response.status_code}. Trying alternative endpoint.")
                
                # Try web portal endpoint if available (modify this based on actual endpoint)
                # Update the format based on your actual web portal API
                try:
                    # Try first alternative format (may vary by portal)
                    alt_endpoint = f"{self.base_url}/api/v1/attendance"
                    alt_params = {
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        'limit': max_results
                    }
                    alt_response = self.session.get(alt_endpoint, params=alt_params)
                    
                    if alt_response.status_code == 200:
                        data = alt_response.json()
                        # Process data from alternative endpoint (format may differ)
                        return self._process_alternative_attendance(data)
                except Exception as alt_error:
                    logger.error(f"Failed to get attendance from alternative endpoint: {str(alt_error)}")
                
                # Log the original error
                logger.error(f"Failed to get attendance logs: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error getting attendance logs: {str(e)}")
            return []
            
    def _process_alternative_attendance(self, data):
        """Process attendance data from alternative endpoint (web portal)"""
        attendance_logs = []
        
        try:
            # This parsing would depend on the actual data format returned by the web portal
            # Just a placeholder implementation
            if isinstance(data, list):
                for record in data:
                    log = {
                        'employee_id': record.get('employee_id', ''),
                        'employee_code': record.get('employee_code', ''),
                        'timestamp': record.get('timestamp', ''),
                        'event_type': record.get('event_type', 'Normal'),
                        'status': record.get('status', '')
                    }
                    attendance_logs.append(log)
            elif isinstance(data, dict) and 'attendance' in data:
                for record in data['attendance']:
                    log = {
                        'employee_id': record.get('employee_id', ''),
                        'employee_code': record.get('employee_code', ''),
                        'timestamp': record.get('timestamp', ''),
                        'event_type': record.get('event_type', 'Normal'),
                        'status': record.get('status', '')
                    }
                    attendance_logs.append(log)
        except Exception as e:
            logger.error(f"Error processing alternative attendance data: {str(e)}")
        
        return attendance_logs
    
    def _process_attendance_json(self, data):
        """Process attendance data in JSON format"""
        attendance_logs = []
        
        try:
            events = data.get('AcsEvent', {}).get('InfoList', [])
            for event in events:
                log = {
                    'employee_id': event.get('employeeNoString', ''),
                    'card_no': event.get('cardNo', ''),
                    'device_name': event.get('deviceName', ''),
                    'timestamp': event.get('time', ''),
                    'event_type': self._get_event_type(event.get('major'), event.get('minor')),
                    'status': event.get('currentVerifyMode', '')
                }
                attendance_logs.append(log)
        except Exception as e:
            logger.error(f"Error processing attendance JSON: {str(e)}")
        
        return attendance_logs
    
    def _process_attendance_xml(self, root):
        """Process attendance data in XML format"""
        attendance_logs = []
        
        try:
            for info in root.findall('.//InfoList/AcsEventInfo'):
                log = {
                    'employee_id': self._find_xml_text(info, 'employeeNoString'),
                    'card_no': self._find_xml_text(info, 'cardNo'),
                    'device_name': self._find_xml_text(info, 'deviceName'),
                    'timestamp': self._find_xml_text(info, 'time'),
                    'event_type': self._get_event_type(
                        self._find_xml_text(info, 'major'),
                        self._find_xml_text(info, 'minor')
                    ),
                    'status': self._find_xml_text(info, 'currentVerifyMode')
                }
                attendance_logs.append(log)
        except Exception as e:
            logger.error(f"Error processing attendance XML: {str(e)}")
        
        return attendance_logs
    
    def _get_event_type(self, major, minor):
        """Determine event type based on major and minor codes"""
        # Common event codes for DS-K1T342MFWX-E1
        if major == '5':
            if minor == '75':
                return 'Normal'  # Normal attendance/access
            elif minor in ['10', '11']:
                return 'Card'  # Card verification success/failure
            elif minor in ['12', '13']:
                return 'Fingerprint'  # Fingerprint verification
            elif minor in ['14', '15']:
                return 'Face'  # Face verification
        return f"Unknown ({major}-{minor})"
    
    def get_employees(self):
        """Get employees registered in the Hikvision device"""
        if not self.authenticate():
            return []
        
        try:
            # Get employee list
            # First try the standard ISAPI endpoint
            standard_endpoint = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Record?format=json"
            response = self.session.get(standard_endpoint)
            
            if response.status_code == 200:
                try:
                    # Try to parse as JSON
                    data = response.json()
                    return self._process_employees_json(data)
                except json.JSONDecodeError:
                    # If not JSON, try to parse as XML
                    root = ET.fromstring(response.content)
                    return self._process_employees_xml(root)
            else:
                # If standard endpoint fails, try alternative endpoint (for web portal)
                logger.warning(f"Standard employee endpoint failed: {response.status_code}. Trying alternative endpoint.")
                
                # Try web portal endpoint if available (modify this based on actual endpoint)
                alt_endpoint = f"{self.base_url}/api/v1/employees"
                try:
                    alt_response = self.session.get(alt_endpoint)
                    if alt_response.status_code == 200:
                        data = alt_response.json()
                        # Process data from alternative endpoint (format may differ)
                        return self._process_alternative_employees(data)
                except Exception as alt_error:
                    logger.error(f"Failed to get employees from alternative endpoint: {str(alt_error)}")
                
                # If both standard and alternative endpoints fail, return empty list
                logger.error(f"Failed to get employees: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error getting employees: {str(e)}")
            return []
            
    def _process_alternative_employees(self, data):
        """Process employee data from alternative endpoint (web portal)"""
        employees = []
        
        try:
            # This parsing would depend on the actual data format returned by the web portal
            # Just a placeholder implementation
            if isinstance(data, list):
                for user in data:
                    employee = {
                        'employee_id': user.get('id', ''),
                        'name': user.get('name', ''),
                        'card_no': user.get('badge_id', ''),
                        'status': 'Active' if user.get('active', False) else 'Inactive'
                    }
                    employees.append(employee)
            elif isinstance(data, dict) and 'employees' in data:
                for user in data['employees']:
                    employee = {
                        'employee_id': user.get('id', ''),
                        'name': user.get('name', ''),
                        'card_no': user.get('badge_id', ''),
                        'status': 'Active' if user.get('active', False) else 'Inactive'
                    }
                    employees.append(employee)
        except Exception as e:
            logger.error(f"Error processing alternative employees data: {str(e)}")
        
        return employees
    
    def _process_employees_json(self, data):
        """Process employee data in JSON format"""
        employees = []
        
        try:
            user_infos = data.get('UserInfoSearch', {}).get('UserInfo', [])
            for user in user_infos:
                employee = {
                    'employee_id': user.get('employeeNo', ''),
                    'name': user.get('name', ''),
                    'card_no': user.get('userType', ''),
                    'valid_begin_time': user.get('beginTime', ''),
                    'valid_end_time': user.get('endTime', ''),
                    'status': 'Active' if user.get('enable') == 'true' else 'Inactive'
                }
                employees.append(employee)
        except Exception as e:
            logger.error(f"Error processing employees JSON: {str(e)}")
        
        return employees
    
    def _process_employees_xml(self, root):
        """Process employee data in XML format"""
        employees = []
        
        try:
            for user in root.findall('.//UserInfo'):
                employee = {
                    'employee_id': self._find_xml_text(user, 'employeeNo'),
                    'name': self._find_xml_text(user, 'name'),
                    'card_no': self._find_xml_text(user, 'userType'),
                    'valid_begin_time': self._find_xml_text(user, 'beginTime'),
                    'valid_end_time': self._find_xml_text(user, 'endTime'),
                    'status': 'Active' if self._find_xml_text(user, 'enable') == 'true' else 'Inactive'
                }
                employees.append(employee)
        except Exception as e:
            logger.error(f"Error processing employees XML: {str(e)}")
        
        return employees
    
    def _find_xml_text(self, element, tag, default=''):
        """Helper method to find and get text from an XML element"""
        found = element.find(f".//{tag}")
        return found.text if found is not None and found.text is not None else default
    
    def test_connection(self):
        """Test connection to the Hikvision device"""
        # Just test basic authentication - don't require device info
        auth_success = self.authenticate()
        
        if auth_success:
            logger.info(f"Successfully authenticated with Hikvision device at {self.base_url}")
            
            # Try to get device info but don't fail if it returns empty data
            try:
                device_info = self.get_device_info()
                if device_info and any(device_info.values()):
                    logger.info(f"Retrieved device info: {device_info['model']} {device_info['serial_number']}")
            except Exception as e:
                logger.warning(f"Authentication successful but couldn't get device details: {str(e)}")
            
            # Authentication is enough to consider connection successful
            return True
            
        return False

# Initialize the connector
hikvision_connector = HikvisionConnector()
