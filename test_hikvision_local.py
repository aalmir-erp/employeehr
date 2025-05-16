import os
import sys
import logging
from utils.hikvision_connector import HikvisionConnector

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('hikvision_test')

def test_hikvision_connection(ip_address, username, password, port=80):
    """Test connection to a local Hikvision device"""
    # Create connector with provided credentials
    connector = HikvisionConnector(
        ip_address=ip_address,
        port=port,  # This will be extracted from the URL if included
        username=username,
        password=password
    )
    
    logger.info(f"Base URL: {connector.base_url}")
    
    # Test authentication
    logger.info("Testing authentication...")
    auth_result = connector.authenticate()
    logger.info(f"Authentication result: {auth_result}")
    
    if not auth_result:
        logger.error("Authentication failed! Check credentials and URL.")
        return False
    
    # Get device info
    logger.info("Getting device info...")
    device_info = connector.get_device_info()
    if device_info:
        logger.info("Device info:")
        for key, value in device_info.items():
            logger.info(f"  {key}: {value}")
    else:
        logger.error("Failed to get device info!")
        return False
    
    # Get employees
    logger.info("Getting employees...")
    employees = connector.get_employees()
    logger.info(f"Found {len(employees)} employees")
    if employees:
        # Log first 3 employees for testing
        for i, employee in enumerate(employees[:3]):
            logger.info(f"Employee {i+1}:")
            for key, value in employee.items():
                logger.info(f"  {key}: {value}")
    
    # Get attendance logs
    logger.info("Getting attendance logs...")
    logs = connector.get_attendance_logs(max_results=10)
    logger.info(f"Found {len(logs)} attendance logs")
    if logs:
        # Log first 3 logs for testing
        for i, log in enumerate(logs[:3]):
            logger.info(f"Log {i+1}:")
            for key, value in log.items():
                logger.info(f"  {key}: {value}")
    
    logger.info("Tests completed successfully!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python test_hikvision_local.py <ip_address> <username> <password> [port]")
        print("Example: python test_hikvision_local.py 192.168.1.100 admin Mir@Dxb60 80")
        sys.exit(1)
    
    ip_address = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 80
    
    success = test_hikvision_connection(ip_address, username, password, port)
    sys.exit(0 if success else 1)
