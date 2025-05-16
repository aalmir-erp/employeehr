from flask import Blueprint, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Employee, Shift, SystemConfig
from utils.attendance_processor import check_holiday_and_weekend
from utils.weekend_sync import sync_weekend_flags, fix_weekend_detection
from datetime import datetime

# Create blueprint
bp = Blueprint('admin_debug', __name__, url_prefix='/admin/debug')

@bp.before_request
def before_request():
    """Ensure only admin users can access admin debug routes"""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Unauthorized access'}), 403

@bp.route('/weekend-config')
@login_required
def weekend_config():
    """Get weekend configuration at all levels for debugging"""
    
    # Get system weekend days
    system_config = SystemConfig.query.first()
    system_weekend_days = system_config.weekend_days if system_config else [5, 6]  # Default Sat/Sun
    
    # Get shift weekend days
    shifts = Shift.query.all()
    shift_weekend_configs = {
        shift.id: {
            'name': shift.name,
            'weekend_days': shift.weekend_days
        }
        for shift in shifts
    }
    
    # Get employee weekend days for a sample employee (if any)
    employee_id = request.args.get('employee_id')
    employee_weekend_days = None
    
    if employee_id:
        employee = Employee.query.get(int(employee_id))
        if employee:
            employee_weekend_days = {
                'id': employee.id,
                'name': employee.name,
                'weekend_days': employee.weekend_days,
                'shift_id': employee.current_shift_id
            }
            
            # Add the actual weekend days used after priority logic
            test_date = datetime.now().date()
            is_holiday, is_weekend = check_holiday_and_weekend(employee.id, test_date)
            
            # Add the effective weekend days
            effective_weekend_days = employee.get_weekend_days(test_date)
            
            employee_weekend_days['effective_weekend_days'] = effective_weekend_days
            employee_weekend_days['today_is_weekend'] = is_weekend
    
    # Return the configuration
    return jsonify({
        'system_weekend_days': system_weekend_days,
        'shift_weekend_configs': shift_weekend_configs,
        'employee_weekend_days': employee_weekend_days
    })
    
@bp.route('/fix-weekend', methods=['GET', 'POST'])
@login_required
def fix_weekend():
    """Fix weekend detection for all attendance records"""
    if request.method == 'POST':
        shift_id = request.form.get('shift_id')
        if shift_id:
            shift_id = int(shift_id)
        
        updated_count = sync_weekend_flags(
            shift_id=shift_id, 
            recalculate_all=True
        )
        
        flash(f'Successfully updated {updated_count} attendance records with correct weekend flags', 'success')
        return redirect(url_for('admin.weekend_config'))
    
    # GET request - show the form
    shifts = Shift.query.all()
    return jsonify({
        'message': 'Use POST method to apply the fix',
        'available_shifts': [{'id': s.id, 'name': s.name} for s in shifts]
    })