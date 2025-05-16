"""
Utility for synchronizing weekend settings across employee records.
This ensures that when shift weekend settings are updated, 
all relevant attendance records are also updated.
"""
from datetime import datetime, timedelta
from models import Shift, Employee, AttendanceRecord, SystemConfig, db
from sqlalchemy import and_

def get_weekend_days_name(day_numbers):
    """Convert day numbers to day names for display"""
    if not day_numbers:
        return "Not set"
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return ', '.join([day_names[day] for day in day_numbers if 0 <= day < 7])

def sync_weekend_flags(date_from=None, date_to=None, shift_id=None, recalculate_all=False):
    """
    Update weekend flags in attendance records after weekend configuration changes.
    
    Args:
        date_from (datetime): Start date for records to update
        date_to (datetime): End date for records to update
        shift_id (int): Only update records for this shift
        recalculate_all (bool): Recalculate all records regardless of conditions
    
    Returns:
        int: Number of records updated
    """
    # Default date range to current month if not specified
    if not date_from:
        today = datetime.now().date()
        date_from = datetime(today.year, today.month, 1).date()
    
    if not date_to:
        date_to = datetime.now().date() + timedelta(days=30)
    
    # Build query for records to update
    query = AttendanceRecord.query
    
    # Apply date range filter
    query = query.filter(
        AttendanceRecord.date >= date_from,
        AttendanceRecord.date <= date_to
    )
    
    # Apply shift filter if specified
    if shift_id:
        query = query.join(Employee).filter(Employee.current_shift_id == shift_id)
    
    # Fetch records that need updating
    records = query.all()
    updated_count = 0
    
    # Process each record
    for record in records:
        employee = record.employee
        
        if not employee:
            continue
            
        # Use employee's weekend detection logic
        weekend_days = employee.get_weekend_days(record.date)
        
        # Set weekend flag based on date's day of week
        is_weekend = record.date.weekday() in weekend_days
        
        # Update if different or forced recalculation
        if recalculate_all or record.is_weekend != is_weekend:
            record.is_weekend = is_weekend
            updated_count += 1
    
    # Commit changes if any were made
    if updated_count > 0:
        db.session.commit()
        
    return updated_count

def fix_weekend_detection():
    """
    Fix weekend detection across the system by ensuring attendance records
    correctly reflect the current weekend configuration.
    """
    # Update all shift-related weekend flags
    shifts = Shift.query.all()
    total_updated = 0
    
    # Process each shift
    for shift in shifts:
        # Only process shifts with weekend days set
        if shift.weekend_days:
            # Update all records for this shift
            updated = sync_weekend_flags(shift_id=shift.id, recalculate_all=True)
            total_updated += updated
            
    return total_updated