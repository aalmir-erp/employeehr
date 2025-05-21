"""
Advanced Rule-Based Overtime Calculation Engine

This module provides functions to calculate overtime based on configurable rules.
It supports:
- Different rates for weekdays, weekends, and holidays
- Night shift differential
- Department-specific rules
- Maximum overtime limits (daily, weekly, monthly)
- Rule priorities and validities
- Separate tracking of regular, weekend, and holiday overtime
"""

from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from flask import current_app

def get_applicable_rule(employee, date):
    """
    Find the most applicable overtime rule for an employee on a specific date
    Returns the rule object or None if no applicable rule found
    """
    from models import OvertimeRule
    
    # Skip if no employee or department
    if not employee or not employee.department:
        return None
        
    department = employee.department
    
    try:
        # Get valid rules ordered by priority (highest first)
        rules = OvertimeRule.query.filter(
            OvertimeRule.is_active == True,
            or_(
                OvertimeRule.valid_from.is_(None),
                OvertimeRule.valid_from <= date
            ),
            or_(
                OvertimeRule.valid_until.is_(None),
                OvertimeRule.valid_until >= date
            )
        ).order_by(OvertimeRule.priority.desc()).all()
        
        # Find first rule that applies to this department
        for rule in rules:
            if rule.applies_to_department(department):
                return rule
    except Exception as e:
        current_app.logger.error(f"Error finding applicable overtime rule: {str(e)}")
    
    return None

def calculate_overtime(record, recalculate=False, commit=True):
    """
    Calculate overtime for an attendance record using applicable rules
    
    Args:
        record: AttendanceRecord object
        recalculate: Force recalculation even if already calculated
        commit: Whether to commit changes to the database
        
    Returns:
        tuple (overtime_hours, overtime_rate)
    """
    from models import db
    
    # Skip if no check-in/check-out or already calculated and not forcing recalculation
    if not record.check_in or not record.check_out:
        return 0.0, 1.0
        
    if record.overtime_hours > 0 and record.overtime_rate > 1.0 and not recalculate:
        return record.overtime_hours, record.overtime_rate
    
    # Calculate work hours if needed
    if record.work_hours <= 0 or recalculate:
        record.calculate_work_hours()
    
    # Calculate overtime hours and rate
    result = record.calculate_overtime()
    
    # Commit changes if requested
    if commit:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving overtime calculation: {str(e)}")
    
    return result

def calculate_weekly_overtime(employee_id, start_date, end_date=None):
    """
    Calculate total overtime for an employee in a week
    
    Args:
        employee_id: Employee ID
        start_date: Start date of the week
        end_date: End date of the week (defaults to start_date + 6 days)
        
    Returns:
        tuple (total_overtime_hours, weighted_average_rate)
    """
    from models import AttendanceRecord
    
    if not end_date:
        end_date = start_date + timedelta(days=6)
    
    # Get all attendance records for the employee in the date range
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date
    ).all()
    
    # Sum up overtime hours and weighted rates
    total_overtime = 0.0
    weighted_sum = 0.0
    
    for record in records:
        # Calculate overtime if not already calculated
        if record.overtime_hours <= 0:
            calculate_overtime(record)
            
        total_overtime += record.overtime_hours
        weighted_sum += record.overtime_hours * record.overtime_rate
    
    # Calculate weighted average rate
    avg_rate = weighted_sum / total_overtime if total_overtime > 0 else 1.0
    
    return total_overtime, avg_rate

def calculate_monthly_overtime(employee_id, year, month):
    """
    Calculate total overtime for an employee in a month
    
    Args:
        employee_id: Employee ID
        year: Year (integer)
        month: Month (integer, 1-12)
        
    Returns:
        tuple (total_overtime_hours, weighted_average_rate)
    """
    from models import AttendanceRecord
    import calendar
    
    # Get first and last day of the month
    last_day = calendar.monthrange(year, month)[1]
    start_date = datetime(year, month, 1).date()
    end_date = datetime(year, month, last_day).date()
    
    # Get all attendance records for the employee in the date range
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date
    ).all()
    
    # Sum up overtime hours and weighted rates
    total_overtime = 0.0
    weighted_sum = 0.0
    
    for record in records:
        # Calculate overtime if not already calculated
        if record.overtime_hours <= 0:
            calculate_overtime(record)
            
        total_overtime += record.overtime_hours
        weighted_sum += record.overtime_hours * record.overtime_rate
    
    # Calculate weighted average rate
    avg_rate = weighted_sum / total_overtime if total_overtime > 0 else 1.0
    
    return total_overtime, avg_rate

def apply_overtime_limits(employee_id, date, overtime_hours, rule=None):
    """
    Apply maximum overtime limits (daily/weekly/monthly)
    
    Args:
        employee_id: Employee ID
        date: Date of the record
        overtime_hours: Requested overtime hours
        rule: OvertimeRule to use (if None, finds applicable rule)
        
    Returns:
        float: Allowed overtime hours after applying limits
    """
    from models import Employee, OvertimeRule
    
    # If no rule specified, find applicable rule
    if not rule:
        employee = Employee.query.get(employee_id)
        if not employee:
            return overtime_hours
        rule = get_applicable_rule(employee, date)
    
    # If no rule found, use default maximum (4 hours)
    if not rule:
        return min(overtime_hours, 4.0)
    
    # Apply daily limit
    allowed_hours = min(overtime_hours, rule.max_daily_overtime)
    
    # Check weekly limit if stricter
    week_start = date - timedelta(days=date.weekday())  # Monday of current week
    current_weekly, _ = calculate_weekly_overtime(employee_id, week_start, date - timedelta(days=1))
    if current_weekly + allowed_hours > rule.max_weekly_overtime:
        allowed_hours = max(0, rule.max_weekly_overtime - current_weekly)
    
    # Check monthly limit if stricter
    current_monthly, _ = calculate_monthly_overtime(employee_id, date.year, date.month)
    if current_monthly + allowed_hours > rule.max_monthly_overtime:
        allowed_hours = max(0, rule.max_monthly_overtime - current_monthly)
    
    return allowed_hours

def process_attendance_records(date=None, employee_id=None, recalculate=False):
    """
    Process and calculate overtime for attendance records
    Can be run for a specific date, employee, or both
    
    Args:
        date: Process records for this date only
        employee_id: Process records for this employee only
        recalculate: Force recalculation even if already calculated
        
    Returns:
        int: Number of records processed
    """
    from models import AttendanceRecord, db
    
    # Build query with filters
    query = AttendanceRecord.query
    
    if date:
        query = query.filter(AttendanceRecord.date == date)
    
    if employee_id:
        query = query.filter(AttendanceRecord.employee_id == employee_id)
    
    # Only process records with both check-in and check-out
    query = query.filter(
        AttendanceRecord.check_in.isnot(None),
        AttendanceRecord.check_out.isnot(None)
    )
    
    records = query.all()
    processed_count = 0
    print (records, "   records  -----")
    
    for record in records:
        try:
            # Calculate work hours and overtime
            calculate_overtime(record, recalculate, commit=False)
            processed_count += 1
        except Exception as e:
            current_app.logger.error(f"Error processing record ID {record.id}: {str(e)}")
    
    # Commit all changes at once
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing overtime calculations: {str(e)}")
    
    return processed_count
    
def recalculate_holiday_overtime():
    """
    Recalculate overtime specifically for holiday records
    This is useful after adding new holidays
    """
    from models import db, AttendanceRecord
    
    # Get records for holiday dates
    records = AttendanceRecord.query.filter(AttendanceRecord.is_holiday == True).all()
    count = 0
    
    for record in records:
        if record.check_in and record.check_out:
            calculate_overtime(record, recalculate=True, commit=False)
            count += 1
    
    # Commit all changes at once for better performance
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error while recalculating holiday overtime: {str(e)}")
        
    return count