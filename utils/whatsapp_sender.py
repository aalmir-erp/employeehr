import os
import random
import string
import requests
import json
from datetime import datetime, timedelta
from urllib.parse import quote
from flask import current_app
from app import db
from models import OTPVerification, Employee

# Get API key from environment variables
WASSENGER_API_KEY = os.environ.get('WASSENGER_API_KEY')
WASSENGER_API_URL = "https://api.wassenger.com/v1/messages"

# Headers for API requests
HEADERS = {
    "Content-Type": "application/json",
    "Token": WASSENGER_API_KEY
}

def generate_otp(length=6):
    """Generate a random numeric OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))

def find_employee_by_phone(phone):
    """Find an employee by phone number"""
    # Normalize phone number
    phone = normalize_phone_number(phone)
    
    # Try to find employee with this phone number
    employee = Employee.query.filter_by(phone=phone).first()
    
    return employee

def normalize_phone_number(phone):
    """Normalize phone number to international format"""
    # Remove any whitespace, dashes, etc.
    phone = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    # Ensure it has a + prefix
    if not phone.startswith('+'):
        phone = '+' + phone
    
    return phone

def send_otp(phone, employee_id=None):
    """Send OTP via WhatsApp
    
    Args:
        phone (str): Phone number to send OTP to
        employee_id (int, optional): Employee ID for verification
        
    Returns:
        tuple: (success (bool), message (str))
    """
    # Check if we have the API key
    if not WASSENGER_API_KEY:
        return False, "WhatsApp API key not configured"
    
    # Normalize phone number
    phone = normalize_phone_number(phone)
    
    # Generate a new OTP
    otp_code = generate_otp()
    
    # Set expiration time (10 minutes from now)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    # Create or update OTP entry in database
    existing_otp = OTPVerification.query.filter_by(phone=phone, is_verified=False).first()
    
    if existing_otp:
        # Update existing entry
        existing_otp.otp_code = otp_code
        existing_otp.expires_at = expires_at
        existing_otp.employee_id = employee_id
        existing_otp.created_at = datetime.utcnow()
    else:
        # Create new entry
        new_otp = OTPVerification(
            phone=phone,
            otp_code=otp_code,
            expires_at=expires_at,
            employee_id=employee_id
        )
        db.session.add(new_otp)
    
    db.session.commit()
    
    # Prepare message text
    message_text = f"Your MIR AMS verification code is: *{otp_code}*\n\nThis code will expire in 10 minutes."
    
    # Send message via Wassenger API
    try:
        payload = {
            "phone": phone,
            "message": message_text,
            "priority": "express"
        }
        
        response = requests.post(WASSENGER_API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        
        result = response.json()
        
        if response.status_code == 200 or response.status_code == 201:
            return True, "OTP sent successfully"
        else:
            return False, f"Failed to send OTP: {result.get('message', 'Unknown error')}"
            
    except requests.exceptions.RequestException as e:
        return False, f"API request failed: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def verify_otp(phone, otp_code):
    """Verify OTP for a phone number
    
    Args:
        phone (str): Phone number
        otp_code (str): OTP code to verify
        
    Returns:
        tuple: (success (bool), result (str or Employee))
            - If successful, returns (True, Employee)
            - If failed, returns (False, error_message)
    """
    # Normalize phone number
    phone = normalize_phone_number(phone)
    
    # Find OTP verification entry
    verification = OTPVerification.query.filter_by(
        phone=phone,
        otp_code=otp_code,
        is_verified=False
    ).first()
    
    if not verification:
        return False, "Invalid OTP code"
    
    # Check if OTP has expired
    if datetime.utcnow() > verification.expires_at:
        return False, "OTP has expired"
    
    # Mark as verified
    verification.is_verified = True
    db.session.commit()
    
    # Get associated employee
    employee = None
    if verification.employee_id:
        employee = Employee.query.get(verification.employee_id)
    else:
        # Try to find employee by phone number
        employee = Employee.query.filter_by(phone=phone).first()
    
    if not employee:
        return False, "No employee found with this phone number"
    
    return True, employee
