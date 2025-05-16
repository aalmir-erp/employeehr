"""
Create sample employees for each department to test the bonus system
"""
import os
import sys
from datetime import datetime

from app import app, db
from models import Employee, User


def create_sample_employees():
    """Create employees for different departments if they don't exist"""
    
    # Department employee data
    department_employees = {
        "Engineering": [
            {"employee_code": "ENG001", "name": "John Smith", "designation": "Senior Developer"},
            {"employee_code": "ENG002", "name": "Emily Chen", "designation": "Software Engineer"},
            {"employee_code": "ENG003", "name": "David Kim", "designation": "DevOps Engineer"},
            {"employee_code": "ENG004", "name": "Sarah Johnson", "designation": "UI/UX Designer"},
            {"employee_code": "ENG005", "name": "Michael Wang", "designation": "QA Engineer"}
        ],
        "Production": [
            {"employee_code": "PRD001", "name": "Robert Brown", "designation": "Production Manager"},
            {"employee_code": "PRD002", "name": "Jessica Lee", "designation": "Line Supervisor"},
            {"employee_code": "PRD003", "name": "Thomas Garcia", "designation": "Quality Control"},
            {"employee_code": "PRD004", "name": "Amanda Taylor", "designation": "Production Technician"},
            {"employee_code": "PRD005", "name": "Kevin Martinez", "designation": "Shift Leader"}
        ],
        "HR": [
            {"employee_code": "HR001", "name": "Lisa Wilson", "designation": "HR Manager"},
            {"employee_code": "HR002", "name": "Steven Miller", "designation": "Recruiter"},
            {"employee_code": "HR003", "name": "Jennifer Davis", "designation": "Benefits Coordinator"},
            {"employee_code": "HR004", "name": "Richard Harris", "designation": "Training Coordinator"}
        ],
        "Sales": [
            {"employee_code": "SLS001", "name": "Michelle Lewis", "designation": "Sales Manager"},
            {"employee_code": "SLS002", "name": "Daniel Clark", "designation": "Account Executive"},
            {"employee_code": "SLS003", "name": "Patricia Moore", "designation": "Sales Representative"},
            {"employee_code": "SLS004", "name": "Christopher White", "designation": "Business Developer"},
            {"employee_code": "SLS005", "name": "Elizabeth Young", "designation": "Sales Analyst"}
        ]
    }
    
    employees_created = 0
    employees_skipped = 0
    
    for department, employees in department_employees.items():
        for emp_data in employees:
            # Check if employee already exists
            existing_employee = Employee.query.filter_by(employee_code=emp_data["employee_code"]).first()
            
            if existing_employee:
                print(f"Skipping existing employee: {emp_data['name']} ({emp_data['employee_code']})")
                employees_skipped += 1
                continue
            
            # Create new employee
            employee = Employee(
                employee_code=emp_data["employee_code"],
                name=emp_data["name"],
                position=emp_data["designation"],  # Position instead of designation
                department=department,
                join_date=datetime.now().date(),  # join_date instead of date_of_joining
                is_active=True
            )
            
            db.session.add(employee)
            employees_created += 1
    
    db.session.commit()
    print(f"Successfully added {employees_created} employees. Skipped {employees_skipped} existing employees.")


def create_supervisor_accounts():
    """Create supervisor user accounts for the first employee in each department"""
    
    # Create a supervisor role for employees
    for department in ["Engineering", "Production", "HR", "Sales"]:
        # Get first employee in department
        supervisor = Employee.query.filter_by(department=department).first()
        
        if supervisor:
            # Check if the supervisor has a user account
            supervisor_user = User.query.filter_by(email=f"{supervisor.employee_code.lower()}@mir.ae").first()
            
            if not supervisor_user:
                # Create user account for supervisor
                supervisor_username = supervisor.name.split()[0].lower()
                supervisor_user = User(
                    username=supervisor_username,
                    email=f"{supervisor.employee_code.lower()}@mir.ae",
                    password_hash='pbkdf2:sha256:600000$T1UHnKTHtBskgpX0$4c68ac5b43cf74e1f40ae8439a0b85cdee31e26b8d1b97b99f0409a492ca0d95',  # admin123
                    role='supervisor',
                    is_active=True
                )
                db.session.add(supervisor_user)
                db.session.commit()
                print(f"Created supervisor user for {supervisor.name} in {department}")
            else:
                print(f"Supervisor user already exists for {supervisor.name} in {department}")


def main():
    """Main function to execute the script"""
    print("Creating sample employees...")
    with app.app_context():
        create_sample_employees()
        create_supervisor_accounts()
    print("Done!")


if __name__ == "__main__":
    main()