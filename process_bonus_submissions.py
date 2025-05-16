"""
Process existing bonus submissions by approving or rejecting them.
This script demonstrates the bonus system workflow without creating new evaluations.
"""
import os
import random
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from app import app, db
from models import BonusSubmission, BonusAuditLog, User


def approve_random_submission():
    """Approve a random submission as HR"""
    # Get a random submitted submission
    submission = BonusSubmission.query.filter_by(status='submitted').order_by(db.func.random()).first()
    
    if not submission:
        print("No submitted submissions available to approve")
        return False
    
    # Get HR user
    hr_user = User.query.filter_by(role='hr').first()
    if not hr_user:
        print("No HR user found. Using admin.")
        hr_user = User.query.filter_by(username='admin').first()
    
    # Approve the submission
    submission.status = 'approved'
    submission.reviewed_by = hr_user.id
    submission.reviewed_at = datetime.now()
    
    # Create audit log
    audit_log = BonusAuditLog(
        submission_id=submission.id,
        user_id=hr_user.id,
        action="approved",
        notes=f"Approved {submission.department} evaluations",
        timestamp=datetime.now()
    )
    
    db.session.add(audit_log)
    db.session.commit()
    
    print(f"Successfully approved {submission.department} evaluations")
    return True


def reject_random_submission():
    """Reject a random submission as HR with feedback"""
    # Get a random submitted submission
    submission = BonusSubmission.query.filter_by(status='submitted').order_by(db.func.random()).first()
    
    if not submission:
        print("No submitted submissions available to reject")
        return False
    
    # Get HR user
    hr_user = User.query.filter_by(role='hr').first()
    if not hr_user:
        print("No HR user found. Using admin.")
        hr_user = User.query.filter_by(username='admin').first()
    
    # Reject the submission
    submission.status = 'rejected'
    submission.reviewed_by = hr_user.id
    submission.reviewed_at = datetime.now()
    submission.notes = "Please review your evaluations. Some scores seem inconsistent with performance. Provide more detailed justification for extreme scores (both high and low)."
    
    # Create audit log
    audit_log = BonusAuditLog(
        submission_id=submission.id,
        user_id=hr_user.id,
        action="rejected",
        notes=f"Rejected {submission.department} evaluations with feedback",
        timestamp=datetime.now()
    )
    
    db.session.add(audit_log)
    db.session.commit()
    
    print(f"Successfully rejected {submission.department} evaluations with feedback")
    return True


def main():
    """Main function to execute the script"""
    print("Processing bonus submissions...")
    with app.app_context():
        # Approve one submission
        approve_random_submission()
        
        # Reject one submission
        reject_random_submission()
    
    print("Done!")


if __name__ == "__main__":
    main()