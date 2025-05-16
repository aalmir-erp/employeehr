#!/usr/bin/env python

"""
Reset an admin user password in the database.

Usage:
  python reset_admin_password.py <username> <new_password>

Example:
  python reset_admin_password.py admin password123
"""

import sys
import os
from app import app, db
from models import User

def reset_password(username, new_password):
    """Reset the password for a user"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"Error: User '{username}' not found")
            return False
        
        user.set_password(new_password)
        user.force_password_change = False  # Remove forced password change if set
        db.session.commit()
        
        print(f"Password for '{username}' has been reset successfully")
        print(f"Login details:")
        print(f"  Username: {username}")
        print(f"  Email: {user.email}")
        print(f"  Is Admin: {'Yes' if user.is_admin else 'No'}")
        return True

def get_all_users():
    """List all users in the database"""
    with app.app_context():
        users = User.query.all()
        print(f"Available users in the database:")
        print("{:<5} {:<20} {:<30} {:<10}".format("ID", "Username", "Email", "Is Admin"))
        print("-" * 65)
        for user in users:
            print("{:<5} {:<20} {:<30} {:<10}".format(
                user.id, user.username, user.email, "Yes" if user.is_admin else "No"))

def main():
    if len(sys.argv) < 2:
        print("Available users:")
        get_all_users()
        print("\nUsage: python reset_admin_password.py <username> <new_password>")
        return
    
    if len(sys.argv) == 2 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        return
    
    if len(sys.argv) < 3:
        print("Error: Both username and new password are required")
        print("Usage: python reset_admin_password.py <username> <new_password>")
        return
    
    username = sys.argv[1]
    new_password = sys.argv[2]
    
    reset_password(username, new_password)

if __name__ == "__main__":
    main()
