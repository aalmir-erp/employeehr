"""
WhatsApp notification service using Wassenger API.
Used for sending notifications about bonus evaluations.
"""
import os
import json
import requests
from datetime import datetime
from flask import current_app

def get_wassenger_api_key():
    """Get Wassenger API key from environment variable"""
    api_key = os.environ.get("WASSENGER_API_KEY")
    if not api_key:
        current_app.logger.error("WASSENGER_API_KEY not set in environment variables")
        return None
    return api_key

def get_employee_phone_numbers(submission):
    """Get employee phone numbers from a submission"""
    from models import Employee
    
    # Get all employee IDs from the submission's evaluations
    employee_ids = set()
    for evaluation in submission.evaluations:
        employee_ids.add(evaluation.employee_id)
    
    # Fetch employee records to get phone numbers
    employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()
    
    # Return only employees with valid phone numbers
    return {emp.id: emp.phone for emp in employees if emp.phone}

def format_notification_message(submission, status):
    """Format WhatsApp notification message based on submission status"""
    if status == "approved":
        message = (
            f"🌟 *Performance Evaluation Approved* 🌟\n\n"
            f"Your performance evaluation for the period "
            f"*{submission.period.name if submission.period else 'Current Period'}* "
            f"has been *APPROVED* by HR.\n\n"
            f"Department: {submission.department}\n"
            f"Date Approved: {datetime.now().strftime('%d-%m-%Y')}\n\n"
            f"Please contact your supervisor for details about your evaluation results."
        )
    elif status == "rejected":
        message = (
            f"⚠️ *Performance Evaluation Update* ⚠️\n\n"
            f"Your performance evaluation for the period "
            f"*{submission.period.name if submission.period else 'Current Period'}* "
            f"requires additional review.\n\n"
            f"Department: {submission.department}\n"
            f"Date: {datetime.now().strftime('%d-%m-%Y')}\n\n"
            f"Your supervisor will contact you with more information."
        )
    else:
        message = (
            f"📋 *Performance Evaluation Update* 📋\n\n"
            f"Your performance evaluation for the period "
            f"*{submission.period.name if submission.period else 'Current Period'}* "
            f"has been updated.\n\n"
            f"Department: {submission.department}\n"
            f"Date: {datetime.now().strftime('%d-%m-%Y')}\n\n"
            f"Contact your supervisor for more details."
        )
    
    return message

def send_whatsapp_message(phone_number, message):
    """Send WhatsApp message using Wassenger API"""
    api_key = get_wassenger_api_key()
    if not api_key:
        return False
    
    # Prepare phone number (remove + and ensure it has country code)
    if phone_number.startswith('+'):
        phone_number = phone_number[1:]
    
    # Ensure phone number has country code (default to UAE +971)
    if not phone_number.startswith('971') and len(phone_number) <= 10:
        # Assume UAE number, remove leading 0 if present
        if phone_number.startswith('0'):
            phone_number = phone_number[1:]
        phone_number = f"971{phone_number}"
    
    url = "https://api.wassenger.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "Token": api_key
    }
    payload = {
        "phone": phone_number,
        "message": message,
        "priority": "normal"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in (200, 201):
            current_app.logger.info(f"WhatsApp message sent to {phone_number}")
            return True
        else:
            current_app.logger.error(
                f"Failed to send WhatsApp message: {response.status_code} - {response.text}"
            )
            return False
    except Exception as e:
        current_app.logger.error(f"Error sending WhatsApp message: {str(e)}")
        return False

def send_whatsapp_notifications(submission, status):
    """Send WhatsApp notifications to all employees in a submission"""
    # Get employee phone numbers
    employee_phones = get_employee_phone_numbers(submission)
    if not employee_phones:
        current_app.logger.warning("No valid employee phone numbers found for notifications")
        return False
    
    # Format message
    message = format_notification_message(submission, status)
    
    # Send messages to all employees
    success_count = 0
    for employee_id, phone in employee_phones.items():
        if send_whatsapp_message(phone, message):
            success_count += 1
    
    current_app.logger.info(
        f"Sent {success_count} WhatsApp notifications out of {len(employee_phones)} employees"
    )
    return success_count > 0