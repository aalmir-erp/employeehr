"""
Routes for managing overtime rules and calculations
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
#from flask import request, jsonify
import xmlrpc.client

from flask_login import login_required, current_user
from sqlalchemy import func, desc,case
from models import db, OvertimeRule, AttendanceRecord, Employee
from utils.overtime_engine import process_attendance_records, calculate_monthly_overtime, calculate_weekly_overtime

bp = Blueprint('overtime', __name__)

@bp.route('/')
@login_required
def index():
    """Show overview of overtime rules and statistics"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get all active rules
    rules = OvertimeRule.query.filter_by(is_active=True).order_by(OvertimeRule.priority.desc()).all()
    
    # Get top employees with overtime this month
    current_month = date.today().replace(day=1)
    top_overtime = db.session.query(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.department,
        func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0).label('total_overtime')
    ).join(
        AttendanceRecord, Employee.id == AttendanceRecord.employee_id
    ).filter(
        AttendanceRecord.date >= current_month,
        Employee.is_active == True
    ).group_by(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.department
    ).order_by(
        desc('total_overtime')
    ).limit(10).all()
    
    # Calculate overall statistics
    stats = {
        'total_rules': OvertimeRule.query.count(),
        'active_rules': OvertimeRule.query.filter_by(is_active=True).count(),
        'employees_with_overtime': db.session.query(AttendanceRecord.employee_id).filter(
            AttendanceRecord.overtime_hours > 0,
            AttendanceRecord.date >= current_month
        ).distinct().count(),
        'total_overtime_hours': db.session.query(func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0)).filter(
            AttendanceRecord.date >= current_month
        ).scalar() or 0
    }
    
    return render_template(
        'overtime/index.html', 
        rules=rules, 
        top_overtime=top_overtime,
        stats=stats
    )

@bp.route('/rules')
@login_required
def rules():
    """Show list of all overtime rules"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get all rules
    rules = OvertimeRule.query.order_by(OvertimeRule.priority.desc()).all()
    
    return render_template('overtime/rules.html', rules=rules)

@bp.route('/rules/add', methods=['GET', 'POST'])
@login_required
def add_rule():
    """Add a new overtime rule"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            description = request.form.get('description')
            
            # Time thresholds
            daily_regular_hours = float(request.form.get('daily_regular_hours', 8.0))
            
            # Multipliers
            weekday_multiplier = float(request.form.get('weekday_multiplier', 1.5))
            weekend_multiplier = float(request.form.get('weekend_multiplier', 2.0))
            holiday_multiplier = float(request.form.get('holiday_multiplier', 2.5))
            
            # Applicable days
            apply_on_weekday = 'apply_on_weekday' in request.form
            apply_on_weekend = 'apply_on_weekend' in request.form
            apply_on_holiday = 'apply_on_holiday' in request.form
            
            # Night shift settings
            night_shift_multiplier = float(request.form.get('night_shift_multiplier', 1.2))
            night_shift_start_time_str = request.form.get('night_shift_start_time')
            night_shift_end_time_str = request.form.get('night_shift_end_time')
            
            # Parse time strings
            night_shift_start_time = None
            night_shift_end_time = None
            
            if night_shift_start_time_str and night_shift_end_time_str:
                try:
                    night_shift_start_time = datetime.strptime(night_shift_start_time_str, '%H:%M').time()
                    night_shift_end_time = datetime.strptime(night_shift_end_time_str, '%H:%M').time()
                except ValueError:
                    flash('Invalid time format for night shift times. Use HH:MM format.', 'danger')
                    return redirect(url_for('overtime.add_rule'))
            
            # Maximum limits
            max_daily_overtime = float(request.form.get('max_daily_overtime', 4.0))
            max_weekly_overtime = float(request.form.get('max_weekly_overtime', 15.0))
            max_monthly_overtime = float(request.form.get('max_monthly_overtime', 36.0))
            
            # Rule priority
            priority = int(request.form.get('priority', 10))
            
            # Department scope
            departments = request.form.get('departments')
            
            # Rule validity
            valid_from_str = request.form.get('valid_from')
            valid_until_str = request.form.get('valid_until')
            
            valid_from = None
            valid_until = None
            
            if valid_from_str:
                try:
                    valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format for valid from. Use YYYY-MM-DD format.', 'danger')
                    return redirect(url_for('overtime.add_rule'))
            
            if valid_until_str:
                try:
                    valid_until = datetime.strptime(valid_until_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format for valid until. Use YYYY-MM-DD format.', 'danger')
                    return redirect(url_for('overtime.add_rule'))
            
            # Create rule
            rule = OvertimeRule(
                name=name,
                description=description,
                daily_regular_hours=daily_regular_hours,
                weekday_multiplier=weekday_multiplier,
                weekend_multiplier=weekend_multiplier,
                holiday_multiplier=holiday_multiplier,
                apply_on_weekday=apply_on_weekday,
                apply_on_weekend=apply_on_weekend,
                apply_on_holiday=apply_on_holiday,
                night_shift_start_time=night_shift_start_time,
                night_shift_end_time=night_shift_end_time,
                night_shift_multiplier=night_shift_multiplier,
                max_daily_overtime=max_daily_overtime,
                max_weekly_overtime=max_weekly_overtime,
                max_monthly_overtime=max_monthly_overtime,
                priority=priority,
                departments=departments,
                valid_from=valid_from,
                valid_until=valid_until,
                is_active=True
            )
            
            db.session.add(rule)
            db.session.commit()
            
            flash(f'Overtime rule "{name}" created successfully', 'success')
            return redirect(url_for('overtime.rules'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating rule: {str(e)}', 'danger')
    
    # Get all departments for dropdown
    departments = db.session.query(Employee.department).filter(
        Employee.department.isnot(None)
    ).distinct().order_by(Employee.department).all()
    
    unique_departments = [dept[0] for dept in departments if dept[0]]
    
    return render_template('overtime/add_rule.html', departments=unique_departments)

@bp.route('/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_rule(rule_id):
    """Edit an existing overtime rule"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get rule
    rule = OvertimeRule.query.get_or_404(rule_id)
    
    if request.method == 'POST':
        try:
            # Get form data
            rule.name = request.form.get('name')
            rule.description = request.form.get('description')
            
            # Time thresholds
            rule.daily_regular_hours = float(request.form.get('daily_regular_hours', 8.0))
            
            # Multipliers
            rule.weekday_multiplier = float(request.form.get('weekday_multiplier', 1.5))
            rule.weekend_multiplier = float(request.form.get('weekend_multiplier', 2.0))
            rule.holiday_multiplier = float(request.form.get('holiday_multiplier', 2.5))
            
            # Applicable days
            rule.apply_on_weekday = 'apply_on_weekday' in request.form
            rule.apply_on_weekend = 'apply_on_weekend' in request.form
            rule.apply_on_holiday = 'apply_on_holiday' in request.form
            
            # Night shift settings
            rule.night_shift_multiplier = float(request.form.get('night_shift_multiplier', 1.2))
            night_shift_start_time_str = request.form.get('night_shift_start_time')
            night_shift_end_time_str = request.form.get('night_shift_end_time')
            
            # Parse time strings
            if night_shift_start_time_str and night_shift_end_time_str:
                try:
                    rule.night_shift_start_time = datetime.strptime(night_shift_start_time_str, '%H:%M').time()
                    rule.night_shift_end_time = datetime.strptime(night_shift_end_time_str, '%H:%M').time()
                except ValueError:
                    flash('Invalid time format for night shift times. Use HH:MM format.', 'danger')
                    return redirect(url_for('overtime.edit_rule', rule_id=rule_id))
            else:
                rule.night_shift_start_time = None
                rule.night_shift_end_time = None
            
            # Maximum limits
            rule.max_daily_overtime = float(request.form.get('max_daily_overtime', 4.0))
            rule.max_weekly_overtime = float(request.form.get('max_weekly_overtime', 15.0))
            rule.max_monthly_overtime = float(request.form.get('max_monthly_overtime', 36.0))
            
            # Rule priority
            rule.priority = int(request.form.get('priority', 10))
            
            # Department scope
            rule.departments = request.form.get('departments')
            
            # Rule validity
            valid_from_str = request.form.get('valid_from')
            valid_until_str = request.form.get('valid_until')
            
            if valid_from_str:
                try:
                    rule.valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format for valid from. Use YYYY-MM-DD format.', 'danger')
                    return redirect(url_for('overtime.edit_rule', rule_id=rule_id))
            else:
                rule.valid_from = None
            
            if valid_until_str:
                try:
                    rule.valid_until = datetime.strptime(valid_until_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format for valid until. Use YYYY-MM-DD format.', 'danger')
                    return redirect(url_for('overtime.edit_rule', rule_id=rule_id))
            else:
                rule.valid_until = None
            
            # Rule status
            rule.is_active = 'is_active' in request.form
            
            db.session.commit()
            
            flash(f'Overtime rule "{rule.name}" updated successfully', 'success')
            return redirect(url_for('overtime.rules'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating rule: {str(e)}', 'danger')
    
    # Get all departments for dropdown
    departments = db.session.query(Employee.department).filter(
        Employee.department.isnot(None)
    ).distinct().order_by(Employee.department).all()
    
    unique_departments = [dept[0] for dept in departments if dept[0]]
    
    return render_template('overtime/edit_rule.html', rule=rule, departments=unique_departments)

@bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    """Delete an overtime rule"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get rule
    rule = OvertimeRule.query.get_or_404(rule_id)
    
    try:
        # Get rule name for notification
        rule_name = rule.name
        
        # Delete rule
        db.session.delete(rule)
        db.session.commit()
        
        flash(f'Overtime rule "{rule_name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting rule: {str(e)}', 'danger')
    
    return redirect(url_for('overtime.rules'))

@bp.route('/rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_rule(rule_id):
    """Toggle rule active status"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get rule
    rule = OvertimeRule.query.get_or_404(rule_id)
    
    try:
        # Toggle status
        rule.is_active = not rule.is_active
        db.session.commit()
        
        status = 'activated' if rule.is_active else 'deactivated'
        flash(f'Overtime rule "{rule.name}" {status} successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating rule status: {str(e)}', 'danger')
    
    return redirect(url_for('overtime.rules'))

@bp.route('/recalculate', methods=['GET', 'POST'])
@login_required
def recalculate():
    """Recalculate overtime for specific date or employee"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            recalc_type = request.form.get('recalc_type')
            
            if recalc_type == 'date':
                date_str = request.form.get('date')
                if not date_str:
                    flash('Please select a date', 'danger')
                    return redirect(url_for('overtime.recalculate'))
                
                try:
                    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format. Use YYYY-MM-DD format.', 'danger')
                    return redirect(url_for('overtime.recalculate'))
                
                # Process records for this date
                count = process_attendance_records(date=target_date, recalculate=True)
                flash(f'Successfully recalculated overtime for {count} records on {target_date}', 'success')
                
            elif recalc_type == 'employee':
                employee_id = request.form.get('employee_id')
                if not employee_id:
                    flash('Please select an employee', 'danger')
                    return redirect(url_for('overtime.recalculate'))
                
                # Process records for this employee
                count = process_attendance_records(employee_id=employee_id, recalculate=True)
                
                # Get employee details for notification
                employee = Employee.query.get(employee_id)
                if employee:
                    flash(f'Successfully recalculated overtime for {count} records of {employee.name}', 'success')
                else:
                    flash(f'Successfully recalculated overtime for {count} records', 'success')
                
            elif recalc_type == 'all':
                # Confirm with a token to prevent accidental recalculation
                if request.form.get('confirm_token') != 'recalculate-all-overtime':
                    flash('Invalid confirmation token for recalculating all records', 'danger')
                    return redirect(url_for('overtime.recalculate'))
                
                # Process all records - this could take a while
                count = process_attendance_records(recalculate=True)
                flash(f'Successfully recalculated overtime for {count} records', 'success')
            
            return redirect(url_for('overtime.index'))
            
        except Exception as e:
            flash(f'Error recalculating overtime: {str(e)}', 'danger')
    
    # Get employees for dropdown
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    return render_template('overtime/recalculate.html', employees=employees)

@bp.route('/employee/<int:employee_id>', methods=['GET'])
@login_required
def employee_overtime(employee_id):
    """Show overtime details for a specific employee"""
    
    # Get employee
    employee = Employee.query.get_or_404(employee_id)
    
    # Check permissions - admins can view any employee, users can only view themselves
    if not current_user.is_admin and (not current_user.id or current_user.id != employee.user_id):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get date range from query parameters
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    
    from_date = None
    to_date = None
    
    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid from date format. Use YYYY-MM-DD format.', 'danger')
    
    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid to date format. Use YYYY-MM-DD format.', 'danger')
    
    # Default to current month if no dates specified
    if not from_date:
        from_date = date.today().replace(day=1)
    
    if not to_date:
        # Last day of the same month
        next_month = from_date.replace(month=from_date.month + 1 if from_date.month < 12 else 1,
                                       year=from_date.year if from_date.month < 12 else from_date.year + 1)
        to_date = (next_month - timedelta(days=1))
    
    # Get overtime records
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= from_date,
        AttendanceRecord.date <= to_date,
        AttendanceRecord.overtime_hours > 0
    ).order_by(AttendanceRecord.date).all()
    # Calculate summary statistics
    total_hours = sum(r.overtime_hours or 0 for r in records)
    total_weekday_overtime = sum(r.regular_overtime_hours or 0 for r in records)
    total_weekend_overtime = sum(r.weekend_overtime_hours or 0 for r in records)
    total_holiday_overtime = sum(r.holiday_overtime_hours or 0 for r in records)
    
    weighted_sum = sum((r.overtime_hours or 0) * (r.overtime_rate or 0) for r in records)
    avg_rate = weighted_sum / total_hours if total_hours > 0 else 0
    
    # Group by week for weekly summary
    weekly_summary = {}
    for record in records:
        # Get the Monday of the week
        week_start = record.date - timedelta(days=record.date.weekday())
        week_key = week_start.strftime('%Y-%m-%d')
        
        if week_key not in weekly_summary:
            weekly_summary[week_key] = {
                'start_date': week_start,
                'end_date': week_start + timedelta(days=6),
                'hours': 0,
                'weekday_hours': 0,
                'weekend_hours': 0,
                'holiday_hours': 0,
                'weighted_sum': 0
            }
        
        weekly_summary[week_key]['hours'] += record.overtime_hours or 0
        weekly_summary[week_key]['weekday_hours'] += record.regular_overtime_hours or 0
        weekly_summary[week_key]['weekend_hours'] += record.weekend_overtime_hours or 0
        weekly_summary[week_key]['holiday_hours'] += record.holiday_overtime_hours or 0
        weekly_summary[week_key]['weighted_sum'] += (record.overtime_hours or 0) * (record.overtime_rate or 0)
    
    # Calculate average rate for each week
    for week in weekly_summary.values():
        week['avg_rate'] = week['weighted_sum'] / week['hours'] if week['hours'] > 0 else 0
    
    # Sort weeks by start date
    weeks = sorted(weekly_summary.values(), key=lambda w: w['start_date'])
    
    return render_template(
        'overtime/employee_detail.html', 
        employee=employee,
        records=records,
        from_date=from_date,
        to_date=to_date,
        total_hours=total_hours,
        total_weekday_overtime=total_weekday_overtime,
        total_weekend_overtime=total_weekend_overtime,
        total_holiday_overtime=total_holiday_overtime,
        avg_rate=avg_rate,
        weeks=weeks
    )



@bp.route('/send_overtime_to_odoo', methods=['POST'])
def send_overtime_to_odoo():
    try:
        data = request.get_json()
        run_id = 350
        overtime_data = data.get('overtime_data')

        # Odoo credentials
        URL = 'http://sib.mir.ae:8050'
        DB = 'aalmir__2025_05_06'
        USER = 'admin'
        PASSWORD = '123'

        # Authenticate with Odoo
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USER, PASSWORD, {})

        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        result = models.execute_kw(DB, uid, PASSWORD,
            'hr.payslip.run', 'set_overtime_for_payslip_run',
            [run_id, overtime_data]
        )

        return jsonify({'message': 'Data sent successfully to Odoo.', 'result': result}), 200

    except Exception as e:
        return jsonify({'message': 'Error sending data.', 'error': str(e)}), 500


@bp.route('/report', methods=['GET'])
@login_required
def report():
    """Show overtime report"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get date range from query parameters
    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    department = request.args.get('department')
    
    from_date = None
    to_date = None
    
    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid from date format. Use YYYY-MM-DD format.', 'danger')
    
    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid to date format. Use YYYY-MM-DD format.', 'danger')
    
    # Default to current month if no dates specified
    if not from_date:
        from_date = date.today().replace(day=1)
    
    if not to_date:
        next_month = from_date.replace(month=from_date.month + 1 if from_date.month < 12 else 1,
                                      year=from_date.year if from_date.month < 12 else from_date.year + 1)
        to_date = (next_month - timedelta(days=1))
    
    # Build query for overtime report including absent days count
    query = db.session.query(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.department,
        func.coalesce(func.sum(AttendanceRecord.overtime_hours), 0).label('total_overtime'),
        func.coalesce(func.sum(AttendanceRecord.regular_overtime_hours), 0).label('weekday_overtime'),
        func.coalesce(func.sum(AttendanceRecord.weekend_overtime_hours), 0).label('weekend_overtime'),
        func.coalesce(func.sum(AttendanceRecord.overt_time_weighted), 0).label('overt_time_weighted'),
        func.coalesce(func.sum(
            case(
                (AttendanceRecord.status == 'absent', 1),
                else_=0
            )
        ), 0).label('absent_days'),
        func.coalesce(func.sum(AttendanceRecord.holiday_overtime_hours), 0).label('holiday_overtime'),
        func.coalesce(func.avg(AttendanceRecord.overtime_rate), 0).label('avg_rate')
    ).join(
        AttendanceRecord, Employee.id == AttendanceRecord.employee_id
    ).filter(
        AttendanceRecord.date >= from_date,
        AttendanceRecord.date <= to_date,
        Employee.is_active == True
    )
    
    # Apply department filter if specified
    if department:
        query = query.filter(Employee.department == department)
    
    # Group and order results
    results = query.group_by(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.department
    ).order_by(
        desc('total_overtime')
    ).all()
    
    # Calculate totals
    total_overtime = sum(r.total_overtime or 0 for r in results)
    total_weekday_overtime = sum(r.weekday_overtime or 0 for r in results)
    total_absents = sum(r.absent_days or 0 for r in results)
    total_weekend_overtime = sum(r.weekend_overtime or 0 for r in results)
    total_holiday_overtime = sum(r.holiday_overtime or 0 for r in results)
    
    # Get departments for dropdown
    departments = db.session.query(Employee.department).filter(
        Employee.department.isnot(None)
    ).distinct().order_by(Employee.department).all()
    
    unique_departments = [dept[0] for dept in departments if dept[0]]
    
    return render_template(
        'overtime/report.html', 
        results=results,
        from_date=from_date,
        to_date=to_date,
        total_overtime=total_overtime,
        total_absents=total_absents,
        total_weekday_overtime=total_weekday_overtime,
        total_weekend_overtime=total_weekend_overtime,
        total_holiday_overtime=total_holiday_overtime,
        departments=unique_departments,
        selected_department=department
    )
