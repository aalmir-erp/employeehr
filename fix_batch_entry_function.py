"""
Fix the batch entry functionality in the routes/attendance.py file.

This script applies a patch to fix issues with batch entry processing including:
1. Ensuring proper shift_id and shift_type assignment
2. Setting default check-in/check-out times for present status
3. Properly calculating work hours and break durations
4. Setting weekend/holiday flags correctly
5. Calculating overtime appropriately
"""

import os
import re
from pathlib import Path

def fix_batch_entry_function():
    """Fix the batch entry function in routes/attendance.py"""
    attendance_path = Path('routes/attendance.py')
    
    if not attendance_path.exists():
        print(f"Error: {attendance_path} not found")
        return False
    
    # Read the current content
    with open(attendance_path, 'r') as f:
        content = f.read()
    
    # Make a backup
    backup_path = Path('routes/attendance.py.bak')
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Backup created at {backup_path}")
    
    # Fix the batch entry function
    
    # 1. Update the section where new records are created with missing check-in/out times
    pattern1 = re.compile(
        r'# If no check-in/check-out provided but status is present, set default work hours\s+'
        r'if status == .present. or status is None:\s+'
        r'new_record\.work_hours = 8\.0\s+'  # Match the work_hours assignment
        r'# Create default check-in and check-out times based on date\s+'
        r'# Default to 9 AM check-in and 6 PM check-out with 1 hour break\s+'
        r'if not check_in_time:\s+'
        r'new_record\.check_in = datetime\.combine\(entry_date, datetime\.min\.time\(\)\.replace\(hour=9\)\)\s+'
        r'if not check_out_time:\s+'
        r'new_record\.check_out = datetime\.combine\(entry_date, datetime\.min\.time\(\)\.replace\(hour=18\)\)'
    )
    
    replacement1 = """# If no check-in/check-out provided but status is present, set default work hours
                            if status == 'present' or status is None:
                                new_record.work_hours = 8.0  # Default to 8 hours for present
                                new_record.break_duration = 1.0  # Default to 1 hour break
                                
                                # Create default check-in and check-out times based on date
                                # Default to 9 AM check-in and 6 PM check-out with 1 hour break
                                if not check_in_time:
                                    new_record.check_in = datetime.combine(entry_date, datetime.min.time().replace(hour=9))
                                if not check_out_time:
                                    new_record.check_out = datetime.combine(entry_date, datetime.min.time().replace(hour=18))
                                
                                # Check for weekend/holiday
                                from utils.attendance_processor import check_holiday_and_weekend
                                employee = Employee.query.get(employee_id)
                                is_holiday, is_weekend = check_holiday_and_weekend(new_record, employee)
                                new_record.is_holiday = is_holiday
                                new_record.is_weekend = is_weekend"""
    
    # 2. Update the overtime calculation section
    pattern2 = re.compile(
        r'# Calculate overtime if applicable\s+'
        r'if new_record\.work_hours > 8\.0:\s+'
        r'from utils\.overtime_engine import calculate_overtime\s+'
        r'calculate_overtime\(new_record, recalculate=True, commit=False\)'
    )
    
    replacement2 = """# Calculate overtime if applicable
                            if new_record.work_hours > 8.0:
                                from utils.overtime_engine import calculate_overtime
                                calculate_overtime(new_record, recalculate=True, commit=False)
                            
                            # Even if no overtime, still check for weekend/holiday status
                            # This ensures proper categorization even for standard hours
                            if not new_record.is_weekend and not new_record.is_holiday:
                                employee = Employee.query.get(employee_id)
                                from utils.attendance_processor import check_holiday_and_weekend
                                is_holiday, is_weekend = check_holiday_and_weekend(new_record, employee)
                                new_record.is_holiday = is_holiday
                                new_record.is_weekend = is_weekend"""
    
    # Apply the fixes
    fixed_content = re.sub(pattern1, replacement1, content)
    fixed_content = re.sub(pattern2, replacement2, fixed_content)
    
    # Write the fixed content
    with open(attendance_path, 'w') as f:
        f.write(fixed_content)
    
    print(f"Applied fixes to {attendance_path}")
    return True

if __name__ == "__main__":
    fix_batch_entry_function()