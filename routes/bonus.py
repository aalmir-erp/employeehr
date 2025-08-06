"""
Routes for employee bonus management system
"""
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from collections import defaultdict, OrderedDict
from flask_login import login_required, current_user
from markupsafe import Markup
from sqlalchemy import func
import csv
from io import StringIO
import threading
import requests

from models import (
    db, User, Employee, Department, BonusQuestion, BonusEvaluationPeriod, 
    BonusSubmission, BonusEvaluation, BonusAuditLog, SystemConfig, BonusEvaluationHistory
)
from utils.decorators import role_required
from utils.wassenger import send_whatsapp_notifications

bp = Blueprint('bonus', __name__)


@bp.route('/')
@login_required
def index():
    """Bonus dashboard"""
    # Determine user role and redirect accordingly
    if current_user.has_role('hr'):
        return redirect(url_for('bonus.hr_dashboard'))
    elif current_user.has_role('supervisor'):
        return redirect(url_for('bonus.supervisor_dashboard'))
    else:
        flash('You do not have permission to access the bonus system.', 'warning')
        return redirect(url_for('index.index'))


@bp.route('/hr/dashboard')
@login_required
@role_required('hr')
def hr_dashboard():
    """HR bonus dashboard"""
    # Get all evaluation periods
    periods = BonusEvaluationPeriod.query.order_by(BonusEvaluationPeriod.start_date.desc()).all()
    
    # Get counts for different submission statuses
    submissions_stats = db.session.query(
        BonusSubmission.status, 
        func.count(BonusSubmission.id)
    ).group_by(BonusSubmission.status).all()
    
    # Format stats into a dictionary
    stats = {
        'total_periods': len(periods),
        'active_periods': sum(1 for p in periods if p.status in ['open', 'in_review']),
        'submitted': dict(submissions_stats).get('submitted', 0),
        'approved': dict(submissions_stats).get('approved', 0),
        'rejected': dict(submissions_stats).get('rejected', 0),
        'draft': dict(submissions_stats).get('draft', 0),
    }
    
    # Get list of departments with questions
    departments_with_questions = db.session.query(
        BonusQuestion.department, 
        func.count(BonusQuestion.id)
    ).filter(BonusQuestion.is_active == True).group_by(BonusQuestion.department).all()
    
    return render_template(
        'bonus/hr_dashboard.html',
        periods=periods,
        stats=stats,
        departments_with_questions=departments_with_questions
    )


@bp.route('/supervisor/dashboard')
@login_required
@role_required('supervisor')
def supervisor_dashboard():
    """Supervisor bonus dashboard"""
    # Get supervisor's department
    supervisor_department = None
    if hasattr(current_user, 'employee') and current_user.employee:
        supervisor_department = current_user.employee.department
    
    if not supervisor_department:
        flash('You are not assigned to a department.', 'warning')
        return redirect(url_for('index.index'))
    
    # Get active evaluation periods
    active_periods = BonusEvaluationPeriod.query.filter(
        BonusEvaluationPeriod.status.in_(['open', 'in_review'])
    ).order_by(BonusEvaluationPeriod.start_date.desc()).all()
    
    # Get this supervisor's submissions
    submissions = BonusSubmission.query.filter(
        BonusSubmission.department == supervisor_department,
        BonusSubmission.submitted_by == current_user.id
    ).order_by(BonusSubmission.created_at.desc()).all()
    
    # Get employees in supervisor's department
    department_employees = Employee.query.filter_by(
        department=supervisor_department,
        is_active=True,
        is_bonus=True
    ).order_by(Employee.name).all()
    
    return render_template(
        'bonus/supervisor_dashboard.html',
        active_periods=active_periods,
        submissions=submissions,
        department=supervisor_department,
        employees=department_employees
    )


# HR Routes for Question Management
@bp.route('/hr/questions')
@login_required
@role_required('hr')
def hr_questions():
    """HR question management"""
    # Get all departments
    departments = db.session.query(Employee.department).distinct().all()
    department_list = [d[0] for d in departments if d[0]]
    
    # Get all questions grouped by department
    questions = BonusQuestion.query.order_by(
        BonusQuestion.department, 
        BonusQuestion.id
    ).all()
    
    # Group questions by department
    questions_by_dept = {}
    for question in questions:
        if question.department not in questions_by_dept:
            questions_by_dept[question.department] = []
        questions_by_dept[question.department].append(question)
    
    return render_template(
        'bonus/hr_questions.html',
        departments=department_list,
        questions_by_dept=questions_by_dept
    )


@bp.route('/hr/question/add', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def add_question():
    """Add a new bonus question"""
    if request.method == 'POST':
        department = request.form.get('department')
        question_text = request.form.get('question_text')
        min_value = request.form.get('min_value', type=int)
        max_value = request.form.get('max_value', type=int)
        default_value = request.form.get('default_value', type=int)
        weight = request.form.get('weight', type=float)
        only_hr = 'only_hr' in request.form
        
        # Validate input
        if not department or not question_text:
            flash('Department and question text are required.', 'danger')
            return redirect(url_for('bonus.add_question'))
        
        if min_value is None or max_value is None or default_value is None:
            flash('Min, max, and default values must be integers.', 'danger')
            return redirect(url_for('bonus.add_question'))
        
        if weight is None:
            weight = 1.0
        
        if min_value >= max_value:
            flash('Min value must be less than max value.', 'danger')
            return redirect(url_for('bonus.add_question'))
        
        if default_value < min_value or default_value > max_value:
            flash('Default value must be between min and max values.', 'danger')
            return redirect(url_for('bonus.add_question'))
            
        # Note: We now allow negative values for min, max, and default
        
        # Create new question
        question = BonusQuestion(
            department=department,
            question_text=question_text,
            min_value=min_value,
            max_value=max_value,
            default_value=default_value,
            weight=weight,
            only_hr=only_hr,
            created_by=current_user.id
        )
        
        db.session.add(question)
        db.session.commit()
        
        flash(f'Question "{question_text}" added successfully.', 'success')
        return redirect(url_for('bonus.hr_questions'))
    
    # GET request
    departments = db.session.query(Employee.department).distinct().all()
    department_list = [d[0] for d in departments if d[0]]
    
    return render_template(
        'bonus/add_question.html',
        departments=department_list
    )


@bp.route('/hr/question/<int:question_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def edit_question(question_id):
    """Edit an existing bonus question"""
    question = BonusQuestion.query.get_or_404(question_id)
    
    if request.method == 'POST':
        department = request.form.get('department')
        question_text = request.form.get('question_text')
        min_value = request.form.get('min_value', type=int)
        max_value = request.form.get('max_value', type=int)
        default_value = request.form.get('default_value', type=int)
        weight = request.form.get('weight', type=float)
        is_active = 'is_active' in request.form
        only_hr = 'only_hr' in request.form
        
        # Validate input
        if not department or not question_text:
            flash('Department and question text are required.', 'danger')
            return redirect(url_for('bonus.edit_question', question_id=question_id))
        
        if min_value is None or max_value is None or default_value is None:
            flash('Min, max, and default values must be integers.', 'danger')
            return redirect(url_for('bonus.edit_question', question_id=question_id))
        
        if weight is None:
            weight = 1.0
        
        if min_value >= max_value:
            flash('Min value must be less than max value.', 'danger')
            return redirect(url_for('bonus.edit_question', question_id=question_id))
        
        if default_value < min_value or default_value > max_value:
            flash('Default value must be between min and max values.', 'danger')
            return redirect(url_for('bonus.edit_question', question_id=question_id))
            
        # Note: We now allow negative values for min, max, and default
        
        # Update question
        question.department = department
        question.question_text = question_text
        question.min_value = min_value
        question.max_value = max_value
        question.default_value = default_value
        question.weight = weight
        question.is_active = is_active
        question.only_hr = only_hr
        question.updated_at = datetime.now()
        
        db.session.commit()
        
        flash(f'Question "{question_text}" updated successfully.', 'success')
        return redirect(url_for('bonus.hr_questions'))
    
    # GET request
    departments = db.session.query(Employee.department).distinct().all()
    department_list = [d[0] for d in departments if d[0]]
    
    return render_template(
        'bonus/edit_question.html',
        question=question,
        departments=department_list
    )


# HR Routes for Evaluation Period Management
@bp.route('/hr/periods')
@login_required
@role_required('hr')
def hr_periods():
    """HR evaluation period management"""
    periods = BonusEvaluationPeriod.query.order_by(
        BonusEvaluationPeriod.start_date.desc()
    ).all()
    
    return render_template(
        'bonus/hr_periods.html',
        periods=periods
    )


@bp.route('/hr/period/add', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def add_period():
    """Add a new evaluation period"""
    if request.method == 'POST':
        name = request.form.get('name')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        # Validate input
        if not name or not start_date or not end_date:
            flash('Name, start date, and end date are required.', 'danger')
            return redirect(url_for('bonus.add_period'))
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('bonus.add_period'))
        
        if start_date >= end_date:
            flash('Start date must be before end date.', 'danger')
            return redirect(url_for('bonus.add_period'))
        
        # Create new period
        period = BonusEvaluationPeriod(
            name=name,
            start_date=start_date,
            end_date=end_date,
            created_by=current_user.id
        )
        
        db.session.add(period)
        db.session.commit()
        
        flash(f'Evaluation period "{name}" added successfully.', 'success')
        return redirect(url_for('bonus.hr_periods'))
    
    # GET request
    return render_template('bonus/add_period.html')


@bp.route('/hr/period/<int:period_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def edit_period(period_id):
    """Edit an evaluation period"""
    period = BonusEvaluationPeriod.query.get_or_404(period_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        status = request.form.get('status')
        
        # Validate input
        if not name or not start_date or not end_date or not status:
            flash('All fields are required.', 'danger')
            return redirect(url_for('bonus.edit_period', period_id=period_id))
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('bonus.edit_period', period_id=period_id))
        
        if start_date >= end_date:
            flash('Start date must be before end date.', 'danger')
            return redirect(url_for('bonus.edit_period', period_id=period_id))
        
        # Update period
        period.name = name
        period.start_date = start_date
        period.end_date = end_date
        period.status = status
        
        db.session.commit()
        
        flash(f'Evaluation period "{name}" updated successfully.', 'success')
        return redirect(url_for('bonus.hr_periods'))
    
    # GET request
    return render_template('bonus/edit_period.html', period=period)


# Routes for Supervisor Bonus Submissions
@bp.route('/supervisor/submit/<int:period_id>', methods=['GET', 'POST'])
@login_required
@role_required('supervisor')
def supervisor_submit(period_id):
    """Supervisor bonus submission form"""
    period = BonusEvaluationPeriod.query.get_or_404(period_id)
    
    # Check if period is open for submissions
    if period.status != 'open':
        flash('This evaluation period is not open for submissions.', 'warning')
        return redirect(url_for('bonus.supervisor_dashboard'))
    
    # Get supervisor's department
    supervisor_department = None
    if hasattr(current_user, 'employee') and current_user.employee:
        supervisor_department = current_user.employee.department
    
    if not supervisor_department:
        flash('You are not assigned to a department.', 'warning')
        return redirect(url_for('bonus.supervisor_dashboard'))
    
    # Check if supervisor already has a submission for this period
    existing_submission = BonusSubmission.query.filter_by(
        period_id=period_id,
        department=supervisor_department,
        submitted_by=current_user.id
    ).first()
    
    if existing_submission:
        if existing_submission.status == 'draft':
            # Continue editing draft
            return redirect(url_for('bonus.edit_submission', submission_id=existing_submission.id))
        else:
            flash('You already have a submission for this period.', 'info')
            return redirect(url_for('bonus.view_submission', submission_id=existing_submission.id))
    
    if request.method == 'POST':
        # Create new submission (draft)
        submission = BonusSubmission(
            period_id=period_id,
            department=supervisor_department,
            submitted_by=current_user.id,
            status='draft'
        )
        
        db.session.add(submission)
        db.session.commit()
        
        # Create audit log entry
        log = BonusAuditLog(
            submission_id=submission.id,
            action='created',
            user_id=current_user.id,
            notes=f'Draft submission created for {supervisor_department}, period {period.name}'
        )
        
        db.session.add(log)
        db.session.commit()
        
        flash('Draft submission created successfully. You can now add evaluations.', 'success')
        return redirect(url_for('bonus.edit_submission', submission_id=submission.id))
    
    # GET request - show confirmation form
    return render_template(
        'bonus/supervisor_submit_confirm.html',
        period=period,
        department=supervisor_department
    )


@bp.route('/submission/<int:submission_id>/save_score', methods=['POST'])
@login_required
def save_single_score(submission_id):
    """Save a single evaluation score via AJAX"""
    submission = BonusSubmission.query.get_or_404(submission_id)
    
    # Check permissions
    if not (current_user.has_role('supervisor') or current_user.has_role('hr')):
        return jsonify({'success': False, 'error': 'Permission denied'})
    
    if submission.status != 'draft':
        return jsonify({'success': False, 'error': 'Cannot edit submitted evaluations'})
    
    try:
        employee_id = int(request.form.get('employee_id'))
        question_id = int(request.form.get('question_id'))
        value = int(request.form.get('value'))
        
        # Validate score range
        question = BonusQuestion.query.get(question_id)
        if not question or value < question.min_value or value > question.max_value:
            return jsonify({'success': False, 'error': 'Invalid score value'})
        
        # Find or create evaluation
        evaluation = BonusEvaluation.query.filter_by(
            submission_id=submission_id,
            employee_id=employee_id,
            question_id=question_id
        ).first()
        
        if evaluation:
            evaluation.value = value
        else:
            evaluation = BonusEvaluation(
                submission_id=submission_id,
                employee_id=employee_id,
                question_id=question_id,
                value=value
            )
            db.session.add(evaluation)
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/submission/<int:submission_id>/edit', methods=['GET'])
@login_required
def edit_submission(submission_id):
    """Edit a bonus submission - UPDATED VERSION with remarks"""
    submission = BonusSubmission.query.get_or_404(submission_id)
    
    # Check permissions
    if not current_user.has_role('hr') and (submission.submitted_by != current_user.id):
        flash('You do not have permission to edit this submission.', 'danger')
        return redirect(url_for('bonus.index'))
    
    # Get employees in department
    employees = Employee.query.filter_by(
        department=submission.department,
        is_active=True,
        is_bonus=True
    ).order_by(Employee.name).all()
    
    # Get active questions for this department
    questions = BonusQuestion.query.filter_by(
        department=submission.department,
        is_active=True
    ).order_by(BonusQuestion.id).all()
    
    # Get evaluations
    evaluations = BonusEvaluation.query.filter_by(
        submission_id=submission.id
    ).all()
    
    # Organize evaluations in a matrix
    evaluation_matrix = {}
    employee_remarks_map = {}
    employee_status_map = {}

    for eval in evaluations:
        if eval.employee_id not in evaluation_matrix:
            evaluation_matrix[eval.employee_id] = {}
        
        # Store question answers
        if eval.question_id is not None:
            evaluation_matrix[eval.employee_id][eval.question_id] = eval
        
        # Store remarks separately
        if eval.remarks and eval.remarks.strip():
            employee_remarks_map[eval.employee_id] = eval.remarks.strip()

        if eval.emp_status and eval.emp_status.strip():
            employee_status_map[eval.employee_id] = eval.emp_status.strip()

    
    audit_logs = BonusAuditLog.query.filter_by(
        submission_id=submission.id
    ).order_by(BonusAuditLog.timestamp.desc()).all()
    
    return render_template(
        'bonus/edit_submission.html',
        submission=submission,
        employees=employees,
        questions=questions,
        evaluation_matrix=evaluation_matrix,
        employee_remarks_map=employee_remarks_map,
        employee_status_map=employee_status_map,
        audit_logs=audit_logs
    )



@bp.route('/api/evaluation/save', methods=['POST'])
@login_required
def save_evaluation():
    """API endpoint to save a single evaluation"""
    try:
        # Get JSON data
        data = request.json
        current_app.logger.debug(f"Received evaluation save request: {data}")
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400
        
        submission_id = data.get('submission_id')
        employee_id = data.get('employee_id') 
        question_id = data.get('question_id')
        value = data.get('value')
        
        current_app.logger.debug(f"Parsed data: submission_id={submission_id}, employee_id={employee_id}, question_id={question_id}, value={value}")
        
        if not all([submission_id, employee_id, question_id, value is not None]):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
        # Fetch submission
        submission = BonusSubmission.query.get_or_404(submission_id)
        
        # Check permissions
        if not current_user.has_role('hr') and (submission.submitted_by != current_user.id):
            return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
        
        # Check if submission is editable
        if submission.status not in ['draft', 'rejected']:
            return jsonify({'status': 'error', 'message': 'Submission is not editable'}), 400
        
        # Validate value
        question = BonusQuestion.query.get_or_404(question_id)
        if value < question.min_value or value > question.max_value:
            return jsonify({
                'status': 'error', 
                'message': f'Value must be between {question.min_value} and {question.max_value}'
            }), 400
        
        # Find or create evaluation
        evaluation = BonusEvaluation.query.filter_by(
            submission_id=submission_id,
            employee_id=employee_id,
            question_id=question_id
        ).first()
        
        if evaluation:
            old_value = evaluation.value
            evaluation.value = value
            evaluation.updated_at = datetime.now()
            
            # Create audit log entry
            log = BonusAuditLog(
                submission_id=submission_id,
                employee_id=employee_id,
                question_id=question_id,
                action='updated',
                old_value=old_value,
                new_value=value,
                user_id=current_user.id
            )
            
            db.session.add(log)
        else:
            evaluation = BonusEvaluation(
                submission_id=submission_id,
                employee_id=employee_id,
                question_id=question_id,
                value=value
            )
            
            db.session.add(evaluation)
            
            # Create audit log entry
            log = BonusAuditLog(
                submission_id=submission_id,
                employee_id=employee_id,
                question_id=question_id,
                action='created',
                new_value=value,
                user_id=current_user.id
            )
            
            db.session.add(log)
        
        db.session.commit()
        current_app.logger.debug(f"Successfully saved evaluation: employee_id={employee_id}, question_id={question_id}, value={value}")
        
        # Calculate total points for this employee
        employee_points = submission.calculate_total_points(employee_id)
        
        return jsonify({
            'status': 'success', 
            'message': 'Evaluation saved successfully',
            'total_points': employee_points.get(employee_id, 0)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error saving evaluation: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Failed to save evaluation'}), 500


@bp.route('/save_employee_remarks', methods=['POST'])
@login_required
def save_employee_remarks():
    print (" save_employee_remarks -----------")
    employee_id = request.form.get('employee_id')
    submission_id = request.form.get('submission_id')
    remarks = request.form.get('remarks')
    print ( remarks)

    # Find or update existing evaluation (depends on your schema)
    evaluation = BonusEvaluation.query.filter_by(
        employee_id=employee_id,
        submission_id=submission_id
    ).first()

    if evaluation:
        evaluation.remarks = remarks
    else:
        # Or insert new if required
        evaluation = BonusEvaluation(
            employee_id=employee_id,
            submission_id=submission_id,
            remarks=remarks,
            created_by=current_user.id
        )
        db.session.add(evaluation)

    db.session.commit()
    flash('Remarks saved successfully!', 'success')
    return redirect(request.referrer)



@bp.route('/save_single_evaluation', methods=['POST'])
@login_required
def save_single_evaluation():
    submission_id = request.form.get('submission_id')
    employee_id = request.form.get('employee_id')
    question_id = request.form.get('question_id')
    value = request.form.get('value')
    remarks = request.form.get('remarks')
    print(remarks,employee_id,question_id,value,"==============================>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<=======")

    if not all([submission_id, employee_id, question_id, value]):
        message = "Missing evaluation data."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, message=message), 400
        flash(message, "danger")
        return redirect(request.referrer or url_for('bonus.supervisor_dashboard'))

    try:
        value = float(value)
    except ValueError:
        message = "Invalid score value."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, message=message), 400
        flash(message, "danger")
        return redirect(request.referrer or url_for('bonus.supervisor_dashboard'))

    evaluation = BonusEvaluation.query.filter_by(
        submission_id=submission_id,
        employee_id=employee_id,
        question_id=question_id
    ).first()

    if evaluation:
        evaluation.value = value
    else:
        evaluation = BonusEvaluation(
            submission_id=submission_id,
            employee_id=employee_id,
            question_id=question_id,
            value=value
        )
        
        db.session.add(evaluation)

    try:
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=True)
        flash("Evaluation saved.", "success")
    except Exception as e:
        db.session.rollback()
        message = f"Error saving evaluation: {str(e)}"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, message=message), 500
        flash(message, "danger")

    return redirect(request.referrer or url_for('bonus.edit_submission', submission_id=submission_id))


@bp.route('/save-emp-status', methods=['POST'])
def save_emp_status():
    data = request.get_json()
    emp_id = data.get('employee_id')
    submission_id = data.get('submission_id')
    new_status = data.get('emp_status')

    if not emp_id or not submission_id:
        return jsonify({'message': 'Missing employee_id or submission_id'}), 400

    evaluation = BonusEvaluation.query.filter_by(
        employee_id=emp_id,
        submission_id=submission_id
    ).first()


    if evaluation:
        evaluation.emp_status = new_status
        db.session.commit()
        return jsonify({'message': 'Status updated'}), 200
    else:
        return jsonify({'message': 'Evaluation not found'}), 404

def save_evaluation_history(submission_id):
    evaluations = BonusEvaluation.query.filter_by(submission_id=submission_id).all()

    for eval in evaluations:
        history = BonusEvaluationHistory(
            submission_id=eval.submission_id,
            employee_id=eval.employee_id,
            question_id=eval.question_id,
            value=eval.value,
            notes=eval.notes,
            record_by=current_user.id,
            remarks=eval.remarks
            # odoo_status=eval.odoo_status  # optional: copy status too
        )
        db.session.add(history)

    db.session.commit()


@bp.route('/get_evaluation_history')
def get_evaluation_history():
    from collections import defaultdict

    employee_id = request.args.get('employee_id')
    submission_id = request.args.get('submission_id')

    evaluations = BonusEvaluationHistory.query.filter_by(
        employee_id=employee_id, submission_id=submission_id
    ).order_by(BonusEvaluationHistory.id.asc()).all()

    user_data = defaultdict(lambda: {
        'records': [],
        'latest': None,
        'remarks': None  
    })

    for e in evaluations:
        record_by = e.creator.employee.name if e.creator and e.creator.employee else 'Unknown'
        created_at = e.id  # Or use e.created_at if available

        # Initialize user_data structure
        if record_by not in user_data:
            user_data[record_by] = {
                'records': [],
                'remarks': None,
                'latest': None,
            }

        # Add question entry
        user_data[record_by]['records'].append({
            'question_id': e.question.question_text if e.question else '-',
            'value': e.value,
            'created_at': created_at
        })

        # Save remark separately
        if not user_data[record_by]['remarks'] and e.remarks:
            user_data[record_by]['remarks'] = {
                'question_id': 'Remarks',
                'value': e.remarks,
                'created_at': created_at
            }

        # Track latest creation time
        if not user_data[record_by]['latest'] or created_at > user_data[record_by]['latest']:
            user_data[record_by]['latest'] = created_at

    # Sort groups by latest date
    sorted_user_data = dict(
        sorted(user_data.items(), key=lambda item: item[1]['latest'], reverse=True)
    )

    # Final formatting
    final_data = []
    for record_by, user_info in sorted_user_data.items():
        records = user_info['records']

        # Append remarks at the end of records
        if user_info['remarks']:
            records.append(user_info['remarks'])

        final_data.append({
            'record_by': record_by,
            'records': records
        })
    return jsonify({'data': final_data})


@bp.route('/submission/<int:submission_id>/submit', methods=['POST'])
@login_required
def submit_evaluation(submission_id):
    """Submit a bonus evaluation for review"""
    submission = BonusSubmission.query.get_or_404(submission_id)
    print(submission,"ppppppppppppppppppppppppppppppppp")
    
    # Check permissions
    if submission.submitted_by != current_user.id:
        flash('You do not have permission to submit this evaluation.', 'danger')
        return redirect(url_for('bonus.index'))
    
    # Check if submission is editable
    if submission.status not in ['draft', 'rejected']:
        flash('This submission has already been submitted.', 'warning')
        return redirect(url_for('bonus.view_submission', submission_id=submission_id))
    
    # Verify that all employees have been evaluated on all questions
    employees = Employee.query.filter_by(
        department=submission.department,
        is_active=True,
        is_bonus=True
    ).all()
    
    questions = BonusQuestion.query.filter_by(
        department=submission.department,
        is_active=True
    ).all()
    
    # Count evaluations
    evaluation_count = BonusEvaluation.query.filter_by(
        submission_id=submission_id
    ).count()
    

    evaluation_submit = BonusEvaluation.query.filter_by(
        submission_id=submission_id
    )

    save_evaluation_history(submission_id)
    

    expected_count = len(employees) * len(questions)
    
    # if evaluation_count < expected_count:
    #     flash('Please complete all evaluations before submitting.', 'warning')
    #     return redirect(url_for('bonus.edit_submission', submission_id=submission_id))
    
    # Update submission status
    submission.status = 'submitted'
    submission.submitted_at = datetime.now()
    
    # Create audit log entry
    log = BonusAuditLog(
        submission_id=submission_id,
        action='submitted',
        user_id=current_user.id,
        notes=f'Submission for {submission.department}, period {submission.period.name} submitted for review'
    )
    
    db.session.add(log)
    db.session.commit()
    
    flash('Submission has been sent to HR for review.', 'success')
    return redirect(url_for('bonus.supervisor_dashboard'))


@bp.route('/submission/<int:submission_id>/view')
@login_required
def view_submission(submission_id):
    """View a bonus submission"""
    from models import User  # Import here to avoid circular imports
    
    submission = BonusSubmission.query.get_or_404(submission_id)
    
    # Check permissions
    is_owner = submission.submitted_by == current_user.id
    is_hr = current_user.has_role('hr')
    is_approver = current_user.has_role_approver()
    
    if not (is_owner or is_hr):
        flash('You do not have permission to view this submission.', 'danger')
        return redirect(url_for('bonus.index'))
    
    # Get employees in department
    employees = Employee.query.filter_by(
        department=submission.department,
        is_bonus=True,
        is_active=True
    ).order_by(Employee.name).all()
    
    # Get active questions for this department
    questions = BonusQuestion.query.filter_by(
        department=submission.department,
        is_active=True
    ).order_by(BonusQuestion.id).all()
    
    # Get evaluations
    evaluations = BonusEvaluation.query.filter_by(
        submission_id=submission.id
    ).all()
    
    # Organize evaluations in a matrix for easy access
    evaluation_matrix = {}
    employee_remarks_map = {}
    employee_status_map = {}

    for eval in evaluations:
        print(eval.remarks,"eval.remarks============")
        if eval.employee_id not in evaluation_matrix:
            evaluation_matrix[eval.employee_id] = {}

        # Always add question-based answers
        if eval.question_id is not None:
            evaluation_matrix[eval.employee_id][eval.question_id] = eval

        # Always update remarks separately
        if eval.remarks and eval.remarks.strip():
            employee_remarks_map[eval.employee_id] = eval.remarks.strip()
        
        if eval.emp_status and eval.emp_status.strip():
            employee_status_map[eval.employee_id] = eval.emp_status.strip()
    
    # Calculate total points for each employee
    print(employee_remarks_map,"employee_remarks_map===============")
    
    employee_points = submission.calculate_total_points()
    
    # Get audit logs
    audit_logs = BonusAuditLog.query.filter_by(
        submission_id=submission.id
    ).order_by(BonusAuditLog.timestamp.desc()).all()
    
    # Create a map of user IDs for approvers
    user_map = {}
    if submission.approvers:
        try:
            # Handle different possible formats of approvers
            if isinstance(submission.approvers, list):
                user_ids = [int(uid) for uid in submission.approvers if str(uid).isdigit()]
            elif isinstance(submission.approvers, str):
                # Handle string representation of list: convert from string to list
                import json
                try:
                    approvers_list = json.loads(submission.approvers.replace("'", '"'))
                    user_ids = [int(uid) for uid in approvers_list if str(uid).isdigit()]
                except json.JSONDecodeError:
                    # If not valid JSON, try splitting string
                    approvers_list = submission.approvers.strip('[]').split(',')
                    user_ids = [int(uid.strip()) for uid in approvers_list if uid.strip().isdigit()]
            else:
                # Fallback
                user_ids = []
                
            if user_ids:
                users = User.query.filter(User.id.in_(user_ids)).all()
                user_map = {str(user.id): user for user in users}
        except Exception as e:
            current_app.logger.error(f"Error processing approvers: {e}")
    
    # Generate a CSRF token for the form
    from flask_wtf.csrf import generate_csrf
    csrf_token = generate_csrf()
    csrf_token_field = Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token}">')
    
    return render_template(
        'bonus/view_submission.html',
        submission=submission,
        employees=employees,
        questions=questions,
        evaluation_matrix=evaluation_matrix,
        employee_status_map=employee_status_map,
        employee_points=employee_points,
        audit_logs=audit_logs,
        is_hr=is_hr,
        is_approver=is_approver,
        User=User,
        user_map=user_map,
        csrf_token_field=csrf_token_field,
        employee_remarks_map=employee_remarks_map
    )


# HR Review Routes
@bp.route('/hr/review')
@login_required
@role_required('hr')
def hr_review():
    """HR review dashboard"""
    # Check for filter parameter
    filter_status = request.args.get('filter')
    
    # Get submissions pending review (both newly submitted and in-progress reviews)
    pending_submissions = BonusSubmission.query.filter(
        BonusSubmission.status.in_(['submitted', 'in_review'])
    ).order_by(BonusSubmission.submitted_at.desc()).all()
    
    # Get all other submissions with optional filtering
    if filter_status == 'approved':
        other_submissions = BonusSubmission.query.filter_by(
            status='approved'
        ).order_by(BonusSubmission.reviewed_at.desc()).all()
        pending_submissions = []  # Don't show pending if viewing approved
    elif filter_status == 'draft':
        # Show draft submissions when specifically requested
        other_submissions = BonusSubmission.query.filter_by(
            status='draft'
        ).order_by(BonusSubmission.created_at.desc()).all()
        pending_submissions = []  # Don't show pending if viewing drafts
    elif filter_status == 'rejected':
        other_submissions = BonusSubmission.query.filter_by(
            status='rejected'
        ).order_by(BonusSubmission.reviewed_at.desc()).all()
        pending_submissions = []  # Don't show pending if viewing rejected
    else:
        # Default view - show approved and rejected submissions
        other_submissions = BonusSubmission.query.filter(
            BonusSubmission.status.in_(['approved', 'rejected'])
        ).order_by(BonusSubmission.reviewed_at.desc()).all()

    print(current_user.is_bouns_approver)
    print(" hhhhhhhhhhhhhhhhhhhh")
    
    return render_template(
        'bonus/hr_review.html',
        pending_submissions=pending_submissions,
        other_submissions=other_submissions,
        filter_status=filter_status,
        is_bonus_approver=current_user.is_bouns_approver
    )

def notify_odoo_user_bonus_approvel(data):
    try:

        requests.post("http://erp.mir.ae:8050/odoo_user_bonus_approvel", data=data, timeout=3)

    except requests.exceptions.RequestException as e:
        print("❌ Failed to notify Odoo (created):", e)



@bp.route('/hr/review/<int:submission_id>', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def hr_review_submission(submission_id):
    """HR review a specific submission with multi-level approval"""
    # Get how many HR approvals are required from system config
    system_config = SystemConfig.query.first()
    print(" kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk")
    required_approvals = 2  # Default fallback
    
    if system_config and system_config.required_approvals:
        required_approvals = system_config.required_approvals
    
    submission = BonusSubmission.query.get_or_404(submission_id)
    print(submission.department, " 00000000000000000000000000")
    
    # Check if submission can be reviewed
    if submission.status not in ['submitted', 'in_review']:
        flash('This submission is not pending review.', 'warning')
        return redirect(url_for('bonus.hr_review'))
    
    if request.method == 'POST':
        decision = request.form.get('decision')
        notes = request.form.get('notes', '')
        
        if decision not in ['approve', 'reject']:
            flash('Invalid decision.', 'danger')
            return redirect(url_for('bonus.hr_review_submission', submission_id=submission_id))
        
        # Handle rejection - immediately mark as rejected
        if decision == 'reject':
            submission.status = 'rejected'
            submission.reviewed_by = current_user.id
            submission.reviewed_at = datetime.now()
            submission.notes = notes
            
            # Create audit log entry
            log = BonusAuditLog(
                submission_id=submission_id,
                action='rejected',
                user_id=current_user.id,
                notes=notes or 'Submission rejected by HR'
            )





            
            db.session.add(log)
            db.session.commit()
            
            # Send WhatsApp notifications to employees
            try:
                send_whatsapp_notifications(submission, 'rejected')
            except Exception as e:
                current_app.logger.error(f"Failed to send WhatsApp notifications: {str(e)}")
            
            flash('Submission has been rejected.', 'warning')
            return redirect(url_for('bonus.hr_review'))
        
        # Handle approval - multi-level process
        current_approvers = submission.approvers or []

        
        # Check if current user already approved
        if current_user.id in current_approvers:
            flash('You have already approved this submission.', 'info')
            return redirect(url_for('bonus.view_submission', submission_id=submission_id))
        
        # Add current user to approvers
        current_approvers.append(current_user.id)
        submission.approvers = current_approvers
        
        # Update approval level
        submission.approval_level = len(current_approvers)
        
        # Change status to in_review after first approval
        if submission.status == 'submitted':
            submission.status = 'in_review'

            print(" odoo hit methdo  Super HR ")
            
            # users = User.query.filter_by(is_bouns_approver=True).all()
            users = User.query.filter_by(is_bouns_approver=True).all()
            print ( users) 
            print("---------------------------")
            print (users[0].employee_id)
            for user in users:
                print(user.employee_id)
                print(" hhhhhhhhhhhhhhhhhhhhhhhhhhhhhh")
            emp = Employee.query.filter_by(id=users[0].employee_id).first()
            print(emp)

            # print(users[0].email)


            # need to make history here
            save_evaluation_history(submission_id)
            
            # data['email'] = users.email
            # data['body'] = " HR has been Approved the bonus. Please Review and Approve"
            body_html = """
                Dear {EMPNAME},
                HR has approved and submitted the bonuses for {DEPARTMENT} department for your review in ERP. Please review and approve.
                Login to your ERP and click attendance app link.
                Best regards,<br/>HR Department
            """.format(EMPNAME=emp.name, DEPARTMENT=submission.department)
            # data['body'] = body_html
            # data['employee_id'] = users.employee_id.odoo_id

            thread = threading.Thread(target=notify_odoo_user_bonus_approvel, args=({
                    'email': emp.email,
                    'body': body_html,
                    'employee_id': emp.odoo_id,
                    # 'employee_id': employee.odoo_id,
                    # 'phone': employee.phone,
                    # 'is_reset':False
                },))
            thread.start()

        if notes:

            log_note = notes+' HR Approved (Awaiting management approval)'
        else:
            log_note = 'HR Approved (Awaiting management approval)'

        
        # Create audit log entry for this approval
        log = BonusAuditLog(
            submission_id=submission_id,
            action=f'Approved by',
            user_id=current_user.id,
            notes=log_note
        )


        db.session.add(log)
        
        # Check if all required approvals received
        if len(current_approvers) >= required_approvals:

            if notes:

                log_note = notes+' Final approved by management.'
            else:
                log_note = 'Final approved by management.'

            

            # Final approval - update status and other fields
            submission.status = 'approved'
            submission.reviewed_by = current_user.id
            submission.reviewed_at = datetime.now()
            submission.notes = notes
            
            # Create final approval audit log
            final_log = BonusAuditLog(
                submission_id=submission_id,
                action='approved',
                user_id=current_user.id,
                notes=log_note
            )
            save_evaluation_history(submission_id)

            db.session.add(final_log)
            print(" odoo hit methdo  Super HR ")
            
            # users = User.query.filter_by(is_bouns_approver=True).all()
            users = User.query.filter_by(role='hr', is_bouns_approver=False).all()
            for user in users:
                print (user)
                print(" hahashdahdsahsd sa")

                emp = Employee.query.filter_by(id=user.employee_id).first()
                print(emp)

                # print(users[0].email)
                
                # data['email'] = users.email
                # data['body'] = " HR has been Approved the bonus. Please Review and Approve"
                body_html = """
                    Dear {EMPNAME},
                    Final approval for the payroll bonuses  for {DEPARTMENT} department has been Done. Please review and Submit to payroll.
                    
                    Best regards,<br/>HR Department
                """.format(EMPNAME=emp.name, DEPARTMENT=submission.department)
                # data['body'] = body_html
                # data['employee_id'] = users.employee_id.odoo_id

                thread = threading.Thread(target=notify_odoo_user_bonus_approvel, args=({
                        'email': emp.email,
                        'body': body_html,
                        'employee_id': emp.odoo_id,
                        # 'employee_id': employee.odoo_id,
                        # 'phone': employee.phone,
                        # 'is_reset':False
                    },))
                thread.start()

            
            # Update original_value for all evaluations
            evaluations = BonusEvaluation.query.filter_by(
                submission_id=submission_id
            ).all()
            
            for eval in evaluations:
                eval.original_value = eval.value
            
            # Send WhatsApp notifications to employees
            try:
                send_whatsapp_notifications(submission, 'approved')
            except Exception as e:
                current_app.logger.error(f"Failed to send WhatsApp notifications: {str(e)}")
            
            flash('Final approval completed. Submission has been approved.', 'success')
        else:
            # Partial approval
            flash(f'Approval recorded ({len(current_approvers)} of {required_approvals} approvals).', 'success')
        
        db.session.commit()
        return redirect(url_for('bonus.hr_review'))
    
    # GET request
    return redirect(url_for('bonus.view_submission', submission_id=submission_id))


@bp.route('/hr/edit/<int:evaluation_id>', methods=['POST'])
@login_required
@role_required('hr')
def hr_edit_evaluation(evaluation_id):
    """HR edit an individual evaluation"""
    current_app.logger.debug(f"Processing edit request for evaluation ID: {evaluation_id}")
    evaluation = BonusEvaluation.query.get_or_404(evaluation_id)
    
    # Check if submission is in an editable state (HR can edit during review and after approval)
    valid_statuses = ['submitted', 'in_review', 'approved']
    if evaluation.submission.status not in valid_statuses:
        current_app.logger.error(f"Invalid submission status: {evaluation.submission.status}")
        return jsonify({'status': 'error', 'message': 'Can only edit evaluations in review or approved status'}), 400
    
    # Get data
    data = request.json
    current_app.logger.debug(f"Received data: {data}")
    
    try:
        new_value = float(data.get('value'))
    except (TypeError, ValueError):
        current_app.logger.error(f"Invalid value received: {data.get('value')}")
        return jsonify({'status': 'error', 'message': 'Value must be a number'}), 400
        
    notes = data.get('notes', '')
    
    # Validate value
    question = BonusQuestion.query.get(evaluation.question_id)
    if question and (new_value < question.min_value or new_value > question.max_value):
        current_app.logger.error(f"Value out of range: {new_value}, allowed range is {question.min_value}-{question.max_value}")
        return jsonify({
            'status': 'error', 
            'message': f'Value must be between {question.min_value} and {question.max_value}'
        }), 400
    
    # Update evaluation
    old_value = evaluation.value
    evaluation.value = new_value
    evaluation.notes = notes
    
    # Create detailed audit log entry
    log = BonusAuditLog(
        submission_id=evaluation.submission_id,
        employee_id=evaluation.employee_id,
        question_id=evaluation.question_id,
        action='hr_updated',
        old_value=old_value,
        new_value=new_value,
        notes=f"Changed from {old_value} to {new_value}. {notes}",
        user_id=current_user.id
    )
    
    try:
        db.session.add(log)
        db.session.commit()
        current_app.logger.debug(f"Successfully updated evaluation {evaluation_id} from {old_value} to {new_value}")
        
        # Calculate new total points
        current_app.logger.debug(f"Calculating new total points for employee {evaluation.employee_id}")
        employee_points = evaluation.submission.calculate_total_points(evaluation.employee_id)
        
        employee_id = evaluation.employee_id
        total_points = employee_points.get(employee_id, 0)
        
        current_app.logger.debug(f"Employee ID: {employee_id}, points dictionary: {employee_points}")
        current_app.logger.debug(f"New total points for employee {employee_id}: {total_points}")
        
        # Return response with employee ID for debugging
        return jsonify({
            'status': 'success',
            'message': 'Evaluation updated successfully',
            'total_points': total_points,
            'employee_id': employee_id
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving evaluation: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Error saving: {str(e)}'}), 500


@bp.route('/hr/export/<int:submission_id>')
@login_required
@role_required('hr')
def export_submission(submission_id):
    """Export submission data for Odoo"""
    submission = BonusSubmission.query.get_or_404(submission_id)
    
    # Check if submission is approved
    if submission.status != 'approved':
        flash('Only approved submissions can be exported.', 'warning')
        return redirect(url_for('bonus.view_submission', submission_id=submission_id))
    
    # Calculate total points for each employee
    employee_points = submission.calculate_total_points()
    
    # Get employee data
    employee_data = []
    for employee_id, points in employee_points.items():
        employee = Employee.query.get(employee_id)
        if employee and employee.odoo_id:
            employee_data.append({
                'id': employee.id,
                'name': employee.name,
                'odoo_id': employee.odoo_id,
                'department': employee.department,
                'bonus_points': points
            })
    
    # TODO: Implement actual Odoo export logic here
    
    return render_template(
        'bonus/export_data.html',
        submission=submission,
        employee_data=employee_data
    )