"""
Authentication and authorization utilities
"""
from functools import wraps

from flask import flash, redirect, url_for, current_app
from flask_login import current_user


def role_required(role):
    """
    Decorator to check if user has required role
    
    Args:
        role (str): Required role for the view (e.g., 'admin', 'hr', 'supervisor')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is logged in
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Check admin access (admins can access all roles)
            if current_user.role == 'admin':
                return f(*args, **kwargs)
            
            # Check role match
            if current_user.role != role:
                flash(f'You need {role} privileges to access this page.', 'danger')
                if current_user.role == 'hr':
                    return redirect(url_for('bonus.hr_dashboard'))
                elif current_user.role == 'supervisor':
                    return redirect(url_for('bonus.supervisor_dashboard'))
                else:
                    print (" getttingherer  ---------------------------")
                    return redirect(url_for('main.index'))
                    
            # User has correct role
            return f(*args, **kwargs)
        return decorated_function
    return decorator