import logging
from datetime import datetime, date, timedelta
from models import Employee, AttendanceRecord, Shift, ShiftAssignment, Holiday
from app import db

logger = logging.getLogger(__name__)

def get_employee_shift(employee_id, target_date=None):
    """Get an employee's shift for a specific date"""
    if not target_date:
        target_date = date.today()
    
    # Get the employee
    employee = Employee.query.get(employee_id)
    if not employee:
        return None
    
    # Check if there's a specific shift assignment for this date
    shift_assignment = ShiftAssignment.query.filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.start_date <= target_date,
        (ShiftAssignment.end_date >= target_date) | (ShiftAssignment.end_date.is_(None)),
        ShiftAssignment.is_active == True
    ).first()
    
    if shift_assignment:
        return shift_assignment.shift
    
    # Fall back to employee's default shift
    if employee.current_shift_id:
        return employee.current_shift
    
    return None

def is_holiday(employee_id, target_date=None):
    """Check if the given date is a holiday for the employee"""
    if not target_date:
        target_date = date.today()
    
    # Check for global holidays
    global_holiday = Holiday.query.filter_by(
        date=target_date,
        is_employee_specific=False
    ).first()
    
    if global_holiday:
        return True
    
    # Check for employee-specific holidays
    employee_holiday = Holiday.query.filter_by(
        date=target_date,
        is_employee_specific=True,
        employee_id=employee_id
    ).first()
    
    return employee_holiday is not None

def format_time_display(time_obj):
    """Format time object for display"""
    if not time_obj:
        return ""
    if isinstance(time_obj, datetime):
        return time_obj.strftime("%H:%M")
    return time_obj.strftime("%H:%M")

def get_date_range(start_date, end_date):
    """Generate a list of dates between start and end"""
    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)
    return date_list

def calculate_work_hours(check_in, check_out, break_duration=0.0):
    """Calculate work hours between check in and check out"""
    if not check_in or not check_out:
        return 0
    
    # Calculate the time difference in hours
    delta = check_out - check_in
    hours = delta.total_seconds() / 3600
    
    # Convert break_duration to float in case it's passed as int or string
    try:
        break_duration_float = float(break_duration)
    except (ValueError, TypeError):
        break_duration_float = 0.0
    
    # Subtract break duration
    hours -= break_duration_float
    
    return max(0, hours)

def calculate_overtime(work_hours, standard_hours):
    """Calculate overtime hours"""
    if work_hours > standard_hours:
        return work_hours - standard_hours
    return 0

def get_attendance_stats(employee_id, start_date, end_date):
    """Get attendance statistics for an employee over a date range"""
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date
    ).all()
    
    stats = {
        'present': 0,
        'absent': 0,
        'late': 0,
        'total_hours': 0,
        'overtime_hours': 0,
        'total_overtime': 0,  # Added for template compatibility
        'present_count': 0,   # Also for template compatibility
        'absent_count': 0,    # Also for template compatibility
        'late_count': 0,      # Also for template compatibility
        'total_days': len(records),
        'avg_hours': 0
    }
    
    for record in records:
        if record.status == 'present':
            stats['present'] += 1
            stats['total_hours'] += record.work_hours if record.work_hours is not None else 0
            overtime = record.overtime_hours if record.overtime_hours is not None else 0
            stats['overtime_hours'] += overtime
            stats['total_overtime'] += overtime
        elif record.status == 'absent':
            stats['absent'] += 1
        elif record.status == 'late':
            stats['late'] += 1
            stats['present'] += 1
            stats['total_hours'] += record.work_hours if record.work_hours is not None else 0
            overtime = record.overtime_hours if record.overtime_hours is not None else 0
            stats['overtime_hours'] += overtime
            stats['total_overtime'] += overtime
    
    # Update count fields for template consistency
    stats['present_count'] = stats['present']
    stats['absent_count'] = stats['absent']
    stats['late_count'] = stats['late']
    
    # Calculate average work hours
    if stats['present'] > 0:
        stats['avg_hours'] = stats['total_hours'] / stats['present']
    
    return stats

def get_device_status_stats():
    """Get summary statistics of device statuses"""
    from models import AttendanceDevice
    
    devices = AttendanceDevice.query.all()
    stats = {
        'total': len(devices),
        'online': 0,
        'offline': 0,
        'error': 0
    }
    
    for device in devices:
        if device.status == 'online':
            stats['online'] += 1
        elif device.status == 'offline':
            stats['offline'] += 1
        elif device.status == 'error':
            stats['error'] += 1
    
    return stats
