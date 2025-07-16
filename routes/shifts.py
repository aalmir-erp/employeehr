from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from app import db, app
from models import Shift, ShiftAssignment, Employee, Holiday
import logging

# Create blueprint
bp = Blueprint('shifts', __name__, url_prefix='/shifts')

@bp.route('/')
@login_required
def index():
    """Show all shifts"""
    shifts = Shift.query.order_by(Shift.name).all()
    return render_template('shifts/index.html', shifts=shifts)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_shift():
    """Add a new shift"""
    # if not current_user.is_admin or not current_user.has_role('hr'):
    #     flash('You do not have permission to access this page', 'danger')
    #     return redirect(url_for('shifts.index'))
    
    if request.method == 'POST':
        # Extract form data
        name = request.form.get('name')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        color_code = request.form.get('color_code', '#000000')
        grace_period_minutes = request.form.get('grace_period_minutes', 0)
        break_duration = request.form.get('break_duration', 0)
        is_active = 'is_active' in request.form
        is_overnight = True if request.form.get('is_overnight') else False
        
        # Convert time strings to time objects
        try:
            start_time = datetime.strptime(start_time, '%H:%M').time()
            end_time = datetime.strptime(end_time, '%H:%M').time()
            grace_period_minutes = int(grace_period_minutes)
            break_duration = float(break_duration)
        except ValueError as e:
            flash(f'Invalid time format: {str(e)}', 'danger')
            return render_template('shifts/add_shift.html')
        
        # Create and save the new shift
        new_shift = Shift(
            name=name,
            start_time=start_time,
            end_time=end_time,
            color_code=color_code,
            grace_period_minutes=grace_period_minutes,
            break_duration=break_duration,
            is_active=is_active,
            is_overnight=is_overnight

        )
        
        try:
            db.session.add(new_shift)
            db.session.commit()
            flash(f'Shift "{name}" created successfully!', 'success')
            return redirect(url_for('shifts.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating shift: {str(e)}', 'danger')
    
    return render_template('shifts/add_shift.html')

@bp.route('/edit/<int:shift_id>', methods=['GET', 'POST'])
@login_required
def edit_shift(shift_id):
    """Edit an existing shift"""
    if not current_user.is_admin and not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('shifts.index'))
    
    # Get the shift or return 404
    shift = Shift.query.get_or_404(shift_id)
    
    if request.method == 'POST':
        # Extract form data
        shift.name = request.form.get('name')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        shift.is_overnight = True if request.form.get('is_overnight') else False
        shift.color_code = request.form.get('color_code', '#000000')
        
        try:
            shift.grace_period_minutes = int(request.form.get('grace_period_minutes', 0))
            shift.break_duration = float(request.form.get('break_duration', 0))
            shift.is_active = 'is_active' in request.form
            
            # Convert time strings to time objects
            shift.start_time = datetime.strptime(start_time, '%H:%M').time()
            shift.end_time = datetime.strptime(end_time, '%H:%M').time()
            
            # Handle weekend days (comma separated string of day numbers)
            weekend_days_str = request.form.get('weekend_days', '')
            if weekend_days_str:
                weekend_days = [int(day.strip()) for day in weekend_days_str.split(',') if day.strip().isdigit()]
                shift.weekend_days = weekend_days
            else:
                shift.weekend_days = []
            
            # Save changes
            db.session.commit()
            flash(f'Shift "{shift.name}" updated successfully!', 'success')
            return redirect(url_for('shifts.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating shift: {str(e)}', 'danger')
    
    # Pre-format time for form
    start_time_str = shift.start_time.strftime('%H:%M') if shift.start_time else '08:00'
    end_time_str = shift.end_time.strftime('%H:%M') if shift.end_time else '17:00'
    
    # Format weekend days for form
    weekend_days_str = ','.join(str(day) for day in shift.weekend_days) if shift.weekend_days else ''
    
    return render_template('shifts/edit_shift.html', 
                          shift=shift,
                          start_time=start_time_str,
                          end_time=end_time_str,
                          weekend_days=weekend_days_str)

@bp.route('/get_employees_by_department', methods=['GET'])
@login_required
def get_employees_by_department():
    print(" in get_employees_by_department ")
    department = request.args.get('department')
    print(department)
    query = Employee.query.filter_by(is_active=True)
    
    if department and department != 'all':
        query = query.filter(Employee.department == department)
    
    employees = query.order_by(Employee.name).all()
    employee_data = [{'id': e.id, 'name': e.name, 'department': e.department or 'No Dept'} for e in employees]
    print(employee_data, "employee_data")
    
    return jsonify(employee_data)


@bp.route('/assign', methods=['GET', 'POST'])
@login_required
def assign_shift():
    """Assign shifts to employees"""
    print (current_user.has_role, "------------------------------------------------")
    print (current_user.has_role('hr'))
    if not current_user.is_admin and not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('shifts.index'))
    
    # Get all active employees and shifts
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()
    
    # Get department filter
    departments = list(set([e.department for e in employees if e.department]))
    departments.sort()
    
    # Get the selected department filter
    selected_department = request.args.get('department', '')
    selected_shift_id = request.args.get('shift_id')
    
    # Convert shift_id to int if present
    if selected_shift_id:
        try:
            selected_shift_id = int(selected_shift_id)
        except ValueError:
            selected_shift_id = None
    
    # Filter employees by department if selected
    filtered_employees = employees
    if selected_department:
        filtered_employees = [e for e in employees if e.department == selected_department]
    
    # Handle POST request (new assignment)
    if request.method == 'POST':
        employee_ids = request.form.getlist('employee_id')
        # employee_ids = map(int, request.form.getlist('employee_id'))

        print(employee_ids)
        print(" =========================================== ")
        shift_id = request.form.get('shift_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        days_of_week = request.form.getlist('days_of_week')
        
        try:
            # Convert data types
            # employee_id = int(employee_id)
            shift_id = int(shift_id)
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            days_of_week = [int(day) for day in days_of_week]
            
            # Create assignments for each selected day within the date range
            created_count = 0
            current_date = start_date
            
            while current_date <= end_date:
                for employee_id in employee_ids:
                    if employee_id ==0 or employee_id=='0':
                        continue
                    print (employee_id, "employee_id ------------------------")
                    print (current_date.weekday(), "current_date.weekday()")
                    print(days_of_week, "days_of_week ----")
                    # Only create assignment if this weekday is selected
                    if current_date.weekday() in days_of_week:
                        # Check if assignment already exists
                        existing = ShiftAssignment.query.filter_by(
                            employee_id=employee_id,
                            start_date=current_date
                        ).first()
                        print (existing, "existing")
                        
                        if existing:
                            # Update existing assignment
                            existing.shift_id = shift_id
                            db.session.add(existing)
                            created_count += 1
                        else:
                            # Create new assignment
                            assignment = ShiftAssignment(
                                employee_id=employee_id,
                                shift_id=shift_id,
                                start_date=current_date,
                                end_date=current_date  # Single day assignment
                            )
                            db.session.add(assignment)
                            
                            # Update the employee's current_shift_id as well
                            employee = Employee.query.get(employee_id)
                            if employee:
                                employee.current_shift_id = shift_id
                                db.session.add(employee)
                                
                            created_count += 1
                    
                    # Move to next day
                    current_date += timedelta(days=1)
            
            db.session.commit()
            flash(f'Successfully created {created_count} shift assignments', 'success')
            
            # Redirect with the same filters
            redirect_url = url_for('shifts.assign_shift')
            if selected_department:
                redirect_url += f'?department={selected_department}'
            if selected_shift_id:
                redirect_url += f'{"&" if selected_department else "?"}shift_id={selected_shift_id}'
                
            return redirect(redirect_url)
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating assignments: {str(e)}', 'danger')
    
    # Get existing assignments for the current month
    today = date.today()
    month_start = date(today.year, today.month, 1)
    next_month = today.month + 1 if today.month < 12 else 1
    next_year = today.year if today.month < 12 else today.year + 1
    month_end = date(next_year, next_month, 1) - timedelta(days=1)
    
    assignments = ShiftAssignment.query.filter(
        ShiftAssignment.start_date >= month_start,
        ShiftAssignment.start_date <= month_end
    ).order_by(ShiftAssignment.start_date).all()
    
    return render_template('shifts/assign_shift.html',
                          employees=filtered_employees,
                          shifts=shifts,
                          departments=departments,
                          selected_department=selected_department,
                          selected_shift_id=selected_shift_id,
                          assignments=assignments,
                          month_start=month_start,
                          month_end=month_end)

@bp.route('/scheduler')
@login_required
def scheduler():
    """Interactive shift scheduler with multiple view options (weekly/monthly/employee/shift)"""

    if not current_user.is_admin and not current_user.has_role('hr') and not current_user.has_role('supervisor'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('shifts.index'))

    view_type = request.args.get('view_type', 'default')
    today = date.today()

    # All employees & shifts
    all_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    all_shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()

    # Supervisor: restrict employees & departments
    if current_user.has_role('supervisor') and not current_user.is_admin and not current_user.has_role('hr'):
        user_department = current_user.department
        all_employees = [e for e in all_employees if e.department == user_department]
        departments = [user_department]
        selected_department = user_department
    else:
        departments = sorted(list({e.department for e in all_employees if e.department}))
        selected_department = request.args.get('department', '')

    selected_employee_id = request.args.get('employee_id')
    selected_shift_id = request.args.get('shift_id')

    # Safely cast to int
    try:
        selected_employee_id = int(selected_employee_id) if selected_employee_id else None
    except ValueError:
        selected_employee_id = None
    try:
        selected_shift_id = int(selected_shift_id) if selected_shift_id else None
    except ValueError:
        selected_shift_id = None

    # Week start
    week_start_str = request.args.get('week_start')
    try:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date() if week_start_str else today - timedelta(days=today.weekday())
    except ValueError:
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Month start
    month_select_str = request.args.get('month_select')
    try:
        month_start = datetime.strptime(f"{month_select_str}-01", '%Y-%m-%d').date() if month_select_str else today.replace(day=1)
    except ValueError:
        month_start = today.replace(day=1)

    # Month grid calculation
    first_day_of_grid = month_start - timedelta(days=month_start.weekday())
    next_month = date(month_start.year + 1, 1, 1) if month_start.month == 12 else date(month_start.year, month_start.month + 1, 1)
    last_day_of_month = next_month - timedelta(days=1)
    last_day_of_grid = last_day_of_month + timedelta(days=(6 - last_day_of_month.weekday()))
    month_days = [first_day_of_grid + timedelta(days=i) for i in range((last_day_of_grid - first_day_of_grid).days + 1)]

    # Weekly view days
    days = [week_start + timedelta(days=i) for i in range(7)]

    # Query range
    query_start_date = first_day_of_grid
    query_end_date = last_day_of_grid
    start_date = week_start
    end_date = week_end

    # Filters
    if selected_employee_id:
        filtered_employees = [e for e in all_employees if e.id == selected_employee_id]
    elif selected_department:
        filtered_employees = [e for e in all_employees if e.department == selected_department]
    else:
        filtered_employees = all_employees

    filtered_shifts = [s for s in all_shifts if s.id == selected_shift_id] if selected_shift_id else all_shifts

    # Assignments query
    assignments_query = ShiftAssignment.query.filter(
        ShiftAssignment.start_date <= query_end_date,
        (ShiftAssignment.end_date >= query_start_date) | (ShiftAssignment.end_date.is_(None)),
        ShiftAssignment.is_active == True
    )

    if selected_employee_id:
        assignments_query = assignments_query.filter_by(employee_id=selected_employee_id)
    if selected_shift_id:
        assignments_query = assignments_query.filter_by(shift_id=selected_shift_id)

    assignments = assignments_query.all()

    # Organize assignments
    employee_assignments = {}
    for assignment in assignments:
        employee = next((e for e in all_employees if e.id == assignment.employee_id), None)
        if not employee:
            continue
        if selected_department and employee.department != selected_department:
            continue

        assignment.shift = next((s for s in all_shifts if s.id == assignment.shift_id), None)
        if assignment.employee_id not in employee_assignments:
            employee_assignments[assignment.employee_id] = {}

        assignment_start = max(assignment.start_date, query_start_date)
        assignment_end = min(assignment.end_date or query_end_date, query_end_date)

        current = assignment_start
        while current <= assignment_end:
            date_key = current.strftime('%Y-%m-%d')
            employee_assignments[assignment.employee_id][date_key] = assignment
            current += timedelta(days=1)

    # Holidays
    holiday_records = Holiday.query.filter(
        Holiday.date >= query_start_date,
        Holiday.date <= query_end_date
    ).all()
    holidays = {h.date.strftime('%Y-%m-%d'): h.name for h in holiday_records}

    show_unassigned = request.args.get('show_unassigned') == '1'

    employee_assignments = {}

    for employee in filtered_employees:
        employee_assignments[employee.id] = {}

        for day in month_days:
            date_key = day.strftime('%Y-%m-%d')
            employee_assignments[employee.id][date_key] = None  # Default to None

    # Fill in actual assignments
    for assignment in assignments:
        if selected_department and assignment.employee_id not in [e.id for e in filtered_employees]:
            continue

        assignment.shift = next((s for s in all_shifts if s.id == assignment.shift_id), None)

        assignment_start = max(assignment.start_date, query_start_date)
        assignment_end = min(assignment.end_date or query_end_date, query_end_date)

        current = assignment_start
        while current <= assignment_end:
            date_key = current.strftime('%Y-%m-%d')
            if assignment.employee_id in employee_assignments:
                employee_assignments[assignment.employee_id][date_key] = assignment
            current += timedelta(days=1)

    # Format helper
    def format_date(d):
        return d.strftime('%d/%m/%Y')

    return render_template('shifts/scheduler.html',
        employees=filtered_employees,
        all_employees=all_employees,
        shifts=filtered_shifts,
        all_shifts=all_shifts,
        start_date=start_date,
        end_date=end_date,
        week_start=week_start,
        week_end=week_end,
        month_start=month_start,
        month_days=month_days,
        days=days,
        format_date=format_date,
        assignments=assignments,
        employee_assignments=employee_assignments,
        holidays=holidays,
        departments=departments,
        selected_department=selected_department,
        selected_employee_id=selected_employee_id,
        selected_shift_id=selected_shift_id,
        view_type=view_type,
        timedelta=timedelta
    )

@bp.route('/assignment/add', methods=['POST'])
@login_required
def add_assignment():
    """Add a new shift assignment"""
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not current_user.is_admin or not current_user.has_role('hr'):
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Permission denied'})
        flash('You do not have permission to perform this action', 'danger')
        return redirect(url_for('shifts.scheduler'))
    
    employee_id = request.form.get('employee_id', type=int)
    shift_id = request.form.get('shift_id', type=int)
    start_date = request.form.get('date') or request.form.get('start_date')
    end_date = request.form.get('end_date', None)
    
    if not employee_id or not shift_id or not start_date:
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        flash('Missing required fields', 'danger')
        return redirect(url_for('shifts.scheduler'))
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Invalid date format'})
        flash('Invalid date format', 'danger')
        return redirect(url_for('shifts.scheduler'))
    
    # Check if there's an existing assignment for this employee on this date
    existing_assignment = ShiftAssignment.query.filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.start_date <= start_date,
        (ShiftAssignment.end_date >= start_date) | (ShiftAssignment.end_date.is_(None))
    ).first()
    
    if existing_assignment:
        # Update the existing assignment
        existing_assignment.shift_id = shift_id
        db.session.commit()
        
        if is_ajax_request:
            return jsonify({'success': True, 'message': 'Shift assignment updated'})
        flash('Shift assignment updated successfully', 'success')
        return redirect(url_for('shifts.scheduler'))
    
    # Check for existing assignments for this employee on the same day
    existing_assignments = ShiftAssignment.query.filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.start_date <= start_date,
        (ShiftAssignment.end_date >= start_date) | (ShiftAssignment.end_date.is_(None))
    ).all()
    
    # Get the shift being assigned to check for time conflicts
    new_shift = Shift.query.get(shift_id)
    if not new_shift:
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Invalid shift selected'})
        flash('Invalid shift selected', 'danger')
        return redirect(url_for('shifts.scheduler'))
    
    # Check for overlapping shifts on the same day
    for existing in existing_assignments:
        existing_shift = Shift.query.get(existing.shift_id)
        if existing_shift:
            # Simple check - don't allow multiple shifts on the same day
            if is_ajax_request:
                return jsonify({'success': False, 'message': 'Employee already has a shift assigned for this date'})
            flash('Employee already has a shift assigned for this date', 'danger')
            return redirect(url_for('shifts.scheduler'))
            
    # Create new assignment
    assignment = ShiftAssignment(
        employee_id=employee_id,
        shift_id=shift_id,
        start_date=start_date,
        end_date=end_date
    )
    
    try:
        db.session.add(assignment)
        db.session.commit()
        
        if is_ajax_request:
            return jsonify({'success': True, 'message': 'Shift assignment added'})
        flash('Shift assignment added successfully', 'success')
        return redirect(url_for('shifts.scheduler'))
    except Exception as e:
        db.session.rollback()
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Error saving shift assignment: ' + str(e)})
        flash('Error saving shift assignment: ' + str(e), 'danger')
        return redirect(url_for('shifts.scheduler'))

@bp.route('/assignment/delete/<int:assignment_id>', methods=['POST'])
@login_required
def assignment_delete(assignment_id):
    """Delete a shift assignment"""
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not current_user.is_admin or not current_user.has_role('hr'):
        if is_ajax_request:
            return jsonify({'success': False, 'message': 'Permission denied'})
        flash('You do not have permission to perform this action', 'danger')
        return redirect(url_for('shifts.scheduler'))
    
    try:
        assignment = ShiftAssignment.query.get_or_404(assignment_id)
        
        db.session.delete(assignment)
        db.session.commit()
        
        if is_ajax_request:
            return jsonify({'success': True, 'message': 'Shift assignment deleted'})
        flash('Shift assignment deleted successfully', 'success')
        return redirect(url_for('shifts.scheduler'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting shift assignment {assignment_id}: {str(e)}")
        
        if is_ajax_request:
            return jsonify({'success': False, 'message': f'Error deleting shift assignment: {str(e)}'}), 500
        flash(f'Error deleting shift assignment: {str(e)}', 'danger')
        return redirect(url_for('shifts.scheduler'))

@bp.route('/holidays')
@login_required
def holidays():
    """Manage holidays"""
    if not current_user.is_admin or not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('shifts.index'))
    
    # Get the current year
    current_year = date.today().year
    year = request.args.get('year', type=int, default=current_year)
    
    # Get filter parameters
    employee_id = request.args.get('employee_id', '')
    is_recurring = request.args.get('is_recurring', '')
    
    # Start with base query
    query = Holiday.query
    
    # Filter by year if specified
    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        query = query.filter(Holiday.date.between(start_date, end_date))
    
    # Filter by holiday type
    if employee_id == 'company':
        # Company-wide holidays only
        query = query.filter(Holiday.is_employee_specific == False)
    elif employee_id == 'employee':
        # Any employee-specific holidays
        query = query.filter(Holiday.is_employee_specific == True)
    elif employee_id and employee_id.isdigit():
        # Specific employee's holidays
        query = query.filter(Holiday.employee_id == int(employee_id))
    
    # Filter by recurring status
    if is_recurring == '1':
        query = query.filter(Holiday.is_recurring == True)
    elif is_recurring == '0':
        query = query.filter(Holiday.is_recurring == False)
    
    # Get final sorted results
    holidays = query.order_by(Holiday.date).all()
    
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # For filter select options
    selected_employee_id = employee_id
    selected_recurring = is_recurring
    
    return render_template('shifts/holidays.html', 
                          holidays=holidays, 
                          employees=employees, 
                          current_year=current_year,
                          selected_year=year,
                          selected_employee_id=selected_employee_id,
                          selected_recurring=selected_recurring)

@bp.route('/holidays/add', methods=['POST'])
@login_required
def add_holiday():
    """Add a new holiday"""
    if not current_user.is_admin or not current_user.has_role('hr'):
        flash('You do not have permission to perform this action', 'danger')
        return redirect(url_for('shifts.holidays'))
    
    name = request.form.get('name')
    holiday_date = request.form.get('date')
    is_recurring = 'is_recurring' in request.form
    is_employee_specific = 'is_employee_specific' in request.form
    employee_id = request.form.get('employee_id', type=int)
    
    if not name or not holiday_date:
        flash('Name and date are required', 'danger')
        return redirect(url_for('shifts.holidays'))
    
    try:
        holiday_date = datetime.strptime(holiday_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format', 'danger')
        return redirect(url_for('shifts.holidays'))
    
    # Create new holiday
    holiday = Holiday(
        name=name,
        date=holiday_date,
        is_recurring=is_recurring,
        is_employee_specific=is_employee_specific
    )
    
    if is_employee_specific and employee_id:
        holiday.employee_id = employee_id
    
    db.session.add(holiday)
    db.session.commit()
    
    flash('Holiday added successfully', 'success')
    return redirect(url_for('shifts.holidays'))

@bp.route('/holidays/delete/<int:holiday_id>', methods=['POST'])
@login_required
def delete_holiday(holiday_id):
    """Delete a holiday"""
    if not current_user.is_admin or not current_user.has_role('hr'):
        flash('You do not have permission to perform this action', 'danger')
        return redirect(url_for('shifts.holidays'))
    
    try:
        holiday = Holiday.query.get_or_404(holiday_id)
        
        db.session.delete(holiday)
        db.session.commit()
        
        flash('Holiday deleted successfully', 'success')
        return redirect(url_for('shifts.holidays'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting holiday {holiday_id}: {str(e)}")
        flash(f'Error deleting holiday: {str(e)}', 'danger')
        return redirect(url_for('shifts.holidays'))

@bp.route('/assignments/batch-delete', methods=['POST'])
@login_required
def batch_delete_assignments():
    """Delete multiple shift assignments at once"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    # Get assignment IDs from request JSON
    data = request.get_json()
    if not data or 'assignment_ids' not in data:
        return jsonify({'success': False, 'message': 'No assignment IDs provided'}), 400
    
    assignment_ids = data['assignment_ids']
    if not assignment_ids or not isinstance(assignment_ids, list):
        return jsonify({'success': False, 'message': 'Invalid assignment IDs'}), 400
    
    success_count = 0
    error_count = 0
    failed_ids = []
    
    for assignment_id in assignment_ids:
        try:
            assignment = ShiftAssignment.query.get(assignment_id)
            if assignment:
                db.session.delete(assignment)
                success_count += 1
            else:
                error_count += 1
                failed_ids.append(assignment_id)
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deleting shift assignment {assignment_id}: {str(e)}")
            error_count += 1
            failed_ids.append(assignment_id)
    
    try:
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'Successfully deleted {success_count} assignments. Failed to delete {error_count} assignments.',
            'failed_ids': failed_ids
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error committing batch delete: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Database error: {str(e)}',
            'failed_ids': assignment_ids
        }), 500

@bp.route('/api/employee-assignments/<int:employee_id>')
@login_required
def api_employee_assignments(employee_id):
    """Get shift assignments for a specific employee"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({'error': 'Start and end dates are required'}), 400
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    assignments = ShiftAssignment.query.filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.start_date <= end_date,
        (ShiftAssignment.end_date >= start_date) | (ShiftAssignment.end_date.is_(None))
    ).all()
    
    result = []
    for assignment in assignments:
        shift = Shift.query.get(assignment.shift_id)
        result.append({
            'id': assignment.id,
            'shift_id': assignment.shift_id,
            'shift_name': shift.name if shift else 'Unknown',
            'start_date': assignment.start_date.isoformat(),
            'end_date': assignment.end_date.isoformat() if assignment.end_date else None,
            'color': shift.color_code if shift else '#ccc'
        })
    
    return jsonify(result)


@bp.route('/advanced-batch-delete', methods=['POST'])
@login_required
def advanced_batch_delete():
    """Delete multiple shift assignments by criteria (department, employee, date range)"""
    if not (current_user.is_admin or current_user.role in ['hr', 'supervisor']):
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Required parameters
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': 'Date range is required'}), 400
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400
        
        # Build base query for all assignments in date range
        query = ShiftAssignment.query.filter(
            ShiftAssignment.start_date <= end_date,
            (ShiftAssignment.end_date >= start_date) | (ShiftAssignment.end_date.is_(None))
        )
        
        # Optional filters
        employee_ids = data.get('employee_ids')
        department = data.get('department')
        shift_id = data.get('shift_id')
        
        # Filter by employee IDs if provided
        if employee_ids and isinstance(employee_ids, list):
            query = query.filter(ShiftAssignment.employee_id.in_(employee_ids))
        
        # Filter by department if provided
        elif department:
            # Get all employees in the department
            department_employees = Employee.query.filter_by(department=department).all()
            department_employee_ids = [e.id for e in department_employees]
            
            if department_employee_ids:
                query = query.filter(ShiftAssignment.employee_id.in_(department_employee_ids))
            else:
                # No employees in this department
                return jsonify({'success': True, 'message': 'No assignments found', 'count': 0})
        
        # Filter by shift ID if provided
        if shift_id:
            query = query.filter(ShiftAssignment.shift_id == shift_id)
        
        # Get all assignments matching the criteria
        assignments = query.all()
        count = len(assignments)
        
        # Delete all matching assignments
        for assignment in assignments:
            db.session.delete(assignment)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{count} assignments deleted successfully', 
            'count': count
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in advanced batch delete: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@bp.route('/batch-assign', methods=['POST'])
@login_required
def batch_assign():
    """Assign shifts to multiple employees/dates at once"""
    print("=============================================================================")
    if not (current_user.is_admin or current_user.role in ['hr', 'supervisor']):
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Required parameters
        shift_id = data.get('shift_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        days_of_week = data.get('days_of_week', [0, 1, 2, 3, 4])  # Monday-Friday by default
        
        if not shift_id or not start_date or not end_date:
            return jsonify({'success': False, 'message': 'Missing required parameters'}), 400
        
        # Validate shift
        shift = Shift.query.get(shift_id)
        if not shift:
            return jsonify({'success': False, 'message': 'Invalid shift ID'}), 400
        
        # Parse dates
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400
        
        # Get target employees
        employee_ids = data.get('employee_ids')
        department = data.get('department')
        
        if employee_ids and isinstance(employee_ids, list):
            employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()
        elif department:
            employees = Employee.query.filter_by(department=department).all()
        else:
            employees = Employee.query.filter_by(is_active=True).all()
        
        if not employees:
            return jsonify({'success': False, 'message': 'No employees found with the given criteria'}), 400
        
        # Create a list of dates in the range
        date_list = []
        current_date = start_date
        while current_date <= end_date:
            # Check if current day of week is in the selected days
            # Monday is 0, Sunday is 6
            if current_date.weekday() in days_of_week:
                date_list.append(current_date)
            current_date += timedelta(days=1)
        
        if not date_list:
            return jsonify({'success': False, 'message': 'No dates match the selected days of week'}), 400
        
        # Count successful assignments
        assignment_count = 0
        
        # For each employee and date, create an assignment
        for employee in employees:
            for assignment_date in date_list:
                # Check for existing assignment on this date
                existing = ShiftAssignment.query.filter(
                    ShiftAssignment.employee_id == employee.id,
                    ShiftAssignment.start_date <= assignment_date,
                    (ShiftAssignment.end_date >= assignment_date) | (ShiftAssignment.end_date.is_(None))
                ).first()
                
                if existing:
                    # Skip if already assigned (don't override)
                    continue
                
                # Create new assignment
                new_assignment = ShiftAssignment(
                    employee_id=employee.id,
                    shift_id=shift_id,
                    start_date=assignment_date,
                    end_date=assignment_date  # Single day assignment
                )
                
                db.session.add(new_assignment)
                assignment_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{assignment_count} shift assignments created',
            'count': assignment_count
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in batch assign: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
