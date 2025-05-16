"""
Create a sample evaluation period and submissions for testing
"""
import os
import sys
from datetime import datetime, timedelta

from app import app, db
from models import BonusEvaluationPeriod, BonusSubmission, User, Employee


def create_sample_evaluation_period():
    """Create a sample evaluation period for the current month"""
    
    # Find admin user
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        print("Error: Admin user not found. Please create an admin user first.")
        return False
    
    # Get current month
    now = datetime.now()
    start_date = datetime(now.year, now.month, 1)
    
    # If we're in the last 5 days of the month, use next month
    if now.day > 25:
        if now.month == 12:
            start_date = datetime(now.year + 1, 1, 1)
        else:
            start_date = datetime(now.year, now.month + 1, 1)
    
    # Set end date to last day of the month
    if start_date.month == 12:
        end_date = datetime(start_date.year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(start_date.year, start_date.month + 1, 1) - timedelta(days=1)
    
    # Create period name
    period_name = f"{start_date.strftime('%B %Y')} Bonus Evaluation"
    
    # Check if period already exists
    existing_period = BonusEvaluationPeriod.query.filter_by(name=period_name).first()
    if existing_period:
        print(f"Period '{period_name}' already exists.")
        return existing_period
    
    # Create new period
    period = BonusEvaluationPeriod(
        name=period_name,
        start_date=start_date,
        end_date=end_date,
        status='active',
        created_by=admin_user.id
    )
    
    db.session.add(period)
    db.session.commit()
    print(f"Created evaluation period: {period_name}")
    return period


def create_sample_submissions(period):
    """Create sample submissions for departments"""
    
    # Find admin user
    admin_user = User.query.filter_by(username='admin').first()
    
    departments = ["Engineering", "Production", "HR", "Sales"]
    submissions_created = 0
    
    for department in departments:
        # Check if submission already exists
        existing_submission = BonusSubmission.query.filter_by(
            period_id=period.id,
            department=department
        ).first()
        
        if existing_submission:
            print(f"Submission for {department} already exists.")
            continue
        
        # Find employees in this department
        employees = Employee.query.filter_by(department=department).limit(5).all()
        
        if not employees:
            print(f"No employees found in {department} department. Creating submission anyway.")
        
        # Create submission
        submission = BonusSubmission(
            period_id=period.id,
            department=department,
            status='draft',
            submitted_by=admin_user.id
        )
        
        db.session.add(submission)
        submissions_created += 1
    
    db.session.commit()
    print(f"Created {submissions_created} department submissions")
    return submissions_created


def main():
    """Main function to execute the script"""
    print("Creating sample evaluation period and submissions...")
    with app.app_context():
        period = create_sample_evaluation_period()
        if period:
            create_sample_submissions(period)
    print("Done!")


if __name__ == "__main__":
    main()