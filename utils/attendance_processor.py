"""
Utility functions for processing attendance logs and records
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_

from models import AttendanceLog, AttendanceRecord, Employee, db, Holiday,Shift



def determine_shift_type(check_in_time, employee_id=None):
    """
    Determine shift type based on check-in time and employee's assigned shift
    
    Morning shift: 5:00 AM - 11:59 AM
    Afternoon shift: 12:00 PM - 5:59 PM
    Night shift: 6:00 PM - 4:59 AM
    
    If employee_id is provided, we'll first try to determine the shift type
    from the employee's current shift assignment.
    """
    if not check_in_time:
        return 'unknown'
    
    # Try to get shift type from employee's current shift if available
    if employee_id:
        from models import Employee, Shift
        employee = Employee.query.get(employee_id)
        if employee and employee.current_shift_id:
            shift = Shift.query.get(employee.current_shift_id)
            if shift:
                # Night shift is typically labeled with "night" in the name
                if shift.name and ('night' in shift.name.lower() or 'evening' in shift.name.lower()):
                    return 'night'
                # Day shift is typically labeled with "day" in the name
                elif shift.name and ('day' in shift.name.lower() or 'morning' in shift.name.lower()):
                    return 'day'
                # Check shift start time if available
                if shift.start_time:
                    hour = shift.start_time.hour
                    if 17 <= hour or hour < 5:  # 5 PM to 5 AM
                        return 'night'
                    else:
                        return 'day'
    
    # Fallback to time-based determination if we couldn't determine from shift
    hour = check_in_time.hour
    
    if 5 <= hour < 12:
        return 'day'
    elif 12 <= hour < 18:
        return 'afternoon'
    else:
        return 'night'


def calculate_total_duration(check_in, check_out):
    """Calculate total duration including breaks"""
    if not check_in or not check_out:
        return 0
        
    # Handle overnight shifts
    end_time = check_out
    if end_time < check_in:
        end_time = end_time + timedelta(days=1)
        
    duration = (end_time - check_in).total_seconds() / 3600
    return round(duration, 2)


def estimate_break_duration(logs):
    """
    Estimate break duration from a series of punch logs and detect actual break start/end times
    
    Algorithm:
    1. Sort logs by timestamp
    2. Identify in/out pairs by looking at log_type
    3. Any time an employee goes out and then comes back in during shift hours is counted as a break
    4. ALL break time durations are added up to calculate total break duration
    5. For the main break record (break_start/break_end), prioritize breaks that occur during lunch hours
    6. If no lunch break found, use the largest break
    
    Returns:
        tuple: (total_break_duration, primary_break_start, primary_break_end)
    """
    # Debug info
    print(f"DEBUG - estimate_break_duration called with {len(logs) if logs else 0} logs")
    
    if not logs or len(logs) < 3:  # Need at least check-in, break, check-out
        print(f"DEBUG - Not enough logs to detect break: {len(logs) if logs else 0} logs")
        return 1, None, None
        
    # Sort logs by timestamp
    sorted_logs = sorted(logs, key=lambda x: x.timestamp)
    
    # Debug - Print all logs for this employee on this day
    for i, log in enumerate(sorted_logs):
        print(f"DEBUG - Log {i+1}: {log.timestamp} - {log.log_type}")
    
    total_break_time = 0
    previous_time = None
    previous_log = None
    
    # Track breaks
    detected_breaks = []
    
    # Look for out->in sequences
    for i in range(1, len(sorted_logs)):
        current_log = sorted_logs[i]
        previous_log = sorted_logs[i-1]
        
        # If we have an out->in sequence, that's a break
        if (previous_log.log_type.lower() in ['out', 'check_out'] and 
            current_log.log_type.lower() in ['in', 'check_in']):
            
            # Calculate duration of the break in hours
            diff = (current_log.timestamp - previous_log.timestamp).total_seconds() / 3600
            
            # Debug 
            print(f"DEBUG - Break sequence found between {previous_log.timestamp} ({previous_log.log_type}) and {current_log.timestamp} ({current_log.log_type}): {diff:.2f} hours")
            
            # Only count breaks > 5 minutes to avoid erroneous quick check-in/check-outs 
            # And breaks < 5 hours to avoid missing punch situations
            if 0.08 < diff < 5:
                # Add to total break time - this is the critical part for multiple breaks
                # ALL breaks are counted here, not just the primary lunch break
                total_break_time += diff
                print(f"DEBUG - Break added: {diff:.2f} hours, running total={total_break_time:.2f}")
                
                # Calculate lunch hour score for this break
                is_lunch_time = (11 <= previous_log.timestamp.hour <= 14) or (11 <= current_log.timestamp.hour <= 14)
                is_fully_lunch = (11 <= previous_log.timestamp.hour <= 14) and (11 <= current_log.timestamp.hour <= 14)
                lunch_score = 3 if is_fully_lunch else 1 if is_lunch_time else 0
                
                # Add duration score - prioritize breaks close to 1 hour for lunch
                duration_score = 0
                duration_diff = abs(diff - 1.0)
                if duration_diff < 0.1:  # Within 6 minutes of 1 hour
                    duration_score = 3
                elif duration_diff < 0.25:  # Within 15 minutes of 1 hour
                    duration_score = 2
                elif duration_diff < 0.5:  # Within 30 minutes of 1 hour
                    duration_score = 1
                
                # Record this break with its scores
                detected_breaks.append({
                    'start': previous_log.timestamp,  
                    'end': current_log.timestamp,
                    'duration': diff,
                    'is_lunch_time': is_lunch_time,
                    'is_fully_lunch': is_fully_lunch,
                    'lunch_score': lunch_score,
                    'duration_score': duration_score,
                    'total_score': lunch_score + duration_score
                })
    
    # If total breaks < 0.1 hours, we have minimal breaks
    # Default to returning None for break_start/break_end in this case
    if total_break_time < 0.1:
        print(f"DEBUG - Total break time too small: {total_break_time:.2f} hours")
        if total_break_time < 1:
            total_break_time = 1
        return total_break_time, None, None
    
    # Find the most appropriate break using our sophisticated algorithm
    # First check if we have any breaks detected
    if not detected_breaks:
        print(f"DEBUG - No out-in sequences detected for breaks")
        if total_break_time < 1:
            total_break_time = 1
        return total_break_time, None, None
    
    # Sort breaks by total score (lunch + duration score)
    sorted_breaks = sorted(detected_breaks, key=lambda x: (x['total_score'], x['duration']), reverse=True)
    
    # Select the primary break (the one to be stored in break_start/break_end fields)
    # This is the highest scoring break, but we're still counting ALL breaks in the total duration
    selected_break = sorted_breaks[0]
    break_start = selected_break['start']
    break_end = selected_break['end']
    
    # Debug info about the primary break
    if selected_break['is_fully_lunch']:
        print(f"DEBUG - Selected primary break (fully lunch): {selected_break['duration']:.2f} hours from {break_start} to {break_end}")
    elif selected_break['is_lunch_time']:
        print(f"DEBUG - Selected primary break (partial lunch): {selected_break['duration']:.2f} hours from {break_start} to {break_end}")
    else:
        print(f"DEBUG - Selected primary break (non-lunch): {selected_break['duration']:.2f} hours from {break_start} to {break_end}")
    
    # Important: Print summary of all breaks
    for i, brk in enumerate(detected_breaks):
        is_primary = (brk['start'] == break_start and brk['end'] == break_end)
        print(f"DEBUG - Break {i+1}: {brk['duration']:.2f} hours from {brk['start']} to {brk['end']} - score: {brk['total_score']} {'(PRIMARY)' if is_primary else ''}")
    
    print(f"DEBUG - Final break result: {round(total_break_time, 2):.2f} hours total, primary break: start={break_start}, end={break_end}")
    print (" --------------------------------------- ")
    # total_break_time = 4
    if  total_break_time <1:
        total_break_time = 1
    return round(total_break_time, 2), break_start, break_end


def process_unprocessed_logs(limit=None, date_from=None, date_to=None):
    from utils.overtime_engine import calculate_overtime
    employee_ids = []

    print(f"DEBUG - Starting process_unprocessed_logs with limit={limit}, date_from={date_from}, date_to={date_to}")

    query = db.session.query(
        AttendanceLog.employee_id,
        func.date(AttendanceLog.timestamp).label('log_date')
    ).filter(AttendanceLog.is_processed == False)

    if date_from:
        query = query.filter(func.date(AttendanceLog.timestamp) >= date_from)
    if date_to:
        query = query.filter(func.date(AttendanceLog.timestamp) <= date_to)

    unprocessed_combinations = query.distinct().order_by(
        AttendanceLog.employee_id,
        func.date(AttendanceLog.timestamp)
    )

    if limit:
        unprocessed_combinations = unprocessed_combinations.limit(limit)

    records_created = 0
    logs_processed = 0
    all_combinations = list(unprocessed_combinations)

    print(f"DEBUG - Found {len(all_combinations)} unprocessed employee-date combinations")

    for emp_id, log_date in all_combinations:
        employee_ids.append(emp_id)
        print(f"DEBUG - Processing employee {emp_id} on date {log_date}")

        next_day = log_date + timedelta(days=1)

        current_logs = AttendanceLog.query.filter(
            AttendanceLog.employee_id == emp_id,
            func.date(AttendanceLog.timestamp).in_([log_date, next_day])
        ).order_by(AttendanceLog.timestamp).all()

        logs = [log for log in current_logs if not log.is_processed]
        if not logs:
            print(f"DEBUG - No unprocessed logs for employee {emp_id} on {log_date}, skipping")
            continue

        # Pair up IN/OUT logs
        sessions = []
        i = 0
        while i < len(logs) - 1:
            in_log = logs[i]
            out_log = logs[i + 1]
            if in_log.log_type in ['IN', 'check_in'] and out_log.log_type in ['OUT', 'check_out']:
                sessions.append((in_log, out_log))
                i += 2
            else:
                i += 1

        if not sessions:
            print(f"DEBUG - No valid IN/OUT session found for employee {emp_id} on {log_date}")
            continue

        # Use first IN and last OUT for main check-in/check-out
        check_in = sessions[0][0].timestamp
        check_out = sessions[-1][1].timestamp

        # Compute total work hours
        total_duration = sum([
            (out_log.timestamp - in_log.timestamp).total_seconds() / 3600.0
            for in_log, out_log in sessions
        ])

        # Compute break (if multiple sessions)
        break_duration = 0.0
        break_start = None
        break_end = None
        if len(sessions) > 1:
            break_start = sessions[0][1].timestamp
            break_end = sessions[1][0].timestamp
            break_duration = (break_end - break_start).total_seconds() / 3600.0

        work_hours = max(0.0, total_duration - break_duration)

        # Use check_in.date() to correctly anchor the attendance to start day
        record_date = check_in.date()

        # Check holiday/weekend
        is_holiday, is_weekend = check_holiday_and_weekend(emp_id, record_date)

        # Determine shift type
        shift_type = determine_shift_type(check_in, emp_id)

        # Fetch/create attendance record
        record = AttendanceRecord.query.filter_by(
            employee_id=emp_id,
            date=record_date
        ).first()

        if not record:
            record = AttendanceRecord(employee_id=emp_id, date=record_date)
            records_created += 1

        # Default status
        status = 'present'

        # Check late arrival
        employee = Employee.query.get(emp_id)
        if employee and employee.current_shift_id:
            shift = Shift.query.get(employee.current_shift_id)
            if shift and shift.start_time:
                grace_minutes = shift.grace_period_minutes or 0
                shift_start = datetime.combine(record_date, shift.start_time) + timedelta(minutes=grace_minutes)
                if check_in > shift_start:
                    status = 'late'

        # Update record fields
        record.check_in = check_in
        record.check_out = check_out
        record.total_duration = total_duration
        record.break_duration = break_duration
        record.break_start = break_start
        record.break_end = break_end
        record.work_hours = work_hours
        record.status = status
        record.is_holiday = is_holiday
        record.is_weekend = is_weekend
        record.break_calculated = False
        record.shift_type = shift_type

        db.session.add(record)
        db.session.flush()

        for in_log, out_log in sessions:
            in_log.is_processed = True
            in_log.attendance_record_id = record.id
            out_log.is_processed = True
            out_log.attendance_record_id = record.id
            logs_processed += 2

        try:
            db.session.commit()
            try:
                calculate_overtime(record, recalculate=True)
            except Exception as e:
                print(f"ERROR - Overtime calculation failed for record {record.id}: {str(e)}")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR - DB commit failed for employee {emp_id} on {record_date}: {str(e)}")

    # Optional: Mark absents
    if date_from and date_to:
        print("DEBUG - Checking for missing dates to mark as absent...")
        for emp in Employee.query.filter(Employee.id.in_(employee_ids)).all():
            current_date = date_from
            while current_date <= date_to:
                record_exists = AttendanceRecord.query.filter_by(
                    employee_id=emp.id,
                    date=current_date
                ).first()
                is_holiday, is_weekend = check_holiday_and_weekend(emp.id, current_date)
                if not record_exists and not is_holiday and not is_weekend:
                    db.session.add(AttendanceRecord(
                        employee_id=emp.id,
                        date=current_date,
                        status='absent',
                        check_in=None,
                        check_out=None,
                        work_hours=0,
                        break_duration=0,
                        is_holiday=False,
                        is_weekend=False
                    ))
                    records_created += 1
                current_date += timedelta(days=1)

        db.session.commit()

    print(f"DEBUG - Finished processing. Created {records_created} records, processed {logs_processed} logs")
    return records_created, logs_processed




def check_holiday_and_weekend(employee_id, date_obj):
    """
    Check if a given date is a holiday or weekend for a specific employee
    Returns tuple: (is_holiday, is_weekend)
    """
    # Check if it's a holiday
    is_holiday = False
    
    # Check for employee-specific holiday
    holiday = Holiday.query.filter(
        Holiday.date == date_obj,
        Holiday.employee_id == employee_id
    ).first()
    
    if holiday:
        is_holiday = True
    else:
        # Check for general holiday (non-employee-specific)
        general_holiday = Holiday.query.filter(
            Holiday.date == date_obj,
            Holiday.is_employee_specific == False
        ).first()
        
        if general_holiday:
            is_holiday = True
            
        # Check for recurring holiday (like New Year's Day every year)
        recurring_holiday = Holiday.query.filter(
            func.extract('month', Holiday.date) == date_obj.month,
            func.extract('day', Holiday.date) == date_obj.day,
            Holiday.is_recurring == True,
            or_(
                Holiday.is_employee_specific == False,
                Holiday.employee_id == employee_id
            )
        ).first()
        
        if recurring_holiday:
            is_holiday = True
    
    # Check if it's a weekend based on the employee's configuration
    employee = Employee.query.get(employee_id)
    is_weekend = False
    
    if employee:
        # Use the employee's weekend days (this automatically follows the priority logic)
        weekend_days = employee.get_weekend_days(date_obj)
        
        # Debug logging to help diagnose weekend detection issues
        print(f"DEBUG - Employee {employee_id}, date {date_obj}, weekday {date_obj.weekday()}, weekend_days {weekend_days}")
        
        # Check if the date's weekday is in the employee's weekend days
        is_weekend = date_obj.weekday() in weekend_days
        
        # Extra verification - Sunday is weekday 6
        if date_obj.weekday() == 6 and 6 in weekend_days:
            is_weekend = True
    
    return is_holiday, is_weekend

def get_processing_stats():
    """Get stats about processed and unprocessed logs"""
    total_logs = AttendanceLog.query.count()
    processed_logs = AttendanceLog.query.filter(AttendanceLog.is_processed == True).count()
    unprocessed_logs = AttendanceLog.query.filter(AttendanceLog.is_processed == False).count()
    
    total_records = AttendanceRecord.query.count()
    
    # Count records by shift type
    day_shifts = AttendanceRecord.query.filter(AttendanceRecord.shift_type == 'day').count()
    afternoon_shifts = AttendanceRecord.query.filter(AttendanceRecord.shift_type == 'afternoon').count()
    night_shifts = AttendanceRecord.query.filter(AttendanceRecord.shift_type == 'night').count()
    
    # Count records with overtime
    overtime_records = AttendanceRecord.query.filter(AttendanceRecord.overtime_hours > 0).count()
    
    # Count records with excessive breaks (over 1.5 hours)
    excessive_breaks = AttendanceRecord.query.filter(AttendanceRecord.break_duration > 1.5).count()
    
    return {
        'total_logs': total_logs,
        'processed_logs': processed_logs,
        'unprocessed_logs': unprocessed_logs,
        'total_records': total_records,
        'day_shifts': day_shifts,
        'afternoon_shifts': afternoon_shifts, 
        'night_shifts': night_shifts,
        'overtime_records': overtime_records,
        'excessive_breaks': excessive_breaks
    }