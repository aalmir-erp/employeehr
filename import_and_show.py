import requests
import csv
import sys
from bs4 import BeautifulSoup
import re
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
USERNAME = "admin"
PASSWORD = "admin123"
CSV_FILE_PATH = "/tmp/import.csv"

# Create a session to maintain cookies
session = requests.Session()

def login():
    """Log in to the system and return True if successful"""
    # First get the login page
    response = session.get(f"{BASE_URL}/auth/login")
    if response.status_code != 200:
        print(f"Failed to access login page: {response.status_code}")
        return False
    
    # Perform login without CSRF token (the form doesn't have one)
    login_data = {
        'username': USERNAME,
        'password': PASSWORD,
        'remember': 'on'
    }
    
    response = session.post(f"{BASE_URL}/auth/login", data=login_data)
    
    # Check if login was successful (should redirect to home page)
    if response.status_code == 200 and "Dashboard" in response.text:
        print("Login successful")
        return True
    else:
        print(f"Login failed: {response.status_code}")
        return False

def import_csv():
    """Import the CSV file and return True if successful"""
    # Get the import page
    response = session.get(f"{BASE_URL}/attendance/import-csv")
    if response.status_code != 200:
        print(f"Failed to access import page: {response.status_code}")
        return False
    
    # Find default device ID
    default_device_id = "1"  # Default fallback
    soup = BeautifulSoup(response.text, 'html.parser')
    for select_tag in soup.find_all('select'):
        if select_tag.get('name') == 'device_id':
            for option in select_tag.find_all('option'):
                if option.get('selected'):
                    default_device_id = option.get('value')
                    break
            break
    
    # Prepare the import data
    import_data = {
        'device_id': default_device_id,
        'create_missing': 'on'
    }
    
    files = {
        'csv_file': open(CSV_FILE_PATH, 'rb')
    }
    
    # Perform the import
    response = session.post(f"{BASE_URL}/attendance/import-csv", data=import_data, files=files)
    
    # Check if import was successful
    if response.status_code == 200 or response.status_code == 302:
        print("CSV import request submitted successfully")
        
        # Check for success message in redirected page
        if response.status_code == 302:
            redirect_url = response.headers.get('Location')
            if redirect_url:
                if not redirect_url.startswith('http'):
                    redirect_url = BASE_URL + redirect_url
                response = session.get(redirect_url)
            
        soup = BeautifulSoup(response.text, 'html.parser')
        flash_messages = soup.find_all('div', class_='alert')
        for message in flash_messages:
            print(f"Flash message: {message.text.strip()}")
            if 'success' in message.get('class', []) and 'imported' in message.text:
                print("Import successful!")
                return True
        
        return True
    else:
        print(f"Import failed: {response.status_code}")
        return False

def show_imported_data():
    """Show the imported attendance data"""
    # Access the attendance page
    response = session.get(f"{BASE_URL}/attendance/daily")
    if response.status_code != 200:
        print(f"Failed to access attendance page: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the attendance table
    attendance_table = None
    for table in soup.find_all('table'):
        if table.get('id') == 'attendanceTable':
            attendance_table = table
            break
    
    if not attendance_table:
        print("Could not find attendance table")
        return
    
    # Extract and print the records
    records = []
    for row in attendance_table.find('tbody').find_all('tr'):
        columns = row.find_all('td')
        if len(columns) >= 5:
            emp_name = columns[0].text.strip()
            emp_code = columns[1].text.strip()
            date = columns[2].text.strip()
            check_in = columns[3].text.strip()
            check_out = columns[4].text.strip()
            
            records.append({
                'name': emp_name,
                'code': emp_code,
                'date': date,
                'check_in': check_in,
                'check_out': check_out
            })
    
    # Print the records
    print(f"\nFound {len(records)} attendance records:")
    print("-" * 80)
    print(f"{'Name':<30} {'Code':<10} {'Date':<12} {'Check In':<10} {'Check Out':<10}")
    print("-" * 80)
    
    for record in records[:20]:  # Show first 20 records
        print(f"{record['name']:<30} {record['code']:<10} {record['date']:<12} {record['check_in']:<10} {record['check_out']:<10}")
    
    if len(records) > 20:
        print(f"... and {len(records) - 20} more records")
    
    print("-" * 80)

def show_raw_logs():
    """Show the imported raw attendance logs"""
    # Access the raw logs page
    response = session.get(f"{BASE_URL}/attendance/raw-logs")
    if response.status_code != 200:
        print(f"Failed to access raw logs page: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the logs table
    logs_table = None
    for table in soup.find_all('table'):
        if table.get('id') == 'logsTable':
            logs_table = table
            break
    
    if not logs_table:
        print("Could not find logs table")
        return
    
    # Extract and print the logs
    logs = []
    for row in logs_table.find('tbody').find_all('tr'):
        columns = row.find_all('td')
        if len(columns) >= 5:
            emp_name = columns[0].text.strip()
            emp_code = columns[1].text.strip()
            timestamp = columns[2].text.strip()
            log_type = columns[3].text.strip()
            device = columns[4].text.strip()
            
            logs.append({
                'name': emp_name,
                'code': emp_code,
                'timestamp': timestamp,
                'log_type': log_type,
                'device': device
            })
    
    # Print the logs
    print(f"\nFound {len(logs)} raw attendance logs:")
    print("-" * 80)
    print(f"{'Name':<30} {'Code':<10} {'Timestamp':<20} {'Type':<6} {'Device':<20}")
    print("-" * 80)
    
    for log in logs[:20]:  # Show first 20 logs
        print(f"{log['name']:<30} {log['code']:<10} {log['timestamp']:<20} {log['log_type']:<6} {log['device']:<20}")
    
    if len(logs) > 20:
        print(f"... and {len(logs) - 20} more logs")
    
    print("-" * 80)

if __name__ == "__main__":
    # Login to the system
    if not login():
        sys.exit(1)
    
    # Import the CSV file
    import_csv()
    
    # Show the raw logs
    show_raw_logs()
    
    # Show the attendance records
    show_imported_data()