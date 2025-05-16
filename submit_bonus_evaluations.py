"""
Submit bonus evaluations that are in draft status for review.
This script demonstrates the supervisor submission workflow.
"""
import os
import random
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app import app, db
from models import BonusSubmission, BonusAuditLog, User


def submit_department_evaluations(department):
    """Submit evaluations for a specific department"""
    # Get submission in draft status for the specified department
    submission = BonusSubmission.query.filter_by(
        department=department, 
        status='draft'
    ).first()
    
    if not submission:
        print(f"No draft submission found for {department}")
        return False
    
    # Find supervisor for this department
    supervisor = User.query.filter_by(
        role='supervisor', 
        department=department
    ).first()
    
    if not supervisor:
        print(f"No supervisor found for {department}. Using admin.")
        supervisor = User.query.filter_by(username='admin').first()
    
    # Submit the submission
    submission.status = 'submitted'
    submission.submitted_by = supervisor.id
    submission.submitted_at = datetime.now()
    
    # Create audit log
    audit_log = BonusAuditLog(
        submission_id=submission.id,
        user_id=supervisor.id,
        action="submitted",
        notes=f"Submitted {submission.department} evaluations for review",
        timestamp=datetime.now()
    )
    
    db.session.add(audit_log)
    db.session.commit()
    
    print(f"Successfully submitted {submission.department} evaluations for review")
    return True


def main():
    """Main function to execute the script"""
    print("Submitting bonus evaluations for review...")
    with app.app_context():
        # Submit evaluations for specific departments
        for department in ['Engineering', 'HR', 'Sales']:
            submit_department_evaluations(department)
    
    print("Done!")


if __name__ == "__main__":
    main()