from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Text, TypeDecorator
import json
from sqlalchemy import and_, func, or_

# Import db from db.py to avoid circular imports
from db import db

# Custom JSONB type with SQLite compatibility
class JSONB(TypeDecorator):
    """Custom JSONB type that works with both PostgreSQL and SQLite"""
    impl = Text
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(self.impl)
    
    def process_bind_param(self, value, dialect):
        if dialect.name == 'sqlite' and value is not None:
            return json.dumps(value)
        return value
    
    def process_result_value(self, value, dialect):
        if dialect.name == 'sqlite' and value is not None:
            return json.loads(value)
        return value

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    # Rename from is_active to account_active in the model (DB column stays the same)
    account_active = db.Column('is_active', db.Boolean, default=True) 
    odoo_id = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    force_password_change = db.Column(db.Boolean, default=False)
    
    # Role field using PostgreSQL enum type
    # Possible values: 'admin', 'hr', 'supervisor', 'employee'
    role = db.Column(db.String(20), default='employee')
    department = db.Column(db.String(64), nullable=True)
  # 🔹 New fields you asked for:
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    phone_number = db.Column(db.Text, nullable=True)

    # Fix AmbiguousForeignKeysError
    employee = db.relationship('Employee', backref='users', foreign_keys=[employee_id])
    is_bouns_approver = db.Column(db.Boolean, default=False)

    
    @property
    def is_active(self):
        """Return the active status for Flask-Login compatibility."""
        return self.account_active
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_role_approver(self):
        """Check if user has the specified role or higher privileges"""

        if self.is_bouns_approver:
            return True
            
        # Otherwise check role hierarchy
        return False

    def has_role(self, role):
        """Check if user has the specified role or higher privileges"""
        role_hierarchy = {
            'admin': 4,
            'hr': 3,
            'supervisor': 2,
            'employee': 1
        }
        
        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(role, 0)
        
        # Admin has all privileges
        if self.is_admin:
            return True
            
        # Otherwise check role hierarchy
        return user_level >= required_level
    
    def __repr__(self):
        return f'<User {self.username}>'

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    
    # Department-level overtime eligibility settings
    weekday_overtime_eligible = db.Column(db.Boolean, default=True)
    weekend_overtime_eligible = db.Column(db.Boolean, default=True)
    holiday_overtime_eligible = db.Column(db.Boolean, default=True)
    
    # Comment out relationship until department_id is added to Employee table
    # employees = db.relationship('Employee', backref='department_rel', lazy='dynamic')
    
    def __repr__(self):
        return f'<Department {self.name}>'

class PayrollStatus(db.Model):
    __tablename__ = 'payroll_status'

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Key to Employee model
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Payroll ID (optional: make it a string or integer depending on your use case)
    # payroll_id = db.Column(db.Integer, nullable=True)        # Integer ID from Odoo
    payroll_name = db.Column(db.String(64), nullable=True)
    payroll_id_odoo = db.Column(db.Integer, nullable=True)  

    
    # Status fields
    odoo_status = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(64), nullable=True)
    
    # Payroll date
    payroll_date = db.Column(db.Date, nullable=True)

    # Optional relationship backref to Employee
    employee = db.relationship('Employee', backref='payroll_statuses')

    def __repr__(self):
        return f'<PayrollStatus EmployeeID={self.employee_id} Status={self.status}>'

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    odoo_id = db.Column(db.Integer, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    employee_code = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(120),  nullable=True)  # 👈 New field added here

    department = db.Column(db.String(128), nullable=True)  # Store department as string
    # Note: department_id is commented out since it does not exist in the database yet
    # department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    position = db.Column(db.String(128), nullable=True)
    join_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_bonus = db.Column(db.Boolean, default=True)

    phone = db.Column(db.String(20), nullable=True)
    current_shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=True)
    weekend_days = db.Column(JSONB, nullable=True)  # Store list of days (0-6, Monday=0, Sunday=6)
    last_sync = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Individual overtime eligibility settings (highest priority)
    eligible_for_weekday_overtime = db.Column(db.Boolean, default=True)
    eligible_for_weekend_overtime = db.Column(db.Boolean, default=True)
    eligible_for_holiday_overtime = db.Column(db.Boolean, default=True)
    
    # Note: use_department_overtime_settings doesn't exist in the database
    # use_department_overtime_settings = db.Column(db.Boolean, default=True)
    
    # Relationships
    attendance_records = db.relationship('AttendanceRecord', backref='employee', lazy='dynamic')
    shift_assignments = db.relationship('ShiftAssignment', backref='employee', lazy='dynamic')
    current_shift = db.relationship('Shift', foreign_keys=[current_shift_id])
    
    def __repr__(self):
        return f'<Employee {self.name}>'
        
    def get_weekend_days(self, date_obj=None):
        """
        Get weekend days for this employee based on the following precedence:
        1. Employee-specific weekend days if defined
        2. Shift-specific weekend days if employee has a shift assignment on the given date
        3. System-wide default weekend days
        
        Args:
            date_obj: Optional date to check for shift-specific weekend days.
                      If None, uses current date.
        
        Returns:
            List of weekday numbers (0-6, Monday=0, Sunday=6) representing weekend days
        """
        
        if self.weekend_days:
            print(self.weekend_days,"=========================self.weekend_days1")
            return self.weekend_days
        
        if date_obj:
            shift_assignment = ShiftAssignment.query.filter(
                ShiftAssignment.employee_id == self.id,
                ShiftAssignment.start_date <= date_obj,
                (ShiftAssignment.end_date >= date_obj) | (ShiftAssignment.end_date.is_(None))
            ).first()
           
            if shift_assignment and shift_assignment.shift:
                if shift_assignment.shift.weekend_days:
                    print(shift_assignment.shift.weekend_days,'============================shift_assignment.shift.weekend_days2')
                    return shift_assignment.shift.weekend_days
        
        if self.current_shift_id:
            shift = Shift.query.get(self.current_shift_id)
            if shift and shift.weekend_days:
                print(shift.weekend_days,"===================================================shift.weekend_days")
                return shift.weekend_days
        
        system_config = SystemConfig.query.first()
        if system_config and system_config.weekend_days:
            print(system_config.weekend_days,"-=============================================system_config.weekend_days56")
            return system_config.weekend_days
        
        return [5, 6] 

class AttendanceDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    device_id = db.Column(db.String(64), unique=True, nullable=False)
    device_type = db.Column(db.String(64), nullable=False)  # 'biometric', 'rfid', 'hikvision', etc.
    model = db.Column(db.String(64), nullable=True)  # Device model (e.g., 'DS-K1T342MFWX-E1')
    location = db.Column(db.String(256), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(64), nullable=True)  # For devices that use username/password auth
    password = db.Column(db.String(256), nullable=True)  # For storing device password
    api_key = db.Column(db.String(256), nullable=True)  # For devices that use API key auth
    serial_number = db.Column(db.String(64), nullable=True)  # Device serial number
    firmware_version = db.Column(db.String(64), nullable=True)  # Device firmware version
    is_active = db.Column(db.Boolean, default=True)
    last_ping = db.Column(db.DateTime, nullable=True)
    last_sync = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(64), default='offline')  # 'online', 'offline', 'error'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    attendance_logs = db.relationship('AttendanceLog', backref='device', lazy='dynamic')
    
    def __repr__(self):
        return f'<AttendanceDevice {self.name}>'

class AttendanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_device.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    log_type = db.Column(db.String(10), nullable=False)  # 'IN', 'OUT'
    is_processed = db.Column(db.Boolean, default=False)
    attendance_record_id = db.Column(db.Integer, db.ForeignKey('attendance_record.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    location = db.Column(db.String(255), nullable=True)  # Add this line

    
    # Add relationship to Employee
    employee = db.relationship('Employee', backref=db.backref('attendance_logs', lazy='dynamic'))
    
    def __repr__(self):
        return f'<AttendanceLog {self.employee_id} {self.log_type} {self.timestamp}>'

class MissingAttendance(db.Model):
    __tablename__ = 'missing_attendance'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='missing')
    remarks = db.Column(db.Text)

    employee = db.relationship('Employee', backref='missing_attendances')

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=True)
    overtime_rule_id = db.Column(db.Integer, db.ForeignKey('overtime_rule.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='pending')  # 'present', 'absent', 'late', 'half-day', 'pending'
    is_holiday = db.Column(db.Boolean, default=False)
    is_weekend = db.Column(db.Boolean, default=False)
    work_hours = db.Column(db.Float, default=0.0)
    overtime_hours = db.Column(db.Float, default=0.0)  # Total overtime hours
    overtime_rate = db.Column(db.Float, default=1.0)  # Multiplier applied to overtime
    overtime_night_hours = db.Column(db.Float, default=0.0)  # Hours of overtime during night shift
    # Specific overtime categories
    regular_overtime_hours = db.Column(db.Float, default=0.0)  # Weekday overtime
    weekend_overtime_hours = db.Column(db.Float, default=0.0)  # Weekend overtime
    holiday_overtime_hours = db.Column(db.Float, default=0.0)  # Holiday overtime
    break_duration = db.Column(db.Float, default=0.0)
    break_calculated = db.Column(db.Boolean, default=False)  # Flag to indicate if break_duration is from multi-break calculation
    late_minutes = db.Column(db.Integer, default=0)  # Minutes late for shift
    
    # Break time fields
    break_start = db.Column(db.DateTime, nullable=True)  # Actual break start time
    break_end = db.Column(db.DateTime, nullable=True)    # Actual break end time
    
    # Additional analysis fields
    shift_type = db.Column(db.String(20), default='day')  # day, afternoon, night
    total_duration = db.Column(db.Float, default=0.0)  # Total hours including breaks
    
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    overtime_rule = db.relationship('OvertimeRule', backref='attendance_records', lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='attendance_record', lazy='dynamic')
    shift = db.relationship('Shift', backref='attendance_records', lazy=True)
    overt_time_weighted = db.Column(db.Float, default=0.0)
    grace_period_minutes = db.Column(db.Integer, default=0) 
    grace_overtime_hours = db.Column(db.Float, default=0.0)

    
    def __repr__(self):
        return f'<AttendanceRecord {self.employee_id} {self.date}>'
    
    def calculate_work_hours(self):
        """Calculate basic work hours without overtime"""
        if self.check_in and self.check_out:
            # Ensure end time is after start time (handle overnight shifts)
            end_time = self.check_out
            if end_time < self.check_in:
                end_time = end_time + timedelta(days=1)
            
            duration = (end_time - self.check_in).total_seconds() / 3600
            
            # Calculate break duration
            if self.break_calculated:
                # If break_calculated is True, use the stored break_duration
                # This flag indicates the duration was calculated from multiple breaks
                actual_break_duration = self.break_duration if self.break_duration is not None else 0
            elif self.break_start and self.break_end:
                # Use actual break times if they're set and break_calculated is False
                break_end = self.break_end
                if break_end < self.break_start:
                    break_end = break_end + timedelta(days=1)
                actual_break_duration = (break_end - self.break_start).total_seconds() / 3600
                self.break_duration = actual_break_duration
            else:
                # Otherwise use the stored break_duration
                actual_break_duration = self.break_duration if self.break_duration is not None else 0
            
            self.work_hours = max(0, duration - actual_break_duration)
            return self.work_hours
        return 0


        
    def calculate_overtime(self, standard_hours=None):
        """
        Calculate overtime hours and rate using assigned rule or system defaults
        Returns tuple (overtime_hours, overtime_rate)
        """
        employee = self.employee
        if employee:
            self.is_holiday, self.is_weekend = self.check_holiday_and_weekend(employee, self.date)
        if standard_hours is None:
            if self.shift_id and self.shift:
                # Use shift duration as standard hours
                shift_hours = self.shift.get_duration_hours()
                standard_hours = shift_hours if shift_hours is not None else 8.0
            else:
                # Default to 8 hours if no shift assigned
                standard_hours = 12.0
                
        # Update shift_type if we have a shift association but shift_type doesn't match
        if self.shift_id and self.shift:
            if 'night' in self.shift.name.lower() and self.shift_type != 'night':
                self.shift_type = 'night'
            elif 'day' in self.shift.name.lower() and self.shift_type != 'day':
                self.shift_type = 'day'
        
        # Ensure work_hours is not None before comparing
        if self.work_hours is None:
            self.work_hours = 0.0
        
        # Calculate work hours if not already calculated
        if self.work_hours <= 0:
            self.calculate_work_hours()
        
        # For weekends and holidays, ALL hours are considered overtime
        if self.is_weekend or self.is_holiday:
            overtime_hours = self.work_hours
        else:
            # For regular weekdays, only hours beyond standard hours are overtime
            if self.work_hours <= standard_hours:
                self.overtime_hours = 0.0
                self.overtime_rate = 1.0
                return 0.0, 1.0
                
            # Calculate overtime hours (work hours beyond standard hours)
            overtime_hours = self.work_hours - standard_hours 
        
        # Get appropriate overtime rule
        rule = None
        
        # Use linked rule if available
        if self.overtime_rule_id:
            rule = self.overtime_rule
        else:
            # Otherwise find applicable rule based on department, date, etc.
            # Get valid rules for this employee's department
            employee = self.employee
            if employee:
                department = employee.department
                rules = OvertimeRule.query.filter(
                    OvertimeRule.is_active == True,
                    (OvertimeRule.valid_from.is_(None) | (OvertimeRule.valid_from <= self.date)),
                    (OvertimeRule.valid_until.is_(None) | (OvertimeRule.valid_until >= self.date))
                ).order_by(OvertimeRule.priority.desc()).all()
                
                # Find first rule that applies to this department
                for r in rules:
                    if r.applies_to_department(department):
                        rule = r
                        # Store the rule for future reference
                        self.overtime_rule_id = r.id
                        break
        
        # Check if this day is a weekend for this employee
        is_weekend_day = False
        
        # Ensure date is not None
        if self.date is None:
            self.date = datetime.now().date()
            
        if self.employee:
            weekend_days = self.employee.get_weekend_days(self.date)
            if weekend_days:  # Make sure weekend_days isn't None
                is_weekend_day = self.date.weekday() in weekend_days
                
                # Extra verification for Sundays (weekday 6)
                if self.date.weekday() == 6 and 6 in weekend_days:
                    is_weekend_day = True
        else:
            # Fallback to system default if no employee associated
            system_config = SystemConfig.query.first()
            if system_config and system_config.weekend_days:
                is_weekend_day = self.date.weekday() in system_config.weekend_days
            else:
                # Default to Saturday and Sunday if no system config exists
                is_weekend_day = self.date.weekday() >= 5
        
        # Update the is_weekend flag based on the actual weekend configuration
        self.is_weekend = is_weekend_day
            
        # Apply rules if found, otherwise use defaults
        if rule:
            # Get base multiplier based on date and holiday status, passing employee for weekend detection
            rate = rule.get_overtime_multiplier(self.date, self.is_holiday if self.is_holiday is not None else False, self.employee)
            print(rate , "rate  ==== ---- -------------------------------- ")
            # Apply night shift differential if applicable
            is_night_shift = self.shift_type == 'night'
            
            # if self.check_in and self.check_out:
            #     rate = rule.apply_night_shift_differential(self.check_in, self.check_out, rate)
                
            # Apply maximum limits (ensure max_daily_overtime is not None)
            max_daily = rule.max_daily_overtime if rule.max_daily_overtime is not None else 4.0
            capped_overtime = min(overtime_hours, max_daily)
            
            # Calculate specific overtime types
            self.regular_overtime_hours = 0.0
            self.weekend_overtime_hours = 0.0
            self.holiday_overtime_hours = 0.0
            
            # If it's a night shift, track the overtime in the overtime_night_hours field
            if is_night_shift:
                self.overtime_night_hours = capped_overtime
            
            # Ensure is_holiday and is_weekend are not None
            is_holiday = self.is_holiday if self.is_holiday is not None else False
            is_weekend = self.is_weekend if self.is_weekend is not None else False
            
            # Categorize overtime based on day type
            if is_holiday and rule.apply_on_holiday:
                self.holiday_overtime_hours = capped_overtime
            elif is_weekend and rule.apply_on_weekend:
                self.weekend_overtime_hours = capped_overtime
            elif not is_weekend and not is_holiday and rule.apply_on_weekday:
                self.regular_overtime_hours = capped_overtime
                
            # Store total values - ensure it's the sum of all overtime categories
            self.overtime_hours = self.regular_overtime_hours + self.weekend_overtime_hours + self.holiday_overtime_hours #+ (self.grace_period_minutes or 0) / 60.0
            self.overtime_rate = rate
            self.overt_time_weighted =  self.overtime_hours *  self.overtime_rate
            print(capped_overtime,"capped_overtime=======================================================================")
            return capped_overtime, rate
        else:
            # Default calculation
            default_rate = 1.0 if self.is_weekend or self.is_holiday else 0
            
            # Categorize overtime based on day type with default rules
            self.regular_overtime_hours = 0.0
            self.weekend_overtime_hours = 0.0
            self.holiday_overtime_hours = 0.0
            self.overtime_night_hours = 0.0
            
            # Check if this is a night shift for night differential
            is_night_shift = self.shift_type == 'night'
            
            # Check employee eligibility for different overtime types
            employee = self.employee
            overtime_eligible = 0.0
            
            if self.is_holiday:
                if employee and employee.eligible_for_holiday_overtime:
                    self.holiday_overtime_hours = overtime_hours
                    overtime_eligible = overtime_hours
            elif self.is_weekend:
                if employee and employee.eligible_for_weekend_overtime:
                    self.weekend_overtime_hours = overtime_hours
                    overtime_eligible = overtime_hours
            else:
                if employee and employee.eligible_for_weekday_overtime:
                    self.regular_overtime_hours = overtime_hours
                    overtime_eligible = overtime_hours
            
            # Set night overtime hours for night shifts
            if is_night_shift and overtime_eligible > 0:
                self.overtime_night_hours = overtime_eligible
                
            # Ensure overtime_hours is the sum of all overtime categories
            self.overtime_hours =  self.regular_overtime_hours + self.weekend_overtime_hours + self.holiday_overtime_hours  #+ (self.grace_period_minutes or 0) / 60.0
            self.overtime_rate = default_rate
            self.overt_time_weighted =  self.overtime_hours *  self.overtime_rate
            print(overtime_eligible,"overtime_eligible==============================================================================")
            return overtime_eligible, default_rate

    def check_holiday_and_weekend(self,employee_id, date_obj):
        """
        Check if a given date is a holiday or weekend for a specific employee
        Returns tuple: (is_holiday, is_weekend)
        """
        # Check if it's a holiday
        is_holiday = False
        print(employee_id.id,"date_obj================================",date_obj)
        
        # Check for employee-specific holiday
        holiday = Holiday.query.filter(
            Holiday.date == date_obj,
            Holiday.employee_id == employee_id.id
        ).first()
        
        
        if holiday:
            is_holiday = True
        else:
            # Check for general holiday (non-employee-specific)
            general_holiday = Holiday.query.filter(
                Holiday.date == date_obj,
                Holiday.is_employee_specific == False
            ).first()
            
            if general_holiday:
                is_holiday = True
                
            # Check for recurring holiday (like New Year's Day every year)
            recurring_holiday = Holiday.query.filter(
                func.extract('month', Holiday.date) == date_obj.month,
                func.extract('day', Holiday.date) == date_obj.day,
                Holiday.is_recurring == True,
                or_(
                    Holiday.is_employee_specific == False,
                    Holiday.employee_id == employee_id.id
                )
            ).first()
            
            if recurring_holiday:
                is_holiday = True
        
        # Check if it's a weekend based on the employee's configuration
        employee = Employee.query.get(employee_id.id)
        is_weekend = False
        
        if employee:
            # Use the employee's weekend days (this automatically follows the priority logic)
            weekend_days = employee.get_weekend_days(date_obj)
            
            # Debug logging to help diagnose weekend detection issues
            print(f"DEBUG - Employee {employee_id}, date {date_obj}, weekday {date_obj.weekday()}, weekend_days {weekend_days}")
            
            # Check if the date's weekday is in the employee's weekend days
            is_weekend = date_obj.weekday() in weekend_days
            
            # Extra verification - Sunday is weekday 6
            if date_obj.weekday() == 6 and 6 in weekend_days:
                is_weekend = True
        
        return is_holiday, is_weekend

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_overnight = db.Column(db.Boolean, default=False)
    break_duration = db.Column(db.Float, default=0.0)  # Duration in hours
    grace_period_minutes = db.Column(db.Integer, default=15)  # Grace period for late arrivals in minutes
    is_active = db.Column(db.Boolean, default=True)
    color_code = db.Column(db.String(7), default="#3498db")  # Hex color for UI display
    weekend_days = db.Column(JSONB, nullable=True)  # Store list of days (0-6, Monday=0, Sunday=6)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    employees = db.relationship('Employee', backref=db.backref('assigned_shift', overlaps="current_shift"), lazy='dynamic')
    shift_assignments = db.relationship('ShiftAssignment', backref='shift', lazy='dynamic')
    
    def __repr__(self):
        return f'<Shift {self.name}>'
    
    def get_duration_hours(self):
        """Calculate shift duration in hours"""
        if self.is_overnight:
            # For overnight shifts, add 24 hours to end time
            end = datetime.combine(datetime.today(), self.end_time) + timedelta(days=1)
            start = datetime.combine(datetime.today(), self.start_time)
        else:
            end = datetime.combine(datetime.today(), self.end_time)
            start = datetime.combine(datetime.today(), self.start_time)
        
        duration = (end - start).total_seconds() / 3600
        return duration

class ShiftAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)  # NULL means indefinite
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ShiftAssignment {self.employee_id} {self.shift_id}>'

class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    date = db.Column(db.Date, nullable=False)
    is_recurring = db.Column(db.Boolean, default=False)
    is_employee_specific = db.Column(db.Boolean, default=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Holiday {self.name} {self.date}>'

class DeviceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('attendance_device.id'), nullable=False)
    log_type = db.Column(db.String(20), nullable=False)  # 'connection', 'error', 'sync'
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DeviceLog {self.device_id} {self.log_type}>'

class OdooMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_field = db.Column(db.String(64), nullable=False)
    odoo_field = db.Column(db.String(64), nullable=False)
    field_type = db.Column(db.String(20), default='text')  # 'text', 'number', 'date', 'boolean'
    is_required = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    default_value = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<OdooMapping {self.employee_field} -> {self.odoo_field}>'

class OdooConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=True)  # Full URL to Odoo instance
    host = db.Column(db.String(255), nullable=True)  # Keeping for backwards compatibility
    port = db.Column(db.Integer, nullable=True, default=5432)  # Keeping for backwards compatibility
    database = db.Column(db.String(255), nullable=True)
    username = db.Column(db.String(255), nullable=True)  # New field matching form
    user = db.Column(db.String(255), nullable=True)  # Keeping for backwards compatibility
    api_key = db.Column(db.String(255), nullable=True)  # New field for API key
    password = db.Column(db.String(255), nullable=True)  # Keeping for backwards compatibility
    is_active = db.Column(db.Boolean, default=False)  # Whether integration is enabled
    auto_sync = db.Column(db.Boolean, default=False)  # Whether to auto-sync on schedule
    sync_interval_hours = db.Column(db.Integer, default=24)
    last_sync = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        if self.url:
            return f'<OdooConfig {self.url}>'
        elif self.host:
            return f'<OdooConfig {self.host}:{self.port}/{self.database}>'
        else:
            return f'<OdooConfig {self.id}>'
            
    @property
    def connection_string(self):
        """Return a connection string for this configuration"""
        if self.url:
            return self.url
        elif self.host:
            return f'{self.host}:{self.port}'
        return None

class ERPConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_url = db.Column(db.String(255), nullable=False, default='https://erp.mir.ae:4082')
    username = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    auto_sync = db.Column(db.Boolean, default=False)
    sync_interval_hours = db.Column(db.Integer, default=24)
    last_sync = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ERPConfig {self.api_url}>'    

class OTPVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    
    def __repr__(self):
        return f'<OTPVerification {self.phone}>'

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    system_name = db.Column(db.String(128), default="MIR Attendance Management System")
    weekend_days = db.Column(JSONB, default=[5, 6])  # Default weekends: Saturday (5) and Sunday (6)
    default_work_hours = db.Column(db.Float, default=8.0)
    timezone = db.Column(db.String(64), default="Asia/Dubai") 
    date_format = db.Column(db.String(32), default="DD/MM/YYYY")
    time_format = db.Column(db.String(32), default="HH:mm:ss")
    
    # Break configuration
    minimum_break_duration = db.Column(db.Integer, default=15)  # Minimum break duration in minutes
    maximum_break_duration = db.Column(db.Integer, default=300)  # Maximum break duration in minutes
    
    # Default shift settings
    default_shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=True)
    
    # Bonus system configuration
    required_approvals = db.Column(db.Integer, default=2)  # Number of HR approvals required for bonus submissions
    
    # AI Assistant configuration
    ai_enabled = db.Column(db.Boolean, default=False)
    ai_provider = db.Column(db.String(64), default="openai")
    ai_model = db.Column(db.String(64), default="gpt-4o")
    ai_api_key = db.Column(db.String(256), nullable=True)  # Encrypted API key
    
    # AI Feature toggles
    enable_employee_assistant = db.Column(db.Boolean, default=False)
    enable_report_insights = db.Column(db.Boolean, default=False)
    enable_anomaly_detection = db.Column(db.Boolean, default=False)
    enable_predictive_scheduling = db.Column(db.Boolean, default=False)
    
    # AI advanced settings
    max_tokens = db.Column(db.Integer, default=1000)
    temperature = db.Column(db.Float, default=0.7)
    prompt_template = db.Column(db.Text, nullable=True)
    
    # AI usage statistics
    ai_total_queries = db.Column(db.Integer, default=0)
    ai_monthly_tokens = db.Column(db.Integer, default=0)
    ai_success_rate = db.Column(db.Float, default=0.0)
    
    # System metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    default_shift = db.relationship('Shift', foreign_keys=[default_shift_id])
    
    def __repr__(self):
        return f'<SystemConfig {self.id}>'
        
    @property
    def openai_api_key(self):
        """Backwards compatibility with old field name"""
        return self.ai_api_key
        
    @openai_api_key.setter
    def openai_api_key(self, value):
        """Backwards compatibility with old field name"""
        self.ai_api_key = value
        
    @property
    def ai_assistant_enabled(self):
        """Backwards compatibility with old field name"""
        return self.ai_enabled
        
    @ai_assistant_enabled.setter
    def ai_assistant_enabled(self, value):
        """Backwards compatibility with old field name"""
        self.ai_enabled = value

class OvertimeRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Rule conditions
    apply_on_weekday = db.Column(db.Boolean, default=True)
    apply_on_weekend = db.Column(db.Boolean, default=True)
    apply_on_holiday = db.Column(db.Boolean, default=True)
    
    # Applicable departments (comma-separated list, NULL means all)
    departments = db.Column(db.String(512), nullable=True)
    
    # Time thresholds
    daily_regular_hours = db.Column(db.Float, default=8.0)  # Standard work hours per day
    
    # Multipliers for overtime calculation
    weekday_multiplier = db.Column(db.Float, default=1.5)  # Standard overtime rate
    weekend_multiplier = db.Column(db.Float, default=2.0)  # Weekend overtime rate
    holiday_multiplier = db.Column(db.Float, default=2.5)  # Holiday overtime rate
    
    # Time threshold for night shift differential (e.g., 22:00)
    night_shift_start_time = db.Column(db.Time, nullable=True)
    night_shift_end_time = db.Column(db.Time, nullable=True)
    night_shift_multiplier = db.Column(db.Float, default=1.2)  # Additional multiplier for night hours
    
    # Maximum hours allowed for overtime per day/week/month
    max_daily_overtime = db.Column(db.Float, default=4.0)    # Max 4h overtime per day
    max_weekly_overtime = db.Column(db.Float, default=15.0)  # Max 15h overtime per week
    max_monthly_overtime = db.Column(db.Float, default=36.0) # Max 36h overtime per month
    
    # Rule priority (higher number = higher priority)
    priority = db.Column(db.Integer, default=10)
    
    # Rule status
    is_active = db.Column(db.Boolean, default=True)
    
    # Rule validities
    valid_from = db.Column(db.Date, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<OvertimeRule {self.name}>'
    
    def applies_to_department(self, department):
        """Check if this rule applies to the given department"""
        if not self.departments:
            return True  # Rule applies to all departments
        
        # Check if department is in comma-separated list
        departments_list = [d.strip().lower() for d in self.departments.split(',')]
        return department.lower().strip() in departments_list
    
    def get_overtime_multiplier(self, date_obj, is_holiday=False, employee=None):
        """
        Get the appropriate multiplier based on date and holiday status.
        Takes into account employee-specific, shift-specific or system-wide weekend settings.
        """
        if is_holiday and self.apply_on_holiday:
            return self.holiday_multiplier
        
        # Check if it's a weekend based on employee's weekend days or system config
        is_weekend = False
        if employee:
            # Use the employee's weekend days configuration
            weekend_days = employee.get_weekend_days(date_obj)
            is_weekend = date_obj.weekday() in weekend_days
        else:
            # Fallback to system default (weekend is Saturday and Sunday)
            system_config = SystemConfig.query.first()
            if system_config and system_config.weekend_days:
                is_weekend = date_obj.weekday() in system_config.weekend_days
            else:
                # Default to Saturday and Sunday if no system config exists
                is_weekend = date_obj.weekday() >= 5
        
        if is_weekend and self.apply_on_weekend:
            return self.weekend_multiplier
        
        if not is_weekend and self.apply_on_weekday:
            return self.weekday_multiplier
        
        # Default multiplier if no specific condition matches
        return 1.0
    
    def apply_night_shift_differential(self, start_datetime, end_datetime, base_multiplier):
        """
        Apply night shift differential to hours worked during the night shift period
        Returns adjusted multiplier
        """
        if not self.night_shift_start_time or not self.night_shift_end_time:
            return base_multiplier  # No night shift differential defined
        
        # Create datetime objects for night shift start/end on the same day as check-in
        base_date = start_datetime.date()
        night_start = datetime.combine(base_date, self.night_shift_start_time)
        night_end = datetime.combine(base_date, self.night_shift_end_time)
        
        # Handle overnight night shift (e.g., 22:00-06:00)
        if night_end < night_start:
            night_end = night_end + timedelta(days=1)
        
        # Ensure end_datetime is after start_datetime (handle overnight shifts)
        if end_datetime < start_datetime:
            end_datetime = end_datetime + timedelta(days=1)
        
        # Calculate total work duration
        total_duration = (end_datetime - start_datetime).total_seconds() / 3600
        
        # Calculate night shift overlap
        night_overlap_start = max(start_datetime, night_start)
        night_overlap_end = min(end_datetime, night_end)
        
        # If there's an overlap with night shift
        if night_overlap_end > night_overlap_start:
            night_hours = (night_overlap_end - night_overlap_start).total_seconds() / 3600
            regular_hours = total_duration - night_hours
            
            # Calculate weighted average multiplier
            if total_duration > 0:
                adjusted_multiplier = (
                    (regular_hours * base_multiplier) + 
                    (night_hours * base_multiplier * self.night_shift_multiplier)
                ) / total_duration
                return adjusted_multiplier
        
        return base_multiplier  # No night shift overlap


# Bonus Calculation System Models
class BonusQuestion(db.Model):
    """Bonus question definition by HR for departments"""
    id = db.Column(db.Integer, primary_key=True)
    department = db.Column(db.String(128), nullable=False)
    question_text = db.Column(db.String(256), nullable=False)
    min_value = db.Column(db.Integer, default=-10, nullable=False)
    max_value = db.Column(db.Integer, default=10, nullable=False)
    default_value = db.Column(db.Integer, default=0, nullable=False)
    weight = db.Column(db.Float, default=1.0, nullable=False)  # Weight factor for this question
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    # need to  create boolen here for thee type Attendance, Efficiency, Waste Reduction
    only_hr = db.Column(db.Boolean, default=True)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    evaluations = db.relationship('BonusEvaluation', back_populates='question', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<BonusQuestion {self.question_text[:20]}...>"


class BonusEvaluationPeriod(db.Model):
    """Period for which bonus evaluations are conducted"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)  # E.g. "Q1 2025", "May 2025"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(32), default='open', nullable=False)  # open, in_review, approved, closed
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    submissions = db.relationship('BonusSubmission', back_populates='period', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<BonusEvaluationPeriod {self.name}>"



class BonusSubmission(db.Model):
    """Bonus submission by supervisor for a department"""
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('bonus_evaluation_period.id'), nullable=False)
    department = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(32), default='draft', nullable=False)  # draft, submitted, in_review, approved, rejected
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    submitted_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Multi-level approval fields
    approval_level = db.Column(db.Integer, default=0)  # 0=not approved, 1=first level, 2=second level, 3=final
    approvers = db.Column(JSONB, default=list)  # List of user IDs who approved
    supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))  # Current assigned supervisor
    
    # Relationships
    period = db.relationship('BonusEvaluationPeriod', back_populates='submissions')
    submitter = db.relationship('User', foreign_keys=[submitted_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    supervisor = db.relationship('Employee', foreign_keys=[supervisor_id])
    evaluations = db.relationship('BonusEvaluation', back_populates='submission', cascade='all, delete-orphan')
    audit_logs = db.relationship('BonusAuditLog', back_populates='submission', cascade='all, delete-orphan')
    
    def calculate_total_points(self, employee_id=None):
        """Calculate total bonus points for all employees or a specific employee"""
        print ( "in method ")
        if employee_id:
            print ( "in employee_id ")
            evaluations = [e for e in self.evaluations if e.employee_id == employee_id]
        else:
            print ( "else employee_id ")
            evaluations = self.evaluations
            
        # Group by employee
        employee_points = {}
        for eval in evaluations:
            print ( "loop evaluations ")
            if eval.employee_id not in employee_points:
                employee_points[eval.employee_id] = 0
            print ( eval.value,"eval.value" )
            print(eval.question.weight, "eval.question.weight")
            print(eval.submission_id)
            employee_points[eval.employee_id] += eval.value * eval.question.weight
            
        return employee_points
    
    def __repr__(self):
        return f"<BonusSubmission {self.department} - {self.period.name if self.period else 'No Period'}>"


class BonusEvaluationHistory(db.Model):
    __tablename__ = 'bonus_evaluation_history'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('bonus_submission.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('bonus_question.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    record_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    odoo_status = db.Column(db.String(64), nullable=True)

    # Forward relationships only
    creator = db.relationship('User')
    submission = db.relationship('BonusSubmission')  # No back_populates
    employee = db.relationship('Employee')
    question = db.relationship('BonusQuestion')

    def __repr__(self):
        return f"<BonusEvaluationHistory Employee={self.employee_id} Question={self.question_id} Value={self.value}>"

class BonusEvaluation(db.Model):
    """Individual bonus evaluation for an employee on a specific question"""
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('bonus_submission.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('bonus_question.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    original_value = db.Column(db.Integer)  # To track changes by HR
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    submission = db.relationship('BonusSubmission', back_populates='evaluations')
    employee = db.relationship('Employee')
    question = db.relationship('BonusQuestion', back_populates='evaluations')
    odoo_status = db.Column(db.String(64), nullable=True)
    
    def __repr__(self):
        return f"<BonusEvaluation Employee={self.employee_id} Question={self.question_id} Value={self.value}>"


class BonusAuditLog(db.Model):
    """Audit log for all changes to bonus evaluations"""
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('bonus_submission.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    question_id = db.Column(db.Integer, db.ForeignKey('bonus_question.id'))
    action = db.Column(db.String(32), nullable=False)  # created, updated, submitted, approved, rejected
    old_value = db.Column(db.Integer)
    new_value = db.Column(db.Integer)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    submission = db.relationship('BonusSubmission', back_populates='audit_logs')
    employee = db.relationship('Employee')
    question = db.relationship('BonusQuestion')
    user = db.relationship('User')
    
    def __repr__(self):
        return f"<BonusAuditLog {self.action} by {self.user_id} at {self.timestamp}>"
