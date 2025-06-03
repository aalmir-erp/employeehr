from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required
from datetime import datetime, date, timedelta
import calendar
import csv
import io
import xlsxwriter
import json
from app import db
from models import Employee, AttendanceRecord, Shift
from utils.helpers import get_date_range, get_attendance_stats

# Create blueprint
bp = Blueprint('reports', __name__, url_prefix='/reports')

@bp.route('/')
@login_required
def index():
    """Reports dashboard"""
    # Get employees for the employee selection dropdown
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    return render_template('reports/index.html', employees=employees)
    
@bp.route('/dashboard')
@login_required
def dashboard():
    """Comprehensive attendance dashboard with drill-down capabilities"""
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    today = date.today()
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        # Default to current month if dates are invalid
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    
    # Get filter parameters
    department = request.args.get('department', 'all')
    employee_ids = request.args.getlist('employee_ids')
    selected_statuses = request.args.getlist('status[]')
    
    # Default statuses if none selected
    if not selected_statuses:
        selected_statuses = ['present', 'absent', 'late', 'early_out']
    
    # Get all employees for the dropdown (regardless of filters)
    all_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # Apply filters for the report
    query = Employee.query.filter_by(is_active=True)
    
    # Department filter
    if department != 'all':
        query = query.filter_by(department=department)
    
    # Employee filter
    if employee_ids:
        query = query.filter(Employee.id.in_([int(e_id) for e_id in employee_ids]))
    
    # Get filtered employees
    employees = query.all()
    
    # Get all attendance records for this period based on the filters
    records_query = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id.in_([e.id for e in employees]),
        AttendanceRecord.date.between(start_date, end_date)
    )
    
    # Status filter
    if selected_statuses:
        records_query = records_query.filter(AttendanceRecord.status.in_(selected_statuses))
    
    records = records_query.all()
    
    # Get departments for filter
    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    
    # Calculate overall statistics
    total_days = (end_date - start_date).days + 1
    working_days = len([d for d in get_date_range(start_date, end_date) if d.weekday() < 5])  # Mon-Fri
    
    present_count = sum(1 for r in records if r.status == 'present')
    absent_count = sum(1 for r in records if r.status == 'absent')
    late_count = sum(1 for r in records if r.status == 'late')
    early_out_count = sum(1 for r in records if r.status in ['early_out', 'early-out'])
    missing_count = sum(1 for r in records if r.status not in ['present', 'absent', 'late', 'early_out', 'early-out'])
    
    total_work_hours = sum(r.work_hours for r in records if r.work_hours is not None)
    total_overtime = sum(r.overtime_hours for r in records if r.overtime_hours is not None)
    avg_hours = total_work_hours / present_count if present_count else 0
    avg_overtime = total_overtime / len(employees) if employees else 0
    
    statistics = {
        'total_days': total_days,
        'working_days': working_days,
        'present': present_count,
        'absent': absent_count,
        'late': late_count,
        'early_out': early_out_count,
        'missing': missing_count,
        'total_hours': total_work_hours,
        'total_overtime': total_overtime,
        'avg_hours': avg_hours,
        'avg_overtime': avg_overtime,
        'present_percent': round((present_count / (total_days * len(employees)) * 100), 1) if total_days and employees else 0,
        'absent_percent': round((absent_count / (total_days * len(employees)) * 100), 1) if total_days and employees else 0,
        'late_percent': round((late_count / present_count * 100), 1) if present_count else 0
    }
    
    # Prepare employee summary data
    employee_summary = []
    for employee in employees:
        hours = 0
        if employee.current_shift:
            start_time = employee.current_shift.start_time  # datetime.time object
            end_time = employee.current_shift.end_time  # datetime.time object

            # Combine with today's date to make full datetime objects
            start_dt = datetime.combine(date.today(), start_time)
            end_dt = datetime.combine(date.today(), end_time)

            # If the shift goes past midnight (e.g., 10 PM to 6 AM), add 1 day to end_dt
            if end_dt < start_dt:
                end_dt += timedelta(days=1)

            # Calculate duration
            duration = end_dt - start_dt

        # Optional: get duration in hours, minutes, etc.
            hours = duration.total_seconds() / 3600
        emp_records = [r for r in records if r.employee_id == employee.id]
        present_days = sum(1 for r in emp_records if r.status == 'present')
        if present_days >1:
            x=1

        absent_days = sum(1 for r in emp_records if r.status == 'absent')
        weekdays_work_days = sum(1 for r in emp_records if r.is_weekend == True)
        late_count = sum(1 for r in emp_records if r.status == 'late')
        early_out_count = sum(1 for r in emp_records if r.status in ['early_out', 'early-out'])
        missing_count = sum(1 for r in emp_records if r.status not in ['present', 'absent', 'late', 'early_out', 'early-out'])
        
        total_hours = sum(r.work_hours for r in emp_records if r.work_hours is not None)
        # overtime_hours = sum(r.overtime_hours for r in emp_records if r.overt_time_weighted > 0 is not None)
        overtime_hours = sum(   r.overt_time_weighted for r in emp_records if r.overt_time_weighted is not None and r.overt_time_weighted > 0 )
        
        employee_summary.append({
            'employee': employee,
            'present_days': present_days,
            'absent_days': absent_days,
            'late_count': late_count,
            'early_out_count': early_out_count,
            'missing_count': missing_count,
            'total_hours': total_hours,
            'overtime_hours': overtime_hours,
            'expected_time':hours*(present_days-weekdays_work_days)
        })
    
    # Sort by name (you could add other sort options)
    employee_summary.sort(key=lambda x: x['employee'].name)
    
    # Generate trend data (attendance patterns over the date range)
    dates_in_range = get_date_range(start_date, end_date)
    trend_dates = [d.strftime('%Y-%m-%d') for d in dates_in_range]
    trend_present = []
    trend_absent = []
    trend_late = []
    
    for d in dates_in_range:
        day_records = [r for r in records if r.date == d]
        trend_present.append(sum(1 for r in day_records if r.status == 'present'))
        trend_absent.append(sum(1 for r in day_records if r.status == 'absent'))
        trend_late.append(sum(1 for r in day_records if r.status == 'late'))
    
    return render_template('reports/dashboard.html',
                          start_date=start_date,
                          end_date=end_date,
                          departments=departments,
                          all_employees=all_employees,
                          selected_department=department,
                          selected_employee_ids=employee_ids,
                          selected_statuses=selected_statuses,
                          statistics=statistics,
                          employee_summary=employee_summary,
                          trend_dates=trend_dates,
                          trend_present=trend_present,
                          trend_absent=trend_absent,
                          trend_late=trend_late)

@bp.route('/daily')
@login_required
def daily():
    """Daily attendance report"""
    selected_date = request.args.get('date', date.today().isoformat())
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    department = request.args.get('department', 'all')
    
    # Query attendance records for the selected date
    query = AttendanceRecord.query.filter_by(date=selected_date)
    
    # Apply department filter if specified
    if department != 'all':
        query = query.join(Employee).filter(Employee.department == department)
    
    records = query.all()
    
    # Calculate statistics
    total_records = len(records)
    present_count = sum(1 for r in records if r.status == 'present')
    absent_count = sum(1 for r in records if r.status == 'absent')
    late_count = sum(1 for r in records if r.status == 'late')
    
    # Get departments for filter
    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    
    return render_template('reports/daily.html',
                          date=selected_date,
                          records=records,
                          total_records=total_records,
                          present_count=present_count,
                          absent_count=absent_count,
                          late_count=late_count,
                          departments=departments,
                          selected_department=department)

@bp.route('/weekly')
@login_required
def weekly():
    """Weekly attendance report"""
    # Get the date range for the week
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # Allow overriding the week through query parameters
    start_date = request.args.get('start_date')
    if start_date:
        try:
            start_of_week = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_of_week = start_of_week + timedelta(days=6)
        except ValueError:
            pass
    
    # Generate list of dates for the week
    week_dates = get_date_range(start_of_week, end_of_week)
    
    # Get all employees
    employees = Employee.query.filter_by(is_active=True).all()
    
    # Prepare data for the report
    employee_data = []
    for employee in employees:
        # Get attendance records for this employee for the week
        records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.date.between(start_of_week, end_of_week)
        ).all()
        
        # Create a dict to store daily status
        weekly_status = {}
        for d in week_dates:
            record = next((r for r in records if r.date == d), None)
            if record:
                weekly_status[d.isoformat()] = {
                    'status': record.status,
                    'work_hours': record.work_hours,
                    'id': record.id
                }
            else:
                weekly_status[d.isoformat()] = {
                    'status': 'unknown',
                    'work_hours': 0,
                    'id': None
                }
        
        # Calculate weekly stats
        present_days = sum(1 for d in week_dates if weekly_status[d.isoformat()]['status'] == 'present')
        absent_days = sum(1 for d in week_dates if weekly_status[d.isoformat()]['status'] == 'absent')
        total_hours = sum(weekly_status[d.isoformat()]['work_hours'] for d in week_dates)
        
        employee_data.append({
            'employee': employee,
            'weekly_status': weekly_status,
            'present_days': present_days,
            'absent_days': absent_days,
            'total_hours': total_hours
        })
    
    return render_template('reports/weekly.html',
                          start_date=start_of_week,
                          end_date=end_of_week,
                          week_dates=week_dates,
                          employee_data=employee_data)

@bp.route('/monthly')
@login_required
def monthly():
    """Monthly attendance report"""
    # Get the current month and year
    today = date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))
    
    # Create date objects for the first and last day of the month
    first_day = date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_num)
    
    # Generate list of all days in the month
    month_dates = get_date_range(first_day, last_day)
    
    # Get filter parameters
    department = request.args.get('department', 'all')
    employee_id = request.args.get('employee_id', 'all')
    
    # Get all employees for the dropdown (regardless of filters)
    all_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # Apply filters for the report
    query = Employee.query.filter_by(is_active=True)
    
    # Department filter
    if department != 'all':
        query = query.filter_by(department=department)
    
    # Employee filter
    if employee_id != 'all':
        try:
            employee_id = int(employee_id)
            query = query.filter_by(id=employee_id)
        except (ValueError, TypeError):
            pass  # Invalid employee_id, ignore this filter
    
    # Get filtered employees
    employees = query.all()
    
    # Get all attendance records for this month based on the filters
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id.in_([e.id for e in employees]),
        AttendanceRecord.date.between(first_day, last_day)
    ).all()
    
    # Organize records by employee and date
    employee_records = {}
    for record in records:
        if record.employee_id not in employee_records:
            employee_records[record.employee_id] = {}
        employee_records[record.employee_id][record.date.isoformat()] = record
    
    # Prepare data for the report
    employee_data = []
    for employee in employees:
        monthly_status = {}
        for d in month_dates:
            date_str = d.isoformat()
            if employee.id in employee_records and date_str in employee_records[employee.id]:
                record = employee_records[employee.id][date_str]
                monthly_status[date_str] = {
                    'status': record.status,
                    'work_hours': record.work_hours,
                    'id': record.id
                }
            else:
                monthly_status[date_str] = {
                    'status': 'unknown',
                    'work_hours': 0,
                    'id': None
                }
        
        # Calculate monthly stats
        present_days = sum(1 for d in month_dates if monthly_status[d.isoformat()]['status'] == 'present')
        absent_days = sum(1 for d in month_dates if monthly_status[d.isoformat()]['status'] == 'absent')
        total_hours = sum(monthly_status[d.isoformat()]['work_hours'] for d in month_dates)
        
        employee_data.append({
            'employee': employee,
            'monthly_status': monthly_status,
            'present_days': present_days,
            'absent_days': absent_days,
            'total_hours': total_hours
        })
    
    # Get departments for filter
    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    
    # Generate years for the dropdown (current year plus 3 years before)
    current_year = date.today().year
    years = list(range(current_year - 3, current_year + 1))
    
    # Calculate monthly statistics
    statistics = None
    department_summary = None
    
    # Only calculate statistics if there are records
    if records:
        # Attendance statistics
        working_days = len([d for d in month_dates if d.weekday() < 5])  # Mon-Fri
        present_count = sum(1 for r in records if r.status == 'present')
        absent_count = sum(1 for r in records if r.status == 'absent')
        late_count = sum(1 for r in records if r.status == 'late')
        holidays = sum(1 for d in month_dates if d.weekday() >= 5)  # Sat-Sun as holidays
        
        # Calculate average hours and total overtime
        total_work_hours = sum(r.work_hours for r in records if r.work_hours is not None)
        total_overtime = sum(r.overtime_hours for r in records if r.overtime_hours is not None)
        avg_hours = total_work_hours / len(records) if records else 0
        
        statistics = {
            'working_days': working_days,
            'present': present_count,
            'absent': absent_count,
            'late': late_count,
            'holidays': holidays,
            'avg_hours': avg_hours,
            'total_overtime': total_overtime
        }
        
        # Generate department summary
        from sqlalchemy import func, case, distinct
        
        # First, get distinct employee count per department
        dept_employee_counts = db.session.query(
            Employee.department,
            func.count(distinct(Employee.id)).label('total_employees')
        ).join(
            AttendanceRecord, Employee.id == AttendanceRecord.employee_id
        ).filter(
            AttendanceRecord.date.between(first_day, last_day)
        ).group_by(
            Employee.department
        ).all()
        
        # Create a dictionary to lookup employee counts by department
        dept_emp_count_dict = {dept.department: dept.total_employees for dept in dept_employee_counts}
        
        # Then get attendance statistics
        dept_summary = db.session.query(
            Employee.department,
            func.sum(AttendanceRecord.work_hours).label('total_hours'),
            func.sum(AttendanceRecord.overtime_hours).label('total_overtime'),
            func.count(AttendanceRecord.id).label('total_records'),
            func.sum(case((AttendanceRecord.status == 'present', 1), else_=0)).label('present_count'),
            func.sum(case((AttendanceRecord.status == 'absent', 1), else_=0)).label('absent_count'),
            func.sum(case((AttendanceRecord.status == 'late', 1), else_=0)).label('late_count')
        ).join(
            AttendanceRecord, Employee.id == AttendanceRecord.employee_id
        ).filter(
            AttendanceRecord.date.between(first_day, last_day)
        ).group_by(
            Employee.department
        ).all()
        
        # Process the summary data
        department_summary = []
        for dept in dept_summary:
            if dept.total_records > 0:
                present_percent = (dept.present_count / dept.total_records) * 100
                absent_percent = (dept.absent_count / dept.total_records) * 100
                late_percent = (dept.late_count / dept.total_records) * 100
                avg_hours = dept.total_hours / dept.total_records if dept.total_records > 0 else 0
                
                department_summary.append({
                    'department': dept.department,
                    'total_employees': dept_emp_count_dict.get(dept.department, 0),
                    'present_percent': present_percent,
                    'absent_percent': absent_percent,
                    'late_percent': late_percent,
                    'avg_hours': avg_hours,
                    'total_overtime': dept.total_overtime or 0
                })
    
    return render_template('reports/monthly.html',
                          years=years,
                          selected_year=year,
                          selected_month=month,
                          month_name=calendar.month_name[month],
                          month_dates=month_dates,
                          employee_data=employee_data,
                          departments=departments,
                          all_employees=all_employees,
                          selected_department=department,
                          selected_employee_id=employee_id,
                          statistics=statistics,
                          summary=department_summary)

@bp.route('/employee/<int:employee_id>')
@login_required
def employee(employee_id):
    """Detailed report for a specific employee"""
    employee = Employee.query.get_or_404(employee_id)
    
    # Get date range
    today = date.today()
    start_date = request.args.get('start_date', (today - timedelta(days=30)).isoformat())
    end_date = request.args.get('end_date', today.isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today
    
    # Get attendance records for this employee in the date range
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date.between(start_date, end_date)
    ).order_by(AttendanceRecord.date).all()
    
    # Get the employee's shift
    from utils.helpers import get_employee_shift
    current_shift = get_employee_shift(employee_id)
    
    # Calculate overall statistics
    stats = get_attendance_stats(employee_id, start_date, end_date)
    
    # Calculate attendance percentages
    total_workdays = (end_date - start_date).days + 1
    attendance_rate = (stats['present'] / total_workdays) * 100 if total_workdays > 0 else 0
    
    # Calculate overtime statistics
    total_overtime_hours = 0
    night_overtime_hours = 0
    highest_daily_overtime = 0
    overtime_days = 0
    
    for record in records:
        if record.overtime_hours is not None and record.overtime_hours > 0:
            total_overtime_hours += record.overtime_hours
            overtime_days += 1
            if record.overtime_hours > highest_daily_overtime:
                highest_daily_overtime = record.overtime_hours
            if record.overtime_night_hours is not None and record.overtime_night_hours > 0:
                night_overtime_hours += record.overtime_night_hours
    
    # Calculate lateness statistics (using status field since there's no late_minutes column)
    from sqlalchemy import func
    late_days_count = db.session.query(func.count(AttendanceRecord.id)).filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date.between(start_date, end_date),
        AttendanceRecord.status == 'late'
    ).scalar() or 0
    
    # For now, we'll just report days late instead of minutes
    late_minutes_total = late_days_count * 30  # Approximate 30 minutes per late day
    
    # Get average hours worked per day
    avg_hours = db.session.query(func.avg(AttendanceRecord.work_hours)).filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date.between(start_date, end_date),
        AttendanceRecord.work_hours > 0
    ).scalar() or 0
    
    # Add enhanced statistics to the stats dictionary
    stats.update({
        'total_overtime_hours': total_overtime_hours,
        'night_overtime_hours': night_overtime_hours,
        'highest_daily_overtime': highest_daily_overtime,
        'overtime_days': overtime_days,
        'late_minutes_total': late_minutes_total,
        'avg_hours': avg_hours
    })
    
    return render_template('reports/employee.html',
                          employee=employee,
                          records=records,
                          start_date=start_date,
                          end_date=end_date,
                          stats=stats,
                          attendance_rate=attendance_rate,
                          current_shift=current_shift)

@bp.route('/export/csv', methods=['GET'])
@login_required
def export_csv():
    """Export attendance data as CSV"""
    report_type = request.args.get('type', 'daily')
    
    if report_type == 'daily':
        selected_date = request.args.get('date', date.today().isoformat())
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
        
        # Query attendance records for the selected date
        records = AttendanceRecord.query.filter_by(date=selected_date).all()
        
        # Create CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Employee ID', 'Employee Name', 'Department', 'Check-In', 'Check-Out', 'Work Hours', 'Overtime Hours', 'Status'])
        
        # Write data rows
        for record in records:
            employee = Employee.query.get(record.employee_id)
            writer.writerow([
                employee.employee_code,
                employee.name,
                employee.department or 'N/A',
                record.check_in.strftime('%H:%M:%S') if record.check_in else 'N/A',
                record.check_out.strftime('%H:%M:%S') if record.check_out else 'N/A',
                f"{record.work_hours:.2f}",
                f"{record.overtime_hours:.2f}" if record.overtime_hours else '0.00',
                record.status
            ])
        
        # Prepare the response
        output.seek(0)
        filename = f"attendance_report_{selected_date.strftime('%Y-%m-%d')}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    elif report_type == 'monthly':
        year = int(request.args.get('year', date.today().year))
        month = int(request.args.get('month', date.today().month))
        
        # Create date objects for the first and last day of the month
        first_day = date(year, month, 1)
        _, last_day_num = calendar.monthrange(year, month)
        last_day = date(year, month, last_day_num)
        
        # Get all attendance records for this month
        records = AttendanceRecord.query.filter(
            AttendanceRecord.date.between(first_day, last_day)
        ).order_by(AttendanceRecord.employee_id, AttendanceRecord.date).all()
        
        # Create CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Employee ID', 'Employee Name', 'Department', 'Date', 'Check-In', 'Check-Out', 'Work Hours', 'Overtime Hours', 'Status'])
        
        # Write data rows
        for record in records:
            employee = Employee.query.get(record.employee_id)
            writer.writerow([
                employee.employee_code,
                employee.name,
                employee.department or 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.check_in.strftime('%H:%M:%S') if record.check_in else 'N/A',
                record.check_out.strftime('%H:%M:%S') if record.check_out else 'N/A',
                f"{record.work_hours:.2f}",
                f"{record.overtime_hours:.2f}" if record.overtime_hours else '0.00',
                record.status
            ])
        
        # Prepare the response
        output.seek(0)
        filename = f"monthly_attendance_{year}_{month:02d}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    elif report_type == 'absent':
        # Get date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        department = request.args.get('department', 'all')
        
        today = date.today()
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = today - timedelta(days=30)
            end_date = today
        
        # Query for absent records
        query = AttendanceRecord.query.filter(
            AttendanceRecord.date.between(start_date, end_date),
            AttendanceRecord.status == 'absent'
        ).join(Employee)
        
        # Filter by department if specified
        if department != 'all':
            query = query.filter(Employee.department == department)
            
        absent_records = query.order_by(AttendanceRecord.date.desc(), Employee.name).all()
        
        # Create CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Employee ID', 'Employee Name', 'Department', 'Date', 'Day of Week', 'Reason/Leave Type'])
        
        # Write data rows
        for record in absent_records:
            employee = Employee.query.get(record.employee_id)
            writer.writerow([
                employee.employee_code,
                employee.name,
                employee.department or 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.date.strftime('%A'),
                record.leave_type or 'Unexcused'
            ])
        
        # Prepare the response
        output.seek(0)
        filename = f"absent_employees_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    elif report_type == 'late':
        # Get date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        department = request.args.get('department', 'all')
        
        today = date.today()
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = today - timedelta(days=30)
            end_date = today
        
        # Query for late records
        query = AttendanceRecord.query.filter(
            AttendanceRecord.date.between(start_date, end_date),
            AttendanceRecord.status == 'late'
        ).join(Employee)
        
        # Filter by department if specified
        if department != 'all':
            query = query.filter(Employee.department == department)
            
        late_records = query.order_by(AttendanceRecord.date.desc(), Employee.name).all()
        
        # Create CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Employee ID', 'Employee Name', 'Department', 'Date', 'Check-In Time', 'Expected Time', 'Late Minutes', 'Day of Week'])
        
        # Write data rows
        for record in late_records:
            employee = Employee.query.get(record.employee_id)
            # Get the employee's shift to determine expected time
            from utils.helpers import get_employee_shift
            shift = get_employee_shift(employee.id)
            expected_time = "9:00 AM"  # Default
            if shift and hasattr(shift, 'start_time'):
                expected_time = shift.start_time.strftime('%H:%M:%S')
                
            writer.writerow([
                employee.employee_code,
                employee.name,
                employee.department or 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.check_in.strftime('%H:%M:%S') if record.check_in else 'N/A',
                expected_time,
                "30 min",  # Default 30 min late as no late_minutes field exists
                record.date.strftime('%A')
            ])
        
        # Prepare the response
        output.seek(0)
        filename = f"late_arrivals_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    return jsonify({'error': 'Invalid report type'}), 400

@bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """Get attendance data for charts"""
    chart_type = request.args.get('type', 'daily')
    
    if chart_type == 'daily':
        selected_date = request.args.get('date', date.today().isoformat())
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
        
        # Get attendance records for the day
        records = AttendanceRecord.query.filter_by(date=selected_date).all()
        
        # Calculate statistics
        present_count = sum(1 for r in records if r.status == 'present')
        absent_count = sum(1 for r in records if r.status == 'absent')
        late_count = sum(1 for r in records if r.status == 'late')
        pending_count = sum(1 for r in records if r.status == 'pending')
        
        return jsonify({
            'labels': ['Present', 'Absent', 'Late', 'Pending'],
            'datasets': [{
                'data': [present_count, absent_count, late_count, pending_count],
                'backgroundColor': ['#28a745', '#dc3545', '#ffc107', '#6c757d']
            }]
        })
    
    elif chart_type == 'monthly':
        year = int(request.args.get('year', date.today().year))
        month = int(request.args.get('month', date.today().month))
        
        # Create date objects for the first and last day of the month
        first_day = date(year, month, 1)
        _, last_day_num = calendar.monthrange(year, month)
        last_day = date(year, month, last_day_num)
        
        # Generate all dates in the month
        dates = []
        current_date = first_day
        while current_date <= last_day:
            dates.append(current_date)
            current_date += timedelta(days=1)
        
        # Get attendance counts for each day
        present_counts = []
        absent_counts = []
        
        for day in dates:
            records = AttendanceRecord.query.filter_by(date=day).all()
            present_counts.append(sum(1 for r in records if r.status == 'present'))
            absent_counts.append(sum(1 for r in records if r.status == 'absent'))
        
        return jsonify({
            'labels': [d.strftime('%d') for d in dates],
            'datasets': [
                {
                    'label': 'Present',
                    'data': present_counts,
                    'backgroundColor': 'rgba(40, 167, 69, 0.2)',
                    'borderColor': '#28a745',
                    'borderWidth': 1
                },
                {
                    'label': 'Absent',
                    'data': absent_counts,
                    'backgroundColor': 'rgba(220, 53, 69, 0.2)',
                    'borderColor': '#dc3545',
                    'borderWidth': 1
                }
            ]
        })
    
    return jsonify({'error': 'Invalid chart type'}), 400

@bp.route('/export/employee-summary/<string:format>')
@login_required
def export_employee_summary(format):
    """Export employee attendance summary in various formats"""
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    today = date.today()
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        # Default to current month if dates are invalid
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    
    # Get all active employees
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # Prepare data for export
    export_data = []
    
    for employee in employees:
        # Get all attendance records for this employee in the date range
        records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.date.between(start_date, end_date)
        ).all()
        
        # Calculate statistics
        present_days = sum(1 for r in records if r.status == 'present')
        absent_days = sum(1 for r in records if r.status == 'absent')
        late_count = sum(1 for r in records if r.status == 'late')
        early_out_count = sum(1 for r in records if r.status in ['early_out', 'early-out'])
        missing_count = sum(1 for r in records if r.status not in ['present', 'absent', 'late', 'early_out', 'early-out'])
        
        total_hours = sum(r.work_hours for r in records if r.work_hours is not None)
        overtime_hours = sum(r.overtime_hours for r in records if r.overtime_hours is not None)
        
        export_data.append({
            'employee_id': employee.id,
            'employee_code': employee.employee_code,
            'employee_name': employee.name,
            'department': employee.department or 'Unassigned',
            'present_days': present_days,
            'absent_days': absent_days,
            'late_count': late_count,
            'early_out_count': early_out_count,
            'missing_count': missing_count,
            'total_hours': round(total_hours, 1) if total_hours else 0,
            'overtime_hours': round(overtime_hours, 1) if overtime_hours else 0
        })
    
    # Format-specific exports
    if format == 'csv':
        output = io.StringIO()
        fieldnames = [
            'employee_code', 'employee_name', 'department', 'present_days', 
            'absent_days', 'late_count', 'early_out_count', 'missing_count', 
            'total_hours', 'overtime_hours'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in export_data:
            writer.writerow({field: item[field] for field in fieldnames})
        
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'employee_attendance_summary_{start_date.isoformat()}_{end_date.isoformat()}.csv'
        )
        
    elif format == 'excel':
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Attendance Summary')
        
        # Add headers
        headers = [
            'Employee Code', 'Employee Name', 'Department', 'Present Days', 
            'Absent Days', 'Late Arrivals', 'Early Departures', 'Missing Punch', 
            'Work Hours', 'Overtime Hours'
        ]
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3c8dbc',
            'color': 'white',
            'border': 1
        })
        
        data_format = workbook.add_format({
            'border': 1
        })
        
        number_format = workbook.add_format({
            'border': 1,
            'num_format': '0.0'
        })
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Add data
        for row, item in enumerate(export_data, 1):
            worksheet.write(row, 0, item['employee_code'], data_format)
            worksheet.write(row, 1, item['employee_name'], data_format)
            worksheet.write(row, 2, item['department'], data_format)
            worksheet.write(row, 3, item['present_days'], data_format)
            worksheet.write(row, 4, item['absent_days'], data_format)
            worksheet.write(row, 5, item['late_count'], data_format)
            worksheet.write(row, 6, item['early_out_count'], data_format)
            worksheet.write(row, 7, item['missing_count'], data_format)
            worksheet.write(row, 8, item['total_hours'], number_format)
            worksheet.write(row, 9, item['overtime_hours'], number_format)
        
        # Adjust column widths
        worksheet.set_column(0, 0, 15)  # Employee Code
        worksheet.set_column(1, 1, 25)  # Employee Name
        worksheet.set_column(2, 2, 15)  # Department
        worksheet.set_column(3, 7, 15)  # Present - Missing
        worksheet.set_column(8, 9, 15)  # Work Hours, Overtime
        
        workbook.close()
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_attendance_summary_{start_date.isoformat()}_{end_date.isoformat()}.xlsx'
        )
        
    elif format == 'odoo':
        # Mapping between AMS fields and Odoo HR Attendance fields
        # Odoo HR Attendance model fields:
        # - employee_id: Employee reference
        # - check_in: Check-in datetime
        # - check_out: Check-out datetime
        # - worked_hours: Hours worked
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Odoo HR Attendance Data')
        
        # Add Odoo header
        headers = [
            'External ID', 'Employee', 'Employee External ID', 'Check In', 'Check Out', 
            'Worked Hours', 'Work From Home', 'Department', 'Status', 'Overtime Hours'
        ]
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#875A7B',  # Odoo purple
            'color': 'white',
            'border': 1
        })
        
        data_format = workbook.add_format({
            'border': 1
        })
        
        number_format = workbook.add_format({
            'border': 1,
            'num_format': '0.0'
        })
        
        date_format = workbook.add_format({
            'border': 1,
            'num_format': 'yyyy-mm-dd hh:mm:ss'
        })
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Process records by day and employee
        row = 1
        for employee in employees:
            records = AttendanceRecord.query.filter(
                AttendanceRecord.employee_id == employee.id,
                AttendanceRecord.date.between(start_date, end_date)
            ).order_by(AttendanceRecord.date).all()
            
            for record in records:
                # Skip records with no check-in or check-out times
                if not record.check_in or not record.check_out:
                    continue
                
                # Create Odoo-compatible timestamps - the timestamps already include the date
                check_in = record.check_in
                check_out = record.check_out
                
                # Calculate worked hours (Odoo uses duration in hours)
                worked_hours = record.work_hours if record.work_hours is not None else 0
                
                # Create External ID for attendance record
                external_id = f"mir_ams_attendance_{employee.employee_code}_{record.date.strftime('%Y%m%d')}"
                
                # Map employee code to external ID for Odoo
                employee_external_id = f"mir_ams_employee_{employee.employee_code}"
                
                # Write data row
                worksheet.write(row, 0, external_id, data_format)  # External ID
                worksheet.write(row, 1, employee.name, data_format)  # Employee name
                worksheet.write(row, 2, employee_external_id, data_format)  # Employee External ID
                worksheet.write(row, 3, check_in, date_format)  # Check In
                worksheet.write(row, 4, check_out, date_format)  # Check Out
                worksheet.write(row, 5, worked_hours, number_format)  # Worked Hours
                worksheet.write(row, 6, 'No', data_format)  # Work From Home (default: No)
                worksheet.write(row, 7, employee.department or 'Unassigned', data_format)  # Department
                worksheet.write(row, 8, record.status.capitalize(), data_format)  # Status
                worksheet.write(row, 9, record.overtime_hours or 0, number_format)  # Overtime Hours
                
                row += 1
        
        # Adjust column widths
        worksheet.set_column(0, 0, 30)  # External ID
        worksheet.set_column(1, 1, 25)  # Employee name
        worksheet.set_column(2, 2, 30)  # Employee External ID
        worksheet.set_column(3, 4, 20)  # Check In/Out
        worksheet.set_column(5, 5, 15)  # Worked Hours
        worksheet.set_column(6, 6, 15)  # Work From Home
        worksheet.set_column(7, 7, 15)  # Department
        worksheet.set_column(8, 8, 15)  # Status
        worksheet.set_column(9, 9, 15)  # Overtime Hours
        
        # Add an instructions sheet
        instructions = workbook.add_worksheet('Import Instructions')
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'color': '#875A7B'
        })
        
        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 12
        })
        
        instructions.set_column(0, 0, 120)
        instructions.write(0, 0, "Odoo HR Attendance Import Instructions", title_format)
        instructions.write(2, 0, "How to Import this Data into Odoo:", subtitle_format)
        instructions.write(3, 0, "1. In your Odoo instance, go to Settings and ensure the Developer Mode is activated.")
        instructions.write(4, 0, "2. Go to Technical > Data Import/Export > Import.")
        instructions.write(5, 0, "3. Select the 'Attendances' model.")
        instructions.write(6, 0, "4. Upload this Excel file.")
        instructions.write(7, 0, "5. Map the columns to the corresponding Odoo fields.")
        instructions.write(8, 0, "   - External ID -> External ID")
        instructions.write(9, 0, "   - Employee -> employee_id/name (or use Employee External ID)")
        instructions.write(10, 0, "   - Employee External ID -> employee_id/External ID")
        instructions.write(11, 0, "   - Check In -> check_in")
        instructions.write(12, 0, "   - Check Out -> check_out")
        instructions.write(13, 0, "   - Worked Hours -> worked_hours")
        instructions.write(15, 0, "Note: Make sure to import employees first before importing attendance records.")
        instructions.write(16, 0, "If employees already exist in Odoo with the same names, you may use the names directly instead of External IDs.")
        
        workbook.close()
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'odoo_attendance_import_{start_date.isoformat()}_{end_date.isoformat()}.xlsx'
        )
    
    else:
        return jsonify({'error': 'Unsupported export format'}), 400

@bp.route('/api/employee_attendance/<int:employee_id>')
@login_required
def api_employee_attendance(employee_id):
    """Get detailed attendance data for a specific employee"""
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        # Default to current month if dates are invalid
        today = date.today()
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    
    # Get employee info
    employee = Employee.query.get_or_404(employee_id)
    
    # Get attendance records
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date.between(start_date, end_date)
    ).order_by(AttendanceRecord.date).all()
    
    # Calculate employee summary
    total_days = (end_date - start_date).days + 1
    present_days = sum(1 for r in records if r.status == 'present')
    absent_days = sum(1 for r in records if r.status == 'absent')
    late_days = sum(1 for r in records if r.status == 'late')
    total_hours = sum(r.work_hours for r in records if r.work_hours is not None)
    overtime_hours = sum(r.overtime_hours for r in records if r.overtime_hours is not None)
    
    # Format records for JSON response
    formatted_records = []
    for record in records:
        formatted_records.append({
            'id': record.id,
            'date': record.date.isoformat(),
            'status': record.status,
            'check_in': record.check_in.strftime('%H:%M:%S') if record.check_in else None,
            'check_out': record.check_out.strftime('%H:%M:%S') if record.check_out else None,
            'work_hours': record.work_hours,
            'overtime_hours': record.overtime_hours if record.overt_time_weighted > 0 else 0,
            'overt_time_weighted': record.overt_time_weighted,
            'is_weekend':record.is_weekend,
            'is_holiday': record.is_holiday,
            # Calculate late minutes from check-in time if status is 'late'
            'late_minutes': 0 if not record.check_in or record.status != 'late' else 0,
            'note': record.notes,
            'grace_period_minutes': record.grace_period_minutes,
            'grace_overtime_hours': record.grace_overtime_hours,
            'break_duration': record.break_duration
        })
    
    # Calculate summary stats
    summary = {
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'late_days': late_days,
        'present_percent': round((present_days / total_days) * 100, 1) if total_days > 0 else 0,
        'absent_percent': round((absent_days / total_days) * 100, 1) if total_days > 0 else 0,
        'total_hours': total_hours,
        'overtime_hours': overtime_hours,
        'avg_hours': round(total_hours / present_days, 1) if present_days > 0 else 0,
        'overtime_percent': round((overtime_hours / total_hours) * 100, 1) if total_hours > 0 else 0
    }
    
    # Format employee for JSON response
    employee_data = {
        'id': employee.id,
        'name': employee.name,
        'employee_code': employee.employee_code,
        'department': employee.department or 'Unassigned'
    }
    
    return jsonify({
        'employee': employee_data,
        'records': formatted_records,
        'summary': summary,
        'date_range': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }
    })

@bp.route('/api/day_attendance/<int:employee_id>')
@login_required
def api_day_attendance(employee_id):
    """Get detailed attendance data for a specific employee on a specific day"""
    # Get date from request
    date_param = request.args.get('date')
    
    try:
        req_date = datetime.strptime(date_param, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        req_date = date.today()
    
    # Get employee info
    employee = Employee.query.get_or_404(employee_id)
    
    # Get attendance record
    record = AttendanceRecord.query.filter_by(
        employee_id=employee_id,
        date=req_date
    ).first()
    
    # Get raw attendance logs
    from models import AttendanceLog
    # Convert req_date to datetime range for the day
    start_datetime = datetime.combine(req_date, datetime.min.time())
    end_datetime = datetime.combine(req_date, datetime.max.time())
    
    logs = AttendanceLog.query.filter(
        AttendanceLog.employee_id == employee_id,
        AttendanceLog.timestamp >= start_datetime,
        AttendanceLog.timestamp <= end_datetime
    ).order_by(AttendanceLog.timestamp).all()
    
    # Get employee's shift
    from utils.helpers import get_employee_shift
    shift = get_employee_shift(employee_id)
    
    # Format logs for JSON response
    formatted_logs = []
    if logs:
        for log in logs:
            formatted_logs.append({
                'id': log.id,
                'timestamp': log.timestamp.strftime('%H:%M:%S') if log.timestamp else None,
                'log_type': log.log_type,
                'device_id': log.device_id,
                'device_name': log.device.name if log.device else None,
                'note': None  # AttendanceLog has no note field
            })
    
    # Format record for JSON response
    record_data = None
    if record:
        record_data = {
            'id': record.id,
            'date': record.date.isoformat(),
            'status': record.status,
            'check_in': record.check_in.strftime('%H:%M:%S') if record.check_in else None,
            'check_out': record.check_out.strftime('%H:%M:%S') if record.check_out else None,
            'work_hours': record.work_hours,
            'overtime_hours': record.overtime_hours,
            'late_minutes': 0,  # Setting a default value since field doesn't exist
            'note': record.notes
        }
    else:
        # Create a placeholder record if none exists
        record_data = {
            'id': None,
            'date': req_date.isoformat(),
            'status': 'unknown',
            'check_in': None,
            'check_out': None,
            'work_hours': 0,
            'overtime_hours': 0,
            'late_minutes': 0,
            'note': 'No attendance record exists for this date'
        }
    
    # Format shift data
    shift_data = None
    if shift:
        shift_data = {
            'id': shift.id,
            'name': shift.name,
            'start_time': shift.start_time.strftime('%H:%M:%S') if hasattr(shift, 'start_time') and shift.start_time else '09:00:00',
            'end_time': shift.end_time.strftime('%H:%M:%S') if hasattr(shift, 'end_time') and shift.end_time else '18:00:00',
            'break_duration': shift.break_duration if hasattr(shift, 'break_duration') else 1,
            'expected_hours': shift.expected_hours if hasattr(shift, 'expected_hours') else 8
        }
    
    # Format employee for JSON response
    employee_data = {
        'id': employee.id,
        'name': employee.name,
        'employee_code': employee.employee_code,
        'department': employee.department or 'Unassigned'
    }
    
    return jsonify({
        'employee': employee_data,
        'record': record_data,
        'logs': formatted_logs,
        'shift': shift_data,
        'date': req_date.isoformat()
    })

@bp.route('/absent')
@login_required
def absent():
    """Report of absent employees"""
    # Get date range
    today = date.today()
    start_date = request.args.get('start_date', (today - timedelta(days=30)).isoformat())
    end_date = request.args.get('end_date', today.isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today
    
    department = request.args.get('department', 'all')
    
    # Query for absent records
    query = AttendanceRecord.query.filter(
        AttendanceRecord.date.between(start_date, end_date),
        AttendanceRecord.status == 'absent'
    ).join(Employee)
    
    # Filter by department if specified
    if department != 'all':
        query = query.filter(Employee.department == department)
    
    absent_records = query.order_by(
        AttendanceRecord.date.desc(),
        Employee.name
    ).all()
    
    # Get list of departments for filter
    departments = db.session.query(Employee.department).filter(
        Employee.department != None
    ).distinct().all()
    departments = [d[0] for d in departments]
    
    # Calculate statistics
    employees_with_absences = db.session.query(AttendanceRecord.employee_id).filter(
        AttendanceRecord.date.between(start_date, end_date),
        AttendanceRecord.status == 'absent'
    ).distinct().count()
    
    # Group absences by employee to find repeat offenders
    from sqlalchemy import func
    absences_by_employee = db.session.query(
        AttendanceRecord.employee_id,
        func.count(AttendanceRecord.id).label('absence_count')
    ).filter(
        AttendanceRecord.date.between(start_date, end_date),
        AttendanceRecord.status == 'absent'
    ).group_by(
        AttendanceRecord.employee_id
    ).order_by(
        func.count(AttendanceRecord.id).desc()
    ).limit(10).all()
    
    # Get employee details for top absentees
    top_absentees = []
    for emp_id, absence_count in absences_by_employee:
        employee = Employee.query.get(emp_id)
        if employee:
            top_absentees.append({
                'id': employee.id,
                'name': employee.name,
                'employee_code': employee.employee_code,
                'department': employee.department,
                'absence_count': absence_count
            })
    
    return render_template('reports/absent.html',
                          absent_records=absent_records,
                          start_date=start_date,
                          end_date=end_date,
                          departments=departments,
                          selected_department=department,
                          employees_with_absences=employees_with_absences,
                          top_absentees=top_absentees)

# End of reports routes
