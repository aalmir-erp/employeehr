"""
Routes for managing overtime rules and calculations
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
#from flask import request, jsonify
import xmlrpc.client

from flask_login import login_required, current_user
from sqlalchemy import func, desc,case
from models import db, OvertimeRule, AttendanceRecord, Employee, BonusEvaluation, BonusSubmission
from utils.overtime_engine import process_attendance_records, calculate_monthly_overtime, calculate_weekly_overtime
import requests
from models import PayrollStatus  # adjust import as per your project structure
import json


bp = Blueprint('overtime', __name__)

@bp.route('/')
@login_required
def index():
    """Show overview of overtime rules and statistics"""
    if not current_user.is_admin and  not current_user.has_role('hr'):
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
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Get all rules
    rules = OvertimeRule.query.order_by(OvertimeRule.priority.desc()).all()
    
    return render_template('overtime/rules.html', rules=rules)

@bp.route('/rules/add', methods=['GET', 'POST'])
@login_required
def add_rule():
    """Add a new overtime rule"""
    if not current_user.is_admin and  not current_user.has_role('hr'):
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
    if not current_user.is_admin and  not current_user.has_role('hr'):
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
    if not current_user.is_admin and  not current_user.has_role('hr'):
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
    if not current_user.is_admin and  not current_user.has_role('hr'):
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
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            recalc_type = request.form.get('recalculate_type')
            from_date = request.form.get('from_date')
            to_date = request.form.get('to_date')
            print (" get here recalculated -----------------------------------")
            print (recalc_type)
            
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
                print (" get here recalculated --------------2323---------------------")

                employee_id = request.form.get('employee_id')
                if not employee_id:
                    flash('Please select an employee', 'danger')
                    return redirect(url_for('overtime.recalculate'))
                
                # Process records for this employee
                count = process_attendance_records(date_from=from_date, date_to=to_date, employee_id=employee_id, recalculate=True)
                
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
    employee = Employee.query.get_or_404(employee_id)

    if not current_user.is_admin and not current_user.has_role('hr') and (not current_user.id or current_user.id != employee.user_id):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))

    from_date_str = request.args.get('from_date')
    to_date_str = request.args.get('to_date')
    from_date = None
    to_date = None

    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid from date format.', 'danger')

    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid to date format.', 'danger')

    if not from_date:
        from_date = date.today().replace(day=1)
    if not to_date:
        next_month = from_date.replace(month=from_date.month + 1 if from_date.month < 12 else 1,
                                       year=from_date.year if from_date.month < 12 else from_date.year + 1)
        to_date = next_month - timedelta(days=1)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee_id,
        AttendanceRecord.date >= from_date,
        AttendanceRecord.date <= to_date,
        AttendanceRecord.overtime_hours > 0
    ).order_by(AttendanceRecord.date).all()

    # Apply eligibility checks
    for r in records:
        r.eligible_regular_overtime_hours = r.regular_overtime_hours if employee.eligible_for_weekday_overtime else 0
        r.eligible_weekend_overtime_hours = r.weekend_overtime_hours if employee.eligible_for_weekend_overtime else 0
        r.eligible_holiday_overtime_hours = r.holiday_overtime_hours if employee.eligible_for_holiday_overtime else 0
        r.eligible_overtime_hours = (
            r.eligible_regular_overtime_hours +
            r.eligible_weekend_overtime_hours +
            r.eligible_holiday_overtime_hours
        )
        r.eligible_overt_time_weighted = r.eligible_overtime_hours * (r.overtime_rate or 0)

    total_hours = sum(r.eligible_overtime_hours for r in records)
    total_weekday_overtime = sum(r.eligible_regular_overtime_hours for r in records)
    total_weekend_overtime = sum(r.eligible_weekend_overtime_hours for r in records)
    total_holiday_overtime = sum(r.eligible_holiday_overtime_hours for r in records)
    weighted_sum = sum(r.eligible_overt_time_weighted for r in records)
    avg_rate = weighted_sum / total_hours if total_hours > 0 else 0

    weekly_summary = {}
    for r in records:
        week_start = r.date - timedelta(days=r.date.weekday())
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

        weekly_summary[week_key]['hours'] += r.eligible_overtime_hours
        weekly_summary[week_key]['weekday_hours'] += r.eligible_regular_overtime_hours
        weekly_summary[week_key]['weekend_hours'] += r.eligible_weekend_overtime_hours
        weekly_summary[week_key]['holiday_hours'] += r.eligible_holiday_overtime_hours
        weekly_summary[week_key]['weighted_sum'] += r.eligible_overt_time_weighted

    for week in weekly_summary.values():
        week['avg_rate'] = week['weighted_sum'] / week['hours'] if week['hours'] > 0 else 0

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

@bp.route('/fetch_pay_roll_from_odoo', methods=['POST'])
def fetch_pay_roll_from_odoo():


    data = request.get_json()
    run_id = 350
    overtime_data = data.get('overtime_data')
    from_date = data.get('from_date')
    to_date = data.get('to_date')

    print(overtime_data )

    payload = {
    'employee_ids': overtime_data,
    'run_id': run_id,
    'from_date': from_date,
    'to_date': to_date
    }

    # Send POST request to Odoo controller (adjust URL accordingly)
    try:

        response = requests.post('http://erp.mir.ae:8069/payroll/fetch_payroll_id', json=payload)

        odoo_response = response.json()

        response.raise_for_status()
    except Exception as e:
        return {'error': str(e)}, 500

    payroll_data = odoo_response.get('result', [])

    # print

    for item in payroll_data:
        odoo_id = item['employee_id']
        payroll_number = item['payroll_number']
        payroll_id = item['payroll_id']
        payroll_date = datetime.strptime(item['payroll_date'], '%Y-%m-%d').date()
        state = item['state']

        # Optional: prevent duplicates (e.g., same emp, same payroll_id)
        employee = Employee.query.filter_by(odoo_id=odoo_id).first()

        existing = PayrollStatus.query.filter_by(employee_id=employee.id, payroll_id_odoo=payroll_id).first()
        # if existing:
        #     continue  # Skip existing record

        new_status = PayrollStatus(
            employee_id=employee.id,
            payroll_id_odoo=payroll_id,
            payroll_name=payroll_number,
            payroll_date=payroll_date,
            odoo_status='pending',
            status='created'
        )
        db.session.add(new_status)

    db.session.commit()

    return {'message': 'Payroll status records saved successfully.', 'count': len(payroll_data)}



@bp.route('/send_overtime_to_odoo', methods=['POST'])
def send_overtime_to_odoo():
    # if 1:

    send_scope = request.form.get('send_scope')

    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    is_overtime = request.form.get('is_overtime')
    # is_payroll = request.form.get('is_payroll')
    is_bonus = request.form.get('is_bonus')
    is_leave = request.form.get('is_leave')
    
    if send_scope =='selected':
        raw_data = request.form.get('selected_data')
        selected_employees = json.loads(raw_data) if raw_data else []
        print(selected_employees)
        # 9/0
    else:
        approved_evals = db.session.query(BonusEvaluation).join(BonusSubmission).filter(
        BonusSubmission.status == 'approved'
        ).order_by(
            BonusEvaluation.employee_id,
            desc(BonusSubmission.submitted_at)  # latest first
        ).all()

        # Step 1: Get the latest approved submission
        latest_submission = db.session.query(BonusSubmission).filter(
            BonusSubmission.status == 'approved'
        ).order_by(BonusSubmission.submitted_at.desc()).first()

        # Step 2: Group evaluation values by employee
        grouped_scores = []
        if latest_submission:
            grouped_scores = db.session.query(
                BonusEvaluation.employee_id,
                func.sum(BonusEvaluation.value).label('total_score')
            ).filter(
                BonusEvaluation.submission_id == latest_submission.id
            ).group_by(BonusEvaluation.employee_id).all()

            # Optional: Convert to dicts for JSON/API
            grouped_scores = [
                {'employee_id': emp_id, 'total_score': score}
                for emp_id, score in grouped_scores
            ]

     
            ranked_subq = db.session.query(
            BonusSubmission.id.label('submission_id'),
            BonusSubmission.department,
            BonusSubmission.submitted_at,
            func.rank().over(
                partition_by=BonusSubmission.department,
                order_by=BonusSubmission.submitted_at.desc()
            ).label('rnk')
            ).filter(
                BonusSubmission.status == 'approved'
            ).subquery()

            # Filter only the latest (rank = 1) for each department
            latest_submissions = db.session.query(ranked_subq.c.submission_id, ranked_subq.c.department).filter(
                ranked_subq.c.rnk == 1
            ).all()

            submission_ids = [row.submission_id for row in latest_submissions]
            bonus_point_map = {
            emp_id: score for emp_id, score in db.session.query(
                BonusEvaluation.employee_id,
                func.sum(BonusEvaluation.value)
            ).filter(
                BonusEvaluation.submission_id.in_(submission_ids)
            ).group_by(BonusEvaluation.employee_id).all()
        }

            # Step 2: Keep only the latest per employee
            latest_eval_map = {}
            status_eval_map = {}



            for bonus in approved_evals:
                emp_id = bonus.employee_id
                if emp_id not in latest_eval_map:
                    latest_eval_map[emp_id] = [bonus.value, bonus.id] # keep first (latest due to ordering)
                    status_eval_map [emp_id] = bonus.odoo_status

            # Result: {employee_id: latest approved value}
            print(bonus_point_map)

            bonus_point_subq = db.session.query(
            BonusEvaluation.employee_id.label("employee_id"),
            func.sum(BonusEvaluation.value).label("total_score")
        ).filter(
            BonusEvaluation.submission_id.in_(submission_ids)
        ).group_by(
            BonusEvaluation.employee_id
        ).subquery()

            # Subquery: latest payslip id per employee
            latest_payslip_subq = (
                db.session.query(
                    PayrollStatus.employee_id,
                    func.max(PayrollStatus.id).label("latest_payslip_id")
                )
                .group_by(PayrollStatus.employee_id)
                .subquery()
            )

            # Main query
            results = (
                db.session.query(
                    Employee.id.label("emp_id"),
                    Employee.employee_code,
                    Employee.odoo_id,
                    func.coalesce(bonus_point_subq.c.total_score, 0).label("bonus_point"),
                    func.coalesce(latest_payslip_subq.c.latest_payslip_id, 0).label("payslip_id"),
                )
                .outerjoin(bonus_point_subq, Employee.id == bonus_point_subq.c.employee_id)
                .outerjoin(latest_payslip_subq, Employee.id == latest_payslip_subq.c.employee_id)
                .all()
            )

            selected_employees = [
                {
                    "emp_id": r.emp_id,
                    "employee_code": r.employee_code,
                    "odoo_id": r.odoo_id,
                    "bonus_point": r.bonus_point,
                    "payslip_id": r.payslip_id,
                }
                for r in results
            ]

            print(selected_employees)

    absent = []
    action_dict = {'is_bonus':is_bonus,'is_overtime':is_overtime, 'is_leave':is_leave}



    for item in selected_employees:
        emp_id = item['emp_id']
        print (" ------------------------------------------------------------------JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ")
        print (item)
        
        empl_absent = AttendanceRecord.query.filter(
            AttendanceRecord.date >= from_date,
            AttendanceRecord.employee_id == emp_id,
            AttendanceRecord.date <= to_date,
            AttendanceRecord.status == 'absent',
        ).order_by(AttendanceRecord.date).all()

        for record in empl_absent:
            employee = Employee.query.filter_by(id=record.employee_id).first()
            if not employee or not employee.odoo_id:
                print(f"❌ Skipping: No Odoo ID for employee_id {record.employee_id}")
                continue

            odoo_employee_id = employee.odoo_id
            leave_date_str = str(record.date)
            absent.append({'odoo_employee_id':odoo_employee_id,'leave_date_str':leave_date_str})



        # item['absent_days'] = len(empl_absent)
        

        
        ot = float(item.get('weighted_ot', 0))
        bonus = [item.get('bonus_point'), 1]
        payslip = item.get('payslip_id')

    print(selected_employees, "selected_employees")

    # res = requests.post("http://erp.mir.ae:8069/update_overtime_from_ams", json={'payroll': selected_employees,'absent':absent,'action_dict':action_dict}, timeout=50)

    

    response = json.loads(res.text)
    update_odoo_status_from_response(response)


    return redirect(url_for('overtime.report'))
    # return None 

        # process as needed...

    # return redirectt(url_for('some_view'))
    if False:

        data = request.get_json()
        run_id = 350
        overtime_data = data.get('overtime_data')

        # Odoo credentials
        URL = 'http://sib.mir.ae:8050'
        DB = 'july_04'
        USER = 'admin'
        PASSWORD = '123'

        print (overtime_data,"overtime_data")
        print('ssssssssssssssss')
        from_date = '2025-01-01'
        to_date = '2025-05-31'
        absent_data = {}

        for entry in overtime_data:
            code = entry['employee_id']
            # emp_id = code_id_map.get(code)
            print

            if not code:
                continue  # Skip if employee code not found
            try:
                emp_id = int(code.replace('EMP', '').lstrip('0'))  # "EMP0725" -> 725
            except ValueError:
                continue  #
            print (emp_id,from_date , to_date, " llllllllllllllllllllllll" )
            absent_records = AttendanceRecord.query.filter(
                AttendanceRecord.employee_id == emp_id,
                AttendanceRecord.created_at >= from_date,
                AttendanceRecord.created_at <= to_date,
                AttendanceRecord.status == 'absent'
            ).order_by(AttendanceRecord.date).all()

            absent_data[code] = absent_records

        print (absent_data)




    #     records = AttendanceRecord.query.filter(
    #     AttendanceRecord.employee_id == employee_id,
    #     AttendanceRecord.date >= from_date,
    #     AttendanceRecord.date <= to_date,
    #     AttendanceRecord.overtime_hours > 0
    # ).order_by(AttendanceRecord.date).all()

        return

        # Authenticate with Odoo
        # common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        # uid = common.authenticate(DB, USER, PASSWORD, {})

        # models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        # result = models.execute_kw(DB, uid, PASSWORD,
        #     'hr.payslip.run', 'set_overtime_for_payslip_run',
        #     [run_id, overtime_data]
        # )

        return jsonify({'message': 'Data sent successfully to Odoo.', 'result': result}), 200

    # except Exception as e:
        # return jsonify({'message': 'Error sending data.', 'error': str(e)}), 500

def update_odoo_status_from_response(response):
    if response.get("result", {}).get("status") == "success":
        data_list = response["result"].get("data", [])
        for record in data_list:
            for emp_id_str, result_list in record.items():
                if result_list and result_list[0]:  # Check if first value is True
                    emp_id = int(emp_id_str)

                    # Query and update PayrollStatus
                    status_record = PayrollStatus.query.filter_by(employee_id=emp_id).first()
                    if status_record:
                        status_record.status = "updated"
                        db.session.add(status_record)  # optional, but safe

                # if len(result_list) >= 3 and result_list[1] is True:
                #     bonus_id = result_list[2]
                #     print ( "bouns id ---------------", bonus_id)
                #     bonus_record = BonusEvaluation.query.get(bonus_id)
                #     if bonus_record:
                #         bonus_record.odoo_status = "updated"
                #         db.session.add(bonus_record)

        db.session.commit()


@bp.route('/report', methods=['GET'])
@login_required
def report():
    """Show overtime report"""
    if not current_user.is_admin and not current_user.has_role('hr'):
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Date range filters
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
    
    # Defaults if no dates
    if not from_date:
        from_date = date.today().replace(day=1)
    if not to_date:
        next_month = from_date.replace(month=from_date.month + 1 if from_date.month < 12 else 1,
                                      year=from_date.year if from_date.month < 12 else from_date.year + 1)
        to_date = (next_month - timedelta(days=1))

    # Fetch payroll data in the same date range
    payroll_data = PayrollStatus.query.filter(
        PayrollStatus.payroll_date >= from_date,
        PayrollStatus.payroll_date <= to_date
    ).all()

    # Create mapping: employee_id => payroll_name
    payroll_map_name = {p.employee_id: p.payroll_name for p in payroll_data}
    payroll_map_state = {p.employee_id: p.status for p in payroll_data}
    payroll_mappayroll_id_odoo = {p.employee_id: p.payroll_id_odoo for p in payroll_data}
    

    approved_evals = db.session.query(BonusEvaluation).join(BonusSubmission).filter(
    BonusSubmission.status == 'approved'
    ).order_by(
        BonusEvaluation.employee_id,
        desc(BonusSubmission.submitted_at)  # latest first
    ).all()

    # Step 1: Get the latest approved submission
    # latest_submission = db.session.query(BonusSubmission).filter(
    #     BonusSubmission.status == 'approved'
    # ).order_by(BonusSubmission.submitted_at.desc()).first()

    # Step 2: Group evaluation values by employee
    # grouped_scores = []
    # if latest_submission:
    #     grouped_scores = db.session.query(
    #         BonusEvaluation.employee_id,
    #         func.sum(BonusEvaluation.value).label('total_score')
    #     ).filter(
    #         BonusEvaluation.submission_id == latest_submission.id
    #     ).group_by(BonusEvaluation.employee_id).all()

    #     # Optional: Convert to dicts for JSON/API
    #     grouped_scores = [
    #         {'employee_id': emp_id, 'total_score': score}
    #         for emp_id, score in grouped_scores
    #     ]

 
    ranked_subq = db.session.query(
    BonusSubmission.id.label('submission_id'),
    BonusSubmission.department,
    BonusSubmission.submitted_at,
    func.rank().over(
        partition_by=BonusSubmission.department,
        order_by=BonusSubmission.submitted_at.desc()
    ).label('rnk')
    ).filter(
        BonusSubmission.status == 'approved'
    ).subquery()

#     # Filter only the latest (rank = 1) for each department
    latest_submissions = db.session.query(ranked_subq.c.submission_id, ranked_subq.c.department).filter(
        ranked_subq.c.rnk == 1
    ).all()

    submission_ids = [row.submission_id for row in latest_submissions]
    bonus_point_map = {
    emp_id: score for emp_id, score in db.session.query(
        BonusEvaluation.employee_id,
        func.sum(BonusEvaluation.value)
    ).filter(
        BonusEvaluation.submission_id.in_(submission_ids)
    ).group_by(BonusEvaluation.employee_id).all()
}

    # Step 2: Keep only the latest per employee
    latest_eval_map = {}
    status_eval_map = {}

    for bonus in approved_evals:
        emp_id = bonus.employee_id
        if emp_id not in latest_eval_map:
            latest_eval_map[emp_id] = [bonus.value, bonus.id] # keep first (latest due to ordering)
            status_eval_map [emp_id] = bonus.odoo_status

    # Result: {employee_id: latest approved value}
    # print(bonus_point_map)
    print("ooooooooooooooooooooooooooooooooooooooooooooooooooooo")



    
    # Query with eligibility fields
    query = db.session.query(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.odoo_id,
        Employee.department,
        Employee.eligible_for_weekday_overtime,
        Employee.eligible_for_weekend_overtime,
        Employee.eligible_for_holiday_overtime,
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
    ).outerjoin(
        AttendanceRecord, Employee.id == AttendanceRecord.employee_id
    ).filter(
        AttendanceRecord.date >= from_date,
        AttendanceRecord.date <= to_date,
        Employee.is_active == True
    )

    print ('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk')
    
    if department:
        query = query.filter(Employee.department == department)
    
    results = query.group_by(
        Employee.id,
        Employee.name,
        Employee.employee_code,
        Employee.odoo_id,
        Employee.department,
        Employee.eligible_for_weekday_overtime,
        Employee.eligible_for_weekend_overtime,
        Employee.eligible_for_holiday_overtime
    ).order_by(
        desc('total_overtime')
    ).all()

    # print(results)
    
    # Calculate totals with eligibility check
    total_overtime = sum(r.total_overtime or 0 for r in results)
    total_weekday_overtime = sum(r.weekday_overtime if r.eligible_for_weekday_overtime else 0 for r in results)
    total_weekend_overtime = sum(r.weekend_overtime if r.eligible_for_weekend_overtime else 0 for r in results)
    total_holiday_overtime = sum(r.holiday_overtime if r.eligible_for_holiday_overtime else 0 for r in results)
    total_absents = sum(r.absent_days or 0 for r in results)
    
    # Get unique departments for dropdown
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
        total_weekday_overtime=total_weekday_overtime,
        total_weekend_overtime=total_weekend_overtime,
        total_holiday_overtime=total_holiday_overtime,
        total_absents=total_absents,
        departments=unique_departments,
        payroll_map_name=payroll_map_name,
        payroll_map_state=payroll_map_state,
        payroll_mappayroll_id_odoo=payroll_mappayroll_id_odoo,
        selected_department=department,
        bonus_point_map=bonus_point_map,
        status_eval_map=status_eval_map
    )


