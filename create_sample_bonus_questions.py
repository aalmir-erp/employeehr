"""
Script to create sample bonus questions for different departments
"""
import os
import sys
from datetime import datetime

from app import app, db
from models import BonusQuestion, User


def create_sample_questions():
    """Create sample bonus questions for demo purposes"""
    
    # Find admin user for created_by field
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        print("Error: Admin user not found. Please create an admin user first.")
        return
    
    # Engineering Department Questions
    engineering_questions = [
        {
            "department": "Engineering",
            "question_text": "How well does the employee meet project deadlines?",
            "min_value": -5,
            "max_value": 10,
            "default_value": 0,
            "weight": 1.5
        },
        {
            "department": "Engineering",
            "question_text": "Rate the quality of code/technical work produced during this period",
            "min_value": 0,
            "max_value": 10,
            "default_value": 5,
            "weight": 2.0
        },
        {
            "department": "Engineering",
            "question_text": "How effectively does the employee document their work?",
            "min_value": -2,
            "max_value": 8,
            "default_value": 3,
            "weight": 1.0
        },
        {
            "department": "Engineering",
            "question_text": "Rate the employee's problem-solving abilities",
            "min_value": 0,
            "max_value": 10,
            "default_value": 5,
            "weight": 1.3
        },
        {
            "department": "Engineering",
            "question_text": "How well does the employee collaborate with team members?",
            "min_value": -3,
            "max_value": 7,
            "default_value": 2,
            "weight": 1.0
        }
    ]
    
    # Production Department Questions
    production_questions = [
        {
            "department": "Production",
            "question_text": "Rate the employee's productivity compared to department average",
            "min_value": -5,
            "max_value": 15,
            "default_value": 0,
            "weight": 2.0
        },
        {
            "department": "Production",
            "question_text": "How well does the employee adhere to safety protocols?",
            "min_value": -10,
            "max_value": 5,
            "default_value": 0,
            "weight": 1.5
        },
        {
            "department": "Production",
            "question_text": "Rate the quality of output against quality control standards",
            "min_value": -5,
            "max_value": 10,
            "default_value": 0,
            "weight": 1.5
        },
        {
            "department": "Production",
            "question_text": "How well does the employee maintain equipment and work area?",
            "min_value": -3,
            "max_value": 7,
            "default_value": 2,
            "weight": 0.8
        },
        {
            "department": "Production",
            "question_text": "Rate the employee's attendance and punctuality",
            "min_value": -5,
            "max_value": 5,
            "default_value": 0,
            "weight": 1.0
        }
    ]
    
    # HR Department Questions
    hr_questions = [
        {
            "department": "HR",
            "question_text": "How effectively does the employee handle confidential information?",
            "min_value": -10,
            "max_value": 10,
            "default_value": 5,
            "weight": 2.0
        },
        {
            "department": "HR",
            "question_text": "Rate the employee's communication skills with staff",
            "min_value": -3,
            "max_value": 8,
            "default_value": 4,
            "weight": 1.5
        },
        {
            "department": "HR",
            "question_text": "How well does the employee follow HR policies and procedures?",
            "min_value": -5,
            "max_value": 5,
            "default_value": 0,
            "weight": 1.3
        },
        {
            "department": "HR",
            "question_text": "Rate the employee's conflict resolution abilities",
            "min_value": -3,
            "max_value": 10,
            "default_value": 5,
            "weight": 1.2
        }
    ]
    
    # Sales Department Questions
    sales_questions = [
        {
            "department": "Sales",
            "question_text": "How well did the employee meet their sales targets?",
            "min_value": -10,
            "max_value": 20,
            "default_value": 0,
            "weight": 2.5
        },
        {
            "department": "Sales",
            "question_text": "Rate the employee's client relationship management",
            "min_value": -5,
            "max_value": 10,
            "default_value": 3,
            "weight": 1.5
        },
        {
            "department": "Sales",
            "question_text": "How effectively does the employee generate new leads?",
            "min_value": -2,
            "max_value": 8,
            "default_value": 3,
            "weight": 1.0
        },
        {
            "department": "Sales",
            "question_text": "Rate the employee's product knowledge",
            "min_value": -3,
            "max_value": 7,
            "default_value": 2,
            "weight": 0.8
        },
        {
            "department": "Sales",
            "question_text": "How well does the employee handle customer objections?",
            "min_value": -5,
            "max_value": 10,
            "default_value": 0,
            "weight": 1.2
        }
    ]
    
    # Combine all questions
    all_questions = engineering_questions + production_questions + hr_questions + sales_questions
    
    # Insert questions, skipping existing ones with the same text
    added_count = 0
    skipped_count = 0
    
    for q_data in all_questions:
        # Check if question already exists
        existing = BonusQuestion.query.filter_by(
            department=q_data["department"],
            question_text=q_data["question_text"]
        ).first()
        
        if existing:
            print(f"Skipping existing question: {q_data['question_text']}")
            skipped_count += 1
            continue
        
        # Create new question
        question = BonusQuestion(
            department=q_data["department"],
            question_text=q_data["question_text"],
            min_value=q_data["min_value"],
            max_value=q_data["max_value"],
            default_value=q_data["default_value"],
            weight=q_data["weight"],
            created_by=admin_user.id,
            is_active=True
        )
        
        db.session.add(question)
        added_count += 1
    
    db.session.commit()
    print(f"Successfully added {added_count} questions. Skipped {skipped_count} existing questions.")


if __name__ == "__main__":
    print("Creating sample bonus questions...")
    with app.app_context():
        create_sample_questions()
    print("Done!")