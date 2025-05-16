"""
Utility decorators for routes
"""
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def role_required(role):
    """
    Decorator to check if the current user has the required role
    
    Usage:
    @app.route('/admin')
    @login_required
    @role_required('admin')
    def admin_dashboard():
        return render_template('admin/dashboard.html')
        
    Note: This decorator should be used after @login_required
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(current_user, 'has_role') or not current_user.has_role(role):
                flash(f'You need {role} privileges to access this page.', 'warning')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator