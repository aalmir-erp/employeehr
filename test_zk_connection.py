import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from zk import ZK

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a minimal Flask application for testing
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"  # Use an in-memory database for testing
db.init_app(app)

def test_device_connection(ip_address, port=4370):
    """Test connection to a ZKTeco device"""
    logger.info(f"Testing connection to device at {ip_address}:{port}")
    
    # Create a mock device for testing
    device = AttendanceDevice(
        id=1,
        name="Test Device",
        device_id="TEST001",
        device_type="zkteco",
        ip_address=ip_address,
        port=port,
        is_active=True
    )
    
    # Initialize the ZK device connector
    zk_device = ZKDevice(device)
    
    # Test connection
    success, message = zk_device.connect()
    if success:
        logger.info("✅ Connection successful!")
        
        # Try to get device info
        logger.info("Getting device info...")
        device_info = zk_device.get_device_info()
        if device_info:
            logger.info("Device Info:")
            for key, value in device_info.items():
                logger.info(f"  {key}: {value}")
        else:
            logger.error("❌ Failed to get device info")
        
        # Try to get users
        logger.info("\nGetting users from device...")
        users_success, users_result = zk_device.get_users()
        if users_success:
            if users_result:
                logger.info(f"Found {len(users_result)} users:")
                for i, user in enumerate(users_result, 1):
                    logger.info(f"  {i}. User ID: {user.uid}, Name: {user.name}")
            else:
                logger.warning("No users found on device")
        else:
            logger.error(f"❌ Failed to get users: {users_result}")
        
        # Try to get attendance records
        logger.info("\nGetting attendance records from device...")
        attendance_success, attendance_result = zk_device.get_attendance()
        if attendance_success:
            if attendance_result:
                logger.info(f"Found {len(attendance_result)} attendance records:")
                for i, record in enumerate(attendance_result[:10], 1):  # Show first 10 only to avoid flooding console
                    logger.info(f"  {i}. User ID: {record.user_id}, Timestamp: {record.timestamp}")
                if len(attendance_result) > 10:
                    logger.info(f"  ... and {len(attendance_result) - 10} more records")
            else:
                logger.warning("No attendance records found on device")
        else:
            logger.error(f"❌ Failed to get attendance records: {attendance_result}")
            
        # Disconnect from device
        zk_device.disconnect()
        logger.info("Disconnected from device")
    else:
        logger.error(f"❌ Connection failed: {message}")

if __name__ == "__main__":
    # To use this script, provide the IP address of your ZKTeco device
    # For example: python test_zk_connection.py 192.168.1.201
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_zk_connection.py <ip_address> [port]")
        print("Example: python test_zk_connection.py 192.168.1.201 4370")
        sys.exit(1)
    
    ip_address = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4370
    
    with app.app_context():
        test_device_connection(ip_address, port)
