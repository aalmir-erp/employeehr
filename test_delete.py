"""
Test script to diagnose PostgreSQL deletion issues with attendance records.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Create a minimal app context
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db.init_app(app)

# Import models after db is defined to avoid circular imports
from db import db as dummy_db  # This avoids the circular import with models.py
import models

def test_delete_attendance_logs():
    """Test deleting attendance logs"""
    print("Testing deletion of attendance logs...")
    try:
        result = models.AttendanceLog.query.delete()
        db.session.commit()
        print(f"✓ Successfully deleted {result} attendance logs")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"✗ Error deleting attendance logs: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

def test_delete_attendance_records():
    """Test deleting attendance records"""
    print("Testing deletion of attendance records...")
    try:
        result = models.AttendanceRecord.query.delete()
        db.session.commit()
        print(f"✓ Successfully deleted {result} attendance records")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"✗ Error deleting attendance records: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

def test_delete_records_with_session():
    """Test manually finding and deleting records via session"""
    print("Testing manual deletion via session...")
    try:
        # First find records
        records = models.AttendanceRecord.query.all()
        count = len(records)
        
        # Then delete them one by one
        for record in records:
            db.session.delete(record)
        
        # Commit the changes
        db.session.commit()
        print(f"✓ Successfully deleted {count} attendance records manually")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"✗ Error manually deleting attendance records: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

def test_delete_with_cascade():
    """Test using a more complex deletion with cascade"""
    print("Testing deletion with cascade option...")
    try:
        from sqlalchemy import delete
        
        # Try to delete all attendance logs first
        stmt = delete(models.AttendanceLog)
        result1 = db.session.execute(stmt)
        print(f"Deleted {result1.rowcount} logs")
        
        # Then delete attendance records
        stmt = delete(models.AttendanceRecord)
        result2 = db.session.execute(stmt)
        print(f"Deleted {result2.rowcount} records")
        
        # Commit the changes
        db.session.commit()
        print("✓ Successfully deleted records with cascade")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"✗ Error deleting with cascade: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    with app.app_context():
        print("\n=== TESTING DELETION OF ATTENDANCE RECORDS AND LOGS ===\n")
        
        # Option 1: Delete logs first, then records (recommended approach)
        print("\n--- Option 1: Delete logs first, then records ---")
        if test_delete_attendance_logs():
            test_delete_attendance_records()
            
        # Option 2: Try records first (likely to fail)
        print("\n--- Option 2: Try records first (likely to fail) ---")
        test_delete_attendance_records()
        
        # Option 3: Manual session-based deletion
        print("\n--- Option 3: Manual session-based deletion ---")
        test_delete_records_with_session()
        
        # Option 4: Delete with cascade
        print("\n--- Option 4: Delete with cascade ---")
        test_delete_with_cascade()

if __name__ == "__main__":
    main()