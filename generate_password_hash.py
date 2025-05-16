#!/usr/bin/env python

"""
Generate a properly formatted password hash for a user in the database.
"""

from werkzeug.security import generate_password_hash
import sys

def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_password_hash.py <password>")
        sys.exit(1)
    
    password = sys.argv[1]
    # Generate the hash with the default method (pbkdf2:sha256)
    hash_value = generate_password_hash(password)
    print(f"\nPassword hash for '{password}':\n{hash_value}\n")
    print("SQL command to update admin user:")
    print(f"UPDATE \"user\" SET password_hash = '{hash_value}' WHERE username = 'admin';\n")

if __name__ == "__main__":
    main()
