#!/usr/bin/env python3
"""
Creates comprehensive test scenarios for two test employees:
- Alternating day and night shifts 
- Special scenarios including:
  - Late arrivals
  - Early departures
  - Missing check-ins/check-outs
  - Weekend working
  - Holiday working
  - Overtime patterns

This script is specifically designed to test all aspects of the attendance system.
"""
import os
import sys
import random
from datetime import datetime, timedelta, time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup database connection
db_uri = os.environ.get("DATABASE_URL")
if not db_uri:
    print("Error: DATABASE_URL environment variable not set.")
    sys.exit(1)

# Create database engine and session
engine = create_engine(db_uri)
Session = sessionmaker(bind=engine)
session = Session()

# Test employee IDs
EMPLOYEE_A_ID = 260  # Production employee (TEST-001)
EMPLOYEE_B_ID = 261  # Quality Control employee (TEST-002)

# Shift IDs
DAY_SHIFT_ID = 1   # 8am-8pm
NIGHT_SHIFT_ID = 2  # 8pm-8am (overnight)

# Device ID for logging
DEVICE_ID = 3  # ZKTeco CSV Import device

# Scenario date range
START_DATE = datetime(2025, 5, 1)  # Start from May 1, 2025 (includes Labor Day)
END_DATE = datetime(2025, 5, 31)   # Until May 31, 2025

# Known holidays in the date range
HOLIDAYS = [
    datetime(2025, 5, 1).date(),  # Labor Day
    datetime(2025, 5, 10).date(),  # UAE National Day
    datetime(2025, 5, 15).date(),  # Eid Al Fitr
]

def setup_employee_overtime_settings():
    """
    Configure employees with different overtime eligibility:
    - Employee A: Eligible for weekday and weekend overtime, not holiday overtime
    - Employee B: Eligible for weekday, weekend and holiday overtime
    """
    # First, update Employee A
    query = text("""
        UPDATE employee
        SET 
            weekend_days = '[5, 6]',  /* Standard weekend (Sat, Sun) */
            eligible_for_weekday_overtime = true,
            eligible_for_weekend_overtime = true, 
            eligible_for_holiday_overtime = false  /* Not eligible for holiday overtime */
        WHERE id = :employee_id
    """)
    session.execute(query, {"employee_id": EMPLOYEE_A_ID})
    
    # Then update Employee B with custom weekend
    query = text("""
        UPDATE employee
        SET 
            weekend_days = '[6]',  /* Only Sunday as weekend */
            eligible_for_weekday_overtime = true,
            eligible_for_weekend_overtime = true,
            eligible_for_holiday_overtime = true  /* Eligible for all overtime types */
        WHERE id = :employee_id
    """)
    session.execute(query, {"employee_id": EMPLOYEE_B_ID})
    
    session.commit()
    print("✓ Updated employee overtime eligibility settings")

def clear_existing_data():
    """Clear any existing assignments and logs for our test employees"""
    
    # First, get all attendance_record_ids for these employees
    query = text("""
        SELECT id FROM attendance_record
        WHERE employee_id IN (:emp_a, :emp_b)
    """)
    result = session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID})
    record_ids = [row[0] for row in result]
    
    if record_ids:
        # Clear attendance logs linked to these records
        query = text("""
            UPDATE attendance_log
            SET attendance_record_id = NULL, is_processed = false
            WHERE attendance_record_id IN :record_ids
        """)
        session.execute(query, {"record_ids": tuple(record_ids) if len(record_ids) > 1 else f"({record_ids[0]})"})
    
    # Delete attendance records
    query = text("""
        DELETE FROM attendance_record
        WHERE employee_id IN (:emp_a, :emp_b)
    """)
    session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID})
    
    # Delete attendance logs
    query = text("""
        DELETE FROM attendance_log
        WHERE employee_id IN (:emp_a, :emp_b)
    """)
    session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID})
    
    # Delete shift assignments
    query = text("""
        DELETE FROM shift_assignment
        WHERE employee_id IN (:emp_a, :emp_b)
    """)
    session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID})
    
    session.commit()
    print("✓ Cleared existing data for test employees")

def create_shift_assignments():
    """
    Create shift assignments for the test month:
    - Week 1: Employee A on day shift, Employee B on night shift
    - Week 2: Employee A on night shift, Employee B on day shift
    - Week 3: Employee A on day shift, Employee B on night shift
    - Week 4: Employee A on night shift, Employee B on day shift
    """
    # First week: May 1-7
    week1_start = datetime(2025, 5, 1).date()
    week1_end = datetime(2025, 5, 7).date()
    
    # Second week: May 8-14
    week2_start = datetime(2025, 5, 8).date()
    week2_end = datetime(2025, 5, 14).date()
    
    # Third week: May 15-21
    week3_start = datetime(2025, 5, 15).date()
    week3_end = datetime(2025, 5, 21).date()
    
    # Fourth week: May 22-31
    week4_start = datetime(2025, 5, 22).date()
    week4_end = datetime(2025, 5, 31).date()
    
    # Create assignments
    assignments = [
        # Week 1
        (EMPLOYEE_A_ID, DAY_SHIFT_ID, week1_start, week1_end),
        (EMPLOYEE_B_ID, NIGHT_SHIFT_ID, week1_start, week1_end),
        # Week 2
        (EMPLOYEE_A_ID, NIGHT_SHIFT_ID, week2_start, week2_end),
        (EMPLOYEE_B_ID, DAY_SHIFT_ID, week2_start, week2_end),
        # Week 3
        (EMPLOYEE_A_ID, DAY_SHIFT_ID, week3_start, week3_end),
        (EMPLOYEE_B_ID, NIGHT_SHIFT_ID, week3_start, week3_end),
        # Week 4
        (EMPLOYEE_A_ID, NIGHT_SHIFT_ID, week4_start, week4_end),
        (EMPLOYEE_B_ID, DAY_SHIFT_ID, week4_start, week4_end),
    ]
    
    # Insert assignments
    for employee_id, shift_id, start_date, end_date in assignments:
        query = text("""
            INSERT INTO shift_assignment 
            (employee_id, shift_id, start_date, end_date, is_active) 
            VALUES 
            (:employee_id, :shift_id, :start_date, :end_date, true)
        """)
        session.execute(query, {
            "employee_id": employee_id,
            "shift_id": shift_id,
            "start_date": start_date,
            "end_date": end_date
        })
    
    session.commit()
    print("✓ Created alternating shift assignments for test employees")

def get_shift_times(shift_id, date_obj):
    """Get standard check-in and check-out times for a shift on a given date"""
    query = text("""
        SELECT start_time, end_time, is_overnight
        FROM shift
        WHERE id = :shift_id
    """)
    result = session.execute(query, {"shift_id": shift_id}).fetchone()
    
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

def create_scenario_variation(standard_check_in, standard_check_out, scenario_type, date_obj, is_weekend, is_holiday):
    """Create a specific attendance variation based on the scenario type"""
    
    # These are the possible scenarios we'll generate
    scenarios = {
        'normal': {
            'check_in_delta': (-5, 5),     # Regular attendance (-5 to +5 minutes)
            'check_out_delta': (-5, 5),    # Regular departure (-5 to +5 minutes)
            'break_minutes': (30, 60),     # Normal break duration
            'has_check_in': True,          # Has check-in
            'has_check_out': True,         # Has check-out
        },
        'late': {
            'check_in_delta': (10, 30),    # Late arrival (10-30 minutes late)
            'check_out_delta': (-5, 5),    # Regular departure
            'break_minutes': (30, 60),     # Normal break
            'has_check_in': True,
            'has_check_out': True,
        },
        'early_departure': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (-60, -30), # Early departure (30-60 minutes early)
            'break_minutes': (30, 60),     # Normal break
            'has_check_in': True,
            'has_check_out': True,
        },
        'missing_check_in': {
            'check_in_delta': (0, 0),      # Not used
            'check_out_delta': (-5, 5),    # Regular departure
            'break_minutes': (0, 0),       # Not relevant
            'has_check_in': False,
            'has_check_out': True,
        },
        'missing_check_out': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (0, 0),     # Not used
            'break_minutes': (0, 0),       # Not relevant
            'has_check_in': True,
            'has_check_out': False,
        },
        'long_work': {
            'check_in_delta': (-15, -5),   # Early arrival (5-15 minutes)
            'check_out_delta': (60, 120),  # Late departure (1-2 hours)
            'break_minutes': (30, 60),     # Normal break
            'has_check_in': True,
            'has_check_out': True,
        },
        'short_break': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (-5, 5),    # Regular departure
            'break_minutes': (10, 20),     # Short break (10-20 minutes)
            'has_check_in': True,
            'has_check_out': True,
        },
        'long_break': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (-5, 5),    # Regular departure
            'break_minutes': (90, 120),    # Long break (90-120 minutes)
            'has_check_in': True,
            'has_check_out': True,
        },
        'weekend_work': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (60, 120),  # Longer stay (1-2 hours)
            'break_minutes': (30, 60),     # Normal break
            'has_check_in': True,
            'has_check_out': True,
        },
        'holiday_work': {
            'check_in_delta': (-5, 5),     # Regular arrival
            'check_out_delta': (60, 180),  # Much longer stay (1-3 hours)
            'break_minutes': (30, 60),     # Normal break
            'has_check_in': True,
            'has_check_out': True,
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
    
    return check_in, check_out, break_minutes

def create_attendance_logs():
    """Create attendance logs for our test employees with various scenarios"""
    
    # Get all shift assignments for our test employees
    query = text("""
        SELECT id, employee_id, shift_id, start_date, end_date
        FROM shift_assignment
        WHERE employee_id IN (:emp_a, :emp_b)
        ORDER BY start_date, employee_id
    """)
    assignments = session.execute(query, {"emp_a": EMPLOYEE_A_ID, "emp_b": EMPLOYEE_B_ID}).fetchall()
    
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
        'normal': 5,           # 50% normal days
        'late': 1,             # 10% late arrivals
        'early_departure': 1,  # 10% early departures
        'missing_check_in': 1, # 10% missing check-ins
        'missing_check_out': 1,# 10% missing check-outs
        'long_work': 1,        # 10% overtime days
        'short_break': 0,      # Will be added on specific days
        'long_break': 0,       # Will be added on specific days
    }
    
    # Generate weighted scenario list
    weighted_scenarios = []
    for scenario, weight in scenario_weights.items():
        weighted_scenarios.extend([scenario] * weight)
    
    # Keep track of which dates have been processed
    processed_dates = set()
    
    # Process each assignment
    for assignment in assignments:
        employee_id = assignment.employee_id
        shift_id = assignment.shift_id
        start_date = assignment.start_date
        end_date = assignment.end_date
        
        current_date = start_date
        while current_date <= end_date:
            date_key = (employee_id, current_date)
            
            # Skip if we already processed this date
            if date_key in processed_dates:
                current_date += timedelta(days=1)
                continue
            
            processed_dates.add(date_key)
            
            # Check if it's a weekend or holiday
            is_weekend = current_date.weekday() >= 5  # Saturday or Sunday
            is_holiday = current_date in HOLIDAYS
            
            # Get standard check-in and check-out times for this shift
            standard_check_in, standard_check_out = get_shift_times(shift_id, current_date)
            
            if not standard_check_in or not standard_check_out:
                current_date += timedelta(days=1)
                continue
            
            # Determine scenario for this day
            # Use a seeded random for specific employees and dates to create
            # special scenarios on specific days
            random.seed(f"{employee_id}-{current_date}")
            
            # Special case: Monday May 5th - Employee A has a short break
            if employee_id == EMPLOYEE_A_ID and current_date == datetime(2025, 5, 5).date():
                scenario_type = 'short_break'
            # Special case: Tuesday May 6th - Employee B has a long break
            elif employee_id == EMPLOYEE_B_ID and current_date == datetime(2025, 5, 6).date():
                scenario_type = 'long_break'
            # Special case: Labor Day (May 1) - Employee B works overtime
            elif employee_id == EMPLOYEE_B_ID and current_date == datetime(2025, 5, 1).date():
                scenario_type = 'holiday_work'
            # Special case: Weekend (May 3-4) - Both employees work
            elif current_date.day in [3, 4] and current_date.month == 5:
                scenario_type = 'weekend_work'
            # Default: random scenario
            else:
                scenario_type = random.choice(weighted_scenarios)
            
            # Create the scenario variation
            check_in, check_out, break_minutes = create_scenario_variation(
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
                session.execute(query, {
                    "employee_id": employee_id,
                    "device_id": DEVICE_ID,
                    "timestamp": check_in
                })
            
            # Insert check-out log if exists
            if check_out:
                query = text("""
                    INSERT INTO attendance_log
                    (employee_id, device_id, log_type, timestamp, is_processed)
                    VALUES
                    (:employee_id, :device_id, 'check_out', :timestamp, false)
                """)
                session.execute(query, {
                    "employee_id": employee_id,
                    "device_id": DEVICE_ID,
                    "timestamp": check_out
                })
            
            # Print a summary of this attendance record
            print(f"  → {current_date} - Employee {employee_id} - {scenario_type}: ", end="")
            if check_in:
                print(f"IN:{check_in.strftime('%H:%M')}", end=" ")
            else:
                print("IN:MISSING", end=" ")
                
            if check_out:
                print(f"OUT:{check_out.strftime('%H:%M')}", end=" ")
            else:
                print("OUT:MISSING", end=" ")
                
            if break_minutes > 0:
                print(f"Break:{break_minutes}min")
            else:
                print()
            
            # Move to next day
            current_date += timedelta(days=1)
    
    session.commit()
    print("✓ Created varied attendance logs with different scenarios")

def main():
    """Execute the test data creation process"""
    print("\n==== Creating Advanced Test Scenario ====")
    print(f"• Timeframe: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"• Test Employees: {EMPLOYEE_A_ID} (Production) and {EMPLOYEE_B_ID} (Quality Control)")
    
    # First, clear any existing data
    clear_existing_data()
    
    # Setup employee overtime settings
    setup_employee_overtime_settings()
    
    # Create shift assignments
    create_shift_assignments()
    
    # Create attendance logs with various scenarios
    create_attendance_logs()
    
    print("\n✅ Advanced test scenario created successfully!")
    print("\nTest Employee Details:")
    print(f"1. Employee ID: {EMPLOYEE_A_ID}, Code: TEST-001, Department: Production")
    print("   - Eligible for weekday and weekend overtime")
    print("   - NOT eligible for holiday overtime")
    print(f"2. Employee ID: {EMPLOYEE_B_ID}, Code: TEST-002, Department: Quality Control")
    print("   - Eligible for weekday, weekend, and holiday overtime")
    print("   - Has custom weekend configuration (only Sunday)")
    
    print("\nSpecial Test Dates:")
    print("• May 1: Labor Day (holiday) - Employee B works with holiday overtime")
    print("• May 3-4: Weekend - Both employees work with weekend overtime")
    print("• May 5: Employee A has a short break")
    print("• May 6: Employee B has a long break")
    print("• May 10: UAE National Day (holiday)")
    print("• May 15: Eid Al Fitr (holiday)")
    
    print("\nTo view these test records:")
    print("1. Process the logs by navigating to /attendance/process_all_logs")
    print("2. View attendance reports for May 2025")
    print("3. View the employee schedule for May 2025")
    
if __name__ == "__main__":
    main()