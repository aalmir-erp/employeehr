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
@role_required('hr')
def reassign_supervisor():
    """Reassign a department supervisor"""
    form = SupervisorAssignmentForm()

    # Departments
    all_departments = db.session.query(Employee.department).distinct().all()
    departments = [(d[0], d[0]) for d in all_departments if d[0]]
    form.department.choices = [('', '-- Select Department --')] + sorted(departments)

    # Employees
    active_employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    form.new_supervisor.choices = [('', '-- Select Employee --')] + [(str(emp.id), emp.name) for emp in active_employees]

    # Current Supervisors
    department_supervisors = {}
    for dept in [d[0] for d in all_departments if d[0]]:
        supervisors = User.query.filter_by(department=dept, role='supervisor').all()
        supervisor_employees = []
        for sup in supervisors:
            employee = Employee.query.filter_by(id=sup.employee_id).first()
            if employee:
                supervisor_employees.append(employee)
        department_supervisors[dept] = supervisor_employees

    if request.method == 'POST' and form.validate_on_submit():
        department = form.department.data
        new_supervisor_id = int(form.new_supervisor.data)

        # Find the employee
        new_supervisor = Employee.query.get(new_supervisor_id)
        if not new_supervisor:
            flash('Selected employee not found.', 'danger')
            return redirect(url_for('supervisor.reassign_supervisor'))

        # Try to find existing user via employee_id
        existing_user = User.query.filter_by(employee_id=new_supervisor.id).first()

        if existing_user:
            existing_user.role = 'supervisor'
            existing_user.department = department
            db.session.add(existing_user)
            flash(f'Updated user "{existing_user.username}" to supervisor.', 'success')
        else:
            username = f"emp_{new_supervisor.id}"
            email = f"{username}@company.com"  # You can customize this pattern
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash('changeme'),
                role='supervisor',
                department=department,
                force_password_change=True,
                is_active=True,
                employee_id=new_supervisor.id
            )
            db.session.add(new_user)
            flash(f'Created supervisor account for "{new_supervisor.name}".', 'success')

        # Log it
        log = BonusAuditLog(
            action='supervisor_reassigned',
            user_id=current_user.id,
            notes=f'{new_supervisor.name} assigned as supervisor of {department}'
        )
        db.session.add(log)

        db.session.commit()
        return redirect(url_for('supervisor.reassign_supervisor'))

    return render_template(
        'supervisor/reassign.html',
        form=form,
        active_employees=active_employees,
        department_supervisors=department_supervisors
    )
