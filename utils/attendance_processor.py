"""
Utility functions for processing attendance logs and records
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_

from models import AttendanceLog, AttendanceRecord, Employee, db, Holiday


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
        return 0, None, None
        
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
        return total_break_time, None, None
    
    # Find the most appropriate break using our sophisticated algorithm
    # First check if we have any breaks detected
    if not detected_breaks:
        print(f"DEBUG - No out-in sequences detected for breaks")
        return 0, None, None
    
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
    return round(total_break_time, 2), break_start, break_end


def process_unprocessed_logs(limit=None):
    """
    Process all unprocessed attendance logs with support for overnight shifts
    
    Returns tuple: (records_created, logs_processed)
    """
    from utils.overtime_engine import calculate_overtime
    
    print(f"DEBUG - Starting process_unprocessed_logs with limit={limit}")
    
    # Get distinct employee-date combinations from unprocessed logs
    unprocessed_combinations = db.session.query(
        AttendanceLog.employee_id, 
        func.date(AttendanceLog.timestamp).label('log_date')
    ).filter(
        AttendanceLog.is_processed == False
    ).distinct().order_by(
        AttendanceLog.employee_id, 
        func.date(AttendanceLog.timestamp)
    )
    
    if limit:
        unprocessed_combinations = unprocessed_combinations.limit(limit)
        
    records_created = 0
    logs_processed = 0
    
    # Get all combinations for debugging
    all_combinations = list(unprocessed_combinations)
    print(f"DEBUG - Found {len(all_combinations)} unprocessed employee-date combinations")
    for emp_id, log_date in all_combinations:
        print(f"DEBUG - Will process employee {emp_id} on date {log_date}")
    
    # Process each employee-date combination
    for emp_id, log_date in all_combinations:
        print(f"DEBUG - Processing employee {emp_id} on date {log_date}")
        
        # First, check if this is the start of an overnight shift
        # This means we need to look for logs on the next day as well
        next_day = log_date + timedelta(days=1)
        is_overnight = False
        
        # Fetch logs from the current day
        current_day_logs = AttendanceLog.query.filter(
            AttendanceLog.employee_id == emp_id,
            func.date(AttendanceLog.timestamp) == log_date
        ).order_by(AttendanceLog.timestamp).all()
        
        # Check if this could be the start of an overnight shift
        # This is likely if the last log of the day is a check-in (IN) and no check-out (OUT)
        if current_day_logs and current_day_logs[-1].log_type in ['IN', 'check_in']:
            print(f"DEBUG - Last log of day {log_date} is a check-in, checking for overnight shift")
            
            # Fetch any logs from the next day
            next_day_logs = AttendanceLog.query.filter(
                AttendanceLog.employee_id == emp_id,
                func.date(AttendanceLog.timestamp) == next_day
            ).order_by(AttendanceLog.timestamp).all()
            
            # If there are logs on the next day and the first one is a check-out,
            # this confirms an overnight shift
            if next_day_logs and next_day_logs[0].log_type in ['OUT', 'check_out']:
                is_overnight = True
                print(f"DEBUG - Detected overnight shift for employee {emp_id} from {log_date} to {next_day}")
                
                # Combine logs from both days for processing
                logs = current_day_logs + next_day_logs
            else:
                logs = current_day_logs
        else:
            # Also check if this is the end of an overnight shift that started the previous day
            # In that case, we want to skip processing as it will be handled with the previous day
            prev_day = log_date - timedelta(days=1)
            prev_day_record = AttendanceRecord.query.filter(
                AttendanceRecord.employee_id == emp_id,
                AttendanceRecord.date == prev_day
            ).filter(
                AttendanceRecord.check_out == None
            ).first()
            
            if prev_day_record and current_day_logs and current_day_logs[0].log_type in ['OUT', 'check_out']:
                print(f"DEBUG - This appears to be the end of an overnight shift from {prev_day}, skipping")
                # Process these logs with the previous day's records
                for log in current_day_logs:
                    if not log.is_processed:
                        log.is_processed = True
                        log.attendance_record_id = prev_day_record.id
                        logs_processed += 1
                        
                # Update the previous day's record with the check-out time
                prev_day_record.check_out = current_day_logs[0].timestamp
                # Recalculate duration and work hours
                prev_day_record.total_duration = calculate_total_duration(prev_day_record.check_in, prev_day_record.check_out)
                prev_day_record.work_hours = max(0, prev_day_record.total_duration - (prev_day_record.break_duration or 0))
                
                # Save changes and recalculate overtime
                db.session.commit()
                try:
                    calculate_overtime(prev_day_record, recalculate=True)
                    db.session.commit()
                except Exception as e:
                    print(f"ERROR - Error calculating overtime for overnight record {prev_day_record.id}: {str(e)}")
                    
                # Skip further processing for this day
                continue
            else:
                logs = current_day_logs
        
        # Filter to only unprocessed logs for actual processing
        unprocessed_logs = [log for log in logs if not log.is_processed]
        
        print(f"DEBUG - Found {len(logs)} total logs, {len(unprocessed_logs)} unprocessed")
        
        if not unprocessed_logs:
            print(f"DEBUG - No unprocessed logs for employee {emp_id} on {log_date}, skipping")
            continue
            
        # Determine check-in and check-out times from logs
        if logs:
            # First log should be check-in
            check_in_logs = [log for log in logs if log.log_type in ['IN', 'check_in']]
            check_out_logs = [log for log in logs if log.log_type in ['OUT', 'check_out']]
            
            check_in = check_in_logs[0].timestamp if check_in_logs else None
            check_out = check_out_logs[-1].timestamp if check_out_logs else None
        else:
            check_in = None
            check_out = None
        
        # Skip if we don't have both check-in and check-out
        if not check_in or not check_out:
            print(f"DEBUG - Missing check-in ({check_in}) or check-out ({check_out}) for employee {emp_id}")
            continue
            
        if check_in == check_out:
            print(f"DEBUG - Invalid check-in/check-out times (same value) for employee {emp_id}: {check_in}")
            continue
            
        # Calculate work metrics including actual break times
        # Use all logs (processed and unprocessed) for better break detection
        break_duration, break_start, break_end = estimate_break_duration(logs)
        shift_type = determine_shift_type(check_in, emp_id)  # Use improved shift detection with employee ID
        total_duration = calculate_total_duration(check_in, check_out)
        
        print(f"DEBUG - Work metrics: break_duration={break_duration}, break_start={break_start}, break_end={break_end}")
        print(f"DEBUG - Work metrics: shift_type={shift_type}, total_duration={total_duration}")
        
        # Get or create attendance record
        record = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == emp_id,
            AttendanceRecord.date == log_date
        ).first()
        
        if not record:
            print(f"DEBUG - Creating new attendance record for employee {emp_id} on {log_date}")
            record = AttendanceRecord()
            record.employee_id = emp_id
            record.date = log_date
            records_created += 1
        else:
            print(f"DEBUG - Updating existing record {record.id} for employee {emp_id} on {log_date}")
            
        # Check if the date is a holiday or weekend
        is_holiday, is_weekend = check_holiday_and_weekend(emp_id, log_date)
        
        # Update record with new data
        record.check_in = check_in
        record.check_out = check_out
        record.status = 'present'
        record.break_duration = break_duration
        record.break_start = break_start
        record.break_end = break_end
        record.shift_type = shift_type
        record.total_duration = total_duration
        record.is_holiday = is_holiday
        record.is_weekend = is_weekend
        
        # Save a flag to indicate that break_duration has been explicitly calculated
        # from multiple breaks and should not be recalculated from break_start/break_end
        record.break_calculated = True
        
        # Get the employee
        employee = Employee.query.get(emp_id)
        if employee and employee.current_shift_id:
            # Assign the employee's current shift
            record.shift_id = employee.current_shift_id
        
        # Calculate work hours (total duration minus breaks)
        work_hours = max(0, total_duration - break_duration)
        record.work_hours = work_hours
        
        print(f"DEBUG - Final record values: work_hours={work_hours}, is_holiday={is_holiday}, is_weekend={is_weekend}")
        print(f"DEBUG - Break times: duration={break_duration}, start={break_start}, end={break_end}")
        
        # Save the record to get an ID for association
        db.session.add(record)
        db.session.flush()  # Make sure record has an ID
                
        # Mark logs as processed
        for log in unprocessed_logs:
            log.is_processed = True
            log.attendance_record_id = record.id
            logs_processed += 1
        
        try:
            # Save changes
            db.session.commit()
            print(f"DEBUG - Successfully saved record {record.id}")
            
            # Now use the proper overtime calculation engine
            # This ensures we're using the full rule-based system
            try:
                calculate_overtime(record, recalculate=True)
            except Exception as e:
                print(f"ERROR - Error calculating overtime for record {record.id}: {str(e)}")
                logging.error(f"Error calculating overtime for record {record.id}: {str(e)}")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR - Database error while processing logs: {str(e)}")
            logging.error(f"Database error while processing logs: {str(e)}")

        print("DEBUG - Checking for missing dates to mark as absent (ignoring holidays/weekends)...")

        for emp in Employee.query.all():
            logs = AttendanceLog.query.filter_by(employee_id=emp.id).all()

            if not logs:
                continue
            log_dates = sorted(set(log.timestamp.date() for log in logs))

            if not log_dates:
                continue
            start_date = min(log_dates)
            end_date = max(log_dates)
            current_date = start_date


            while current_date <= end_date:
                    attendance_exists = AttendanceRecord.query.filter_by(
                                employee_id = emp.id,
                            date = current_date
                                                ).first()

                    is_holiday, is_weekend = check_holiday_and_weekend(emp.id, current_date)


                    if not attendance_exists and not is_holiday and not is_weekend:
                        print(f"DEBUG - Marking absent for employee {emp.id} on {current_date}")
                        absent_record = AttendanceRecord(
                                employee_id = emp.id,
                            date = current_date,
                            status = 'absent',
                            check_in = None,
                            check_out = None,
                            work_hours = 0,
                            break_duration = 0,
                            is_holiday = False,
                            is_weekend = False
                                                          )
                        db.session.add(absent_record)
                        records_created += 1
                    current_date += timedelta(days=1)
    
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