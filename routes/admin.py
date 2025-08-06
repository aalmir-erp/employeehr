from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify,session
#from flask_login import login_required, current_user
from flask_login import login_required, current_user, logout_user, login_user
from datetime import datetime, timedelta
from app import db
from utils.odoo_connector import odoo_connector
from models import User, Employee, Shift, ShiftAssignment, AttendanceDevice, OdooConfig, OdooMapping, ERPConfig, SystemConfig
from itsdangerous import URLSafeSerializer, BadSignature
import threading
import requests
import random
import string





# Create blueprint
bp = Blueprint('admin', __name__, url_prefix='/admin')
SECRET_KEY = 'YOUR_SECRET_KEY_HERE' 


# @bp.before_request
# def before_request():
#     """Ensure only admin users can access admin routes"""
#     if not current_user.is_authenticated or not current_user.is_admin:
#         flash('You do not have permission to access the admin area', 'danger')
#         return redirect(url_for('auth.login'))

@bp.route('/')
@login_required
def index():
    """Admin dashboard index"""
    print(current_user.is_authenticated,current_user.is_admin,"=======================================================>>>>>>>>>>>>>")
    if not current_user.is_authenticated or not current_user.is_admin:
                flash('You do not have permission to access the admin area', 'danger')
    # Get counts for dashboard
    total_employees = Employee.query.count()
    active_employees = Employee.query.filter_by(is_active=True).count()
    device_count = AttendanceDevice.query.count()
    online_devices = AttendanceDevice.query.filter_by(status='online').count()
    shift_count = Shift.query.count()
    user_count = User.query.count()
    admin_count = User.query.filter_by(is_admin=True).count()
    
    # Set up dictionary objects for the template as expected
    attendance_devices = {
        'total': device_count,
        'online': online_devices
    }
    
    employee_stats = {
        'total': total_employees,
        'active': active_employees
    }
    
    # For attendance stats, we'll use placeholder data since we don't have real-time stats
    from datetime import datetime
    today = datetime.now().date()
    present_count = 0  # This would normally be calculated from attendance records
    
    # Calculate or set a placeholder percentage
    percent = 0
    if total_employees > 0:
        percent = int((present_count / total_employees) * 100)
        
    attendance_stats = {
        'present': present_count,
        'percent': percent
    }
    
    user_stats = {
        'total': user_count,
        'admin': admin_count
    }
    
    # Get last sync time if available
    odoo_config = OdooConfig.query.first()
    last_sync = odoo_config.last_sync if odoo_config else None
    
    return render_template(
        'admin/index.html',
        attendance_devices=attendance_devices,
        employee_stats=employee_stats,
        attendance_stats=attendance_stats,
        user_stats=user_stats,
        last_sync=last_sync
    )

@bp.route('/login-as/<int:user_id>')
@login_required
def login_as_user(user_id):
    """Login as another user (admin only)"""
    target_user = User.query.get_or_404(user_id)
    
    # Store the original admin user ID in session
    session['original_admin_user_id'] = current_user.id
    session['original_admin_username'] = current_user.username
    
    # Log out current user and login as target user
    logout_user()
    login_user(target_user)
    
    flash(f'Successfully logged in as {target_user.username}', 'success')
    return redirect(url_for('index.index'))

# @bp.route('/loginodoo/<string:employee_token>')
# def login_as_user_odoo(employee_token):
#     s = URLSafeSerializer(SECRET_KEY)

#     employee_id = s.loads(employee_token)
#     print(employee_id)

#     # Use employee_id for your logic here
#     # Example:
#     print(employee_id,"============================================dddddddddddddddd")
#     target_user = User.query.filter_by(odoo_id=employee_id).first_or_404()
#     print(target_user,"================2222222222222222222222222222")

#     logout_user()
#     login_user(target_user)

#     flash(f'Successfully logged in as {target_user.username}', 'success')
#     return redirect(url_for('index.index'))

@bp.route('/loginodoo/<string:employee_token>')
def login_as_user_odoo(employee_token):
    s = URLSafeSerializer(SECRET_KEY)
    print (employee_token)
    odoo_employee_id = s.loads(employee_token)
    print(odoo_employee_id)
    print(" k kkkk")

    # Step 1: Get employee record where odoo_id matches
    employee = Employee.query.filter_by(odoo_id=odoo_employee_id).first_or_404()

    # Step 2: Now get user using the employee.id
    target_user = User.query.filter_by(employee_id=employee.id).first_or_404()

    logout_user()
    login_user(target_user)

    flash(f'Successfully logged in as {target_user.username}', 'success')
    return redirect(url_for('index.index'))

@bp.route('/switch-back-to-admin')
@login_required
def switch_back_to_admin():
    """Switch back to the original admin user"""
    original_admin_user_id = session.get('original_admin_user_id')
    
    if not original_admin_user_id:
        flash('No admin session found to switch back to.', 'warning')
        return redirect(url_for('index.index'))
    
    # Get the original admin user
    admin_user = User.query.get(original_admin_user_id)
    if not admin_user:
        flash('Original admin user not found.', 'error')
        return redirect(url_for('index.index'))
    
    # Clear the session data
    session.pop('original_admin_user_id', None)
    session.pop('original_admin_username', None)
    
    # Log out current user and login as original admin
    logout_user()
    login_user(admin_user)
    
    flash(f'Switched back to admin account: {admin_user.username}', 'success')
    return redirect(url_for('index.index'))


@bp.route('/users/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit a user"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('is_admin')  # This now carries the role value
        is_active = 'is_active' in request.form
        is_bouns_approver = 'is_bouns_approver' in  request.form

        # Check if username or email already exists for another user
        existing_user = User.query.filter(
            ((User.username == username) | (User.email == email)) &
            (User.id != user_id)
        ).first()

        if existing_user:
            flash('Username or email already in use by another user', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))

        if is_bouns_approver:
            role = 'hr'

        # Set values
        user.username = username
        user.email = email
        user.role = role
        user.is_admin = True if role == 'admin' else False
        # user.is_active = is_active
        user.is_bouns_approver = is_bouns_approver

        db.session.commit()
        flash(f'User "{username}" updated successfully', 'success')
        return redirect(url_for('admin.users'))

    # For GET request: load employees
    employees = Employee.query.filter_by(is_active=True).all()
    return render_template('admin/edit_user.html', user=user, employees=employees)


@bp.route('/users/delete', methods=['POST'])
@login_required
def delete_user():
    """Delete a user"""
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User "{username}" deleted successfully', 'success')
    return redirect(url_for('admin.users'))

def notify_odoo_user_created(data):
    try:
        print(" odoo hit methdo ")
        print (data)
        res = requests.post("http://erp.mir.ae:8069/attendance_user_created", data=data, timeout=3)
        print(res, " restune ")
        print(res.text)  # Gets the raw text response
    except requests.exceptions.RequestException as e:
        print("❌ Failed to notify Odoo (created):", e)


def notify_odoo_user_created_list(data):
    # try:
        print("✅ notifying Odoo with created user list")
        print (data, "data")
        requests.post("http://sib.mir.ae:8050/notify_odoo_user_created_list", json={'users': data}, timeout=3)

        # requests.post("http://erp.mir.ae:8050/attendance_user_created_list", json={'users': data}, timeout=3)

        # requests.post("http://erp.mir.ae:8050/attendance_user_created_list", data=data, timeout=3)
    # except requests.exceptions.RequestException as e:
    #     print("❌ Failed to notify Odoo (list):", e)


def notify_odoo_user_skipped_employees(data):
    # try:
        print("✅ notifying Odoo with skipped employee")
        # print (data, "data")
        requests.post("http://erp.mir.ae:8050/notify_odoo_user_skipped_employees", json={'employees': data}, timeout=3)

        # requests.post("http://erp.mir.ae:8050/attendance_skipped_employee", json={'users': data}, timeout=3)
    # except requests.exceptions.RequestException as e:
    #     print("❌ Failed to notify Odoo (skipped):", e)


# ----- MAIN ROUTE -----
@bp.route('/create_missing_users_for_employees', methods=['GET', 'POST'])
@login_required
def create_missing_users_for_employees():
    # default_password = 'Default123'
    default_password = generate_random_password()
    employees = Employee.query.all()

    created_employees = []
    skipped_employees = []

    for employee in employees:
        # Skip if email or phone is missing
        if not employee.email or not employee.phone:
            skipped_employees.append({
                'id': employee.id,
                'name': employee.name,
                'reason': 'Missing email or phone',
                'email': employee.email,
                'phone': employee.phone,
            })
            continue

        # Skip if user already exists with same employee_id or email
        existing_user = User.query.filter(
            (User.employee_id == employee.id) |
            (User.email == employee.email)
        ).first()

        if existing_user:
            skipped_employees.append({
                'id': employee.id,
                'name': employee.name,
                'reason': 'User already exists with same employee or email',
                'email': employee.email,
                'phone': employee.phone,
            })
            continue

        # new_user = User(
        #     email=employee.email,
        #     username=employee.employee_code or f"user{employee.id}",
        #     role='employee',
        #     employee_id=employee.id,
        #     department=employee.department,
        #     is_admin=False,
        #     created_at=datetime.utcnow(),
        #     last_login=None,
        #     force_password_change=False
        # )
        # new_user.set_password(default_password)
        # db.session.add(new_user)
        # db.session.flush()  

        # employee.user_id = new_user.id

        # Notify Odoo (if odoo_id exists)
        if employee.odoo_id:
            pass
            thread = threading.Thread(target=notify_odoo_user_created, args=({
                'email': employee.email,
                'username': employee.employee_code,
                'password': default_password,
                'employee_id': employee.odoo_id,
                'phone': employee.phone,
                'is_reset':False
            },))
            thread.start()

        created_employees.append({
            'id': employee.id,
            'name': employee.name,
            'username': employee.employee_code,
            'email': employee.email,
            'odoo_id': employee.odoo_id,
            'phone': employee.phone,
        })

    db.session.commit()

    # Notify Odoo: Created users
    # ✅ Notify Odoo: Created users (single call)
    if created_employees:
        thread = threading.Thread(target=notify_odoo_user_created_list, args=(created_employees,))
        thread.start()

    # ✅ Notify Odoo: Skipped employees (single call)
    if skipped_employees:
        thread = threading.Thread(target=notify_odoo_user_skipped_employees, args=(skipped_employees,))
        thread.start()

    flash(f"{len(created_employees)} User account created" , "success")
    flash(f"{len(skipped_employees)} User account Skipped" , "success")
    return redirect(url_for('admin.employees'))



@bp.route('/create_user', methods=['POST'])
def create_user():
    employee_id = request.form.get('employee_id')
    email = request.form.get('email')
    username = request.form.get('username')
    phone = request.form.get('phone')
    role = request.form.get('role')

    # Validate required fields
    if not all([employee_id, email, username, role]):
        flash("Missing required fields", "danger")
        return redirect(url_for('admin.employees'))

    # Check if email or username already exists
    if User.query.filter((User.email == email) | (User.username == username)).first():
        flash("Username or Email already exists", "danger")
        return redirect(url_for('admin.employees'))

    # Optionally get employee info
    employee = Employee.query.get(employee_id)
    random_password = generate_random_password()


    new_user = User(
        email=email,
        username=employee.employee_code,
        phone_number=phone,
        role=role,
        employee_id=employee_id,
        department=employee.department if employee else None,
        # password_hash=generate_password_hash("Default123", method='pbkdf2:sha256')  # Change default password policy
    )
    new_user.set_password(random_password)
    db.session.add(new_user)
    db.session.commit()
    print (" i am here odoo hit 0000000000000000000000000")
    print (employee.odoo_id, "employee.odoo_id")

    thread = threading.Thread(target=notify_odoo_user_created, args=({
        'email': email,
        'username': employee.employee_code,
        'password': random_password,
        'employee_id': employee.odoo_id,
        'phone':phone,
        'is_reset':False
    },))
    thread.start()

    flash(f"User account created for {employee.name}", "success")
    return redirect(url_for('admin.employees'))


def generate_random_password(length=8):
    chars = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(random.choice(chars) for _ in range(length))



@bp.route('/users/create')
@login_required
def create_user_old():
    """Delete a user"""
    employee_id = request.form.get('employee_id')
    employee = Employee.query.get_or_404(employee_id)
    if employee:
    
        username = employee.code
        email = employee.code+'@gmail.com'
        password = employee.code+'123'
        confirm_password =  employee.code+'123'
        role = False  # Actually the role value
        employee_id = request.form.get('employee_id') or None

        # Check if passwords match
        # if password != confirm_password:
        #     flash('Passwords do not match', 'danger')
        #     return redirect(url_for('admin.add_user'))

        # Check if user exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
            return redirect(url_for('admin.add_user'))

        # Set admin status based on role
        is_admin =  False

        # Create new user
        user = User(
            username=username,
            email=email,
            is_admin=is_admin,
            role=role,
            employee_id=int(employee_id) if employee_id else None
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
        print (username)

    
    flash(f'User "{username}" Create successfully', 'success')
    return redirect(url_for('admin.users'))



@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    """Add a new user"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('is_admin')  # Actually the role value
        employee_id = request.form.get('employee_id') or None

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('admin.add_user'))

        # Check if user exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
            return redirect(url_for('admin.add_user'))

        # Set admin status based on role
        is_admin = True if role == 'admin' else False

        # Create new user
        user = User(
            username=username,
            email=email,
            is_admin=is_admin,
            role=role,
            employee_id=int(employee_id) if employee_id else None
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash(f'User "{username}" added successfully', 'success')
        return redirect(url_for('admin.users'))

    # For GET request: load employee options
    employees = Employee.query.filter_by(is_active=True).all()
    return render_template('admin/add_user.html', employees=employees)



@bp.route('/users')
@login_required
def users():
    """Manage users"""
    users = User.query.all()
    
    # Calculate statistics for the dashboard
    total_count = len(users)
    admin_count = sum(1 for u in users if u.is_admin)
    active_count = sum(1 for u in users if u.is_active)
    
    stats = {
        'total': total_count,
        'admin': admin_count,
        'admin_percent': (admin_count / total_count * 100) if total_count > 0 else 0,
        'active': active_count,
        'active_percent': (active_count / total_count * 100) if total_count > 0 else 0
    }
    
    return render_template('admin/users.html', users=users, stats=stats)



@bp.route('/users/reset-password/<int:user_id>', methods=['GET'])
@login_required
def reset_password_form(user_id):
    """Display form to reset a user's password"""
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to reset passwords', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.get_or_404(user_id)
    return render_template('admin/reset_password.html', user=user)


@bp.route('/users/reset-password', methods=['POST'])
@login_required
def reset_user_password():
    """Process form to reset a user's password"""
    # Ensure user is admin
    if not current_user.is_admin and  not current_user.has_role('hr'):
        flash('You do not have permission to reset passwords', 'danger')
        return redirect(url_for('auth.login'))
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    force_change = 'force_change' in request.form

    
    user = User.query.get_or_404(user_id)
    employee = Employee.query.get(user.employee_id)
    
    # Validate passwords
    if not new_password or len(new_password) < 8:
        flash('Password must be at least 8 characters long', 'danger')
        return redirect(url_for('admin.reset_password_form', user_id=user.id))
    
    if new_password != confirm_password:
        flash('Passwords do not match', 'danger')
        return redirect(url_for('admin.reset_password_form', user_id=user.id))
    
    # Reset the password
    user.set_password(new_password)
    
    # Set force_password_change flag if requested
    if hasattr(user, 'force_password_change'):
        user.force_password_change = force_change
    
    db.session.commit()

    thread = threading.Thread(target=notify_odoo_user_created, args=({
        'email': user.email,
        'username': user.username,
        'password': new_password,
        'employee_id': employee.odoo_id,
        'phone': user.phone_number,
        'is_reset':True
    },))
    thread.start()


    
    flash(f'Password for "{user.username}" has been reset successfully', 'success')
    return redirect(url_for('admin.users'))



@bp.route('/employees',methods=['GET', 'POST'])
@login_required
def employees():
    """Manage employees"""
    # Get employees
    if request.method == 'POST':
        # employee_id = request.args.get('employee_id')
        # action_change = request.args.get('action_change')
        employee_id = request.form.get('employee_id')
        action_change = request.form.get('action_change')
        print(employee_id, "employee_id")
        print(action_change)
        if action_change == '1' and employee_id:
            print(employee_id, "employee_id")
            employee = Employee.query.filter_by(id=employee_id).first()
            if employee.is_active:
                employee.is_active = False
                
                flash('Employee status updated successfully.', 'success')
            elif employee.is_active==False:
                employee.is_active = True
                # db.session.commit()
                flash('Employee status updated successfully.', 'success')
            else:
                flash('Employee not found or already inactive.', 'warning')
            db.session.commit()
    employees = Employee.query.all()

    
    # Get additional data needed for the template
    total_count = len(employees)
    active_count = sum(1 for e in employees if e.is_active)
    departments = set(e.department for e in employees if e.department)
    
    # Calculate attendance statistics
    from datetime import date
    today = date.today()
    present_today = 0
    
    # Create stats dict for the template
    stats = {
        'total': total_count,
        'active': active_count,
        'active_percent': (active_count / total_count * 100) if total_count > 0 else 0,
        'departments': len(departments),
        'present_today': present_today,
        'present_percent': 0
    }
    
    # Get shifts for filters
    shifts = Shift.query.filter_by(is_active=True).all()
    
    # Get filter parameters
    selected_filters = {
        'department': request.args.get('department', ''),
        'shift_id': request.args.get('shift_id', ''),
        'status': request.args.get('status', ''),
        'search': request.args.get('search', '')
    }
    
    return render_template('admin/employees.html', 
                           employees=employees, 
                           departments=departments,
                           shifts=shifts,
                           stats=stats,
                           selected_filters=selected_filters)

@bp.route('/sync-employees', methods=['GET', 'POST'])
@login_required
def sync_employees():
    """Manually sync employees - placeholder"""
    if request.method == 'POST':
        if request.method == 'POST':
            success = odoo_connector.sync_employees()
        
            if success:
                flash('Successfully synced employees from Odoo', 'success')
            else:
                flash('Failed to sync employees from Odoo', 'danger')

        # This is just a placeholder since the actual Odoo sync functionality was not implemented
        # flash('Employee sync functionality is not yet implemented', 'warning')

        # This is just a placeholder since the actual Odoo sync functionality was not implemented
        # flash('Employee sync functionality is not yet implemented', 'warning')
    
    # Redirect to employees page
    return redirect(url_for('admin.employees'))

@bp.route('/overtime-eligibility')
@login_required
def overtime_eligibility():
    """Overtime eligibility configuration page"""
    # Get search and filter parameters
    department = request.args.get('department', '')
    search = request.args.get('search', '')
    
    # Query employees based on filters
    query = Employee.query
    
    if department:
        query = query.filter(Employee.department == department)
    
    if search:
        query = query.filter(Employee.name.ilike(f'%{search}%') | 
                            Employee.employee_code.ilike(f'%{search}%'))
    
    employees = query.order_by(Employee.name).all()
    
    # Get unique departments for filter dropdown
    departments = db.session.query(Employee.department).filter(
        Employee.department.isnot(None)
    ).distinct().order_by(Employee.department).all()
    departments = [d[0] for d in departments if d[0]]  # Extract department names
    
    return render_template(
        'admin/overtime_eligibility.html',
        employees=employees,
        departments=departments,
        selected_department=department,
        search_term=search
    )

@bp.route('/overtime-eligibility/update', methods=['POST'])
@login_required
def update_overtime_eligibility():
    """Update overtime eligibility settings for multiple employees"""
    if not current_user.is_admin:
        flash('You do not have permission to perform this action', 'danger')
        return redirect(url_for('admin.index'))
    
    # Get form data
    employee_ids = request.form.getlist('employee_ids')
    weekday_eligible = 'weekday_eligible' in request.form
    weekend_eligible = 'weekend_eligible' in request.form
    holiday_eligible = 'holiday_eligible' in request.form
    
    if not employee_ids:
        flash('No employees selected', 'warning')
        return redirect(url_for('admin.overtime_eligibility'))
    
    try:
        # Update each employee
        for employee_id in employee_ids:
            employee = Employee.query.get(employee_id)
            if employee:
                employee.eligible_for_weekday_overtime = weekday_eligible
                employee.eligible_for_weekend_overtime = weekend_eligible
                employee.eligible_for_holiday_overtime = holiday_eligible
        
        # Commit changes
        db.session.commit()
        
        flash(f'Successfully updated overtime eligibility settings for {len(employee_ids)} employee(s)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating overtime settings: {str(e)}', 'danger')
    
    return redirect(url_for('admin.overtime_eligibility'))

@bp.route('/overtime-eligibility/employee/<int:employee_id>', methods=['GET', 'POST'])
@login_required
def update_employee_overtime_eligibility(employee_id):
    """Update overtime eligibility for a specific employee"""
    # if not current_user.is_admin:
    #     flash('You do not have permission to perform this action', 'danger')
    #     return redirect(url_for('admin.index'))
    
    # If employee_id is 0 or invalid, redirect to the main overtime page
    # Get the employee
    employee = Employee.query.get(employee_id)
    
    if not employee:
        flash('Invalid employee selected', 'warning')
        return redirect(url_for('admin.overtime_eligibility'))
    
    # Handle GET request - show form
    if request.method == 'GET':
        return render_template(
            'admin/employee_overtime.html',
            employee=employee
        )
    
    # Handle POST request - update settings
    # Get form data
    weekday_eligible = 'weekday_eligible' in request.form
    weekend_eligible = 'weekend_eligible' in request.form
    holiday_eligible = 'holiday_eligible' in request.form
    
    try:
        # Update employee settings
        employee.eligible_for_weekday_overtime = weekday_eligible
        employee.eligible_for_weekend_overtime = weekend_eligible
        employee.eligible_for_holiday_overtime = holiday_eligible
        
        # Commit changes
        db.session.commit()
        
        flash(f'Successfully updated overtime eligibility settings for {employee.name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating overtime settings: {str(e)}', 'danger')
    
    return redirect(url_for('admin.overtime_eligibility'))


@bp.route('/api/employees')
@login_required
def api_employees():
    """API endpoint to get all employees"""
    employees = Employee.query.all()
    return jsonify([{
        'id': employee.id,
        'name': employee.name,
        'department': employee.department,
        'shift_id': employee.current_shift_id
    } for employee in employees])
    
@bp.route('/weekend-config')
@login_required
def weekend_config():
    """Weekend configuration page"""
    shifts = Shift.query.all()
    employees = Employee.query.filter_by(is_active=True).all()
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
        db.session.commit()
    
    return render_template(
        'admin/weekend_config.html',
        shifts=shifts,
        employees=employees,
        system_config=system_config
    )

@bp.route('/system-config')
@login_required
def system_config():
    """System configuration page"""
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
        db.session.commit()
    
    return render_template(
        'admin/system_config.html',
        system_config=system_config
    )

@bp.route('/system-config/update', methods=['POST'])
@login_required
def update_system_config():
    """Update system configuration"""
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
    
    # Update weekend days if present in the form
    weekend_days = request.form.getlist('weekend_days', type=int)
    if weekend_days:
        system_config.weekend_days = weekend_days
    
    # Update other system configs as needed
    # For example: system_config.default_shift_id = request.form.get('default_shift_id', type=int)
    
    db.session.commit()
    flash('System configuration updated successfully', 'success')
    return redirect(url_for('admin.system_config'))

@bp.route('/odoo-config')
@login_required
def odoo_config():
    """Odoo configuration page"""
    odoo_config = OdooConfig.query.first()
    odoo_mappings = OdooMapping.query.all()
    
    return render_template(
        'admin/odoo_config.html',
        odoo_config=odoo_config,
        odoo_mappings=odoo_mappings
    )

@bp.route('/odoo-config/update', methods=['POST'])
@login_required
def update_odoo_config():
    """Update Odoo configuration"""
    odoo_config = OdooConfig.query.first()
    
    if not odoo_config:
        odoo_config = OdooConfig()
        db.session.add(odoo_config)
    
    # Update Odoo connection details
    odoo_config.url = request.form.get('url')
    odoo_config.database = request.form.get('database')
    odoo_config.username = request.form.get('username')
    odoo_config.api_key = request.form.get('api_key')
    odoo_config.is_active = 'is_active' in request.form
    
    db.session.commit()
    flash('Odoo configuration updated successfully', 'success')
    return redirect(url_for('admin.odoo_config'))

@bp.route('/ai-config')
@login_required
def ai_config():
    """AI assistant configuration page"""
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
        db.session.commit()
    
    return render_template(
        'admin/ai_config.html',
        system_config=system_config
    )

@bp.route('/ai-config/update', methods=['POST'])
@login_required
def update_ai_config():
    """Update AI assistant configuration"""
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
    
    # Update AI configuration settings
    system_config.ai_enabled = 'ai_enabled' in request.form
    system_config.ai_provider = request.form.get('ai_provider')
    system_config.ai_model = request.form.get('ai_model')
    system_config.ai_api_key = request.form.get('ai_api_key')
    
    db.session.commit()
    flash('AI assistant configuration updated successfully', 'success')
    return redirect(url_for('admin.ai_config'))

@bp.route('/employee-weekend-config', methods=['GET'])
@login_required
def employee_weekend_config():
    """Employee weekend configuration page"""
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    shifts = Shift.query.all()
    system_config = SystemConfig.query.first()
    
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
        db.session.commit()
    
    # Prepare employees list with explicit weekend days
    for employee in employees:
        # Explicitly get effective weekend days to ensure they're available
        if not hasattr(employee, 'effective_weekend_days'):
            employee.effective_weekend_days = employee.get_weekend_days()
    
    return render_template(
        'admin/employee_weekend_config.html',
        employees=employees,
        shifts=shifts,
        system_config=system_config
    )

@bp.route('/employee-weekend-config/update', methods=['POST'])
@login_required
def update_employee_weekend_config():
    """Update employee weekend configuration"""
    employee_id = request.form.get('employee_id', type=int)
    weekend_days = request.form.getlist('weekend_days', type=int)
    use_default = 'use_default' in request.form
    
    if not employee_id:
        flash('Employee ID is required', 'danger')
        return redirect(url_for('admin.employee_weekend_config'))
    
    employee = Employee.query.get(employee_id)
    if not employee:
        flash('Employee not found', 'danger')
        return redirect(url_for('admin.employee_weekend_config'))
    
    # Update employee weekend days
    if use_default:
        # Set to None to use shift/system defaults
        employee.weekend_days = None
    else:
        # Set specific weekend days
        employee.weekend_days = weekend_days if weekend_days else None
    
    db.session.commit()
    
    flash(f'Weekend days updated for {employee.name}', 'success')
    return redirect(url_for('admin.overtime_eligibility'))

@bp.route('/bulk-update-weekend-config', methods=['POST']) 
@login_required
def bulk_update_weekend_config():
    """Bulk update weekend configuration for multiple employees"""
    employee_ids = request.form.getlist('bulk_employee_ids', type=int)
    weekend_days = request.form.getlist('bulk_weekend_days', type=int)
    use_default = 'bulk_use_default' in request.form
    
    if not employee_ids:
        flash('No employees selected', 'warning')
        return redirect(url_for('admin.employee_weekend_config'))
    
    updated_count = 0
    for employee_id in employee_ids:
        employee = Employee.query.get(employee_id)
        if employee:
            if use_default:
                # Set to None to use shift/system defaults
                employee.weekend_days = None
            else:
                # Set specific weekend days
                employee.weekend_days = weekend_days if weekend_days else None
            
            updated_count += 1
    
    db.session.commit()
    
    flash(f'Weekend days updated for {updated_count} employees', 'success')
    return redirect(url_for('admin.employee_weekend_config'))

@bp.route('/api/weekend-config', methods=['GET'])
@login_required
def api_weekend_config():
    """API to get weekend configuration data"""
    employee_id = request.args.get('employee_id', type=int)
    
    system_config = SystemConfig.query.first()
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
        db.session.commit()
    
    shift_weekend_configs = {}
    shifts = Shift.query.all()
    for shift in shifts:
        if shift.weekend_days:
            shift_weekend_configs[shift.id] = {
                'id': shift.id,
                'name': shift.name,
                'weekend_days': shift.weekend_days
            }
    
    # Ensure system_config.weekend_days has a valid value, default to [5, 6] if None
    system_weekend_days = system_config.weekend_days if system_config.weekend_days else [5, 6]
    
    result = {
        'system_weekend_days': system_weekend_days,  # Default: Saturday and Sunday
        'shift_weekend_configs': shift_weekend_configs,
    }
    
    if employee_id:
        employee = Employee.query.get(employee_id)
        if employee:
            # Get today's date for weekend check
            from datetime import date
            today = date.today()
            today_weekday = today.weekday()  # 0 = Monday, 6 = Sunday
            
            # Get effective weekend days for this employee, ensure it's not None
            effective_weekend_days = employee.get_weekend_days() or []
            
            # Determine if today is a weekend day (safely handle if effective_weekend_days is None)
            today_is_weekend = today_weekday in effective_weekend_days
            
            result['employee_weekend_days'] = {
                'id': employee.id,
                'name': employee.name,
                'weekend_days': employee.weekend_days or [],  # Ensure not None
                'shift_id': employee.current_shift_id,
                'effective_weekend_days': effective_weekend_days,
                'today_is_weekend': today_is_weekend
            }
    
    return jsonify(result)

@bp.route('/update-shift-weekend-config', methods=['POST'])
@login_required
def update_shift_weekend_config():
    """Update shift weekend configuration"""
    shift_id = request.form.get('shift_id', type=int)
    weekend_days = request.form.getlist('weekend_days', type=int)
    use_default = 'use_default' in request.form
    
    if not shift_id:
        flash('Shift ID is required', 'danger')
        return redirect(url_for('admin.weekend_config'))
    
    shift = Shift.query.get(shift_id)
    if not shift:
        flash('Shift not found', 'danger')
        return redirect(url_for('admin.weekend_config'))
    
    # Update shift weekend days
    if use_default:
        # Set to None to use system defaults
        shift.weekend_days = None
    else:
        # Set specific weekend days
        shift.weekend_days = weekend_days if weekend_days else None
    
    db.session.commit()
    
    flash(f'Weekend days updated for {shift.name}', 'success')
    return redirect(url_for('admin.weekend_config'))

@bp.route('/update-system-weekend-config', methods=['POST'])
@login_required
def update_system_weekend_config():
    """Update system weekend configuration"""
    weekend_days = request.form.getlist('weekend_days', type=int)
    
    system_config = SystemConfig.query.first()
    if not system_config:
        system_config = SystemConfig()
        db.session.add(system_config)
    
    # Update system weekend days
    system_config.weekend_days = weekend_days if weekend_days else [5, 6]  # Default to Saturday and Sunday
    
    db.session.commit()
    
    flash('System weekend days updated successfully', 'success')
    return redirect(url_for('admin.weekend_config'))

@bp.route('/api/update-weekend', methods=['POST'])
@login_required
def api_update_weekend():
    """API to update weekend configuration"""
    data = request.json
    
    # Update system-wide weekend days
    if data and 'system_weekend_days' in data:
        system_config = SystemConfig.query.first()
        if not system_config:
            system_config = SystemConfig()
            db.session.add(system_config)
        
        # Ensure we're dealing with valid weekend days data
        weekend_days = data.get('system_weekend_days')
        if weekend_days is not None:
            system_config.weekend_days = weekend_days
            db.session.commit()
    
    # Update shift weekend days
    if data and 'shift_weekend_days' in data and data['shift_weekend_days']:
        for shift_id_str, weekend_days in data['shift_weekend_days'].items():
            try:
                # Convert string ID to integer
                shift_id = int(shift_id_str)
                shift = Shift.query.get(shift_id)
                if shift and weekend_days is not None:
                    shift.weekend_days = weekend_days
            except (ValueError, TypeError):
                # Skip if shift_id is not a valid integer
                continue
        db.session.commit()
    
    # Update employee weekend days
    if data and 'employee_weekend_days' in data and data['employee_weekend_days']:
        for employee_id_str, weekend_days in data['employee_weekend_days'].items():
            try:
                # Convert string ID to integer
                employee_id = int(employee_id_str)
                employee = Employee.query.get(employee_id)
                if employee and weekend_days is not None:
                    employee.weekend_days = weekend_days
            except (ValueError, TypeError):
                # Skip if employee_id is not a valid integer
                continue
        db.session.commit()
    
    return jsonify({'status': 'success'})

@bp.route('/fix-weekend', methods=['POST'])
@login_required
def fix_weekend():
    """Fix weekend flags in attendance records"""
    from datetime import datetime, timedelta
    from models import AttendanceRecord
    
    # Get parameters
    shift_id = request.form.get('shift_id', type=int)
    
    # Define date range - last 30 days
    today = datetime.now().date()
    start_date = today - timedelta(days=30)
    
    # Convert dates to strings in ISO format for string comparison
    # AttendanceRecord.date is stored as a string in ISO format (YYYY-MM-DD)
    start_date_str = start_date.strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    
    # Build query with string comparison
    query = AttendanceRecord.query.filter(
        AttendanceRecord.date >= start_date_str,
        AttendanceRecord.date <= today_str
    )
    
    # Add shift filter if specified
    if shift_id:
        query = query.filter(AttendanceRecord.shift_id == shift_id)
    
    # Get records
    records = query.all()
    updated_count = 0
    
    # Update each record
    for record in records:
        # Get employee
        employee = record.employee
        
        if employee:
            # Determine if date is weekend for this employee
            weekend_days = employee.get_weekend_days(record.date) or []
            is_weekend = record.date.weekday() in weekend_days
        else:
            # Fallback to system default if no employee associated
            system_config = SystemConfig.query.first()
            if system_config and system_config.weekend_days:
                is_weekend = record.date.weekday() in system_config.weekend_days
            else:
                # Default to Saturday and Sunday if no system config exists
                is_weekend = record.date.weekday() >= 5
        
        # Update record if needed
        if record.is_weekend != is_weekend:
            record.is_weekend = is_weekend
            updated_count += 1
    
    # Commit changes
    db.session.commit()
    
    flash(f'Updated weekend flags for {updated_count} records', 'success')
    return redirect(url_for('admin.weekend_config'))