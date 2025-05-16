from flask import Blueprint, redirect, url_for
from flask_login import current_user

# Create blueprint for index/root routes
bp = Blueprint('index', __name__)

@bp.route('/')
def index():
    """Root URL redirects to login or attendance dashboard if logged in"""
    if current_user.is_authenticated:
        return redirect(url_for('attendance.index'))
    else:
        return redirect(url_for('auth.login'))
