"""
Create sample submissions and evaluations for the bonus system to demonstrate functionality
"""
import os
import sys
import random
from datetime import datetime

from app import app, db
from models import (
    BonusEvaluationPeriod, 
    BonusSubmission, 
    BonusQuestion, 
    BonusEvaluation,
    BonusAuditLog,
    User, 
    Employee
)


def create_sample_evaluations():
    """Create sample evaluations for existing submissions"""
    print("Creating sample evaluations for existing submissions...")
    
    # Find admin user
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        print("Error: Admin user not found. Please create an admin user first.")
        return False
    
    # Get all draft submissions
    submissions = BonusSubmission.query.filter_by(status='draft').all()
    if not submissions:
        print("No draft submissions found. Please run create_sample_evaluation_period.py first.")
        return False
    
    evaluations_created = 0
    
    for submission in submissions:
        print(f"\nProcessing submission for {submission.department}...")
        
        # Get questions for this department
        questions = BonusQuestion.query.filter_by(
            department=submission.department,
            is_active=True
        ).all()
        
        if not questions:
            print(f"No questions found for {submission.department}. Skipping.")
            continue
        
        # Get employees in this department
        employees = Employee.query.filter_by(
            department=submission.department
        ).all()
        
        if not employees:
            print(f"No employees found in {submission.department}. Skipping.")
            continue
        
        print(f"Found {len(employees)} employees and {len(questions)} questions")
        
        # Create evaluations
        for employee in employees:
            for question in questions:
                # Check if evaluation already exists
                existing_eval = BonusEvaluation.query.filter_by(
                    submission_id=submission.id,
                    employee_id=employee.id,
                    question_id=question.id
                ).first()
                
                if existing_eval:
                    print(f"Evaluation already exists for {employee.name}, question {question.id}")
                    continue
                
                # Generate a random value within the question's range
                # Bias towards more positive ratings
                value_range = question.max_value - question.min_value
                # 70% chance of being in the upper half of the range
                if random.random() < 0.7:
                    mid_point = question.min_value + (value_range / 2)
                    value = random.randint(int(mid_point), question.max_value)
                else:
                    value = random.randint(question.min_value, question.max_value)
                
                # Create evaluation
                evaluation = BonusEvaluation(
                    submission_id=submission.id,
                    employee_id=employee.id,
                    question_id=question.id,
                    value=value
                )
                
                db.session.add(evaluation)
                evaluations_created += 1
        
        # Create audit log entry
        audit_log = BonusAuditLog(
            submission_id=submission.id,
            user_id=admin_user.id,
            action="evaluations_added",
            notes=f"Added {len(employees) * len(questions)} evaluations",
            timestamp=datetime.now()
        )
        
        db.session.add(audit_log)
    
    db.session.commit()
    print(f"Successfully created {evaluations_created} evaluations")
    return True


def submit_random_submission():
    """Submit a random submission for HR review"""
    # Get a random draft submission
    submission = BonusSubmission.query.filter_by(status='draft').order_by(db.func.random()).first()
    
    if not submission:
        print("No draft submissions available to submit")
        return False
    
    # Find supervisor user for this department
    supervisor = None
    for user in User.query.filter_by(role='supervisor').all():
        if user.department == submission.department:
            supervisor = user
            break
    
    if not supervisor:
        print(f"No supervisor found for {submission.department}. Using admin.")
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
    print("Creating sample evaluations and submissions...")
    with app.app_context():
        # Create evaluations for all submissions
        create_sample_evaluations()
        
        # Submit one submission for review
        submit_random_submission()
        
        # Create another batch of evaluations to ensure we have multiple submissions
        create_sample_evaluations()
        
        # Submit another submission
        submit_random_submission()
        
        # Approve one submission
        approve_random_submission()
        
        # Reject one submission
        reject_random_submission()
    
    print("Done!")


if __name__ == "__main__":
    main()