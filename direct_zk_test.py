import logging
import sys
from datetime import datetime
from zk import ZK, const

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_device_connection(ip_address, port=4370):
    """Test connection to a ZKTeco device directly without using our connector class"""
    logger.info(f"Testing connection to ZKTeco device at {ip_address}:{port}")
    
    # Handle URL formats (like http://erp.mir.ae:4077/)
    # Remove http:// or https:// if present
    if ip_address.startswith('http://') or ip_address.startswith('https://'):
        ip_address = ip_address.split('//', 1)[1].split('/', 1)[0]  # Extract domain from URL
        
    # If IP has port in it, extract the port
    if ':' in ip_address and port == 4370:  # Only extract port if we're using the default
        ip_address, port_str = ip_address.split(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            pass
            
    # Create ZK instance
    logger.info(f"Using ZKTeco connection info: {ip_address}:{port}")
    zk = ZK(ip_address, port=port, timeout=5)
    
    try:
        # Connect to device
        logger.info("Connecting to device...")
        conn = zk.connect()
        logger.info("✅ Connection successful!")
        
        # Get device info
        logger.info("\nDevice Information:")
        logger.info(f"  Firmware Version: {conn.get_firmware_version()}")
        logger.info(f"  Serial Number: {conn.get_serialnumber()}")
        logger.info(f"  Platform: {conn.get_platform()}")
        logger.info(f"  Device Name: {conn.get_device_name()}")
        logger.info(f"  Work Code: {conn.get_workcode()}")
        logger.info(f"  OEM Vendor: {conn.get_oem_vendor()}")
        logger.info(f"  Fingerprint Algorithm: {conn.get_fp_version()}")
        
        # Get users
        logger.info("\nFetching users...")
        users = conn.get_users()
        if users:
            logger.info(f"Found {len(users)} users:")
            for i, user in enumerate(users[:10], 1):  # Show first 10 to avoid flooding
                logger.info(f"  {i}. User ID: {user.uid}, Name: {user.name}")
            if len(users) > 10:
                logger.info(f"  ... and {len(users) - 10} more users")
        else:
            logger.warning("No users found on device")
        
        # Get attendance records
        logger.info("\nFetching attendance records...")
        attendance = conn.get_attendance()
        if attendance:
            logger.info(f"Found {len(attendance)} attendance records:")
            for i, record in enumerate(attendance[:10], 1):  # Show first 10 to avoid flooding
                logger.info(f"  {i}. User ID: {record.user_id}, Timestamp: {record.timestamp}")
            if len(attendance) > 10:
                logger.info(f"  ... and {len(attendance) - 10} more records")
        else:
            logger.warning("No attendance records found on device")
        
        # Disconnect
        conn.disconnect()
        logger.info("\nDisconnected from device")
        
    except Exception as e:
        logger.error(f"❌ Connection failed: {str(e)}")

if __name__ == "__main__":
    # List of IP addresses to try
    ip_addresses = []
    
    if len(sys.argv) >= 2:
        # Use IP addresses provided as command line arguments
        for arg in sys.argv[1:]:
            # Handle URL format (http://domain:port/)
            if arg.startswith('http://') or arg.startswith('https://'):
                # Extract domain and port from URL
                parts = arg.split('//')
                domain_parts = parts[1].split('/')
                ip_port = domain_parts[0]
                
                if ':' in ip_port:
                    ip, port_str = ip_port.split(':')
                    try:
                        port = int(port_str)
                        ip_addresses.append((ip, port))
                    except ValueError:
                        ip_addresses.append((ip_port, 4370))
                else:
                    # No port in URL, use default
                    ip_addresses.append((ip_port, 4370))
            elif ':' in arg:
                # Format: ip:port
                ip, port_str = arg.split(':')
                try:
                    port = int(port_str)
                    ip_addresses.append((ip, port))
                except ValueError:
                    ip_addresses.append((arg, 4370))
            else:
                # Just an IP or hostname
                ip_addresses.append((arg, 4370))
    else:
        # Default IP addresses to try
        print("No IP addresses provided. Will try common IP addresses for ZKTeco devices.")
        print("Usage: python direct_zk_test.py <ip_address> [ip_address2:port] ...")
        print("Example: python direct_zk_test.py 192.168.1.201 192.168.1.200:4370")
        
        # Use the provided device URL
        logger.info("Using the provided device URL: erp.mir.ae:4077")
        ip_addresses = [
            ('erp.mir.ae', 4077)
        ]
    
    # Try each IP address
    for ip, port in ip_addresses:
        try:
            print(f"\n\n=== Testing connection to {ip}:{port} ===")
            test_device_connection(ip, port)
        except Exception as e:
            print(f"Error with {ip}:{port} - {str(e)}")
            continue
