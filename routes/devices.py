from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from models import AttendanceDevice, DeviceLog
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, IntegerField, SelectField, ValidationError
from wtforms.validators import DataRequired, IPAddress, Optional, Length, Regexp
import re
from utils.hikvision_connector import hikvision_connector

# Custom validator for host address (accepts both IP and domain names)
def validate_host(form, field):
    # Check if it's a standard IP address
    ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
    # Check if it's a domain name (allowing subdomains)
    domain_pattern = re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9]{2,}$|^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9]{2,}$')
    # Allow full URLs (http/https)
    url_pattern = re.compile(r'^https?://([^:/\s]+)(:[0-9]+)?(/[^/\s]*)*$')
    
    value = field.data.strip()
    
    # Handle URLs by extracting the domain part
    if value.startswith('http://') or value.startswith('https://'):
        # Extract domain from URL
        url_match = url_pattern.match(value)
        if url_match and url_match.group(1):
            return  # Valid URL format
    
    # Check if it's a valid IP address
    elif ip_pattern.match(value):
        # Validate each octet
        octets = value.split('.')
        if all(0 <= int(octet) <= 255 for octet in octets):
            return  # Valid IP format
    
    # Check if it's a valid domain name
    elif domain_pattern.match(value):
        return  # Valid domain format
        
    # If we got here, the format is invalid
    raise ValidationError('Invalid host format. Please enter a valid IP address, domain name, or URL.')


# Create form for Hikvision devices
class HikvisionDeviceForm(FlaskForm):
    name = StringField('Device Name', validators=[DataRequired(), Length(max=128)])
    device_id = StringField('Device ID', validators=[DataRequired(), Length(max=64)])
    location = StringField('Location', validators=[Optional(), Length(max=256)])
    ip_address = StringField('Host/IP Address', validators=[DataRequired(), validate_host])
    port = IntegerField('Port', default=80)
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)

# Create blueprint
bp = Blueprint('devices', __name__, url_prefix='/devices')

@bp.before_request
def require_admin():
    """Ensure only admin users can access device management"""
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('You do not have permission to access this area', 'danger')
        return redirect(url_for('auth.login'))

@bp.route('/')
@login_required
def index():
    """List all attendance devices"""
    devices = AttendanceDevice.query.order_by(AttendanceDevice.name).all()
    return render_template('devices/index.html', devices=devices)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new attendance device"""
    if request.method == 'POST':
        name = request.form.get('name')
        device_id = request.form.get('device_id')
        device_type = request.form.get('device_type')
        location = request.form.get('location')
        ip_address = request.form.get('ip_address')
        port = request.form.get('port', type=int)
        api_key = request.form.get('api_key')
        
        # Validate required fields
        if not name or not device_id or not device_type:
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('devices.add'))
        
        # Check if device ID already exists
        existing_device = AttendanceDevice.query.filter_by(device_id=device_id).first()
        if existing_device:
            flash('A device with this ID already exists', 'danger')
            return redirect(url_for('devices.add'))
        
        # Create new device
        device = AttendanceDevice(
            name=name,
            device_id=device_id,
            device_type=device_type,
            location=location,
            ip_address=ip_address,
            port=port,
            api_key=api_key,
            status='offline'  # Default status is offline until first ping
        )
        
        # Add the device to the session and commit to get an ID
        db.session.add(device)
        db.session.commit()
        
        # Now create the log entry after the device has an ID
        log = DeviceLog(
            device_id=device.id,
            log_type='connection',
            message=f'Device added to the system by {current_user.username}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Device "{name}" added successfully', 'success')
        return redirect(url_for('devices.index'))
    
    # GET request - render the form
    return render_template('devices/add.html')

@bp.route('/edit/<int:device_id>', methods=['GET', 'POST'])
@login_required
def edit(device_id):
    """Edit an existing attendance device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    if request.method == 'POST':
        device.name = request.form.get('name')
        device.device_type = request.form.get('device_type')
        device.location = request.form.get('location')
        device.ip_address = request.form.get('ip_address')
        device.port = request.form.get('port', type=int)
        
        # Only update API key if a new one is provided
        new_api_key = request.form.get('api_key')
        if new_api_key:
            device.api_key = new_api_key
        
        device.is_active = 'is_active' in request.form
        
        # Log the update
        log = DeviceLog(
            device_id=device.id,
            log_type='connection',
            message=f'Device updated by {current_user.username}'
        )
        db.session.add(log)
        
        db.session.commit()
        
        flash(f'Device "{device.name}" updated successfully', 'success')
        return redirect(url_for('devices.index'))
    
    # GET request - render the form
    return render_template('devices/edit.html', device=device)

@bp.route('/logs/<int:device_id>')
@login_required
def logs(device_id):
    """View logs for a specific device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    page = request.args.get('page', 1, type=int)
    logs = DeviceLog.query.filter_by(device_id=device_id).order_by(
        DeviceLog.timestamp.desc()
    ).paginate(page=page, per_page=50, error_out=False)
    
    return render_template('devices/logs.html', device=device, logs=logs)

@bp.route('/check/<int:device_id>', methods=['POST'])
@login_required
def check_device(device_id):
    """Manually check a device's status"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # Handle URL format for ZKTeco devices
    if device.device_type and device.device_type.lower() == 'zkteco':
        # Clean up the IP/hostname
        ip_address = device.ip_address
        if ip_address and (ip_address.startswith('http://') or ip_address.startswith('https://')):
            # Extract the domain from URL
            ip_address = ip_address.split('//', 1)[1].split('/', 1)[0]
            
            # Check if port is included in the IP address
            if ':' in ip_address and not device.port:
                # Extract port from IP address if it's not set separately
                ip_address, port_str = ip_address.split(':', 1)
                try:
                    device.port = int(port_str)
                except ValueError:
                    pass
                    
            # Update the device record with clean values
            device.ip_address = ip_address
            db.session.commit()
            
            flash(f'Updated device format: {ip_address}:{device.port}', 'info')
    
    # Use the real device connection check
    from utils.scheduler import check_device_connection
    
    previous_status = device.status
    is_online, error_message = check_device_connection(device)
    
    device.status = 'online' if is_online else 'offline'
    device.last_ping = datetime.utcnow()
    
    # Log the status check with detailed error if any
    message = f'Manual status check by {current_user.username}. Status changed from {previous_status} to {device.status}'
    if not is_online and error_message:
        message += f". Error: {error_message}"
    
    log = DeviceLog(
        device_id=device.id,
        log_type='connection',
        message=message
    )
    db.session.add(log)
    
    db.session.commit()
    
    if is_online:
        flash(f'Device is online and working properly!', 'success')
    else:
        # Give more helpful error for ZKTeco devices
        if device.device_type and device.device_type.lower() == 'zkteco':
            flash(f'Device is offline. Error: {error_message}. Ensure the device is accessible from the server and try adding http:// prefix if needed.', 'danger')
        else:
            flash(f'Device is offline. Error: {error_message}', 'danger')
    
    return redirect(url_for('devices.index'))

@bp.route('/delete/<int:device_id>', methods=['POST'])
@login_required
def delete(device_id):
    """Delete a device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # Store the name before deletion for the flash message
    device_name = device.name
    
    # Delete the device and all associated logs
    db.session.delete(device)
    db.session.commit()
    
    flash(f'Device "{device_name}" deleted successfully', 'success')
    return redirect(url_for('devices.index'))

@bp.route('/add-hikvision', methods=['GET', 'POST'])
@login_required
def add_hikvision():
    """Add a new Hikvision DS-K1T342MFWX-E1 device"""
    # Pre-populate with default credentials for the device at erp.mir.ae:4082
    form = HikvisionDeviceForm()
    if not form.is_submitted():
        form.ip_address.data = 'https://erp.mir.ae:4082'
        form.username.data = 'admin'
        form.device_id.data = 'HIK-1'
        form.name.data = 'Hikvision DS-K1T342MFWX-E1 (MIR)'
        # Note: Password not pre-filled for security reasons
    
    if form.validate_on_submit():
        # Check if device ID already exists
        existing_device = AttendanceDevice.query.filter_by(device_id=form.device_id.data).first()
        if existing_device:
            flash('A device with this ID already exists', 'danger')
            return render_template('devices/add_hikvision.html', form=form)
        
        # Create new device
        device = AttendanceDevice(
            name=form.name.data,
            device_id=form.device_id.data,
            device_type='hikvision',
            model='DS-K1T342MFWX-E1',
            location=form.location.data,
            ip_address=form.ip_address.data,
            port=form.port.data,
            username=form.username.data,
            password=form.password.data,
            is_active=form.is_active.data,
            status='offline'  # Default status is offline until first ping
        )
        
        # Add the device to the session and commit to get an ID
        db.session.add(device)
        db.session.commit()
        
        # Try to connect to the device to get additional information
        try:
            # Initialize the connector with device credentials
            temp_connector = hikvision_connector.__class__(
                ip_address=form.ip_address.data,
                port=form.port.data,
                username=form.username.data,
                password=form.password.data
            )
            
            # Try to get device info
            device_info = temp_connector.get_device_info()
            if device_info:
                # Update device with additional information
                device.serial_number = device_info.get('serial_number')
                device.firmware_version = device_info.get('firmware_version')
                device.status = 'online'
                device.last_ping = datetime.utcnow()
                db.session.commit()
                
                # Log successful connection
                log = DeviceLog(
                    device_id=device.id,
                    log_type='connection',
                    message=f'Hikvision device added and connected successfully by {current_user.username}. '
                             f'Serial: {device_info.get("serial_number")}, '
                             f'Firmware: {device_info.get("firmware_version")}'
                )
                db.session.add(log)
                db.session.commit()
                
                flash(f'Device "{form.name.data}" added successfully and connected to the Hikvision device.', 'success')
            else:
                # Log failed connection but successful device addition
                log = DeviceLog(
                    device_id=device.id,
                    log_type='connection',
                    message=f'Hikvision device added by {current_user.username}, but could not connect to retrieve device info.'
                )
                db.session.add(log)
                db.session.commit()
                
                flash(f'Device "{form.name.data}" added, but could not connect to the Hikvision device to retrieve additional info.', 'warning')
        except Exception as e:
            # Log the error but still add the device
            log = DeviceLog(
                device_id=device.id,
                log_type='connection',
                message=f'Hikvision device added by {current_user.username}, but error connecting: {str(e)}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash(f'Device "{form.name.data}" added, but there was an error connecting to the Hikvision device: {str(e)}', 'warning')
        
        return redirect(url_for('devices.index'))
    elif request.method == 'POST' and not form.validate():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    return render_template('devices/add_hikvision.html', form=form)

@bp.route('/api/status')
@login_required
def api_device_status():
    """API endpoint to get the status of all devices"""
    devices = AttendanceDevice.query.all()
    
    result = {
        'total': len(devices),
        'online': 0,
        'offline': 0,
        'error': 0,
        'devices': []
    }
    
    for device in devices:
        result['devices'].append({
            'id': device.id,
            'name': device.name,
            'status': device.status,
            'last_ping': device.last_ping.isoformat() if device.last_ping else None
        })
        
        if device.status == 'online':
            result['online'] += 1
        elif device.status == 'offline':
            result['offline'] += 1
        elif device.status == 'error':
            result['error'] += 1
    
    return jsonify(result)

@bp.route('/fetch-employees/<int:device_id>', methods=['POST'])
@login_required
def fetch_employees(device_id):
    """Fetch employees from a specific device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # First check if the device is online
    from utils.scheduler import check_device_connection
    is_online, error_message = check_device_connection(device)
    
    if not is_online:
        flash(f'Cannot fetch employees: Device is offline. Error: {error_message}', 'danger')
        return redirect(url_for('devices.logs', device_id=device.id))
    
    # Create log entry for the fetch attempt
    log = DeviceLog(
        device_id=device.id,
        log_type='sync',
        message=f'Employee fetch initiated by {current_user.username}.'
    )
    db.session.add(log)
    db.session.commit()
    
    # Connect to the device and fetch actual employees
    try:
        # Connect to the device using appropriate connector based on device type
        if device.device_type.lower() == 'hikvision':
            # Initialize the Hikvision connector
            temp_connector = hikvision_connector.__class__(
                ip_address=device.ip_address,
                port=device.port,
                username=device.username,
                password=device.password
            )
            
            # Fetch employees from device
            employees = temp_connector.get_employees()
            if employees:
                # Process employees and add to database as needed
                # This would typically involve syncing with the Employee model
                count = len(employees)
                
                # Log the successful fetch
                fetch_log = DeviceLog(
                    device_id=device.id,
                    log_type='sync',
                    message=f'Successfully fetched {count} employees from Hikvision device.'
                )
                db.session.add(fetch_log)
                db.session.commit()
                
                # For demonstration, show details of fetched employees
                employee_details = ', '.join([f"{emp.get('name', 'Unknown')} (ID: {emp.get('employee_code', 'N/A')})" for emp in employees[:5]])
                if len(employees) > 5:
                    employee_details += f" and {len(employees) - 5} more"
                
                flash(f'Successfully fetched {count} employees from device: {employee_details}', 'success')
            else:
                flash('No employees found on Hikvision device or this API endpoint does not support employee data retrieval. This may be a documentation or web portal URL rather than a direct device connection.', 'warning')
        elif device.device_type.lower() in ['zkteco', 'biometric', 'fingerprint']:
            # Use ZKTeco connector for biometric devices
            from utils.zk_device import ZKDevice
            zk_device = ZKDevice(device)
            success, message = zk_device.sync_users_to_db()
            
            if success:
                flash(message, 'success')
            else:
                flash(f'Error fetching employees: {message}', 'danger')
        else:
            # Handle other device types or use a generic method
            flash('Device type not supported for direct connection. Please configure device settings.', 'warning')
        
        return redirect(url_for('devices.logs', device_id=device.id))
    except Exception as e:
        flash(f'Error fetching employees: {str(e)}', 'danger')
        return redirect(url_for('devices.logs', device_id=device.id))

@bp.route('/fetch-logs/<int:device_id>', methods=['POST'])
@login_required
def fetch_logs(device_id):
    """Fetch attendance logs from a specific device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # First check if the device is online
    from utils.scheduler import check_device_connection
    is_online, error_message = check_device_connection(device)
    
    if not is_online:
        flash(f'Cannot fetch logs: Device is offline. Error: {error_message}', 'danger')
        return redirect(url_for('devices.logs', device_id=device.id))
    
    # Create log entry for the fetch attempt
    log = DeviceLog(
        device_id=device.id,
        log_type='sync',
        message=f'Attendance log fetch initiated by {current_user.username}.'
    )
    db.session.add(log)
    db.session.commit()
    
    # Connect to the device and fetch actual attendance logs
    try:
        # Connect to the device using appropriate connector based on device type
        if device.device_type.lower() == 'hikvision':
            # Initialize the Hikvision connector
            temp_connector = hikvision_connector.__class__(
                ip_address=device.ip_address,
                port=device.port,
                username=device.username,
                password=device.password
            )
            
            # Fetch attendance logs from device
            # You can optionally specify date range, default is last 24 hours
            from datetime import datetime, timedelta
            start_date = datetime.now() - timedelta(days=1)  # Get logs from last 24 hours
            logs = temp_connector.get_attendance_logs(start_date=start_date)
            
            if logs:
                # Process logs and add to database as needed
                # This would typically involve syncing with the AttendanceLog model
                count = len(logs)
                
                # Log the successful fetch
                fetch_log = DeviceLog(
                    device_id=device.id,
                    log_type='sync',
                    message=f'Successfully fetched {count} attendance logs from Hikvision device.'
                )
                db.session.add(fetch_log)
                db.session.commit()
                
                # For demonstration, show details of fetched logs
                log_details = ', '.join([f"{log.get('employee_code', 'Unknown')} at {log.get('timestamp', 'N/A').strftime('%H:%M:%S')}" for log in logs[:5]])
                if len(logs) > 5:
                    log_details += f" and {len(logs) - 5} more"
                
                flash(f'Successfully fetched {count} attendance logs from device: {log_details}', 'success')
            else:
                flash('No attendance logs found on Hikvision device or this API endpoint does not support attendance data retrieval. This may be a documentation or web portal URL rather than a direct device connection.', 'warning')
        elif device.device_type.lower() in ['zkteco', 'biometric', 'fingerprint']:
            # Use ZKTeco connector for biometric devices
            from utils.zk_device import ZKDevice
            zk_device = ZKDevice(device)
            success, message = zk_device.sync_attendance_to_db()
            
            if success:
                flash(message, 'success')
            else:
                flash(f'Error fetching attendance logs: {message}', 'danger')
        else:
            # Handle other device types or use a generic method
            flash('Device type not supported for direct connection. Please configure device settings.', 'warning')
        
        return redirect(url_for('devices.logs', device_id=device.id))
    except Exception as e:
        flash(f'Error fetching attendance logs: {str(e)}', 'danger')
        return redirect(url_for('devices.logs', device_id=device.id))

@bp.route('/generate-report/<int:device_id>', methods=['POST'])
@login_required
def generate_device_report(device_id):
    """Generate attendance report based on device logs"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # Log the report generation attempt
    log = DeviceLog(
        device_id=device.id,
        log_type='report',
        message=f'Attendance report generation initiated by {current_user.username}.'
    )
    db.session.add(log)
    db.session.commit()
    
    # In a real implementation, this would generate a comprehensive report
    # For demo purposes, redirect to reports section
    flash('Attendance report generation has been initiated. View the report in the Reports section.', 'info')
    return redirect(url_for('reports.index'))

@bp.route('/troubleshoot/<int:device_id>')
@login_required
def troubleshoot_device(device_id):
    """Display detailed troubleshooting information for a device"""
    device = AttendanceDevice.query.get_or_404(device_id)
    
    # Get the latest connection status and error message
    from utils.scheduler import check_device_connection
    is_online, error_message = check_device_connection(device)
    
    # Get recent logs related to this device (last 20)
    recent_logs = DeviceLog.query.filter_by(device_id=device.id)\
        .order_by(DeviceLog.timestamp.desc())\
        .limit(20).all()
    
    return render_template('devices/troubleshoot.html', 
                           device=device, 
                           is_online=is_online, 
                           error_message=error_message,
                           logs=recent_logs)