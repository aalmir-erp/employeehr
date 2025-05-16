from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from app import db
from models import User, Employee
from utils.whatsapp_sender import send_otp, verify_otp, find_employee_by_phone

# Create blueprint
bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('attendance.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            
            # Update last login timestamp
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Check if user needs to change password
            if user.force_password_change:
                flash('You must change your password before continuing', 'warning')
                return redirect(url_for('auth.change_password'))
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('attendance.index')
            
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(next_page)
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html')

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password form"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Verify current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # Validate new password
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('auth.change_password'))
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # Update password
        current_user.set_password(new_password)
        
        # Clear the force_password_change flag if it's set
        if current_user.force_password_change:
            current_user.force_password_change = False
            
        db.session.commit()
        
        flash('Password changed successfully', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('change_password.html')

# Handle first-time setup - create admin user if no users exist
@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-time setup to create admin user"""
    # Check if any users exist
    user_count = User.query.count()
    if user_count > 0:
        flash('Setup has already been completed', 'info')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate password
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('auth.setup'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'danger')
            return redirect(url_for('auth.setup'))
        
        # Create admin user
        admin = User(
            username=username,
            email=email,
            is_admin=True
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        flash('Admin user created successfully. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('setup.html')

@bp.route('/whatsapp-login', methods=['GET', 'POST'])
def whatsapp_login():
    """Handle WhatsApp OTP login"""
    if current_user.is_authenticated:
        return redirect(url_for('attendance.index'))
    
    # Default step
    step = 'enter_phone'
    phone = ''
    
    if request.method == 'POST':
        step = request.form.get('step')
        
        if step == 'request_otp':
            # Get phone from form
            phone = request.form.get('phone')
            
            # Find employee with this phone
            employee = find_employee_by_phone(phone)
            
            if not employee:
                flash('No employee found with this phone number', 'danger')
                return render_template('whatsapp_login.html', step='enter_phone')
            
            # Send OTP via WhatsApp
            success, message = send_otp(phone, employee_id=employee.id)
            
            if success:
                flash('OTP sent to your WhatsApp number', 'success')
                return render_template('whatsapp_login.html', step='enter_otp', phone=phone)
            else:
                flash(f'Failed to send OTP: {message}', 'danger')
                return render_template('whatsapp_login.html', step='enter_phone')
        
        elif step == 'verify_otp':
            # Get phone and OTP from form
            phone = request.form.get('phone')
            otp_code = request.form.get('otp')
            
            # Verify OTP
            success, result = verify_otp(phone, otp_code)
            
            if success and isinstance(result, Employee):
                # Find or create user account for this employee
                user = User.query.filter_by(odoo_id=result.odoo_id).first()
                
                if not user:
                    # Create new user for this employee
                    username = f"emp{result.odoo_id}"
                    email = result.phone + "@example.com"  # Placeholder email
                    
                    user = User(
                        username=username,
                        email=email,
                        odoo_id=result.odoo_id,
                        is_admin=False
                    )
                    # Set a random password (user will login via OTP)
                    import secrets
                    user.set_password(secrets.token_urlsafe(12))
                    db.session.add(user)
                    db.session.commit()
                    
                # Log in the user
                login_user(user)
                
                # Update last login timestamp
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                flash(f'Welcome, {result.name}!', 'success')
                return redirect(url_for('attendance.index'))
            else:
                if not success:
                    flash(f'OTP verification failed: {result}', 'danger')
                else:
                    flash('Employee not found', 'danger')
                return render_template('whatsapp_login.html', step='enter_otp', phone=phone)
    
    # GET request or default
    return render_template('whatsapp_login.html', step=step, phone=phone)
