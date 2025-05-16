"""
Test Data Manager for MIR AMS

This module provides functions to:
1. Reset the database by deleting employee, attendance, and related data
2. Generate fresh test data similar to the advanced test scenario
3. Process the generated logs automatically

Use this module for testing and demonstration purposes.
"""
import os
import sys
import random
import logging
from datetime import datetime, timedelta, time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test employee codes and names
TEST_EMPLOYEES = [
    {"code": "TEST-001", "name": "Test Employee A", "department": "Production"},
    {"code": "TEST-002", "name": "Test Employee B", "department": "Quality Control"}
]

# Shift IDs
DAY_SHIFT_ID = 1   # 9am-5pm
NIGHT_SHIFT_ID = 2  # 8pm-8am

# Device ID for logging
DEVICE_ID = 3  # ZKTeco CSV Import device

# Scenario date range (default to current month)
DEFAULT_START_DATE = datetime.today().replace(day=1)
DEFAULT_END_DATE = (DEFAULT_START_DATE.replace(month=DEFAULT_START_DATE.month+1, day=1) - timedelta(days=1))

# Known holidays (can be customized)
DEFAULT_HOLIDAYS = [
    datetime.today().replace(day=1).date(),  # First day of month as a holiday
    datetime.today().replace(day=15).date(),  # 15th of month as a holiday
]

class TestDataManager:
    """Manages test data for the MIR AMS system"""
    
    def __init__(self, db_uri=None):
        """Initialize with database URI"""
        self.db_uri = db_uri or os.environ.get("DATABASE_URL")
        if not self.db_uri:
            logger.error("Error: DATABASE_URL environment variable not set.")
            sys.exit(1)
        
        # Create database engine and session
        self.engine = create_engine(self.db_uri)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        
        # Store employee IDs for reference
        self.employee_ids = []
    
    def reset_database(self, preserve_admin=True, preserve_config=True):
        """
        Reset the database by deleting all test data
        
        Args:
            preserve_admin: If True, preserves admin user accounts
            preserve_config: If True, preserves system and integration configuration
        """
        logger.info("Starting complete database reset...")
        
        try:
            # Clear foreign key dependencies in the right order
            
            # 1. First clear attendance_log references to attendance_record
            self.session.execute(text("""
                UPDATE attendance_log 
                SET attendance_record_id = NULL, is_processed = false
                WHERE attendance_record_id IS NOT NULL
            """))
            logger.info("Reset attendance log references")
            
            # 2. Clear all OTP verifications
            result = self.session.execute(text("DELETE FROM otp_verification"))
            logger.info(f"Deleted {result.rowcount} OTP verifications")
            
            # 3. Clear all holidays that reference employees
            result = self.session.execute(text("DELETE FROM holiday WHERE employee_id IS NOT NULL"))
            logger.info(f"Deleted {result.rowcount} employee-specific holidays")
            
            # 4. Delete attendance logs 
            result = self.session.execute(text("DELETE FROM attendance_log"))
            logger.info(f"Deleted {result.rowcount} attendance logs")
            
            # 5. Delete attendance records
            result = self.session.execute(text("DELETE FROM attendance_record"))
            logger.info(f"Deleted {result.rowcount} attendance records")
            
            # 6. Delete shift assignments
            result = self.session.execute(text("DELETE FROM shift_assignment"))
            logger.info(f"Deleted {result.rowcount} shift assignments")
            
            # 7. Update employee.current_shift_id to NULL
            self.session.execute(text("UPDATE employee SET current_shift_id = NULL"))
            logger.info("Reset employee shift references")
            
            # 8. Delete employees 
            result = self.session.execute(text("DELETE FROM employee"))
            logger.info(f"Deleted {result.rowcount} employees")
            
            # 9. Now we can safely delete all shifts
            result = self.session.execute(text("DELETE FROM shift"))
            logger.info(f"Deleted {result.rowcount} shifts")
            
            # Delete overtime rules (will regenerate default ones)
            result = self.session.execute(text("DELETE FROM overtime_rule"))
            logger.info(f"Deleted {result.rowcount} overtime rules")
            
            # Reset overtime_rule sequence
            self.session.execute(text("ALTER SEQUENCE overtime_rule_id_seq RESTART WITH 1"))
            
            # Delete holidays
            result = self.session.execute(text("DELETE FROM holiday"))
            logger.info(f"Deleted {result.rowcount} holidays")
                
            # Reset shift sequence to ensure new IDs start from 1
            self.session.execute(text("ALTER SEQUENCE shift_id_seq RESTART WITH 1"))
            
            # Create default shifts
            self.session.execute(text("""
                INSERT INTO shift (id, name, start_time, end_time, is_overnight, 
                                  break_duration, weekend_days, is_active, 
                                  created_at, updated_at)
                VALUES 
                (1, 'Day Shift', '09:00:00', '17:00:00', false, 
                 1.0, '[5, 6]'::jsonb, true, 
                 NOW(), NOW()),
                (2, 'Night Shift', '20:00:00', '08:00:00', true, 
                 1.0, '[5, 6]'::jsonb, true, 
                 NOW(), NOW())
            """))
            logger.info("Created default shifts")
            
            # Create default overtime rule
            self.session.execute(text("""
            INSERT INTO overtime_rule (
                name, description, apply_on_weekday, apply_on_weekend, apply_on_holiday,
                daily_regular_hours, weekday_multiplier, weekend_multiplier, holiday_multiplier,
                priority, is_active, created_at, updated_at
            )
            VALUES (
                'Standard Overtime', 'Default overtime rule', true, true, true,
                8.0, 1.5, 2.0, 2.5,
                10, true, NOW(), NOW()
            )
            """))
            logger.info("Created default overtime rule")
            
            self.session.commit()
            logger.info("Database reset completed successfully")
            return True
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error resetting database: {str(e)}")
            return False
    
    def create_test_employees(self):
        """Create test employees with different departments"""
        logger.info("Creating test employees...")
        self.employee_ids = []
        
        # Get department IDs from database
        departments = {
            "Production": 1,
            "Quality Control": 2,
            "Packaging": 3
        }
        
        try:
            # Create each test employee
            for emp in TEST_EMPLOYEES:
                # Check if department exists
                dept_id = departments.get(emp["department"], 1)  # Default to first department if not found
                
                # Create employee
                query = text("""
                    INSERT INTO employee 
                    (employee_code, name, department, is_active, weekend_days) 
                    VALUES 
                    (:employee_code, :name, :department, true, :weekend_days)
                    RETURNING id
                """)
                
                # First employee has standard weekend (Sat, Sun)
                # Second employee has custom weekend (only Sunday)
                weekend_days = "[5, 6]" if emp == TEST_EMPLOYEES[0] else "[6]"
                
                result = self.session.execute(query, {
                    "employee_code": emp["code"],
                    "name": emp["name"],
                    "department": emp["department"],
                    "weekend_days": weekend_days
                })
                
                employee_id = result.fetchone()[0]
                self.employee_ids.append(employee_id)
                logger.info(f"Created employee: {emp['name']} (ID: {employee_id})")
            
            self.session.commit()
            logger.info(f"Created {len(self.employee_ids)} test employees")
            return self.employee_ids
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating test employees: {str(e)}")
            return []
    
    def create_shift_assignments(self, start_date=None, end_date=None):
        """
        Create shift assignments for the test month:
        - Week 1: Employee A on day shift, Employee B on night shift
        - Week 2: Employee A on night shift, Employee B on day shift
        - Week 3: Employee A on day shift, Employee B on night shift
        - Week 4: Employee A on night shift, Employee B on day shift
        """
        if not self.employee_ids or len(self.employee_ids) < 2:
            logger.error("No test employees found. Please create test employees first.")
            return False
        
        start_date = start_date or DEFAULT_START_DATE.date()
        end_date = end_date or DEFAULT_END_DATE.date()
        
        logger.info(f"Creating shift assignments from {start_date} to {end_date}...")
        
        try:
            # Calculate week boundaries
            days_in_month = (end_date - start_date).days + 1
            week_length = days_in_month // 4 if days_in_month >= 28 else 7
            
            # First week
            week1_start = start_date
            week1_end = start_date + timedelta(days=week_length-1)
            
            # Second week
            week2_start = week1_end + timedelta(days=1)
            week2_end = week2_start + timedelta(days=week_length-1)
            
            # Third week
            week3_start = week2_end + timedelta(days=1)
            week3_end = week3_start + timedelta(days=week_length-1)
            
            # Fourth week (to end of month)
            week4_start = week3_end + timedelta(days=1)
            week4_end = end_date
            
            # Define assignments
            assignments = [
                # Week 1
                (self.employee_ids[0], DAY_SHIFT_ID, week1_start, week1_end),
                (self.employee_ids[1], NIGHT_SHIFT_ID, week1_start, week1_end),
                # Week 2
                (self.employee_ids[0], NIGHT_SHIFT_ID, week2_start, week2_end),
                (self.employee_ids[1], DAY_SHIFT_ID, week2_start, week2_end),
                # Week 3
                (self.employee_ids[0], DAY_SHIFT_ID, week3_start, week3_end),
                (self.employee_ids[1], NIGHT_SHIFT_ID, week3_start, week3_end),
                # Week 4
                (self.employee_ids[0], NIGHT_SHIFT_ID, week4_start, week4_end),
                (self.employee_ids[1], DAY_SHIFT_ID, week4_start, week4_end),
            ]
            
            # Insert assignments
            for employee_id, shift_id, start, end in assignments:
                query = text("""
                    INSERT INTO shift_assignment 
                    (employee_id, shift_id, start_date, end_date, is_active) 
                    VALUES 
                    (:employee_id, :shift_id, :start_date, :end_date, true)
                """)
                self.session.execute(query, {
                    "employee_id": employee_id,
                    "shift_id": shift_id,
                    "start_date": start,
                    "end_date": end
                })
            
            self.session.commit()
            logger.info(f"Created {len(assignments)} shift assignments")
            return True
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating shift assignments: {str(e)}")
            return False
    
    def get_shift_times(self, shift_id, date_obj):
        """Get standard check-in and check-out times for a shift on a given date"""
        query = text("""
            SELECT start_time, end_time, is_overnight
            FROM shift
            WHERE id = :shift_id
        """)
        result = self.session.execute(query, {"shift_id": shift_id}).fetchone()
        
        if not result:
            return None, None
        
        start_time, end_time, is_overnight = result
        
        # Create datetime objects
        check_in_time = datetime.combine(date_obj, start_time)
        
        if is_overnight:
            # For overnight shifts, checkout is on the next day
            next_day = date_obj + timedelta(days=1)
            check_out_time = datetime.combine(next_day, end_time)
        else:
            check_out_time = datetime.combine(date_obj, end_time)
        
        return check_in_time, check_out_time
    
    def create_scenario_variation(self, standard_check_in, standard_check_out, scenario_type, date_obj, is_weekend, is_holiday):
        """Create a specific attendance variation based on the scenario type"""
        
        # These are the possible scenarios we'll generate
        scenarios = {
            'normal': {
                'check_in_delta': (-5, 5),     # Regular attendance (-5 to +5 minutes)
                'check_out_delta': (-5, 5),    # Regular departure (-5 to +5 minutes)
                'break_minutes': (45, 60),     # Normal break duration
                'has_check_in': True,          # Has check-in
                'has_check_out': True,         # Has check-out
                'add_break_punches': True,     # Add break punch logs
            },
            'late': {
                'check_in_delta': (10, 30),    # Late arrival (10-30 minutes late)
                'check_out_delta': (-5, 5),    # Regular departure
                'break_minutes': (45, 60),     # Normal break
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'early_departure': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (-60, -30), # Early departure (30-60 minutes early)
                'break_minutes': (30, 45),     # Shorter break (left early)
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'missing_check_in': {
                'check_in_delta': (0, 0),      # Not used
                'check_out_delta': (-5, 5),    # Regular departure
                'break_minutes': (0, 0),       # Not relevant
                'has_check_in': False,
                'has_check_out': True,
                'add_break_punches': False,    # No break punches
            },
            'missing_check_out': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (0, 0),     # Not used
                'break_minutes': (0, 0),       # Not relevant
                'has_check_in': True,
                'has_check_out': False,
                'add_break_punches': False,    # No break punches
            },
            'long_work': {
                'check_in_delta': (-15, -5),   # Early arrival (5-15 minutes)
                'check_out_delta': (60, 120),  # Late departure (1-2 hours)
                'break_minutes': (45, 60),     # Normal break
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'short_break': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (-5, 5),    # Regular departure
                'break_minutes': (15, 25),     # Short break (15-25 minutes)
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'long_break': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (-5, 5),    # Regular departure
                'break_minutes': (90, 120),    # Long break (90-120 minutes)
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'weekend_work': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (60, 120),  # Longer stay (1-2 hours)
                'break_minutes': (45, 60),     # Normal break
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            },
            'holiday_work': {
                'check_in_delta': (-5, 5),     # Regular arrival
                'check_out_delta': (60, 180),  # Much longer stay (1-3 hours)
                'break_minutes': (45, 60),     # Normal break
                'has_check_in': True,
                'has_check_out': True,
                'add_break_punches': True,     # Add break punch logs
            }
        }
        
        # Override scenario type for weekends and holidays if needed
        if is_weekend:
            scenario_type = 'weekend_work'
        elif is_holiday:
            scenario_type = 'holiday_work'
        
        # Get the scenario parameters
        scenario = scenarios.get(scenario_type, scenarios['normal'])
        
        # Apply check-in variation
        if scenario['has_check_in']:
            minutes_delta = random.randint(*scenario['check_in_delta'])
            check_in = standard_check_in + timedelta(minutes=minutes_delta)
        else:
            check_in = None
        
        # Apply check-out variation
        if scenario['has_check_out']:
            minutes_delta = random.randint(*scenario['check_out_delta'])
            check_out = standard_check_out + timedelta(minutes=minutes_delta)
        else:
            check_out = None
        
        # Calculate break minutes (if both check-in and check-out exist)
        break_minutes = 0
        if check_in and check_out and scenario['break_minutes'][1] > 0:
            break_minutes = random.randint(*scenario['break_minutes'])
            
            # Create break punch logs if needed
            if scenario['add_break_punches'] and break_minutes >= 15:
                # Calculate midpoint of shift for break start
                total_minutes = (check_out - check_in).total_seconds() / 60
                break_start_offset = total_minutes / 2 - break_minutes / 2
                break_start = check_in + timedelta(minutes=break_start_offset)
                
                # Add 5 minutes randomness to break start
                break_start_jitter = random.randint(-5, 5)
                break_start = break_start + timedelta(minutes=break_start_jitter)
                
                # Calculate break end
                break_end = break_start + timedelta(minutes=break_minutes)
                
                # Store break times for punches
                self.break_punches = {
                    'break_out': break_start,
                    'break_in': break_end,
                    'employee_id': None  # Will be set by caller
                }
            else:
                self.break_punches = None
        else:
            self.break_punches = None
        
        return check_in, check_out, break_minutes, scenario_type
    
    def create_attendance_logs(self, start_date=None, end_date=None, holidays=None):
        """Create attendance logs for our test employees with various scenarios"""
        if not self.employee_ids or len(self.employee_ids) < 2:
            logger.error("No test employees found. Please create test employees first.")
            return False
        
        start_date = start_date or DEFAULT_START_DATE.date()
        end_date = end_date or DEFAULT_END_DATE.date()
        holidays = holidays or DEFAULT_HOLIDAYS
        
        logger.info(f"Creating attendance logs from {start_date} to {end_date}...")
        
        try:
            # Get all shift assignments for our test employees
            query = text("""
                SELECT id, employee_id, shift_id, start_date, end_date
                FROM shift_assignment
                WHERE employee_id IN (:emp_a, :emp_b)
                ORDER BY start_date, employee_id
            """)
            assignments = self.session.execute(query, {
                "emp_a": self.employee_ids[0], 
                "emp_b": self.employee_ids[1]
            }).fetchall()
            
            if not assignments:
                logger.error("No shift assignments found. Please create shift assignments first.")
                return False
            
            # These are the scenario types we'll randomly select from
            scenario_types = [
                'normal',          # Normal work day
                'late',            # Late arrival
                'early_departure', # Early departure
                'missing_check_in',# Missing check-in
                'missing_check_out',# Missing check-out
                'long_work',       # Longer work hours (overtime)
                'short_break',     # Short break time
                'long_break',      # Long break time
            ]
            
            # Special scenario distribution (to ensure we have enough test cases)
            scenario_weights = {
                'normal': 4,           # 33.3% normal days
                'late': 2,             # 16.7% late arrivals
                'early_departure': 2,  # 16.7% early departures
                'missing_check_in': 1, # 8.3% missing check-ins
                'missing_check_out': 1,# 8.3% missing check-outs
                'long_work': 1,        # 8.3% overtime days
                'short_break': 1,      # 8.3% short break days
                'long_break': 0,       # Not used directly, will override some normal days
            }
            
            # Generate weighted scenario list
            weighted_scenarios = []
            for scenario, weight in scenario_weights.items():
                weighted_scenarios.extend([scenario] * weight)
            
            # Keep track of which dates have been processed
            processed_dates = set()
            logs_created = 0
            
            # Process each assignment
            for assignment in assignments:
                employee_id = assignment.employee_id
                shift_id = assignment.shift_id
                assign_start_date = max(assignment.start_date, start_date)
                assign_end_date = min(assignment.end_date, end_date)
                
                current_date = assign_start_date
                while current_date <= assign_end_date:
                    date_key = (employee_id, current_date)
                    
                    # Skip if we already processed this date
                    if date_key in processed_dates:
                        current_date += timedelta(days=1)
                        continue
                    
                    processed_dates.add(date_key)
                    
                    # Check if it's a weekend or holiday
                    is_weekend = current_date.weekday() >= 5  # Saturday or Sunday
                    is_holiday = current_date in holidays
                    
                    # Get standard check-in and check-out times for this shift
                    standard_check_in, standard_check_out = self.get_shift_times(shift_id, current_date)
                    
                    if not standard_check_in or not standard_check_out:
                        current_date += timedelta(days=1)
                        continue
                    
                    # Determine scenario for this day
                    # Use a seeded random for specific employees and dates to create
                    # special scenarios on specific days
                    random.seed(f"{employee_id}-{current_date}")
                    
                    # Special case: 5th day - Employee A has a short break
                    if employee_id == self.employee_ids[0] and current_date == start_date + timedelta(days=4):
                        scenario_type = 'short_break'
                    # Special case: 6th day - Employee B has a long break
                    elif employee_id == self.employee_ids[1] and current_date == start_date + timedelta(days=5):
                        scenario_type = 'long_break'
                    # Special case: First holiday - Employee B works overtime
                    elif employee_id == self.employee_ids[1] and holidays and current_date == holidays[0]:
                        scenario_type = 'holiday_work'
                    # Special case: Weekend (3-4 days into month) - Both employees work
                    elif current_date in [start_date + timedelta(days=i) for i in [2, 3]] and current_date.weekday() >= 5:
                        scenario_type = 'weekend_work'
                    # Default: random scenario
                    else:
                        scenario_type = random.choice(weighted_scenarios)
                    
                    # Create the scenario variation
                    check_in, check_out, break_minutes, final_scenario = self.create_scenario_variation(
                        standard_check_in, standard_check_out, scenario_type, 
                        current_date, is_weekend, is_holiday
                    )
                    
                    # Insert check-in log if exists
                    if check_in:
                        query = text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, log_type, timestamp, is_processed)
                            VALUES
                            (:employee_id, :device_id, 'check_in', :timestamp, false)
                        """)
                        self.session.execute(query, {
                            "employee_id": employee_id,
                            "device_id": DEVICE_ID,
                            "timestamp": check_in
                        })
                        logs_created += 1
                    
                    # Insert break logs if they exist
                    if self.break_punches:
                        # Set the employee_id for the break punches
                        self.break_punches['employee_id'] = employee_id
                        
                        # Insert break-out log
                        query = text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, log_type, timestamp, is_processed)
                            VALUES
                            (:employee_id, :device_id, 'break_out', :timestamp, false)
                        """)
                        self.session.execute(query, {
                            "employee_id": employee_id,
                            "device_id": DEVICE_ID,
                            "timestamp": self.break_punches['break_out']
                        })
                        logs_created += 1
                        
                        # Insert break-in log
                        query = text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, log_type, timestamp, is_processed)
                            VALUES
                            (:employee_id, :device_id, 'break_in', :timestamp, false)
                        """)
                        self.session.execute(query, {
                            "employee_id": employee_id,
                            "device_id": DEVICE_ID,
                            "timestamp": self.break_punches['break_in']
                        })
                        logs_created += 1
                    
                    # Insert check-out log if exists
                    if check_out:
                        query = text("""
                            INSERT INTO attendance_log
                            (employee_id, device_id, log_type, timestamp, is_processed)
                            VALUES
                            (:employee_id, :device_id, 'check_out', :timestamp, false)
                        """)
                        self.session.execute(query, {
                            "employee_id": employee_id,
                            "device_id": DEVICE_ID,
                            "timestamp": check_out
                        })
                        logs_created += 1
                    
                    # Print a summary of this attendance record
                    logger.info(f"Created {final_scenario} scenario for {current_date} - Employee {employee_id}")
                    
                    # Move to next day
                    current_date += timedelta(days=1)
            
            self.session.commit()
            logger.info(f"Created {logs_created} attendance logs")
            return logs_created
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating attendance logs: {str(e)}")
            return False
    
    def process_attendance_logs(self):
        """Process attendance logs for test employees"""
        if not self.employee_ids:
            logger.error("No test employees found. Please create test employees first.")
            return False
        
        try:
            # Get all unprocessed logs for test employees
            query = text("""
                SELECT id, employee_id, device_id, timestamp, log_type
                FROM attendance_log
                WHERE employee_id IN :employee_ids
                  AND is_processed = false
                ORDER BY employee_id, timestamp
            """)
            logs = self.session.execute(query, {
                "employee_ids": tuple(self.employee_ids)
            }).fetchall()
            
            if not logs:
                logger.info("No unprocessed logs found for test employees.")
                return True
            
            logger.info(f"Processing {len(logs)} unprocessed logs...")
            
            # Group logs by employee and date
            employee_date_logs = {}
            for log in logs:
                log_date = log.timestamp.date()
                employee_id = log.employee_id
                key = (employee_id, log_date)
                
                if key not in employee_date_logs:
                    employee_date_logs[key] = []
                
                employee_date_logs[key].append(log)
            
            logger.info(f"Grouped into {len(employee_date_logs)} employee-date pairs")
            
            # Process each group of logs
            records_created = 0
            
            for (employee_id, log_date), day_logs in employee_date_logs.items():
                # Process logs to get check-in/check-out times
                check_in = None
                check_out = None
                break_out_times = []
                break_in_times = []
                
                for log in day_logs:
                    if log.log_type == 'check_in' and (check_in is None or log.timestamp < check_in):
                        check_in = log.timestamp
                    elif log.log_type == 'check_out' and (check_out is None or log.timestamp > check_out):
                        check_out = log.timestamp
                    elif log.log_type == 'break_out':
                        break_out_times.append(log.timestamp)
                    elif log.log_type == 'break_in':
                        break_in_times.append(log.timestamp)
                
                if not check_in and not check_out:
                    logger.warning(f"Skipping {log_date} for Employee {employee_id}: no valid logs")
                    continue
                
                # Calculate break duration
                break_duration = 0
                if break_out_times and break_in_times:
                    # Sort the break times
                    break_out_times.sort()
                    break_in_times.sort()
                    
                    # Pair them as best as possible
                    for i in range(min(len(break_out_times), len(break_in_times))):
                        break_out = break_out_times[i]
                        break_in = break_in_times[i]
                        
                        # Only count if break_in is after break_out
                        if break_in > break_out:
                            break_duration += (break_in - break_out).total_seconds() / 3600
                
                # Calculate work hours
                work_hours = 0
                status = 'missing_logs'
                
                # Find shift info to determine if overnight
                query = text("""
                    SELECT s.is_overnight
                    FROM shift_assignment sa
                    JOIN shift s ON sa.shift_id = s.id
                    WHERE sa.employee_id = :employee_id
                      AND sa.start_date <= :date
                      AND (sa.end_date >= :date OR sa.end_date IS NULL)
                """)
                
                shift_info = self.session.execute(query, {
                    "employee_id": employee_id,
                    "date": log_date
                }).fetchone()
                
                is_overnight_shift = shift_info and shift_info.is_overnight
                
                if check_in and check_out:
                    # Calculate work hours
                    if check_out < check_in:
                        # For overnight shifts, add 24 hours
                        next_day_checkout = check_out + timedelta(days=1)
                        work_hours = (next_day_checkout - check_in).total_seconds() / 3600
                    else:
                        work_hours = (check_out - check_in).total_seconds() / 3600
                    
                    # Determine status
                    status = 'present'
                    if work_hours < 4:
                        status = 'half-day'
                elif check_in:
                    status = 'missing_checkout'
                else:
                    status = 'missing_checkin'
                
                # Check if it's a weekend or holiday
                is_weekend = log_date.weekday() >= 5  # Saturday or Sunday
                
                query = text("""
                    SELECT id FROM holiday
                    WHERE date = :date
                """)
                holiday = self.session.execute(query, {"date": log_date}).fetchone()
                is_holiday = bool(holiday)
                
                # Find shift assignment
                query = text("""
                    SELECT shift_id
                    FROM shift_assignment
                    WHERE employee_id = :employee_id
                      AND start_date <= :date
                      AND (end_date >= :date OR end_date IS NULL)
                """)
                shift_assignment = self.session.execute(query, {
                    "employee_id": employee_id,
                    "date": log_date
                }).fetchone()
                
                shift_id = shift_assignment.shift_id if shift_assignment else None
                
                # Find overtime rule
                query = text("""
                    SELECT id FROM overtime_rule
                    WHERE is_active = true
                      AND (valid_from IS NULL OR valid_from <= :date)
                      AND (valid_until IS NULL OR valid_until >= :date)
                    ORDER BY priority DESC
                    LIMIT 1
                """)
                overtime_rule = self.session.execute(query, {"date": log_date}).fetchone()
                overtime_rule_id = overtime_rule.id if overtime_rule else None
                
                # Calculate actual work hours after deducting breaks
                if work_hours > 0 and break_duration > 0:
                    work_hours -= break_duration
                
                # Create attendance record
                query = text("""
                    INSERT INTO attendance_record
                    (employee_id, shift_id, overtime_rule_id, date, check_in, check_out,
                     status, is_holiday, is_weekend, work_hours, break_duration, created_at, updated_at)
                    VALUES
                    (:employee_id, :shift_id, :overtime_rule_id, :date, :check_in, :check_out,
                     :status, :is_holiday, :is_weekend, :work_hours, :break_duration, NOW(), NOW())
                    RETURNING id
                """)
                
                result = self.session.execute(query, {
                    "employee_id": employee_id,
                    "shift_id": shift_id,
                    "overtime_rule_id": overtime_rule_id,
                    "date": log_date,
                    "check_in": check_in,
                    "check_out": check_out,
                    "status": status,
                    "is_holiday": is_holiday,
                    "is_weekend": is_weekend,
                    "work_hours": work_hours,
                    "break_duration": break_duration
                })
                
                record_id = result.fetchone()[0]
                records_created += 1
                
                # Link logs to the record
                for log in day_logs:
                    query = text("""
                        UPDATE attendance_log
                        SET attendance_record_id = :record_id, is_processed = true
                        WHERE id = :log_id
                    """)
                    self.session.execute(query, {"record_id": record_id, "log_id": log.id})
                
                logger.info(f"Created record for {log_date} - Employee {employee_id}: {status}, {work_hours:.2f}h, Break: {break_duration:.2f}h")
            
            self.session.commit()
            logger.info(f"Processed {records_created} attendance records successfully!")
            return records_created
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error processing attendance logs: {str(e)}")
            return False
    
    def setup_complete_test_scenario(self, start_date=None, end_date=None, holidays=None, skip_reset=False):
        """
        Complete end-to-end setup of test data:
        1. Reset database (unless skip_reset=True)
        2. Create test employees
        3. Create shift assignments
        4. Create attendance logs
        5. Process attendance logs
        
        Args:
            start_date: Start date for test data
            end_date: End date for test data
            holidays: List of holiday dates
            skip_reset: If True, skip the database reset step
        
        Returns a summary of actions performed
        """
        results = {
            'reset': False,
            'reset_skipped': skip_reset,
            'employees_created': 0,
            'shifts_created': False,
            'logs_created': 0,
            'records_processed': 0,
            'success': False
        }
        
        # Step 1: Reset database (unless skipped)
        if not skip_reset:
            logger.info("Step 1/5: Resetting database...")
            reset_success = self.reset_database()
            results['reset'] = reset_success
            
            if not reset_success:
                logger.error("Failed to reset database. Aborting test scenario setup.")
                return results
        else:
            logger.info("Step 1/5: Database reset skipped as requested.")
            results['reset'] = True  # Consider this step successful since it was intentionally skipped
        
        # Step 2: Create test employees
        logger.info("Step 2/5: Creating test employees...")
        employee_ids = self.create_test_employees()
        results['employees_created'] = len(employee_ids)
        
        if not employee_ids:
            logger.error("Failed to create test employees. Aborting test scenario setup.")
            return results
        
        # Step 3: Create shift assignments
        logger.info("Step 3/5: Creating shift assignments...")
        shifts_success = self.create_shift_assignments(start_date, end_date)
        results['shifts_created'] = shifts_success
        
        if not shifts_success:
            logger.error("Failed to create shift assignments. Aborting test scenario setup.")
            return results
        
        # Step 4: Create attendance logs
        logger.info("Step 4/5: Creating attendance logs...")
        logs_created = self.create_attendance_logs(start_date, end_date, holidays)
        results['logs_created'] = logs_created
        
        if not logs_created:
            logger.error("Failed to create attendance logs. Aborting test scenario setup.")
            return results
        
        # Step 5: Process attendance logs
        logger.info("Step 5/5: Processing attendance logs...")
        records_processed = self.process_attendance_logs()
        results['records_processed'] = records_processed
        
        # Set overall success
        results['success'] = (
            results['reset'] and 
            len(employee_ids) > 0 and 
            shifts_success and 
            logs_created > 0 and 
            records_processed > 0
        )
        
        if results['success']:
            logger.info("Test scenario setup completed successfully!")
        else:
            logger.warning("Test scenario setup completed with some issues.")
        
        return results


# Create a function to run as a Flask CLI command
def setup_test_data_command(start_date=None, end_date=None):
    """
    Flask CLI command to setup test data
    
    Usage:
        flask setup-test-data [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
    """
    try:
        # Parse dates if provided
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Run the setup
        manager = TestDataManager()
        results = manager.setup_complete_test_scenario(start_date, end_date)
        
        # Return results as JSON
        return results
    except Exception as e:
        logger.exception("Error in setup_test_data_command")
        return {'success': False, 'error': str(e)}