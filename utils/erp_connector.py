import os
import requests
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ERPConnector:
    """Connector for MIR ERP API"""
    
    def __init__(self, base_url=None, username=None, password=None):
        """Initialize the connector with optional credentials"""
        self.base_url = base_url or os.environ.get('ERP_API_URL', 'https://erp.mir.ae:4082')
        self.username = username or os.environ.get('ERP_API_USERNAME')
        self.password = password or os.environ.get('ERP_API_PASSWORD')
        self.token = None
        self.token_expiry = None
    
    def login(self):
        """Authenticate with the ERP API and get access token"""
        if not self.username or not self.password:
            logger.error("ERP API credentials not configured")
            return False
            
        try:
            response = requests.post(
                f"{self.base_url}/doc/index.html#/portal/login",
                json={
                    "username": self.username,
                    "password": self.password
                },
                timeout=10,
                verify=False  # For self-signed certificates, should be True in production
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('token')
                # Set token expiry to 24 hours from now (adjust based on actual expiry)
                self.token_expiry = datetime.now().timestamp() + 86400
                logger.info("Successfully authenticated with ERP API")
                return True
            else:
                logger.error(f"Failed to authenticate with ERP API: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error connecting to ERP API: {str(e)}")
            return False
    
    def ensure_authenticated(self):
        """Ensure we have a valid authentication token"""
        # If no token or expired token, login again
        if not self.token or (self.token_expiry and datetime.now().timestamp() > self.token_expiry):
            return self.login()
        return True
    
    def get_employees(self):
        """Get list of employees from ERP"""
        if not self.ensure_authenticated():
            return []
            
        try:
            response = requests.get(
                f"{self.base_url}/api/employees",  # Adjust endpoint based on actual API
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                timeout=30,
                verify=False  # For self-signed certificates, should be True in production
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get employees: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error fetching employees from ERP API: {str(e)}")
            return []
    
    def get_attendance_data(self, start_date=None, end_date=None, employee_id=None):
        """Get attendance data from ERP"""
        if not self.ensure_authenticated():
            return []
            
        params = {}
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if employee_id:
            params['employee_id'] = employee_id
            
        try:
            response = requests.get(
                f"{self.base_url}/api/attendance",  # Adjust endpoint based on actual API
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                params=params,
                timeout=30,
                verify=False  # For self-signed certificates, should be True in production
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get attendance data: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error fetching attendance data from ERP API: {str(e)}")
            return []

# Initialize the connector
erp_connector = ERPConnector()
