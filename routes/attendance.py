from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file, Response, make_response
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import extract, func
from sqlalchemy.orm import joinedload
import csv
import io
from io import StringIO, BytesIO
import re
from werkzeug.utils import secure_filename
from app import db
from models import Employee, AttendanceRecord, AttendanceLog, AttendanceDevice, Holiday, SystemConfig, ShiftAssignment, Department, Shift,MissingAttendance
from utils.attendance_processor import process_unprocessed_logs, get_processing_stats, check_holiday_and_weekend,calculate_total_duration,estimate_break_duration,determine_shift_type
import xmlrpc.client
# Create blueprint
bp = Blueprint('attendance', __name__, url_prefix='/attendance')

@bp.route('/download_sample_csv')
@login_required
def download_sample_csv():
    """Download a sample CSV file for attendance import"""
    # Get format parameter
    format_type = request.args.get('format', 'zkteco')
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_date_dashed = datetime.now().strftime("%d-%m-%y")
    current_time = datetime.now().strftime("%H:%M:%S")
    
    # Create a CSV in memory
    csv_buffer = StringIO()
    csv_writer = csv.writer(csv_buffer)
    
    if format_type == 'mir':
        # MIR Event Viewer format
        csv_writer.writerow(["Event Viewer Report", "Business Unit:", "MIR-Plastic Industries LLC", "Location:", "MIRDXB", "Department:", "Cleaner/Misc"])
        csv_writer.writerow(["Section:", "Cleaner/Misc", "Employee ID:", "129", "Report Period:", f" {current_date_dashed} To :{current_date_dashed}", "Employee Name:", "KHAMIS"])
        csv_writer.writerow(["Date", "Day", "Terminal ID", "Terminal Name", "Event", "Punch"])
        csv_writer.writerow([current_date_dashed, "Monday", "2", "DXB Attendance", "IN", f"{current_date_dashed}  08:23 am"])
        csv_writer.writerow([current_date_dashed, "Monday", "2", "DXB Attendance", "OUT", f"{current_date_dashed}  09:43 pm"])
        csv_writer.writerow([current_date_dashed, "Monday", "2", "DXB Attendance", "IN", f"{current_date_dashed}  08:06 am"])
        csv_writer.writerow([current_date_dashed, "Monday", "2", "DXB Attendance", "OUT", f"{current_date_dashed}  03:42 pm"])
        
    elif format_type == 'hikvision':
        # Hikvision format
        csv_writer.writerow(["Serial No.", "First Name", "Last Name", "Department", "Employee ID", "Device Name", "Direction", "Verification Method", "Time"])
        csv_writer.writerow(["1", "John", "Smith", "Engineering", "101", "Main Entrance", "Entry", "Face", f"{current_date} 08:05:00"])
        csv_writer.writerow(["2", "John", "Smith", "Engineering", "101", "Main Entrance", "Exit", "Face", f"{current_date} 17:02:00"])
        csv_writer.writerow(["3", "Jane", "Doe", "Marketing", "102", "Main Entrance", "Entry", "Face", f"{current_date} 07:55:00"])
        csv_writer.writerow(["4", "Jane", "Doe", "Marketing", "102", "Main Entrance", "Exit", "Face", f"{current_date} 17:00:00"])
        
    else:
        # ZKTeco standard format (default)
        csv_writer.writerow(["User ID", "Name", "Time", "Status", "Terminal", "Verification Type"])
        
        # Add sample data rows
        csv_writer.writerow(["101", "John Smith", f"{current_date} 08:05:00", "Check In", "Main Entrance", "Face"])
        csv_writer.writerow(["101", "John Smith", f"{current_date} 12:00:00", "Break Out", "Main Entrance", "Face"])
        csv_writer.writerow(["101", "John Smith", f"{current_date} 13:00:00", "Break In", "Main Entrance", "Face"])
        csv_writer.writerow(["101", "John Smith", f"{current_date} 17:02:00", "Check Out", "Main Entrance", "Face"])
        
        csv_writer.writerow(["102", "Jane Doe", f"{current_date} 07:55:00", "Check In", "Main Entrance", "Face"])
        csv_writer.writerow(["102", "Jane Doe", f"{current_date} 12:05:00", "Break Out", "Main Entrance", "Face"])
        csv_writer.writerow(["102", "Jane Doe", f"{current_date} 12:55:00", "Break In", "Main Entrance", "Face"])
        csv_writer.writerow(["102", "Jane Doe", f"{current_date} 17:00:00", "Check Out", "Main Entrance", "Face"])
    
    # Reset the buffer position to the beginning
    csv_buffer.seek(0)
    
    # Create a response with the CSV data
    filename = f"sample_{format_type}_attendance.csv"
    response = make_response(csv_buffer.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-type"] = "text/csv"
    
    return response

@bp.route('/')
@login_required
def index():
    """Attendance dashboard"""
    today = date.today()
    
    # Get today's attendance records
    records = AttendanceRecord.query.filter_by(date=today).all()
    
    # Calculate statistics
    total_employees = Employee.query.filter_by(is_active=True).count()
    present_count = sum(1 for r in records if r.status == 'present')
    absent_count = sum(1 for r in records if r.status == 'absent')
    late_count = sum(1 for r in records if r.status == 'late')
    pending_count = sum(1 for r in records if r.status == 'pending')
    
    # Get missing punches count for notification badge
    missing_punches_count = db.session.query(AttendanceRecord)\
        .filter((AttendanceRecord.check_in.is_(None) | AttendanceRecord.check_out.is_(None)))\
        .filter(AttendanceRecord.date >= today - timedelta(days=7))\
        .filter(AttendanceRecord.status != 'absent')\
        .count()
    
    return render_template('attendance/index.html',
                          date=today,
                          records=records,
                          total_employees=total_employees,
                          present_count=present_count,
                          absent_count=absent_count,
                          late_count=late_count,
                          pending_count=pending_count,
                          missing_punches_count=missing_punches_count)

@bp.route('/daily')
@login_required
def daily():
    """Daily attendance view with support for filtering by shift type"""
    selected_date = request.args.get('date', date.today().isoformat())
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    

    if current_user.has_role('supervisor') and not current_user.is_admin and not current_user.has_role('hr'):
        user_department = current_user.department
        
        department = user_department
    else:
        department = request.args.get('department', 'all')

        # Supervisor: restrict employees & departments


    
    # Get attendance records for the selected date
    query = AttendanceRecord.query.filter_by(date=selected_date)
    
    # Apply department filter if specified
    if department != 'all':
        query = query.join(Employee).filter(Employee.department == department)
    
    # Apply shift type filter if specified
    shift_type = request.args.get('shift_type', 'all')
    if shift_type == 'day':
        # Day shift: typically check-in between 6:00 AM and 12:00 PM
        query = query.filter(
            AttendanceRecord.check_in.isnot(None),
            extract('hour', AttendanceRecord.check_in) >= 6,
            extract('hour', AttendanceRecord.check_in) < 12
        )
    elif shift_type == 'night':
        # Night shift: typically check-in between 6:00 PM and 12:00 AM
        query = query.filter(
            AttendanceRecord.check_in.isnot(None),
            extract('hour', AttendanceRecord.check_in) >= 18
        )
    
    records = query.all()
    
    # Get unique departments for filter
    if current_user.has_role('supervisor') and not current_user.is_admin and not current_user.has_role('hr'):
        user_department = current_user.department
        # all_employees = [e for e in all_employees if e.department == user_department]
        departments = [user_department]
        # selected_department = user_department
    else:
        # departments = sorted(list({e.department for e in all_employees if e.department}))
        # selected_department = request.args.get('department', '')
        departments = db.session.query(Employee.department).distinct().all()
        departments = [d[0] for d in departments if d[0]]
    
    # Define day_delta for template's previous/next day buttons
    day_delta = timedelta(days=1)
    
    return render_template('attendance/daily.html',
                          selected_date=selected_date,
                          day_delta=day_delta,
                          records=records,
                          departments=departments,
                          selected_department=department)

@bp.route('/send_absent_to_odoo', methods=['POST'])
def send_absent_to_odoo():
        data = request.get_json()
        employee_ids = data.get('employee_ids', [])

        URL = 'http://sib.mir.ae:8050'
        DB = 'july_04'
        USER = 'admin'
        PASSWORD = '123'

        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USER, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        for employee_id in employee_ids:
            absent_records = AttendanceRecord.query.filter(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.status == 'absent',
            ).order_by(AttendanceRecord.date).all()

            print(f"📋 Total absent records found: {len(absent_records)}")

            for record in absent_records:
                employee = Employee.query.filter_by(id=record.employee_id).first()
                if not employee or not employee.odoo_id:
                    print(f"❌ Skipping: No Odoo ID for employee_id {record.employee_id}")
                    continue

                odoo_employee_id = employee.odoo_id
                leave_date_str = str(record.date)

                result = models.execute_kw(
                    DB, uid, PASSWORD,
                    'hr.holidays', 'create_unpaid_leave_if_not_exists',
                    [odoo_employee_id, leave_date_str]
                )

                print(f"📅 {leave_date_str} → {result.get('status')}: {result.get('message', result.get('reason'))}")

        return jsonify({'message': 'All absent records processed Successfully.'}), 200

@bp.route('/employee/<int:employee_id>')
@login_required
def employee_attendance(employee_id):
    """View attendance records for a specific employee"""
    employee = Employee.query.get_or_404(employee_id)
    
    # Get date range from query parameters, default to current month
    today = date.today()
    # Support both parameter naming styles (date_from/date_to and start_date/end_date)
    start_date = request.args.get('date_from') or request.args.get('start_date') or date(today.year, today.month, 1).isoformat()
    end_date = request.args.get('date_to') or request.args.get('end_date') or today.isoformat()
    
    # Get status filter if provided
    status = request.args.get('status')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = date(today.year, today.month, 1)
        end_date = today
    
    # Build the query for attendance records
    query = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= start_date,
        AttendanceRecord.date <= end_date
    )
    
    # Apply status filter if provided
    if status:
        query = query.filter(AttendanceRecord.status == status)
    
    # Get the records
    records = query.order_by(AttendanceRecord.date.desc()).all()
    
    # Use actual break times or calculate them if not set
    for record in records:
        if record.break_start and record.break_end:
            # Use actual break times if they exist in the record
            record.break_start_time = record.break_start
            record.break_end_time = record.break_end
        elif record.check_in and record.check_out and record.break_duration > 0:
            # Calculate work period duration in hours
            work_period = (record.check_out - record.check_in).total_seconds() / 3600
            
            # Set default break start time at midpoint of work period
            midpoint = record.check_in + timedelta(hours=work_period / 2)
            
            # Adjust break start to be in the middle of the work period
            # minus half the break duration
            # break_start = midpoint - timedelta(hours=record.break_duration / 2)
            #
            # # Break end time is break start plus break duration
            # break_end = break_start + timedelta(hours=record.break_duration)
            
            # Store these times in the record object for use in the template
            # record.break_start_time = break_start
            # record.break_end_time = break_end
        else:
            record.break_start_time = None
            record.break_end_time = None
    
    # Calculate statistics
    from utils.helpers import get_attendance_stats
    stats = get_attendance_stats(employee_id, start_date, end_date)
    
    return render_template('attendance/employee.html',
                          employee=employee,
                          records=records,
                          start_date=start_date,
                          end_date=end_date,
                          status=status,
                          stats=stats)

@bp.route('/manual_entry', methods=['GET', 'POST'])
@login_required
def manual_entry():
    """Manually enter attendance data"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Default selected values for the form
    selected_employee = None
    selected_date = date.today()
    
    if request.method == 'POST':
        try:
            employee_id = request.form.get('employee_id')
            entry_date = request.form.get('date')
            check_in = request.form.get('check_in')
            check_out = request.form.get('check_out')
            break_start = request.form.get('break_start')
            break_end = request.form.get('break_end') 
            break_duration_str = request.form.get('break_duration', '1')
            status = request.form.get('status')
            notes = request.form.get('notes')
            mark_weekend  = request.form.get('mark_weekend')
            
            # Convert break duration to float, default to 1 hour
            try:
                break_duration = float(break_duration_str)
            except (ValueError, TypeError):
                break_duration = 1.0
            
            # Save these for form repopulation in case of error
            selected_employee = employee_id
            
            # Validate input
            if not employee_id or not entry_date:
                flash('Employee and date are required', 'danger')
                return redirect(url_for('attendance.manual_entry'))
            
            # Parse date and times
            try:
                entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()
                selected_date = entry_date
                
                check_in_time = None
                if check_in:
                    check_in_time = datetime.strptime(f"{entry_date.isoformat()} {check_in}", '%Y-%m-%d %H:%M')
                    
                check_out_time = None
                if check_out:
                    check_out_time = datetime.strptime(f"{entry_date.isoformat()} {check_out}", '%Y-%m-%d %H:%M')
                    
                    # Handle overnight shifts
                    if check_out_time and check_in_time and check_out_time < check_in_time:
                        check_out_time += timedelta(days=1)
                
                # Parse break start and end times
                break_start_time = None
                if break_start:
                    break_start_time = datetime.strptime(f"{entry_date.isoformat()} {break_start}", '%Y-%m-%d %H:%M')
                    # Ensure break start is within the work period
                    if check_in_time and break_start_time < check_in_time:
                        break_start_time = break_start_time + timedelta(days=1)
                
                break_end_time = None
                if break_end:
                    break_end_time = datetime.strptime(f"{entry_date.isoformat()} {break_end}", '%Y-%m-%d %H:%M')
                    # Ensure break end is after break start
                    if break_start_time and break_end_time < break_start_time:
                        break_end_time = break_end_time + timedelta(days=1)
                
                # Calculate break duration from actual times if provided
                if break_start_time and break_end_time:
                    break_duration = (break_end_time - break_start_time).total_seconds() / 3600
            except ValueError as e:
                flash(f'Invalid date or time format: {str(e)}', 'danger')
                employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
                return render_template('attendance/manual_entry.html', 
                                      employees=employees, 
                                      today=date.today(),
                                      selected_employee_id=selected_employee,
                                      form_data=request.form)
            
            # Check if record exists for this date and employee
            record = AttendanceRecord.query.filter_by(
                employee_id=employee_id,
                date=entry_date
            ).first()
            
            if record:
                # Update existing record
                record.check_in = check_in_time
                record.check_out = check_out_time
                record.status = status
                record.notes = notes
                record.break_duration = break_duration
                record.break_start = break_start_time
                record.break_end = break_end_time
                record.is_weekend = True if mark_weekend else False
                
                # Calculate work hours if both check-in and check-out are provided
                if check_in_time and check_out_time:
                    from utils.helpers import calculate_work_hours
                    record.work_hours = calculate_work_hours(
                        check_in_time, 
                        check_out_time, 
                        record.break_duration if record.break_duration else 0
                    )
                
                db.session.commit()
                flash('Attendance record updated successfully', 'success')
                
            else:
                # Create new record
                record = AttendanceRecord(
                    employee_id=employee_id,
                    date=entry_date,
                    check_in=check_in_time,
                    check_out=check_out_time,
                    status=status,
                    notes=notes,
                    break_duration=break_duration,
                    break_start=break_start_time,
                    break_end=break_end_time,
                    is_weekend=True if mark_weekend else False
                )
                
                # Get employee and set shift_id and shift_type
                employee = Employee.query.get(employee_id)
                if employee and employee.current_shift_id:
                    record.shift_id = employee.current_shift_id
                    
                    # Set shift_type based on the employee's shift
                    shift = Shift.query.get(employee.current_shift_id)
                    if shift:
                        if 'night' in shift.name.lower():
                            record.shift_type = 'night'
                        elif 'day' in shift.name.lower():
                            record.shift_type = 'day'
                        # Otherwise, let it be determined by the time
                
                # Calculate work hours if both check-in and check-out are provided
                if check_in_time and check_out_time:
                    from utils.helpers import calculate_work_hours
                    record.work_hours = calculate_work_hours(
                        check_in_time, 
                        check_out_time, 
                        break_duration
                    )
                
                db.session.add(record)
                db.session.commit()
                flash('Attendance record created successfully', 'success')
            
            # Redirect to employee attendance view
            return redirect(url_for('attendance.employee_attendance', employee_id=employee_id))
        
        except Exception as e:
            # Catch any unexpected errors and log them
            import traceback
            traceback.print_exc()
            flash(f'Error processing attendance: {str(e)}', 'danger')
    
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    return render_template('attendance/manual_entry.html', 
                          employees=employees, 
                          today=date.today(),
                          selected_employee_id=selected_employee,
                          selected_date=selected_date)

@bp.route('/batch_entry', methods=['GET', 'POST'])
@login_required
def batch_entry():
    """Batch attendance entry for multiple employees at once with support for multiple days"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Get all active employees
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # Get unique departments
    departments = db.session.query(Employee.department).filter(
        Employee.department != None,
        Employee.department != ''
    ).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    
    if request.method == 'POST':
        try:
            # Get the date range for entries
            date_range_start = datetime.strptime(request.form.get('date_range_start'), '%Y-%m-%d').date()
            date_range_end_str = request.form.get('date_range_end')
            
            # If end date is blank, use start date (single day)
            if not date_range_end_str:
                date_range_end = date_range_start
            else:
                date_range_end = datetime.strptime(date_range_end_str, '%Y-%m-%d').date()
            
            # Validate date range
            if date_range_end < date_range_start:
                flash('End date cannot be before start date', 'danger')
                return redirect(url_for('attendance.batch_entry'))
            
            # Get all selected employees
            selected_employees = request.form.getlist('selected_employees')
            
            # Get log types configuration
            log_types = request.form.getlist('log_types[]')
            default_times = request.form.getlist('default_times[]')
            # Note: apply_days is a list of lists - each entry might have multiple days
            # We'll handle this in the processing loop
            
            # Counter for successful entries
            success_count = 0
            days_processed = 0
            
            # Calculate date range
            current_date = date_range_start
            all_dates = []
            while current_date <= date_range_end:
                all_dates.append(current_date)
                current_date += timedelta(days=1)
            
            days_processed = len(all_dates)
            
            # Process each selected employee
            for employee_id in selected_employees:
                # Get the employee-specific form fields
                check_in = request.form.get(f'check_in_{employee_id}')
                check_out = request.form.get(f'check_out_{employee_id}')
                break_start = request.form.get(f'break_start_{employee_id}')
                break_end = request.form.get(f'break_end_{employee_id}')
                
                # Log the exact input values received from the form
                current_app.logger.debug(f"DEBUG: Received form values for employee {employee_id}:")
                current_app.logger.debug(f"  check_in: '{check_in}'")
                current_app.logger.debug(f"  check_out: '{check_out}'")
                current_app.logger.debug(f"  break_start: '{break_start}'")
                current_app.logger.debug(f"  break_end: '{break_end}'")
                break_duration_str = request.form.get(f'break_duration_{employee_id}', '1')
                status = request.form.get(f'status_{employee_id}')
                notes = request.form.get(f'notes_{employee_id}')
                
                # Debug log the raw time inputs
                current_app.logger.debug(f"FORM INPUT for employee {employee_id}: check_in={check_in}, check_out={check_out}, break_start={break_start}, break_end={break_end}")
                
                # Convert break duration to float, default to 1 hour
                try:
                    break_duration = float(break_duration_str)
                except (ValueError, TypeError):
                    break_duration = 1.0
                
                # Skip if no meaningful data provided
                if not (check_in or check_out or status):
                    continue
                
                # Process each date in the range
                for entry_date in all_dates:
                    # Convert time strings to datetime objects if provided
                    check_in_time = None
                    if check_in:
                        try:
                            # For HTML time inputs (HH:MM format)
                            check_in_time = datetime.combine(entry_date, datetime.strptime(check_in, '%H:%M').time())
                        except ValueError:
                            # For more flexible time inputs (support HH:MM:SS and AM/PM formats)
                            try:
                                check_in_time = datetime.combine(entry_date, datetime.strptime(check_in, '%I:%M %p').time())
                            except ValueError:
                                current_app.logger.error(f"Could not parse check-in time: {check_in}")
                                flash(f'Invalid check-in time format: {check_in}', 'warning')
                    
                    # Debug log the parsed check-in time
                    current_app.logger.debug(f"PARSED check_in_time for employee {employee_id}: {check_in_time}")
                    
                    check_out_time = None
                    if check_out:
                        try:
                            # For HTML time inputs (HH:MM format)
                            check_out_time = datetime.combine(entry_date, datetime.strptime(check_out, '%H:%M').time())
                        except ValueError:
                            # For more flexible time inputs (support HH:MM:SS and AM/PM formats)
                            try:
                                check_out_time = datetime.combine(entry_date, datetime.strptime(check_out, '%I:%M %p').time())
                            except ValueError:
                                current_app.logger.error(f"Could not parse check-out time: {check_out}")
                                flash(f'Invalid check-out time format: {check_out}', 'warning')
                    
                    # Debug log the parsed check-out time
                    current_app.logger.debug(f"PARSED check_out_time for employee {employee_id}: {check_out_time}")
                    
                    # Handle overnight shifts
                    if check_in_time and check_out_time and check_out_time < check_in_time:
                        check_out_time += timedelta(days=1)
                    
                    # Process break start and end times if provided
                    break_start_time = None
                    if break_start:
                        try:
                            # For HTML time inputs (HH:MM format)
                            break_start_time = datetime.combine(entry_date, datetime.strptime(break_start, '%H:%M').time())
                        except ValueError:
                            # Try alternative time format if the standard one doesn't work
                            try:
                                break_start_time = datetime.combine(entry_date, datetime.strptime(break_start, '%I:%M %p').time())
                            except ValueError:
                                current_app.logger.error(f"Could not parse break start time: {break_start}")
                                flash(f'Invalid break start time format: {break_start}. Using default.', 'warning')
                    
                    break_end_time = None
                    if break_end:
                        try:
                            # For HTML time inputs (HH:MM format)
                            break_end_time = datetime.combine(entry_date, datetime.strptime(break_end, '%H:%M').time())
                        except ValueError:
                            # Try alternative time format if the standard one doesn't work
                            try:
                                break_end_time = datetime.combine(entry_date, datetime.strptime(break_end, '%I:%M %p').time())
                            except ValueError:
                                current_app.logger.error(f"Could not parse break end time: {break_end}")
                                flash(f'Invalid break end time format: {break_end}. Using default.', 'warning')
                        
                        # Handle overnight breaks
                        if break_start_time and break_end_time < break_start_time:
                            break_end_time += timedelta(days=1)
                    
                    # Check if a record already exists for this employee and date
                    existing_record = AttendanceRecord.query.filter_by(
                        employee_id=employee_id,
                        date=entry_date
                    ).first()
                    
                    if existing_record:
                        # Update existing record - ALWAYS prioritize submitted values
                        # MODIFIED: Always update time fields when a value is submitted (check_in is not None)
                        # instead of only updating when check_in_time has a value
                        if check_in is not None:
                            existing_record.check_in = check_in_time
                        if check_out is not None:
                            existing_record.check_out = check_out_time
                        if status:
                            existing_record.status = status
                        if notes:
                            existing_record.notes = notes
                        
                        # Update break times and duration
                        existing_record.break_duration = break_duration
                        
                        # If break start and end times are provided, use them and set the break_calculated flag
                        # MODIFIED: Update break times whenever they are submitted (not None)
                        if break_start is not None:
                            existing_record.break_start = break_start_time
                        if break_end is not None:
                            existing_record.break_end = break_end_time
                            
                        # Only calculate break duration if both times are available
                        if existing_record.break_start and existing_record.break_end:
                            existing_record.break_calculated = True
                            actual_break_duration = (existing_record.break_end - existing_record.break_start).total_seconds() / 3600
                            existing_record.break_duration = actual_break_duration
                        
                        # Calculate work hours if both check-in and check-out are provided
                        if existing_record.check_in and existing_record.check_out:
                            from utils.helpers import calculate_work_hours
                            existing_record.work_hours = calculate_work_hours(
                                existing_record.check_in, 
                                existing_record.check_out, 
                                existing_record.break_duration
                            )
                        else:
                            # If status is present but no check-in/out times, set default values
                            if existing_record.status == 'present':
                                existing_record.work_hours = 8.0  # Default to 8 hours for present
                                
                                # Create default check-in and check-out times - only if not existing
                                if not existing_record.check_in:
                                    # Use exact time if it was submitted, otherwise use default 9AM
                                    if check_in_time:
                                        existing_record.check_in = check_in_time
                                    else:
                                        existing_record.check_in = datetime.combine(entry_date, datetime.min.time().replace(hour=9))
                                if not existing_record.check_out:
                                    # Use exact time if it was submitted, otherwise use default 6PM
                                    if check_out_time:
                                        existing_record.check_out = check_out_time
                                    else:
                                        existing_record.check_out = datetime.combine(entry_date, datetime.min.time().replace(hour=18))
                        
                        # Determine shift type based on check-in time (if available)
                        if existing_record.check_in:
                            check_in_hour = existing_record.check_in.hour
                            if 6 <= check_in_hour < 12:
                                existing_record.shift_type = 'day'
                            elif 12 <= check_in_hour < 18:
                                existing_record.shift_type = 'afternoon'
                            elif 18 <= check_in_hour or check_in_hour < 6:
                                existing_record.shift_type = 'night'
                        else:
                            # Default to day shift if no check-in time
                            existing_record.shift_type = 'day'
                        
                        # Try to get employee's current shift if not already set
                        if not existing_record.shift_id:
                            employee = Employee.query.get(employee_id)
                            if employee and employee.current_shift_id:
                                existing_record.shift_id = employee.current_shift_id
                                
                        # Add debug log to verify the final values being saved
                        if existing_record.check_in:
                            # Format the time part to show hours, minutes, seconds
                            check_in_str = existing_record.check_in.strftime('%H:%M:%S')
                            current_app.logger.debug(f"FINAL check_in time for employee {employee_id}: {check_in_str}")
                        if existing_record.check_out:
                            check_out_str = existing_record.check_out.strftime('%H:%M:%S')
                            current_app.logger.debug(f"FINAL check_out time for employee {employee_id}: {check_out_str}")
                        
                        # Calculate overtime if applicable
                        if existing_record.work_hours > 8.0:
                            from utils.overtime_engine import calculate_overtime
                            calculate_overtime(existing_record, recalculate=True, commit=False)
                        
                        # Check for weekend/holiday status for existing records too
                        if not hasattr(existing_record, 'is_weekend') or not hasattr(existing_record, 'is_holiday') or \
                           (not existing_record.is_weekend and not existing_record.is_holiday):
                            # Get the weekend days for this employee
                            employee = Employee.query.get(employee_id)
                            if employee:
                                # Get the necessary attributes for weekend detection
                                weekend_days = employee.weekend_days
                                current_shift_id = employee.current_shift_id
                                
                                # Check if we need to determine weekend days from shift
                                if not weekend_days and current_shift_id:
                                    shift = Shift.query.get(current_shift_id)
                                    if shift and shift.weekend_days:
                                        weekend_days = shift.weekend_days
                                
                                # Default to system config if neither employee nor shift has weekend days
                                if not weekend_days:
                                    system_config = SystemConfig.query.first()
                                    if system_config and system_config.weekend_days:
                                        weekend_days = system_config.weekend_days
                                
                                # Set weekend flag based on date's day of week
                                day_of_week = entry_date.strftime('%A').lower()
                                
                                # Handle the weekend_days which could be a string, list, or None
                                if isinstance(weekend_days, list):
                                    weekend_day_list = []
                                    for day in weekend_days:
                                        if day:
                                            if isinstance(day, str):
                                                weekend_day_list.append(day.lower())
                                            elif isinstance(day, int):
                                                # Convert day number to name (0=Monday, 6=Sunday)
                                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                                if 0 <= day < 7:
                                                    weekend_day_list.append(day_names[day])
                                elif isinstance(weekend_days, str):
                                    weekend_day_list = weekend_days.lower().split(',')
                                else:
                                    weekend_day_list = ['saturday', 'sunday']  # Default
                                    
                                existing_record.is_weekend = day_of_week in weekend_day_list
                                
                                # Check for holidays
                                holiday = Holiday.query.filter(
                                    Holiday.date == entry_date
                                ).first()
                                existing_record.is_holiday = holiday is not None
                        
                        success_count += 1
                    else:
                        # Create new record
                        new_record = AttendanceRecord(
                            employee_id=employee_id,
                            date=entry_date,
                            check_in=check_in_time,
                            check_out=check_out_time,
                            status=status or 'present',
                            notes=notes,
                            break_duration=break_duration,
                            break_start=break_start_time,
                            break_end=break_end_time,
                            break_calculated=True if break_start_time and break_end_time else False
                        )
                        
                        # Calculate work hours if both check-in and check-out are provided
                        if check_in_time and check_out_time:
                            from utils.helpers import calculate_work_hours
                            
                            # If manual break times were provided, calculate actual break duration
                            if break_start_time and break_end_time:
                                actual_break_duration = (break_end_time - break_start_time).total_seconds() / 3600
                                new_record.break_duration = actual_break_duration
                            
                            new_record.work_hours = calculate_work_hours(
                                check_in_time, 
                                check_out_time, 
                                new_record.break_duration
                            )
                        else:
                            # If no check-in/check-out provided but status is present, set default work hours
                            if status == 'present' or status is None:
                                new_record.work_hours = 8.0  # Default to 8 hours for present
                                
                                # Create check-in and check-out times for the new record
                                # MODIFIED: For new records, always prioritize submitted times
                                # over default values, even if submitted times are empty strings
                                
                                # For check-in, always use submitted time if available, otherwise use default
                                if check_in is not None:
                                    new_record.check_in = check_in_time  # This could be None if empty string submitted
                                else:
                                    # Only use default if no time was submitted at all
                                    new_record.check_in = datetime.combine(entry_date, datetime.min.time().replace(hour=9))
                                    
                                # For check-out, always use submitted time if available, otherwise use default
                                if check_out is not None:
                                    new_record.check_out = check_out_time  # This could be None if empty string submitted
                                else:
                                    # Only use default if no time was submitted at all
                                    new_record.check_out = datetime.combine(entry_date, datetime.min.time().replace(hour=18))
                        
                        # Determine shift type based on check-in time (if available)
                        if new_record.check_in:
                            check_in_hour = new_record.check_in.hour
                            if 6 <= check_in_hour < 12:
                                new_record.shift_type = 'day'
                            elif 12 <= check_in_hour < 18:
                                new_record.shift_type = 'afternoon'
                            elif 18 <= check_in_hour or check_in_hour < 6:
                                new_record.shift_type = 'night'
                        else:
                            # Default to day shift if no check-in time
                            new_record.shift_type = 'day'
                        
                        # Try to get employee's current shift
                        employee = Employee.query.get(employee_id)
                        if employee and employee.current_shift_id:
                            new_record.shift_id = employee.current_shift_id
                            
                        # Add debug log to verify the final values for new records
                        if new_record.check_in:
                            check_in_str = new_record.check_in.strftime('%H:%M:%S')
                            current_app.logger.debug(f"NEW RECORD check_in time for employee {employee_id}: {check_in_str}")
                        if new_record.check_out:
                            check_out_str = new_record.check_out.strftime('%H:%M:%S')
                            current_app.logger.debug(f"NEW RECORD check_out time for employee {employee_id}: {check_out_str}")
                            
                        # Calculate overtime if applicable
                        if new_record.work_hours > 8.0:
                            from utils.overtime_engine import calculate_overtime
                            calculate_overtime(new_record, recalculate=True, commit=False)
                        
                        # Even if no overtime, still check for weekend/holiday status
                        # This ensures proper categorization even for standard hours
                        if not hasattr(new_record, 'is_weekend') or not hasattr(new_record, 'is_holiday') or \
                           (not new_record.is_weekend and not new_record.is_holiday):
                            # Get the weekend days for this employee
                            employee = Employee.query.get(employee_id)
                            if employee:
                                # Instead of passing the whole employee object, get the necessary attributes
                                weekend_days = employee.weekend_days
                                current_shift_id = employee.current_shift_id
                                
                                # Check if we need to determine weekend days from shift
                                if not weekend_days and current_shift_id:
                                    shift = Shift.query.get(current_shift_id)
                                    if shift and shift.weekend_days:
                                        weekend_days = shift.weekend_days
                                
                                # Default to system config if neither employee nor shift has weekend days
                                if not weekend_days:
                                    system_config = SystemConfig.query.first()
                                    if system_config and system_config.weekend_days:
                                        weekend_days = system_config.weekend_days
                                
                                # Set weekend flag based on entry date's day of week
                                day_of_week = entry_date.strftime('%A').lower()
                                
                                # Handle the weekend_days which could be a string, list, or None
                                if isinstance(weekend_days, list):
                                    weekend_day_list = []
                                    for day in weekend_days:
                                        if day:
                                            if isinstance(day, str):
                                                weekend_day_list.append(day.lower())
                                            elif isinstance(day, int):
                                                # Convert day number to name (0=Monday, 6=Sunday)
                                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                                if 0 <= day < 7:
                                                    weekend_day_list.append(day_names[day])
                                elif isinstance(weekend_days, str):
                                    weekend_day_list = weekend_days.lower().split(',')
                                else:
                                    weekend_day_list = ['saturday', 'sunday']  # Default
                                    
                                new_record.is_weekend = day_of_week in weekend_day_list
                                
                                # Check for holidays
                                holiday = Holiday.query.filter(
                                    Holiday.date == entry_date
                                ).first()
                                new_record.is_holiday = holiday is not None
                        
                        db.session.add(new_record)
                        success_count += 1
            
            # Commit all changes
            db.session.commit()
            
            # Add debug message with timestamp to help track changes
            import time
            timestamp = int(time.time())
            flash(f'Debug [{timestamp}]: Time values preserved as submitted instead of rounded.', 'info')
            flash(f'Successfully created/updated {success_count} attendance records over {days_processed} days', 'success')
            return redirect(url_for('attendance.index'))
            
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            flash(f'Error processing batch attendance: {str(e)}', 'danger')
    
    return render_template('attendance/batch_entry.html',
                          employees=employees,
                          departments=departments,
                          today=date.today())

@bp.route('/raw-logs')
@login_required
def raw_logs():
    """View raw attendance logs"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Get filter parameters
    employee_id = request.args.get('employee_id', type=int)
    device_id = request.args.get('device_id', type=int)
    log_type = request.args.get('log_type')
    processed = request.args.get('processed')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Base query
    query = AttendanceLog.query
    
    # Apply filters
    if employee_id:
        query = query.filter(AttendanceLog.employee_id == employee_id)
    if device_id:
        query = query.filter(AttendanceLog.device_id == device_id)
    if log_type:
        query = query.filter(AttendanceLog.log_type == log_type)
    if processed == '1':
        query = query.filter(AttendanceLog.is_processed == True)
    elif processed == '0':
        query = query.filter(AttendanceLog.is_processed == False)
    
    # Date filters
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AttendanceLog.timestamp >= from_date)
        except ValueError:
            flash('Invalid from date format', 'warning')
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            to_date = to_date + timedelta(days=1)  # Include the entire day
            query = query.filter(AttendanceLog.timestamp < to_date)
        except ValueError:
            flash('Invalid to date format', 'warning')
    
    # Finalize query with ordering and pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    
    # Remove page from args if present to avoid conflicts with pagination
    filtered_args = request.args.copy()
    if 'page' in filtered_args:
        filtered_args.pop('page')
    
    try:
        # Get the logs with eager loading of relationships to avoid N+1 queries
        query = query.options(joinedload(AttendanceLog.employee), joinedload(AttendanceLog.device))
        paginated_logs = query.order_by(AttendanceLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    except Exception as e:
        current_app.logger.error(f"Pagination error: {str(e)}")
        flash(f"Error loading page {page}. Showing first page instead.", "warning")
        paginated_logs = query.order_by(AttendanceLog.timestamp.desc()).paginate(
            page=1, per_page=per_page, error_out=False
        )
    
    # Process the logs to ensure all data is safe for the template
    # Create a new class that will hold only the processed data
    class SafeLog:
        def __init__(self, log):
            self.id = log.id
            self.employee_name = log.employee.name if log.employee else '-'
            self.device_name = log.device.name if log.device else '-'
            self.timestamp_str = log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else '-'
            self.log_type = log.log_type
            self.is_processed = log.is_processed
            self.created_at_str = log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '-'
    
    # Create a list of safe logs
    safe_logs = []
    for log in paginated_logs.items:
        try:
            safe_logs.append(SafeLog(log))
        except Exception as e:
            current_app.logger.error(f"Error processing log {log.id}: {str(e)}")
            continue
    
    # Get employees and devices for dropdowns
    employees = Employee.query.order_by(Employee.name).all()
    devices = AttendanceDevice.query.order_by(AttendanceDevice.name).all()
    
    return render_template('attendance/raw_logs_safe.html', 
                          logs=safe_logs,
                          pagination=paginated_logs,
                          employees=employees,
                          devices=devices,
                          filtered_args=filtered_args)

@bp.route('/process_all_logs', methods=['GET', 'POST'])
@login_required
def process_all_logs():
    """Process all unprocessed attendance logs with enhanced analysis"""
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Get processing statistics
    stats = get_processing_stats()
    
    # Default no results
    results = None
    
    # Handle POST request (process logs)
    if request.method == 'POST':
        try:
            # Get date range parameters if provided
            date_from_str = request.form.get('date_from')
            date_to_str = request.form.get('date_to')
            employee_id = request.form.get('employee_id')
            print(employee_id, "employee_id")

           
            
            # Convert date strings to date objects if provided
            date_from = None
            date_to = None
            
            if date_from_str:
                try:
                    date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid start date format', 'warning')
            
            if date_to_str:
                try:
                    date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid end date format', 'warning')
            
            # Process logs with enhanced logic and date filtering
            records_created, logs_processed = process_unprocessed_logs(
                date_from=date_from, 
                date_to=date_to
            )
            
            # Process any overtime that might have been missed (records without overtime)
            from utils.overtime_engine import process_attendance_records
            overtime_processed = process_attendance_records(
                date_from=date_from, 
                date_to=date_to, 
                employee_id=employee_id,
                recalculate=True
            )
            
            # Build success message with date range info if provided
            message = f'Successfully processed {logs_processed} logs, created {records_created} new attendance records, and calculated overtime for {overtime_processed} records'
            
            if date_from or date_to:
                date_range_msg = " for "
                if date_from:
                    date_range_msg += f"dates from {date_from.strftime('%Y-%m-%d')}"
                if date_from and date_to:
                    date_range_msg += " to "
                if date_to:
                    date_range_msg += f"{date_to.strftime('%Y-%m-%d')}"
                message += date_range_msg
            
            flash(message, 'success')
            
            # Update statistics after processing
            stats = get_processing_stats()
            
            # Set results for template
            results = {
                'records_created': records_created,
                'logs_processed': logs_processed,
                'overtime_processed': overtime_processed,
                'date_from': date_from.strftime('%Y-%m-%d') if date_from else None,
                'date_to': date_to.strftime('%Y-%m-%d') if date_to else None
            }
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error processing logs: {str(e)}")
            flash(f'Error processing logs: {str(e)}', 'danger')
    
    return render_template('attendance/process_logs.html', stats=stats, results=results)

@bp.route('/process-logs', methods=['POST'])
@login_required
def process_selected_logs():
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('attendance.missing_punches'))

    record_ids = request.form.getlist('selected_records')
    record_ids = [int(rid) for rid in record_ids if rid.isdigit()]
    
    if not record_ids:
        flash('No records selected for processing.', 'warning')
        return redirect(url_for('attendance.missing_punches'))

    selected_logs = AttendanceLog.query.filter(AttendanceLog.id.in_(record_ids)).all()
    employee_date_pairs = set((log.employee_id, log.timestamp.date()) for log in selected_logs)

    records_created = 0
    logs_processed = 0

    for emp_id, log_date in employee_date_pairs:
        logs = AttendanceLog.query.filter(
            AttendanceLog.employee_id == emp_id,
            func.date(AttendanceLog.timestamp) == log_date
        ).order_by(AttendanceLog.timestamp).all()

        # Handle overnight shifts
        is_overnight = False
        if logs and logs[-1].log_type in ['IN', 'check_in']:
            next_day_logs = AttendanceLog.query.filter(
                AttendanceLog.employee_id == emp_id,
                func.date(AttendanceLog.timestamp) == log_date + timedelta(days=1)
            ).order_by(AttendanceLog.timestamp).all()

            if next_day_logs and next_day_logs[0].log_type in ['OUT', 'check_out']:
                is_overnight = True
                logs += next_day_logs

        # Overnight continuation from previous day
        prev_day = log_date - timedelta(days=1)
        prev_day_record = AttendanceRecord.query.filter_by(
            employee_id=emp_id,
            date=prev_day,
            check_out=None
        ).first()

        if prev_day_record and logs and logs[0].log_type in ['OUT', 'check_out']:
            prev_day_record.check_out = logs[0].timestamp
            prev_day_record.total_duration = calculate_total_duration(prev_day_record.check_in, prev_day_record.check_out)
            prev_day_record.work_hours = max(0, prev_day_record.total_duration - (prev_day_record.break_duration or 0))

            for log in logs:
                if not log.is_processed:
                    log.is_processed = True
                    log.attendance_record_id = prev_day_record.id
                    logs_processed += 1

            db.session.commit()
            try:
                from utils.overtime_engine import calculate_overtime
                calculate_overtime(prev_day_record, recalculate=True)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Overtime calculation failed: {str(e)}")
            continue

        # Regular processing
        check_in_logs = [log for log in logs if log.log_type in ['IN', 'check_in']]
        check_out_logs = [log for log in logs if log.log_type in ['OUT', 'check_out']]

        check_in = check_in_logs[0].timestamp if check_in_logs else None
        check_out = check_out_logs[-1].timestamp if check_out_logs else None

        if not check_in or not check_out or check_in == check_out:
            continue

        break_duration, break_start, break_end = estimate_break_duration(logs)
        shift_type = determine_shift_type(check_in, emp_id)
        total_duration = calculate_total_duration(check_in, check_out)

        record = AttendanceRecord.query.filter_by(
            employee_id=emp_id,
            date=log_date
        ).first()
        print(record,"=========================================record====================================================================")
        if not record:
            record = AttendanceRecord(employee_id=emp_id, date=log_date)
            db.session.add(record)
            records_created += 1

        is_holiday, is_weekend = check_holiday_and_weekend(emp_id, log_date)

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
        record.break_calculated = False

        employee = Employee.query.get(emp_id)
        if employee and employee.current_shift_id:
            record.shift_id = employee.current_shift_id

        record.work_hours = max(0, total_duration - break_duration)
        db.session.add(record)
        db.session.flush()

        for log in logs:
            if not log.is_processed:
                log.is_processed = True
                log.attendance_record_id = record.id
                logs_processed += 1

        try:
            db.session.commit()
            try:
                from utils.overtime_engine import calculate_overtime
                calculate_overtime(record, recalculate=True)
                db.session.commit()
            except Exception as e:
                print(f"ERROR - Overtime calculation failed for record {record.id}: {str(e)}")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR - Failed to process logs for employee {emp_id} on {log_date}: {str(e)}")

        try:
            process_attendance_records(log_date, log_date, employee_id=emp_id, recalculate=True)
        except Exception as e:
            print(f"ERROR - Failed to recalculate overtime for employee {emp_id} on {log_date}: {str(e)}")    

    flash(f'Processed {logs_processed} logs and created {records_created} records.', 'success')
    return redirect(url_for('attendance.missing_punches'))

@bp.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    record = MissingAttendance.query.get_or_404(record_id)
    employees = Employee.query.all()
    date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    check_in_time = None
    if request.form['check_in']:
        check_in_time = datetime.strptime(f"{date.isoformat()} {request.form['check_in']}", '%Y-%m-%d %H:%M')
        
    check_out_time = None
    if request.form['check_out']:
        check_out_time = datetime.strptime(f"{date.isoformat()} {request.form['check_out']}", '%Y-%m-%d %H:%M')

    if request.method == 'POST':
        record.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        record.check_in = check_in_time
        record.check_out = check_out_time
        record.remarks = request.form['remarks']
        db.session.commit()
        flash('Record updated successfully!', 'success')
        return redirect(url_for('attendance.missing_attendance'))

    return redirect(url_for('attendance.missing_attendance'))

@bp.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = MissingAttendance.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted successfully!', 'success')
    return redirect(url_for('attendance.missing_attendance'))

@bp.route('/approve_record/<int:record_id>', methods=['POST'])
@login_required
def approve_record(record_id):
    import pytz
    from utils.overtime_engine import process_attendance_records

    karachi = pytz.timezone('Asia/Karachi')  # correct timezone

    record = MissingAttendance.query.get_or_404(record_id)
    record.status = 'fixed'

    # Check if attendance record already exists for that employee on that date
    existing = AttendanceRecord.query.filter_by(
        employee_id=record.employee_id,
        date=record.date
    ).first()

    is_holiday, is_weekend = check_holiday_and_weekend(record.employee_id, record.date)
    employee = Employee.query.get(record.employee_id)
    status = 'present'

    if employee and employee.current_shift_id:
        shift = Shift.query.get(employee.current_shift_id)
        if shift and shift.start_time:
            grace_minutes = shift.grace_period_minutes or 0

            # Create timezone-aware datetime for shift start
            shift_start_naive = datetime.combine(record.date, shift.start_time) + timedelta(minutes=grace_minutes)
            shift_start_datetime = karachi.localize(shift_start_naive)

            # Convert check-in to the same timezone for comparison
            check_in_karachi = record.check_in.astimezone(karachi)

            print(check_in_karachi, shift_start_datetime, "===============================qqqqqqqqqqqqqqqqqqqq",check_in_karachi > shift_start_datetime)

            if check_in_karachi > shift_start_datetime:
                status = 'late'

    if not existing:
        new_attendance = AttendanceRecord(
            employee_id=record.employee_id,
            date=record.date,
            check_in=record.check_in,
            check_out=record.check_out,
            status=status,
            is_weekend=is_weekend,
            is_holiday=is_holiday,
            total_duration=calculate_total_duration(record.check_in, record.check_out),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            notes="Auto-created from fixed missing attendance"
        )
        db.session.add(new_attendance)

    db.session.commit()

    # Recalculate overtime
    process_attendance_records(
        date_from=record.date,
        date_to=record.date,
        employee_id=record.employee_id,
        recalculate=True
    )

    flash('Record approved and attendance created successfully!', 'success')
    return redirect(url_for('attendance.missing_attendance'))




@bp.route('/missing_attendance', methods=['GET', 'POST'])
@login_required
def missing_attendance():
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        date = request.form.get('date')
        check_in = request.form.get('check_in') or None
        check_out = request.form.get('check_out') or None
        status = request.form.get('status')
        remarks = request.form.get('remarks')
        date = datetime.strptime(date, '%Y-%m-%d').date()
        check_in_time = None
        if check_in:
            check_in_time = datetime.strptime(f"{date.isoformat()} {check_in}", '%Y-%m-%d %H:%M')
            
        check_out_time = None
        if check_out:
            check_out_time = datetime.strptime(f"{date.isoformat()} {check_out}", '%Y-%m-%d %H:%M')

        new_record = MissingAttendance(
            employee_id=employee_id,
            date=date,
            check_in=check_in_time,
            check_out=check_out_time,
            status=status,
            remarks=remarks
        )
        db.session.add(new_record)
        db.session.commit()
        flash("Missing attendance recorded successfully.", "success")           
        return redirect(url_for('attendance.missing_attendance'))

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_id = request.args.get('employee_id')        

    records_query = MissingAttendance.query

    if not current_user.is_admin:
        records_query = records_query.filter(MissingAttendance.employee_id == current_user.employee_id)
    else:
        if employee_id:
            records_query = records_query.filter(MissingAttendance.employee_id == employee_id)

    if start_date:
        records_query = records_query.filter(MissingAttendance.date >= start_date)
    if end_date:
        records_query = records_query.filter(MissingAttendance.date <= end_date)

    records = records_query.order_by(MissingAttendance.date.desc()).all()

    if current_user.is_admin:
        employees = Employee.query.all()
    else:
        employee = Employee.query.get(current_user.employee_id)
        employees = [employee] if employee else []

    return render_template('attendance/missing_attendance.html', employees=employees, records=records, current_user=current_user)



@bp.route('/missing-punches', methods=['GET', 'POST'])
@login_required
def missing_punches():
    """View and fix missing punches (check-in or check-out)"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Handle fix punch submission
    if request.method == 'POST':
        record_id = request.form.get('record_id')
        punch_type = request.form.get('punch_type')  # 'check_in' or 'check_out'
        punch_time = request.form.get('punch_time')
        punch_date = request.form.get('punch_date')
        
        if not record_id or not punch_type or not punch_time and punch_date:
            flash('Missing required information to fix the punch', 'danger')
            return redirect(url_for('attendance.missing_punches'))

        timestamp = datetime.strptime(f"{punch_date} {punch_time}", "%Y-%m-%d %H:%M")
            
        record = AttendanceLog.query.get(record_id)
        # if not record:
        #     flash('Record not found', 'danger')
        #     return redirect(url_for('attendance.missing_punches'))
            
        try:
            # Parse the time and combine with the record date
            # punch_datetime = datetime.strptime(f"{record.date.isoformat()} {punch_time}", '%Y-%m-%d %H:%M')
            
            # Apply overnight shift logic if needed
            # if punch_type == 'check_out' and record.check_in and punch_datetime < record.check_in:
            #     punch_datetime += timedelta(days=1)
                
            print(punch_type, "0jjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjjj")
            # Update the record
            new_log = AttendanceLog(
                employee_id=record.employee_id,             # must exist in `employee` table
                device_id=record.device_id,               # must exist in `attendance_device` table
                timestamp=timestamp,
                log_type='OUT' if punch_type=='check_out' else 'IN',            # or 'OUT'
                is_processed=False
            )

            # Add and commit to the database
            db.session.add(new_log)
            db.session.commit()

            # setattr(record, punch_type, punch_datetime)
            
            # # Update status and work hours
            # if punch_type == 'check_out' and record.check_in:
            #     # Both check-in and check-out available, calculate hours
            #     from utils.helpers import calculate_work_hours
            #     record.work_hours = calculate_work_hours(
            #         record.check_in, 
            #         punch_datetime, 
            #         record.break_duration if record.break_duration else 0
            #     )
            #     record.status = 'present'
            # elif punch_type == 'check_in' and record.check_out:
            #     # Both check-in and check-out available, calculate hours
            #     from utils.helpers import calculate_work_hours
            #     record.work_hours = calculate_work_hours(
            #         punch_datetime, 
            #         record.check_out, 
            #         record.break_duration if record.break_duration else 0
            #     )
            #     record.status = 'present'
                
            # db.session.commit()
            flash(f'Successfully fixed {punch_type.replace("_", " ")} time for {record.employee.name}', 'success')
            
        except ValueError as e:
            flash(f'Invalid time format: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            
        return redirect(url_for('attendance.missing_punches'))
    
    # Get filter parameters
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    department = request.args.get('department')
    punch_type = request.args.get('punch_type', 'both')  # 'check_in', 'check_out', or 'both'
    
    # Default to past 7 days if no dates provided
    today = date.today()
    if not date_from:
        date_from = (today - timedelta(days=7)).isoformat()
    if not date_to:
        date_to = today.isoformat()
        
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'danger')
        date_from = today - timedelta(days=7)
        date_to = today
    
    # Build query for missing punches
    query = db.session.query(AttendanceLog)\
        .join(Employee)\
        .filter(AttendanceLog.timestamp >= date_from)\
        .filter(AttendanceLog.timestamp <= date_to)\
        .filter(AttendanceLog.is_processed == False)
        
    # Filter by punch type
    print(query)
    # if punch_type == 'check_in':
    #     query = query.filter(AttendanceLog.check_in.is_(None))
    # elif punch_type == 'check_out':
    #     query = query.filter(AttendanceLog.check_out.is_(None))
    # elif punch_type == 'both':
    #     query = query.filter((AttendanceLog.check_in.is_(None)) | (AttendanceLog.check_out.is_(None)))
    
    # Filter by department if provided
    if department:
        query = query.filter(Employee.department == department)
    
    # Get records
    missing_punch_records = query.order_by(AttendanceLog.timestamp.desc(), Employee.name).all()
    
    # Get list of departments for filter dropdown
    departments = db.session.query(Employee.department).filter(Employee.department != None).distinct().all()
    departments = [d[0] for d in departments]
    
    return render_template('attendance/missing_punches.html', 
                           records=missing_punch_records,
                           date_from=date_from,
                           date_to=date_to,
                           departments=departments,
                           selected_department=department,
                           selected_punch_type=punch_type)

@bp.route('/import_csv', methods=['GET', 'POST'])
@login_required
def import_csv():
    """Import attendance data from CSV files in various formats"""
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('attendance.index'))
    
    # Import CSV parsers
    from utils.csv_parsers import auto_detect_and_parse_csv, parse_mir_csv_file, parse_zkteco_standard_file, parse_hikvision_csv_file, import_attendance_records
    
    # Handle delete records request
    if request.method == 'POST' and 'delete_records' in request.form:
        try:
            # Confirm with a token to prevent accidental deletion
            if request.form.get('confirm_token') != 'delete-attendance-records':
                flash('Invalid confirmation token for deleting records', 'danger')
                return redirect(url_for('attendance.import_csv'))
            
            # Import the safe deletion utility
            from utils.deletion_utils import safe_delete_attendance_records_logs
            
            delete_type = request.form.get('delete_type', 'all')
            
            # Delete all records
            if delete_type == 'all':
                # Use the safe deletion utility with no filters (deletes all)
                deleted_records, deleted_logs = safe_delete_attendance_records_logs()
                
                flash(f'All attendance records ({deleted_records}) and logs ({deleted_logs}) have been deleted successfully', 'success')
                current_app.logger.info(f"Deleted all {deleted_records} records and {deleted_logs} logs")
                
            # Delete by date range
            elif delete_type == 'date_range':
                from_date_str = request.form.get('from_date')
                to_date_str = request.form.get('to_date')
                
                if not from_date_str or not to_date_str:
                    flash('Please provide both start and end dates', 'danger')
                    return redirect(url_for('attendance.import_csv'))
                
                try:
                    from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                    to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
                    return redirect(url_for('attendance.import_csv'))
                
                # Use the safe deletion utility with date filters
                deleted_records, deleted_logs = safe_delete_attendance_records_logs(
                    from_date=from_date, 
                    to_date=to_date
                )
                
                flash(f'Successfully deleted {deleted_records} attendance records and {deleted_logs} logs between {from_date} and {to_date}', 'success')
                current_app.logger.info(f"Deleted {deleted_records} records and {deleted_logs} logs between {from_date} and {to_date}")
                
            # Delete by employee
            elif delete_type == 'employee':
                employee_id = request.form.get('employee_id')
                
                if not employee_id:
                    flash('Please select an employee', 'danger')
                    return redirect(url_for('attendance.import_csv'))
                
                # Also check if date range is specified for this employee
                from_date = None
                to_date = None
                
                from_date_str = request.form.get('emp_from_date')
                to_date_str = request.form.get('emp_to_date')
                
                # Only apply date filter if both dates are provided
                if from_date_str and to_date_str:
                    try:
                        from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                        to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        flash('Invalid date format. Please use YYYY-MM-DD', 'danger')
                        return redirect(url_for('attendance.import_csv'))
                
                # Get employee details for notification
                employee = Employee.query.get(employee_id)
                
                # Use the safe deletion utility with employee and optional date filters
                deleted_records, deleted_logs = safe_delete_attendance_records_logs(
                    employee_id=employee_id,
                    from_date=from_date,
                    to_date=to_date
                )
                
                # Construct success message
                message = f'Successfully deleted {deleted_records} attendance records and {deleted_logs} logs'
                if employee:
                    message += f' for {employee.name} (ID: {employee.employee_code})'
                if from_date and to_date:
                    message += f' between {from_date} and {to_date}'
                
                flash(message, 'success')
                current_app.logger.info(message)
            
            return redirect(url_for('attendance.import_csv'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting records: {str(e)}")
            flash(f'Error deleting records: {str(e)}', 'danger')
            return redirect(url_for('attendance.import_csv'))
    
    # Get default device for logs (create one if needed)
    # First, try to find a device specifically for CSV imports
    default_device = AttendanceDevice.query.filter_by(device_id='csv-import').first()
    
    # If that doesn't exist, try to find any ZKTeco device as fallback
    if not default_device:
        default_device = AttendanceDevice.query.filter_by(device_type='zkteco').first()
    
    # If still no device found, create a new CSV import device
    if not default_device:
        try:
            default_device = AttendanceDevice(
                name="CSV Import",
                device_id="csv-import",
                device_type="csv-import",
                model="CSV Import",
                location="Manual Import",
                is_active=True,
                status="online"
            )
            db.session.add(default_device)
            db.session.commit()
            current_app.logger.info("Created new CSV Import device")
        except Exception as e:
            db.session.rollback()
            # Try one more time in case of a race condition
            default_device = AttendanceDevice.query.filter_by(device_id='csv-import').first()
            if not default_device:
                current_app.logger.error(f"Failed to create CSV Import device: {str(e)}")
                default_device = AttendanceDevice.query.first()  # Get any device as a last resort
    
    # Handle file upload
    if request.method == 'POST' and 'csv_file' in request.files:
        # Check if a file was uploaded
        file = request.files['csv_file']
        
        # Check if the file is empty
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('attendance.import_csv'))
        
        # Check if the file is a CSV
        if not file.filename.lower().endswith('.csv'):
            flash('Only CSV files are allowed', 'danger')
            return redirect(url_for('attendance.import_csv'))
        
        # Process the file
        try:
            import tempfile
            import os
            
            # Save uploaded file to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            file.save(temp_file.name)
            temp_file.close()
            
            # Get the selected format and other options
            file_format = request.form.get('file_format', 'auto')
            device_id = request.form.get('device_id', str(default_device.id))
            create_missing = 'create_missing' in request.form
            
            # Parse based on selected format
            records = []
            
            if file_format == 'auto':
                current_app.logger.info("Auto-detecting CSV format")
                records = auto_detect_and_parse_csv(temp_file.name)
                
            elif file_format == 'mir':
                current_app.logger.info("Using MIR format parser")
                records = parse_mir_csv_file(temp_file.name)
                
            elif file_format == 'zkteco':
                current_app.logger.info("Using ZKTeco format parser")
                records = parse_zkteco_standard_file(temp_file.name)
                
            elif file_format == 'hikvision':
                current_app.logger.info("Using Hikvision format parser")
                records = parse_hikvision_csv_file(temp_file.name)
                
            else:
                flash(f'Unsupported file format: {file_format}', 'danger')
                os.unlink(temp_file.name)
                return redirect(url_for('attendance.import_csv'))
            
            # Clean up temporary file
            os.unlink(temp_file.name)
            
            if not records:
                flash('No valid attendance records found in the file', 'warning')
                return redirect(url_for('attendance.import_csv'))
            
            # Import the records
            current_app.logger.info(f"Importing {len(records)} records with device_id={device_id}")
            logs_created, records_updated = import_attendance_records(db.session, records, int(device_id), create_missing)
            
            flash(f'Successfully imported {logs_created} attendance logs and updated {records_updated} records', 'success')
            return redirect(url_for('attendance.raw_logs'))
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            current_app.logger.error(f"Error importing CSV: {str(e)}\n{error_details}")
            
            # Provide a more user-friendly error message
            if "violates foreign key constraint" in str(e):
                flash('Database error: The employee records could not be created. Make sure to check the "Create missing employees" option.', 'danger')
            elif "encoding" in str(e).lower() or "decode" in str(e).lower():
                flash('Character encoding error: The CSV file contains special characters that could not be processed.', 'danger')
            else:
                flash(f'Error processing file: {str(e)}', 'danger')
                
            return redirect(url_for('attendance.import_csv'))
    
    # Get devices for selection
    devices = AttendanceDevice.query.all()
    
    # Get employees for the delete by employee option
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    return render_template('attendance/import_csv.html', 
                          devices=devices, 
                          default_device=default_device,
                          employees=employees)

def parse_zkteco_csv(file_stream):
    """Parse the ZKTeco CSV file format and extract attendance data
    
    Format examples:
    Format 1 (standard format):
    "User ID","Name","Time","Status","Terminal","Verification Type"
    
    Format 2 (New MIR format - repeated entries with metadata):
    "Event Viewer Report","Business Unit:","MIR-Plastic Industries LLC","Location:","MIRDXB","Department:","Cleaner/Misc","Section:","Cleaner/Misc","Employee ID:","129","Report Period:"," 01-Mar-25    To :31-Mar-25","Employee Name:","KHAMIS","Date","Day","Terminal ID","Terminal Name","Event","Punch",01-Mar-25,"Saturday","2","DXB Attendance","IN",01-Mar-25  08:23 am,07-May-25,13:25:40,"User:","admin","Page -1 of 1"
    """
    try:
        reader = csv.reader(file_stream)
        records = []
        
        # Debug information
        current_app.logger.debug("Starting to parse CSV file")
        
        # First check if this is the complex MIR report format
        # This flag will be used to skip rows properly
        file_stream.seek(0)
        first_row = next(reader, None)
        
        # Reset file pointer to beginning
        file_stream.seek(0)
        reader = csv.reader(file_stream)
        
        is_mir_format = False
        if first_row and len(first_row) > 0 and first_row[0] == "Event Viewer Report":
            is_mir_format = True
            current_app.logger.info("Detected MIR Event Viewer Report format")
        
        # Process each row
        for row_idx, row in enumerate(reader):
            if not row or len(row) < 3:
                continue
                
            current_app.logger.debug(f"Row {row_idx}: Processing row with length {len(row)}")
            
            try:
                # Special handling for MIR format rows
                if is_mir_format:
                    # Extract data from the row using the improved parser
                    try:
                        # Find the employee ID in the row
                        employee_id = None
                        employee_name = None
                        event_type = None
                        timestamp = None
                        
                        # Extract employee ID from "Employee ID:" field
                        for i in range(len(row)):
                            if i < len(row) - 1 and row[i] == "Employee ID:":
                                employee_id = row[i+1].strip()
                                break
                        
                        # Extract employee name from "Employee Name:" field
                        for i in range(len(row)):
                            if i < len(row) - 1 and row[i] == "Employee Name:":
                                raw_name = row[i+1].strip()
                                employee_name = ''.join(c for c in raw_name if ord(c) < 128)  # Remove non-ASCII chars
                                break
                        
                        # Find the Event field which indicates IN/OUT
                        event_positions = [i for i, val in enumerate(row) if val in ["IN", "OUT"]]
                        if event_positions:
                            event_type = row[event_positions[0]]
                        
                        # Find the date and time
                        # Look for punch timestamp (which has am/pm in it)
                        punch_timestamps = []
                        for i in range(len(row)):
                            if isinstance(row[i], str) and (" am" in row[i].lower() or " pm" in row[i].lower()):
                                punch_timestamps.append(row[i])
                        
                        # Check if we found potential timestamps
                        if punch_timestamps:
                            # Try to parse the timestamp
                            for punch_ts in punch_timestamps:
                                # Skip timestamps that are clearly not the right format
                                if not re.search(r'\d{2}-[A-Za-z]{3}-\d{2}', punch_ts):
                                    continue
                                    
                                try:
                                    # Expected format is like "01-Mar-25  08:23 am"
                                    timestamp = datetime.strptime(punch_ts, '%d-%b-%y  %I:%M %p')
                                    break
                                except ValueError:
                                    try:
                                        # Try without the double space
                                        timestamp = datetime.strptime(punch_ts, '%d-%b-%y %I:%M %p')
                                        break
                                    except ValueError:
                                        continue
                        
                        # If no timestamp found yet, try alternative approach with date and punch fields
                        if not timestamp:
                            # Find separate date field
                            date_str = None
                            for i in range(len(row) - 1):
                                if row[i] == "Date" and i+1 < len(row):
                                    date_value = row[i+1].strip()
                                    if re.match(r'\d{2}-[A-Za-z]{3}-\d{2}', date_value):
                                        date_str = date_value
                                        break
                            
                            # Find punch time field
                            time_str = None
                            for i in range(len(row) - 1):
                                if row[i] == "Punch" and i+1 < len(row):
                                    punch_value = row[i+1].strip()
                                    # Try to extract time from punch field
                                    time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m)', punch_value, re.IGNORECASE)
                                    if time_match:
                                        time_str = time_match.group(1)
                                        break
                            
                            # Combine date and time if both were found
                            if date_str and time_str:
                                combined_timestamp = f"{date_str}  {time_str}"
                                current_app.logger.debug(f"Assembled timestamp: {combined_timestamp}")
                                try:
                                    timestamp = datetime.strptime(combined_timestamp, '%d-%b-%y  %I:%M %p')
                                except ValueError:
                                    try:
                                        # Try with single space
                                        combined_timestamp = f"{date_str} {time_str}"
                                        timestamp = datetime.strptime(combined_timestamp, '%d-%b-%y %I:%M %p')
                                    except ValueError:
                                        current_app.logger.warning(f"Could not parse combined timestamp: {combined_timestamp}")
                        
                        # If we have all required fields, create a record
                        if employee_id and event_type and timestamp:
                            records.append({
                                'employee_id': employee_id,
                                'employee_name': employee_name or f"Employee {employee_id}",
                                'date': timestamp.date(),
                                'timestamp': timestamp,
                                'log_type': event_type,  # "IN" or "OUT"
                            })
                            current_app.logger.debug(f"Added record: {employee_id}, {employee_name}, {event_type}, {timestamp}")
                        else:
                            if not employee_id:
                                current_app.logger.warning(f"Missing employee ID in row {row_idx}")
                            if not event_type:
                                current_app.logger.warning(f"Missing event type in row {row_idx}")
                            if not timestamp:
                                current_app.logger.warning(f"Could not parse timestamp in row {row_idx}")
                                
                    except Exception as inner_e:
                        current_app.logger.error(f"Error extracting data from MIR format row {row_idx}: {str(inner_e)}")
                        continue
                    
                # Standard format processing (if needed)
                else:
                    # Standard format process code from original function
                    pass
                    
            except Exception as e:
                current_app.logger.error(f"Error processing row {row_idx}: {str(e)}")
                continue
        
        current_app.logger.info(f"Parsed {len(records)} records from CSV")
        return records
    except Exception as e:
        current_app.logger.error(f"Fatal error parsing CSV: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        raise

def save_attendance_data(records, device_id, create_missing=False):
    """Save the parsed attendance data to the database"""
    logs_created = 0
    records_updated = 0
    
    # Log arguments for debugging
    current_app.logger.debug(f"save_attendance_data called with: records={len(records)}, device_id={device_id}, create_missing={create_missing}")
    
    # Get a mapping of employee codes to employee IDs
    employee_code_map = {str(emp.employee_code): emp.id for emp in Employee.query.all()}
    
    # Create all employees first in a separate transaction
    if create_missing:
        current_app.logger.info("Creating missing employees first...")
        # Find all employee codes that need to be created
        missing_employees = []
        
        for record in records:
            employee_code = record.get('employee_id')
            if not employee_code:
                continue
                
            if employee_code not in employee_code_map and record.get('employee_name'):
                # Enhanced cleaning of employee name to handle special characters
                try:
                    # First try to sanitize while preserving most characters
                    employee_name = record['employee_name']
                    
                    # Remove control characters and replace with spaces
                    employee_name = ''.join(c if (c.isalnum() or c.isspace() or c in '.-_') else ' ' for c in employee_name)
                    
                    # Normalize whitespace
                    employee_name = ' '.join(employee_name.split())
                    
                    # If nothing useful remains, fallback to ASCII-only
                    if not employee_name.strip():
                        employee_name = ''.join(c for c in record['employee_name'] if ord(c) < 128 and c.isprintable())
                        
                    # Last resort fallback if all attempts fail
                    if not employee_name.strip():
                        employee_name = f"Employee {employee_code}"
                        
                except Exception as e:
                    current_app.logger.warning(f"Error cleaning employee name: {str(e)}")
                    # Safe fallback with no special characters
                    employee_name = f"Employee {employee_code}"
                
                # Check if this employee is already in our list to create
                if not any(e['code'] == employee_code for e in missing_employees):
                    missing_employees.append({
                        'code': employee_code,
                        'name': employee_name
                    })
        
        # Create all missing employees in a separate transaction
        if missing_employees:
            try:
                for emp in missing_employees:
                    # Check again in case it was added in a parallel request
                    existing = Employee.query.filter_by(employee_code=emp['code']).first()
                    if existing:
                        employee_code_map[str(emp['code'])] = existing.id
                        continue
                        
                    new_employee = Employee(
                        employee_code=emp['code'],
                        name=emp['name'],
                        is_active=True
                    )
                    db.session.add(new_employee)
                
                db.session.commit()
                current_app.logger.info(f"Created {len(missing_employees)} missing employees")
                
                # Refresh our employee code map
                employee_code_map = {str(emp.employee_code): emp.id for emp in Employee.query.all()}
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error creating employees: {str(e)}")
                # Continue with existing employees only
    
    # Now process all the attendance records in batches to avoid memory issues
    batch_size = 100
    total_records = len(records)
    current_app.logger.info(f"Processing {total_records} records in batches of {batch_size}")
    
    for batch_start in range(0, total_records, batch_size):
        batch_end = min(batch_start + batch_size, total_records)
        current_app.logger.info(f"Processing batch {batch_start}-{batch_end} of {total_records}")
        
        # Start a new transaction for each batch
        batch_logs_created = 0
        
        for record_idx in range(batch_start, batch_end):
            record = records[record_idx]
            employee_code = record.get('employee_id')
            
            # Skip records without employee ID
            if not employee_code:
                continue
                
            # Look up the employee by code
            if employee_code in employee_code_map:
                employee_id = employee_code_map[employee_code]
            else:
                # Skip this record if employee not found and we couldn't create them
                current_app.logger.warning(f"Employee with code {employee_code} not found")
                continue
            
            try:
                # First phase: Create attendance log if not a duplicate
                # Check for duplicate entry with same employee, date, log_type and a timestamp within 5 minutes
                from sqlalchemy import and_, func
                existing_log = db.session.query(AttendanceLog).filter(
                    and_(
                        AttendanceLog.employee_id == employee_id,
                        AttendanceLog.log_type == record['log_type'],
                        func.date(AttendanceLog.timestamp) == record['timestamp'].date(),
                        func.abs(func.extract('epoch', AttendanceLog.timestamp) - 
                                 func.extract('epoch', record['timestamp'])) < 300  # Within 5 minutes
                    )
                ).first()
                
                if existing_log:
                    current_app.logger.debug(
                        f"Skipping duplicate log: Employee ID {employee_id}, " +
                        f"Date {record['timestamp'].date()}, Type {record['log_type']}, " +
                        f"Time {record['timestamp'].time()}"
                    )
                    continue
                    
                # Create attendance log if no duplicate found
                log = AttendanceLog(
                    employee_id=employee_id,
                    device_id=device_id,
                    log_type=record['log_type'],
                    timestamp=record['timestamp'],
                    is_processed=False
                )
                db.session.add(log)
                batch_logs_created += 1
                logs_created += 1
                
                # Second phase: Update attendance record
                record_date = record['timestamp'].date()
                
                # Use a different approach that avoids potential encoding issues
                # Query with an explicit condition instead of filter_by
                attendance_record = db.session.query(AttendanceRecord).filter(
                    and_(
                        AttendanceRecord.employee_id == employee_id,
                        AttendanceRecord.date == record_date
                    )
                ).first()
                
                if not attendance_record:
                    # Create new record if it doesn't exist
                    attendance_record = AttendanceRecord(
                        employee_id=employee_id,
                        date=record_date,
                        status='present'
                    )
                    db.session.add(attendance_record)
            
                # Update check-in or check-out time
                if record['log_type'] == 'IN':
                    # If there's no check-in time or this one is earlier
                    if not attendance_record.check_in or record['timestamp'] < attendance_record.check_in:
                        attendance_record.check_in = record['timestamp']
                        records_updated += 1
                        
                elif record['log_type'] == 'OUT':
                    # If there's no check-out time or this one is later
                    if not attendance_record.check_out or record['timestamp'] > attendance_record.check_out:
                        attendance_record.check_out = record['timestamp']
                        records_updated += 1
                
                # Calculate work hours if both check-in and check-out are provided
                if attendance_record.check_in and attendance_record.check_out:
                    # Use safe calculation method
                    try:
                        attendance_record.work_hours = attendance_record.calculate_work_hours()
                        
                        # Set status based on calculated work hours
                        if attendance_record.work_hours >= 8:  # Full day
                            attendance_record.status = 'present'
                        elif attendance_record.work_hours >= 4:  # Half day
                            attendance_record.status = 'half-day'
                        else:
                            attendance_record.status = 'late'
                    except Exception as calc_error:
                        current_app.logger.error(f"Error calculating work hours: {str(calc_error)}")
                        # Default to present if calculation fails
                        attendance_record.status = 'present'
                        attendance_record.work_hours = 8.0  # Default to 8 hours
                
                # Commit in smaller batches within the batch to prevent memory issues
                if batch_logs_created % 20 == 0:
                    db.session.flush()
                    
            except Exception as e:
                current_app.logger.error(f"Error processing record {record_idx} (Employee {employee_code}): {str(e)}")
                db.session.rollback()  # Rollback on error and continue with next record
    
    # Commit all changes
    try:
        db.session.commit()
        current_app.logger.info(f"Successfully committed {logs_created} logs and {records_updated} records")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing to database: {str(e)}")
        raise
    
    return logs_created, records_updated

# Old process_all_logs function removed to avoid duplication

@bp.route('/import-march-data', methods=['GET', 'POST'])
@login_required
def import_march_data():
    """Import March data from the sample CSV file and show day/night shift examples"""
    if not current_user.is_admin:
        flash('You do not have permission to access this feature', 'danger')
        return redirect(url_for('attendance.index'))
        
    if request.method == 'POST':
        try:
            # Parse CSV file
            file_path = 'attached_assets/rptViewer (1).csv'
            device_id = request.form.get('device_id')
            
            if not device_id:
                flash('Please select a device', 'danger')
                devices = AttendanceDevice.query.all()
                return render_template('attendance/import_march_data.html', devices=devices)
            
            # Step 1: Create device if not exists
            device = AttendanceDevice.query.get(device_id)
            if not device:
                flash('Selected device not found', 'danger')
                return redirect(url_for('attendance.import_march_data'))
                
            # Step 2: Parse CSV file
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                records = []
                
                for row in reader:
                    if len(row) < 25:
                        continue
                        
                    try:
                        # Extract data from CSV
                        employee_code = row[10]
                        employee_name = row[14]
                        event_date_str = row[20]
                        log_type = row[24]
                        punch_time_str = row[25] if len(row) > 25 else None
                        
                        # Skip if missing required data
                        if not employee_code or not event_date_str or not log_type or not punch_time_str:
                            continue
                            
                        # Parse date and time
                        punch_date = datetime.strptime(event_date_str, '%d-%b-%y').date()
                        
                        # Parse time (format: DD-MMM-YY HH:MM am/pm)
                        time_parts = punch_time_str.split()
                        time_str = time_parts[-2] + ' ' + time_parts[-1] 
                        time_obj = datetime.strptime(time_str, '%I:%M %p').time()
                        
                        # Combine date and time
                        timestamp = datetime.combine(punch_date, time_obj)
                        
                        # Check if employee exists or create new one
                        employee = Employee.query.filter_by(employee_code=employee_code).first()
                        if not employee:
                            employee = Employee(
                                employee_code=employee_code,
                                name=employee_name,
                                department="Imported",
                                position="Staff",
                                is_active=True
                            )
                            db.session.add(employee)
                            db.session.flush()
                        
                        # Create the log
                        log = AttendanceLog(
                            employee_id=employee.id,
                            device_id=device.id,
                            log_type=log_type,
                            timestamp=timestamp,
                            is_processed=False
                        )
                        db.session.add(log)
                        
                        records.append({
                            'employee': employee,
                            'timestamp': timestamp,
                            'log_type': log_type
                        })
                        
                    except Exception as e:
                        current_app.logger.warning(f"Error parsing row: {str(e)}")
                        continue
            
            db.session.commit()
            
            # Process the imported logs
            process_count = process_imported_logs()
            
            flash(f'Successfully imported and processed {len(records)} records from March data', 'success')
            
            # Redirect to the March examples page
            return redirect(url_for('attendance.march_examples'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error importing March data: {str(e)}")
            flash(f'Error importing March data: {str(e)}', 'danger')
            return redirect(url_for('attendance.import_march_data'))
    
    # GET request - show import form
    devices = AttendanceDevice.query.all()
    if not devices:
        # Create a default device
        device = AttendanceDevice(
            name='MIR Device',
            device_type='CSV Import',
            ip_address='127.0.0.1',
            port=0,
            is_active=True
        )
        db.session.add(device)
        db.session.commit()
        devices = [device]
        
    return render_template('attendance/import_march_data.html', devices=devices)

@bp.route('/march-examples')
@login_required
def march_examples():
    """Show day and night shift examples for March 2025"""
    # Get March 2025 date range
    march_start = date(2025, 3, 1)
    march_end = date(2025, 3, 31)
    
    # Get day shift records (check-in between 6:00 - 12:00)
    day_shift = AttendanceRecord.query.filter(
        AttendanceRecord.date >= march_start,
        AttendanceRecord.date <= march_end,
        AttendanceRecord.check_in.isnot(None),
        extract('hour', AttendanceRecord.check_in) >= 6,
        extract('hour', AttendanceRecord.check_in) < 12
    ).order_by(AttendanceRecord.date).limit(10).all()
    
    # Get night shift records (check-in after 18:00)
    night_shift = AttendanceRecord.query.filter(
        AttendanceRecord.date >= march_start,
        AttendanceRecord.date <= march_end,
        AttendanceRecord.check_in.isnot(None),
        extract('hour', AttendanceRecord.check_in) >= 18
    ).order_by(AttendanceRecord.date).limit(10).all()
    
    return render_template('attendance/march_examples.html', 
                          day_shift=day_shift,
                          night_shift=night_shift)

def process_imported_logs():
    """Process imported logs - separated for reuse"""
    # Get all unprocessed logs
    unprocessed_logs = AttendanceLog.query.filter_by(is_processed=False).all()
    processed_count = 0
    
    # Group logs by employee and date
    logs_by_employee_date = {}
    for log in unprocessed_logs:
        log_date = log.timestamp.date()
        key = (log.employee_id, log_date)
        
        if key not in logs_by_employee_date:
            logs_by_employee_date[key] = []
            
        logs_by_employee_date[key].append(log)
    
    # Process logs by employee and date
    for (employee_id, log_date), employee_logs in logs_by_employee_date.items():
        # Sort logs by timestamp
        employee_logs.sort(key=lambda x: x.timestamp)
        
        # Find or create attendance record
        attendance_record = AttendanceRecord.query.filter_by(
            employee_id=employee_id,
            date=log_date
        ).first()
        
        if not attendance_record:
            attendance_record = AttendanceRecord(
                employee_id=employee_id,
                date=log_date,
                status='present',
                break_duration=1.0  # Default 1 hour break
            )
            db.session.add(attendance_record)
        
        # Get check-in and check-out times
        in_logs = [log for log in employee_logs if log.log_type == 'IN']
        out_logs = [log for log in employee_logs if log.log_type == 'OUT']
        
        # Set check-in time (earliest IN)
        if in_logs:
            attendance_record.check_in = min(in_logs, key=lambda x: x.timestamp).timestamp
        
        # Set check-out time (latest OUT)
        if out_logs:
            attendance_record.check_out = max(out_logs, key=lambda x: x.timestamp).timestamp
        
        # Calculate work hours and analyze break patterns
        if attendance_record.check_in and attendance_record.check_out:
            # Sort all logs chronologically
            all_logs_sorted = sorted(employee_logs, key=lambda x: x.timestamp)
            
            # Calculate total duration from first check-in to last check-out
            total_duration = (attendance_record.check_out - attendance_record.check_in).total_seconds() / 3600
            
            # Calculate breaks
            break_duration = 0
            potential_breaks = []
            
            # Look for potential breaks (OUT followed by IN)
            current_status = None
            last_timestamp = None
            
            for log in all_logs_sorted:
                if current_status == 'OUT' and log.log_type == 'IN' and last_timestamp:
                    # Found a break (out followed by in)
                    break_time = (log.timestamp - last_timestamp).total_seconds() / 3600
                    if break_time > 0.25:  # Only count breaks longer than 15 minutes
                        potential_breaks.append({
                            'start': last_timestamp,
                            'end': log.timestamp,
                            'duration': break_time
                        })
                        break_duration += break_time
                
                current_status = log.log_type
                last_timestamp = log.timestamp
            
            # If no breaks found but should have a standard break
            if break_duration == 0 and total_duration >= 5:
                break_duration = 1.0  # Standard 1 hour break
            
            # Set break duration
            attendance_record.break_duration = break_duration
            
            # Calculate work hours (total duration minus break)
            work_hours = total_duration - break_duration
            attendance_record.work_hours = work_hours
            
            # Calculate overtime (anything over 8 working hours)
            overtime_hours = max(0, work_hours - 8)
            attendance_record.overtime_hours = overtime_hours
            
            # Determine shift type based on check-in time
            check_in_hour = attendance_record.check_in.hour
            if 6 <= check_in_hour < 12:
                attendance_record.shift_type = 'day'
            elif 12 <= check_in_hour < 18:
                attendance_record.shift_type = 'afternoon'
            elif 18 <= check_in_hour or check_in_hour < 6:
                attendance_record.shift_type = 'night'
            
            # Set extra details for analysis
            attendance_record.total_duration = total_duration
            
            # Set status based on work hours
            if work_hours >= 8:
                attendance_record.status = 'present'
            elif work_hours >= 4:
                attendance_record.status = 'half-day'
            else:
                attendance_record.status = 'present'
            
            # Store break details in notes
            if potential_breaks:
                break_notes = []
                for i, brk in enumerate(potential_breaks):
                    start_time = brk['start'].strftime('%H:%M')
                    end_time = brk['end'].strftime('%H:%M')
                    duration = brk['duration']
                    break_notes.append(f"Break {i+1}: {start_time}-{end_time} ({duration:.2f}h)")
                
                attendance_record.notes = "; ".join(break_notes)
                
                # Highlight excessive break
                if break_duration > 1.0:
                    attendance_record.notes += f"; LONG BREAK ALERT: {break_duration:.2f}h total (standard: 1h)"
        
        # Mark logs as processed
        for log in employee_logs:
            log.is_processed = True
            processed_count += 1
    
    # Commit changes
    db.session.commit()
    return processed_count

@bp.route('/api/punch', methods=['POST'])
def api_punch():
    """API endpoint for recording attendance punches from devices"""
    # This would be used by actual attendance devices to submit punches
    try:
        data = request.get_json()
        
        # Basic validation
        required_fields = ['employee_code', 'device_id', 'log_type', 'timestamp']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Get employee by code
        employee = Employee.query.filter_by(employee_code=data['employee_code']).first()
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        
        # Create attendance log
        from models import AttendanceDevice, AttendanceLog
        
        device = AttendanceDevice.query.filter_by(device_id=data['device_id']).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(data['timestamp'])
        except ValueError:
            timestamp = datetime.utcnow()
        
        # Create log
        log = AttendanceLog(
            employee_id=employee.id,
            device_id=device.id,
            log_type=data['log_type'].upper(),  # IN or OUT
            timestamp=timestamp
        )
        
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'log_id': log.id}), 201
        
    except Exception as e:
        current_app.logger.error(f"Error in attendance punch API: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

# @bp.route('/test_break_detection')
# def test_break_detection():
#     """Test endpoint for break time detection"""
#     if not current_user.is_admin:
#         flash('You do not have permission to access this page', 'danger')
#         return redirect(url_for('attendance.index'))
    
#     try:
#         # Create a test record with explicit break times
#         test_date = date(2025, 6, 1)
        
#         # Check if record already exists
#         existing = AttendanceRecord.query.filter(
#             AttendanceRecord.employee_id == 260,
#             AttendanceRecord.date == test_date
#         ).first()
        
#         if existing:
#             # Update existing record
#             record = existing
#             message1 = f"Updating existing record {record.id} for break time test"
#         else:
#             # Create new record
#             record = AttendanceRecord()
#             record.employee_id = 260
#             record.date = test_date
#             record.shift_type = 'day'
#             record.status = 'present'
#             message1 = "Creating new record for break time test"
        
#         # Set explicit check-in and check-out times
#         record.check_in = datetime(2025, 6, 1, 8, 0, 0)
#         record.check_out = datetime(2025, 6, 1, 17, 0, 0)
        
#         # Set explicit break times
#         record.break_start = datetime(2025, 6, 1, 12, 0, 0)
#         record.break_end = datetime(2025, 6, 1, 13, 0, 0)
#         record.break_duration = 1.0
        
#         # Calculate total hours
#         record.total_duration = 9.0
#         record.work_hours = 8.0
        
#         # Save the record
#         db.session.add(record)
#         db.session.commit()
        
#         # Verify the record was saved correctly
#         saved = AttendanceRecord.query.get(record.id)
#         message2 = f"Saved test record with break_start={saved.break_start}, break_end={saved.break_end}"
        
#         # TEST 2: Create logs to test auto-detection of breaks
#         test_date2 = date(2025, 6, 2)
        
#         # Clear any existing logs for this date and employee
#         AttendanceLog.query.filter(
#             AttendanceLog.employee_id == 260,
#             func.date(AttendanceLog.timestamp) == test_date2
#         ).delete()
        
#         # Clear any existing attendance record
#         AttendanceRecord.query.filter(
#             AttendanceRecord.employee_id == 260,
#             AttendanceRecord.date == test_date2
#         ).delete()
        
#         # Create test logs with multiple breaks
#         logs = [
#             # Employee checks in at 8:00 AM
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 8, 0, 0),
#                 log_type='check_in',
#                 is_processed=False
#             ),
#             # Short mid-morning break (10:00-10:15 AM)
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 10, 0, 0),
#                 log_type='check_out',
#                 is_processed=False
#             ),
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 10, 15, 0),
#                 log_type='check_in',
#                 is_processed=False
#             ),
#             # Lunch break (12:00-1:00 PM)
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 12, 0, 0),
#                 log_type='check_out',
#                 is_processed=False
#             ),
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 13, 0, 0),
#                 log_type='check_in',
#                 is_processed=False
#             ),
#             # Short afternoon break (3:00-3:10 PM)
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 15, 0, 0),
#                 log_type='check_out',
#                 is_processed=False
#             ),
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 15, 10, 0),
#                 log_type='check_in',
#                 is_processed=False
#             ),
#             # Employee checks out at 5:00 PM
#             AttendanceLog(
#                 employee_id=260,
#                 device_id=3,
#                 timestamp=datetime(2025, 6, 2, 17, 0, 0),
#                 log_type='check_out',
#                 is_processed=False
#             )
#         ]
        
#         # Add logs to the session
#         for log in logs:
#             db.session.add(log)
#         db.session.commit()
        
#         message3 = f"Created test logs for 2025-06-02"
        
#         # Process the logs
#         from utils.attendance_processor import process_unprocessed_logs
#         records_created, logs_processed = process_unprocessed_logs()
        
#         # Check if the attendance record was created with break times
#         result = AttendanceRecord.query.filter(
#             AttendanceRecord.employee_id == 260,
#             AttendanceRecord.date == test_date2
#         ).first()
        
#         if result:
#             message4 = f"Record created with break_start={result.break_start}, break_end={result.break_end}"
#         else:
#             message4 = "No record created for the test logs"
        
#         # Check if this is an API call
#         if request.headers.get('Accept', '').find('application/json') != -1:
#             # Return JSON response
#             results = {
#                 "test1_record_id": record.id if record else None,
#                 "test1_break_start": saved.break_start.strftime('%Y-%m-%d %H:%M:%S') if saved.break_start else None,
#                 "test1_break_end": saved.break_end.strftime('%Y-%m-%d %H:%M:%S') if saved.break_end else None,
#                 "test2_record_id": result.id if result else None,
#                 "test2_break_start": result.break_start.strftime('%Y-%m-%d %H:%M:%S') if result and result.break_start else None,
#                 "test2_break_end": result.break_end.strftime('%Y-%m-%d %H:%M:%S') if result and result.break_end else None,
#                 "records_created": records_created,
#                 "logs_processed": logs_processed,
#                 "messages": [message1, message2, message3, message4]
#             }
#             return jsonify(results)
            
#         # Otherwise, return the HTML template
#         return render_template('attendance/test_break_detection.html', 
#                                direct_test=saved, 
#                                log_test=result,
#                                records_created=records_created,
#                                logs_processed=logs_processed)
        
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"Error in break detection test: {str(e)}")
#         flash(f"Error in test: {str(e)}", "danger")
#         return redirect(url_for('attendance.index'))
