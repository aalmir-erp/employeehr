"""
Routes for supervisor management functionality
"""
from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime

from models import db, Employee, User, BonusAuditLog
from utils.auth import role_required
from forms.supervisor_forms import SupervisorAssignmentForm

bp = Blueprint('supervisor', __name__)

@bp.route('/reassign', methods=['GET', 'POST'])
@login_required
# @role_required('hr')
def reassign_supervisor():
    """Reassign a department supervisor"""
    form = SupervisorAssignmentForm()
    
    # Populate department select field
    all_departments = db.session.query(Employee.department).distinct().all()
    departments = [(d[0], d[0]) for d in all_departments if d[0]]
    form.department.choices = [('', '-- Select Department --')] + sorted(departments)
    
    # Get active employees for selection
    active_employees = Employee.query.filter_by(
        is_active=True
    ).order_by(Employee.name).all()
    
    # Populate employee select field with string IDs for proper form validation
    employee_choices = [(str(emp.id), emp.name) for emp in active_employees]
    form.new_supervisor.choices = [('', '-- Select Employee --')] + employee_choices
    
    # For each department, find current supervisor
    department_supervisors = {}
    for dept in [d[0] for d in all_departments if d[0]]:
        # Find supervisor users for this department
        supervisors = User.query.filter_by(
            department=dept, 
            role='supervisor'
        ).all()
        
        if supervisors:
            # Get the employee records for these supervisors
            supervisor_employees = []
            for sup in supervisors:
                employee = Employee.query.filter_by(email=sup.email).first()
                if employee:
                    supervisor_employees.append(employee)
            
            department_supervisors[dept] = supervisor_employees
    
    if request.method == 'POST' and form.validate_on_submit():
        department = form.department.data
        new_supervisor_id = form.new_supervisor.data
        
        # Find the new supervisor employee
        new_supervisor = Employee.query.get(new_supervisor_id)
        if not new_supervisor:
            flash('Selected employee not found.', 'danger')
            return redirect(url_for('supervisor.reassign_supervisor'))
        
        # Check if employee already has a user account (using employee_id as reference)
        existing_user = User.query.filter_by(username=f"emp_{new_supervisor.employee_id}").first()
        
        if existing_user:
            # Update existing user to supervisor role
            existing_user.role = 'supervisor'
            existing_user.department = department
            
            db.session.add(existing_user)
            flash(f'Existing user {existing_user.username} updated to supervisor role.', 'success')
        else:
            # Create new user account for supervisor
            username = new_supervisor.email.split('@')[0]
            new_user = User()
            new_user.username = username
            new_user.email = new_supervisor.email
            new_user.password_hash = generate_password_hash('changeme')
            new_user.role = 'supervisor'
            new_user.department = department
            new_user.force_password_change = True
            
            db.session.add(new_user)
            flash(f'New supervisor account created for {new_supervisor.name}.', 'success')
        
        # Log the supervisor change
        log = BonusAuditLog()
        log.action = 'supervisor_reassigned'
        log.user_id = current_user.id
        log.notes = f'Department {department} supervisor reassigned to {new_supervisor.name}'
        db.session.add(log)
        
        db.session.commit()
        flash(f'Department {department} supervisor reassigned successfully.', 'success')
        return redirect(url_for('supervisor.reassign_supervisor'))
    
    return render_template(
        'supervisor/reassign.html',
        form=form,
        active_employees=active_employees,
        department_supervisors=department_supervisors
    )