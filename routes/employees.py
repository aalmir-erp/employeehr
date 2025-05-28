"""
Employee management routes - for viewing employees, departments, and managing user-employee links
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Employee, User, Department
from utils.auth import role_required

bp = Blueprint('employees', __name__, url_prefix='/employees')

@bp.route('/')
@login_required
# @role_required('admin')
def index():
    """Employee management dashboard"""
    # Get all employees with their linked users
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.department, Employee.name).all()
    
    # Get all departments (unique from employees)
    departments = db.session.query(Employee.department).filter(
        Employee.department.isnot(None),
        Employee.is_active == True
    ).distinct().order_by(Employee.department).all()
    
    # Convert to list of strings
    departments = [dept[0] for dept in departments if dept[0]]
    
    # Get users without employee links
    unlinked_users = User.query.filter(User.employee == None).all()
    
    # Count employees by department
    dept_counts = {}
    for employee in employees:
        dept = employee.department or 'Unassigned'
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
    
    return render_template('employees/index.html',
                         employees=employees,
                         departments=departments,
                         unlinked_users=unlinked_users,
                         dept_counts=dept_counts)

@bp.route('/department/<string:dept_name>')
@login_required
# @role_required('admin')
def department_view(dept_name):
    """View employees in a specific department"""
    if dept_name == 'unassigned':
        employees = Employee.query.filter(
            Employee.department.is_(None),
            Employee.is_active == True
        ).order_by(Employee.name).all()
        dept_name = 'Unassigned'
    else:
        employees = Employee.query.filter(
            Employee.department == dept_name,
            Employee.is_active == True
        ).order_by(Employee.name).all()
    
    return render_template('employees/department.html',
                         employees=employees,
                         department_name=dept_name)

@bp.route('/link-user', methods=['POST'])
@login_required
# @role_required('admin')
def link_user_to_employee():
    """Link a user account to an employee record"""
    user_id = request.form.get('user_id')
    employee_id = request.form.get('employee_id')
    
    if not user_id or not employee_id:
        flash('Both user and employee must be selected', 'danger')
        return redirect(url_for('employees.index'))
    
    try:
        user = User.query.get(user_id)
        employee = Employee.query.get(employee_id)
        
        if not user or not employee:
            flash('User or employee not found', 'danger')
            return redirect(url_for('employees.index'))
        
        # Check if employee is already linked
        if employee.user_id:
            flash(f'Employee {employee.name} is already linked to another user', 'warning')
            return redirect(url_for('employees.index'))
        
        # Link the user to employee
        employee.user_id = user.id
        db.session.commit()
        
        flash(f'Successfully linked user {user.username} to employee {employee.name}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error linking user to employee: {str(e)}', 'danger')
    
    return redirect(url_for('employees.index'))

@bp.route('/unlink-user', methods=['POST'])
@login_required
# @role_required('admin')
def unlink_user_from_employee():
    """Unlink a user account from an employee record"""
    employee_id = request.form.get('employee_id')
    
    if not employee_id:
        flash('Employee ID is required', 'danger')
        return redirect(url_for('employees.index'))
    
    try:
        employee = Employee.query.get(employee_id)
        
        if not employee:
            flash('Employee not found', 'danger')
            return redirect(url_for('employees.index'))
        
        if not employee.user_id:
            flash(f'Employee {employee.name} is not linked to any user', 'warning')
            return redirect(url_for('employees.index'))
        
        # Store username for flash message
        username = employee.user.username if employee.user else 'Unknown'
        
        # Unlink the user
        employee.user_id = None
        db.session.commit()
        
        flash(f'Successfully unlinked user {username} from employee {employee.name}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error unlinking user from employee: {str(e)}', 'danger')
    
    return redirect(url_for('employees.index'))

@bp.route('/assign-supervisor', methods=['POST'])
@login_required
# @role_required('admin')
def assign_department_supervisor():
    """Assign a user as supervisor for a department"""
    user_id = request.form.get('user_id')
    department = request.form.get('department')
    
    if not user_id or not department:
        flash('Both user and department must be selected', 'danger')
        return redirect(url_for('employees.index'))
    
    try:
        user = User.query.get(user_id)
        
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('employees.index'))
        
        # Update user's role to supervisor and set department
        user.role = 'supervisor'
        user.department = department
        
        db.session.commit()
        
        flash(f'Successfully assigned {user.username} as supervisor for {department} department', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning supervisor: {str(e)}', 'danger')
    
    return redirect(url_for('employees.index'))